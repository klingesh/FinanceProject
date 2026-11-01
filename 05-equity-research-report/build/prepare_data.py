"""Assemble the ratio-workbook inputs from Screener, the companies' own filings and S&P (stockanalysis.com).

Output
  data/ratio_inputs.csv                      one row per company x line item, columns FY2021..FY2026 (Rs crore)
  outputs/data_crosscheck.csv                every overlapping line from two sources and the gap
  data/prepare_log.txt                       what was used and the cross-check summary

Source rules (also written into the workbook's Raw_Data sheet):
  * Screener.in consolidated pages and schedules are the primary source for the statements (FY2021 = opening
    balance sheet for averages).
  * Cost of goods sold (materials consumed + purchases of stock-in-trade + change in inventories) and exceptional
    items come from the companies' own audited results: NSE XBRL files for FY2021-FY2024 (data/xbrl_annual.csv)
    and the Q4 FY2026 results PDFs for FY2025-FY2026 (data/company_reported_fy25_fy26.csv).
    Reason: Screener's expense schedule only has "Raw material cost" and "Change in inventory" (no purchases of
    traded goods line) and its total is Rs 2,256 crore below Asian Paints' audited FY2026 COGS, which would put
    gross margin at 50.1% instead of 43.8%. Screener's "exceptional items" split also differs from the filings.
  * Indigo Paints had no subsidiary until FY2024 (51% of Apple Chemie India), so FY2021-FY2023 use its standalone
    accounts, which covered the whole business. Screener's consolidated FY2023 column equals the standalone one.
  * Total current assets/liabilities and cash + short-term investments come from S&P Global Market Intelligence
    via stockanalysis.com (Rs million / 10 = Rs crore), FY2022-FY2026; they match the companies' FY2026 balance sheets.

Run:  python build/prepare_data.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCR = ROOT / "data" / "screener"
SPD = ROOT / "data" / "stockanalysis"
OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)

COMPANIES = ["ASIANPAINT", "BERGEPAINT", "KANSAINER", "JSWDULUX", "INDIGOPNTS"]
NAMES = {"ASIANPAINT": "Asian Paints", "BERGEPAINT": "Berger Paints", "KANSAINER": "Kansai Nerolac",
         "JSWDULUX": "JSW Dulux", "INDIGOPNTS": "Indigo Paints"}
YEARS = [2021, 2022, 2023, 2024, 2025, 2026]
FY = [f"FY{y}" for y in YEARS]
XBRL = pd.read_csv(ROOT / "data" / "xbrl_annual.csv")
CO2526 = pd.read_csv(ROOT / "data" / "company_reported_fy25_fy26.csv")
# One-off gains reported outside the "exceptional items" line (pre-tax, Rs crore). Excluded from adjusted metrics.
ONEOFF = {("JSWDULUX", 2026): (80.8, "Net gain on sale of immovable properties (Rs 808 mn), a separate income line in "
                                     "the consolidated P&L (page 17 of the Q4 FY26 results)")}


def scope_for(sym: str, year: int) -> str:
    """Indigo: standalone up to FY2023 (no subsidiary then); everyone else consolidated."""
    return "standalone" if (sym == "INDIGOPNTS" and year <= 2023) else "consolidated"


def screener_table(sym: str, scope: str, section: str) -> pd.DataFrame:
    df = pd.read_csv(SCR / f"{sym}_{scope}_{section}.csv")
    return df.set_index("item")


def screener_sched(sym: str, scope: str) -> pd.DataFrame:
    f = SCR / f"{sym}_{scope}_schedules.csv"
    return pd.read_csv(f) if f.exists() else pd.DataFrame(columns=["section", "parent", "item", "period", "value"])


def scr_value(sym: str, year: int, section: str, item: str) -> float | None:
    scope = scope_for(sym, year)
    df = screener_table(sym, scope, section)
    col = f"Mar {year}"
    if item not in df.index or col not in df.columns:
        return None
    v = df.loc[item, col]
    if isinstance(v, pd.Series):
        v = v.iloc[0]
    return None if pd.isna(v) else float(v)


def sched_value(sym: str, year: int, section: str, parent: str, item: str) -> float | None:
    scope = scope_for(sym, year)
    sc = screener_sched(sym, scope)
    m = sc[(sc["section"] == section) & (sc["parent"] == parent) & (sc["item"] == item) & (sc["period"] == f"Mar {year}")]
    if m.empty or pd.isna(m["value"].iloc[0]):
        return None
    return float(m["value"].iloc[0])


def sp_table(sym: str, page: str, idx: int) -> pd.DataFrame:
    df = pd.read_csv(SPD / f"{sym}_{page}_t{idx}.csv")
    first = df.columns[0]
    df = df.set_index(first)
    ren = {}
    for c in df.columns:
        for y in YEARS:
            if c.startswith(f"FY {y} "):
                ren[c] = f"FY{y}"
    return df.rename(columns=ren)


def sp_value(sym: str, year: int, page: str, idx: int, item: str) -> float | None:
    df = sp_table(sym, page, idx)
    col = f"FY{year}"
    if item not in df.index or col not in df.columns:
        return None
    v = df.loc[item, col]
    if isinstance(v, pd.Series):
        v = v.iloc[0]
    try:
        v = float(str(v).replace(",", ""))
    except ValueError:
        return None
    return v / 10.0  # Rs million -> Rs crore


def company_value(sym: str, year: int, code: str) -> float | None:
    """Audited figure from the company's own filing: XBRL for FY2021-FY2024, Q4 FY26 results PDF for FY2025-FY2026."""
    if year <= 2024:
        m = XBRL[(XBRL.company == sym) & (XBRL.fiscal_year == f"FY{year}")]
        key = {"COGS": "COGS", "EXC": "EXC", "REV": "REV"}[code]
    else:
        m = CO2526[(CO2526.company == sym) & (CO2526.fiscal_year == f"FY{year}")]
        key = {"COGS": "COGS", "EXC": "EXC", "REV": "REV", "PATOWN": "PATOWN"}[code]
    if m.empty or key not in m.columns or pd.isna(m.iloc[0][key]):
        return None
    return round(float(m.iloc[0][key]), 2)


def build_rows(sym: str) -> list[dict]:
    rows = []

    def add(code, label, fn, years, source, note=""):
        vals = {f"FY{y}": (fn(y) if y in years else None) for y in YEARS}
        rows.append({"company": sym, "name": NAMES[sym], "code": code, "item": label, **vals,
                     "source": source, "note": note})

    allyrs = YEARS
    spyrs = [2022, 2023, 2024, 2025, 2026]
    co_src = ("Company results: NSE XBRL annual filing (FY2021-24, data/xbrl_annual.csv); Q4 FY26 results PDF "
              "(FY2025-26, data/company_reported_fy25_fy26.csv)")
    add("REV", "Revenue from operations", lambda y: scr_value(sym, y, "profit-loss", "Sales"), allyrs,
        "Screener P&L 'Sales'")
    add("COGS", "Cost of goods sold (materials + traded goods + inventory change)",
        lambda y: company_value(sym, y, "COGS"), allyrs, co_src,
        "Cost of materials consumed + purchases of stock-in-trade + changes in inventories, as reported")
    add("EBITDA", "Operating profit (EBITDA, before other income)",
        lambda y: scr_value(sym, y, "profit-loss", "Operating Profit"), allyrs, "Screener P&L 'Operating Profit'")
    add("OTHINC", "Other income (incl. share of associates and one-offs)",
        lambda y: scr_value(sym, y, "profit-loss", "Other Income"), allyrs, "Screener P&L 'Other Income'",
        "Screener adds share of associates/JVs and exceptional items to other income")
    add("EXCEP", "of which exceptional items (pre-tax, + = gain)", lambda y: company_value(sym, y, "EXC") or 0.0,
        allyrs, co_src, "See data/exceptional_items_company_reported.csv for what each item is")
    add("ONEOFF", "of which other one-off gains outside exceptional items",
        lambda y: ONEOFF.get((sym, y), (0.0, ""))[0], allyrs, "Company results (Q4 FY26 PDF)",
        "; ".join(v[1] for (s, yy), v in ONEOFF.items() if s == sym))
    add("INT", "Finance costs (incl. lease interest)", lambda y: scr_value(sym, y, "profit-loss", "Interest"),
        allyrs, "Screener P&L 'Interest'")
    add("DEP", "Depreciation and amortisation", lambda y: scr_value(sym, y, "profit-loss", "Depreciation"),
        allyrs, "Screener P&L 'Depreciation'")
    add("PBT", "Profit before tax", lambda y: scr_value(sym, y, "profit-loss", "Profit before tax"), allyrs,
        "Screener P&L 'Profit before tax'")
    add("PAT", "Profit for the year (incl. minority share)",
        lambda y: scr_value(sym, y, "profit-loss", "Net Profit"), allyrs, "Screener P&L 'Net Profit'")

    def pat_own(y):
        v = sched_value(sym, y, "profit-loss", "Net Profit", "Profit for EPS")
        return v if v is not None else scr_value(sym, y, "profit-loss", "Net Profit")
    add("PATOWN", "Profit attributable to owners", pat_own, allyrs,
        "Screener schedule 'Net Profit' > 'Profit for EPS'")
    add("EQCAP", "Equity share capital", lambda y: scr_value(sym, y, "balance-sheet", "Equity Capital"), allyrs,
        "Screener BS 'Equity Capital'")
    add("RES", "Reserves (other equity)", lambda y: scr_value(sym, y, "balance-sheet", "Reserves"), allyrs,
        "Screener BS 'Reserves'")
    add("NCI", "Non-controlling interest", lambda y: sched_value(sym, y, "balance-sheet", "Other Liabilities",
                                                                  "Non controlling int") or 0.0, allyrs,
        "Screener schedule 'Other Liabilities' > 'Non controlling int' (0 if not shown)",
        "Indigo shows no NCI line in its balance sheet (it carries a liability for the minority stake)"
        if sym == "INDIGOPNTS" else "")
    add("BORR", "Borrowings incl. lease liabilities", lambda y: scr_value(sym, y, "balance-sheet", "Borrowings"),
        allyrs, "Screener BS 'Borrowings'")
    add("LEASE", "of which lease liabilities",
        lambda y: sched_value(sym, y, "balance-sheet", "Borrowings", "Lease Liabilities") or 0.0, allyrs,
        "Screener schedule 'Borrowings' > 'Lease Liabilities'")
    add("OTHLIAB", "Other liabilities (incl. NCI, payables, provisions)",
        lambda y: scr_value(sym, y, "balance-sheet", "Other Liabilities"), allyrs, "Screener BS 'Other Liabilities'")
    add("TOTLIAB", "Total liabilities and equity",
        lambda y: scr_value(sym, y, "balance-sheet", "Total Liabilities"), allyrs, "Screener BS 'Total Liabilities'")
    add("FA", "Net fixed assets (net block incl. intangibles)",
        lambda y: scr_value(sym, y, "balance-sheet", "Fixed Assets"), allyrs, "Screener BS 'Fixed Assets'")
    add("CWIP", "Capital work in progress", lambda y: scr_value(sym, y, "balance-sheet", "CWIP"), allyrs,
        "Screener BS 'CWIP'")
    add("INVEST", "Investments", lambda y: scr_value(sym, y, "balance-sheet", "Investments"), allyrs,
        "Screener BS 'Investments'")
    add("OTHASSET", "Other assets (current and other)", lambda y: scr_value(sym, y, "balance-sheet", "Other Assets"),
        allyrs, "Screener BS 'Other Assets'")
    add("TA", "Total assets", lambda y: scr_value(sym, y, "balance-sheet", "Total Assets"), allyrs,
        "Screener BS 'Total Assets'")
    add("INV", "Inventories", lambda y: sched_value(sym, y, "balance-sheet", "Other Assets", "Inventories"),
        allyrs, "Screener schedule 'Other Assets' > 'Inventories'")
    add("REC", "Trade receivables", lambda y: sched_value(sym, y, "balance-sheet", "Other Assets", "Trade receivables"),
        allyrs, "Screener schedule 'Other Assets' > 'Trade receivables'")
    add("CASH", "Cash and cash equivalents",
        lambda y: sched_value(sym, y, "balance-sheet", "Other Assets", "Cash Equivalents"), allyrs,
        "Screener schedule 'Other Assets' > 'Cash Equivalents'")
    add("PAY", "Trade payables", lambda y: sched_value(sym, y, "balance-sheet", "Other Liabilities", "Trade Payables"),
        allyrs, "Screener schedule 'Other Liabilities' > 'Trade Payables'")
    add("CA", "Total current assets", lambda y: sp_value(sym, y, "balance", 0, "Total Current Assets"), spyrs,
        "S&P via stockanalysis.com balance sheet (Rs mn / 10)")
    add("CL", "Total current liabilities (incl. current debt and leases)",
        lambda y: sp_value(sym, y, "balance", 1, "Total Current Liabilities"), spyrs,
        "S&P via stockanalysis.com balance sheet (Rs mn / 10)")
    add("CASHSTI", "Cash + short-term investments (incl. liquid funds)",
        lambda y: sp_value(sym, y, "balance", 0, "Cash & Short-Term Investments"), spyrs,
        "S&P via stockanalysis.com balance sheet (Rs mn / 10)")
    add("CFO", "Cash from operating activities",
        lambda y: scr_value(sym, y, "cash-flow", "Cash from Operating Activity"), allyrs,
        "Screener cash flow 'Cash from Operating Activity'")
    add("CAPEX", "Capital expenditure (fixed and intangible assets purchased)",
        lambda y: -(sched_value(sym, y, "cash-flow", "Cash from Investing Activity", "Fixed assets purchased") or 0.0),
        allyrs, "Screener schedule 'Cash from Investing Activity' > 'Fixed assets purchased' (sign flipped)",
        "JSW Dulux FY2026 includes Rs 1,152 cr of intangible assets bought (cash flow, Q4 FY26 results)"
        if sym == "JSWDULUX" else "")
    # cross-check lines (not used in ratios)
    add("REV_CO", "Cross-check: revenue from operations (company filing)", lambda y: company_value(sym, y, "REV"),
        allyrs, co_src)
    add("PATOWN_CO", "Cross-check: profit to owners (company filing)", lambda y: company_value(sym, y, "PATOWN"),
        [2025, 2026], "Company results: Q4 FY26 results PDF (data/company_reported_fy25_fy26.csv)")
    add("COGS_SP", "Cross-check: cost of revenue (S&P)", lambda y: sp_value(sym, y, "income", 0, "Cost of Revenue"),
        spyrs, "S&P via stockanalysis.com 'Cost of Revenue' (Rs mn / 10)")

    def rmc(y):
        a = sched_value(sym, y, "profit-loss", "Material Cost %", "Raw material cost")
        b = sched_value(sym, y, "profit-loss", "Material Cost %", "Change in inventory")
        return None if a is None else a + (b or 0.0)
    add("RMC_SCR", "Cross-check: Screener raw material cost + change in inventory", rmc, allyrs,
        "Screener schedule 'Material Cost %'", "No purchases-of-traded-goods line; not used")
    add("PATOWN_SP", "Cross-check: net income to common (S&P)",
        lambda y: sp_value(sym, y, "income", 0, "Net Income to Common"), spyrs, "S&P via stockanalysis.com")
    add("TA_SP", "Cross-check: total assets (S&P)", lambda y: sp_value(sym, y, "balance", 0, "Total Assets"),
        spyrs, "S&P via stockanalysis.com")
    add("INV_SP", "Cross-check: inventory (S&P)", lambda y: sp_value(sym, y, "balance", 0, "Inventory"), spyrs,
        "S&P via stockanalysis.com")
    return rows


def main() -> None:
    rows = []
    for sym in COMPANIES:
        rows.extend(build_rows(sym))
    df = pd.DataFrame(rows)
    df.to_csv(ROOT / "data" / "ratio_inputs.csv", index=False)

    # cross-check report: every pair of sources for the same line
    pairs = [("REV", "REV_CO", "REV"), ("PATOWN", "PATOWN_CO", "PATOWN"), ("COGS", "COGS_SP", "REV"),
             ("COGS", "RMC_SCR", "REV"), ("PATOWN", "PATOWN_SP", "PATOWN"), ("TA", "TA_SP", "TA"),
             ("INV", "INV_SP", "INV")]
    cc = []
    for sym in COMPANIES:
        sub = df[df.company == sym].set_index("code")
        for a, b, base in pairs:
            for c in FY:
                x, y, z = sub.loc[a, c], sub.loc[b, c], sub.loc[base, c]
                if pd.isna(x) or pd.isna(y):
                    continue
                cc.append({"company": NAMES[sym], "line": a, "versus": b, "year": c, "used_value": x,
                           "other_value": round(float(y), 2), "gap": round(float(y - x), 2),
                           "gap_pct_of": base, "gap_pct": round(float((y - x) / z * 100), 2) if z else np.nan})
    ccdf = pd.DataFrame(cc)
    ccdf.to_csv(OUT / "data_crosscheck.csv", index=False)
    old = OUT / "data_crosscheck_screener_vs_sp.csv"
    if old.exists():
        old.unlink()  # replaced by data_crosscheck.csv

    log = ["Cross-check summary (max absolute gap, % of the base line):"]
    for (line, versus), g in ccdf.groupby(["line", "versus"]):
        i = g["gap_pct"].abs().idxmax()
        log.append(f"  {line} vs {versus}: max |gap| {abs(g.loc[i, 'gap_pct']):.2f}% ({g.loc[i, 'company']} "
                   f"{g.loc[i, 'year']}), median |gap| {g['gap_pct'].abs().median():.2f}%")
    missing = df[df.code.isin(["REV", "COGS", "EBITDA", "PBT", "PATOWN", "TA", "INV", "REC", "PAY"])][FY[1:]].isna().sum().sum()
    log.append(f"Missing values in key ratio inputs FY2022-26: {missing}")
    (ROOT / "data" / "prepare_log.txt").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))
    print(df[["name", "code"] + FY].to_string(max_rows=400))


if __name__ == "__main__":
    main()
