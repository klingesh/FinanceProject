"""Python mirror of every ratio in AsianPaints_Ratio_Analysis.xlsx.

The workbook computes the ratios with live Excel formulas. This module computes the same ratios in pandas
from data/ratio_inputs.csv so that (1) verify_workbook.py can compare every Excel cell with an independent
calculation and (2) the report and figures use numbers that are proven to equal the workbook.

Definitions (Rs crore inputs; averages = (opening + closing) / 2, FY2021 is the opening balance sheet):
  gross margin        = (revenue - COGS) / revenue, COGS = materials + purchases of traded goods + inventory change
  EBITDA margin       = operating profit (before other income) / revenue
  net margin          = PAT attributable to owners / revenue
  one-offs            = exceptional items + other one-off gains reported outside that line (JSW Dulux FY2026)
  adjusted PAT        = PAT to owners - one-offs x (PAT / PBT)   [one-offs taxed at the year's effective rate]
  ROE                 = PAT to owners / average owners' equity
  ROA                 = PAT to owners / average total assets
  ROCE                = (PBT + finance costs - one-offs) / average (equity + NCI + borrowings incl. leases)
  current ratio       = current assets / current liabilities
  quick ratio         = (current assets - inventories) / current liabilities
  cash ratio          = (cash + short-term investments) / current liabilities
  debt / equity       = borrowings incl. leases / owners' equity
  net debt / EBITDA   = (borrowings incl. leases - cash - short-term investments) / EBITDA   (negative = net cash)
  interest cover      = (EBITDA - depreciation) / finance costs
  asset turnover      = revenue / average total assets
  fixed-asset turnover= revenue / average net fixed assets
  inventory days      = average inventories / COGS x 365
  receivable days     = average trade receivables / revenue x 365
  payable days        = average trade payables / COGS x 365
  cash conversion     = inventory days + receivable days - payable days
DuPont 3-step: net margin x asset turnover x equity multiplier (average assets / average equity) = ROE
DuPont 5-step: tax burden (PAT to owners / PBT) x interest burden (PBT / EBIT) x EBIT margin (EBIT / revenue)
               x asset turnover x equity multiplier = ROE, with EBIT = PBT + finance costs.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
COMPANIES = ["ASIANPAINT", "BERGEPAINT", "KANSAINER", "JSWDULUX", "INDIGOPNTS"]
NAMES = {"ASIANPAINT": "Asian Paints", "BERGEPAINT": "Berger Paints", "KANSAINER": "Kansai Nerolac",
         "JSWDULUX": "JSW Dulux", "INDIGOPNTS": "Indigo Paints"}
ALL_FY = [f"FY{y}" for y in range(2021, 2027)]
FY = ALL_FY[1:]          # ratio years FY2022-FY2026
DAYS = 365

# (code, label, group, format, better) ; better: "high", "low" or "" (not ranked)
RATIOS = [
    ("GM", "Gross margin", "Profitability", "pct", "high"),
    ("EBITDAM", "EBITDA margin (before other income)", "Profitability", "pct", "high"),
    ("NPM", "Net profit margin (PAT to owners)", "Profitability", "pct", "high"),
    ("NPM_ADJ", "Net margin excl. one-off items", "Profitability", "pct", "high"),
    ("ROE", "Return on equity (ROE)", "Profitability", "pct", "high"),
    ("ROE_ADJ", "ROE excl. one-off items", "Profitability", "pct", "high"),
    ("ROA", "Return on assets (ROA)", "Profitability", "pct", "high"),
    ("ROCE", "ROCE (EBIT excl. one-offs / avg capital employed)", "Profitability", "pct", "high"),
    ("CR", "Current ratio", "Liquidity", "x", "high"),
    ("QR", "Quick ratio", "Liquidity", "x", "high"),
    ("CASHR", "Cash ratio", "Liquidity", "x", "high"),
    ("DE", "Debt / equity (incl. leases)", "Leverage", "x", "low"),
    ("NDEBITDA", "Net debt / EBITDA (negative = net cash)", "Leverage", "x", "low"),
    ("ICR", "Interest cover (EBIT / finance costs)", "Leverage", "x1", "high"),
    ("AT", "Asset turnover", "Efficiency", "x", "high"),
    ("FAT", "Fixed-asset turnover", "Efficiency", "x", "high"),
    ("INVD", "Inventory days (on COGS)", "Efficiency", "days", "low"),
    ("RECD", "Receivable days (on revenue)", "Efficiency", "days", "low"),
    ("PAYD", "Payable days (on COGS)", "Efficiency", "days", "high"),
    ("CCC", "Cash conversion cycle", "Efficiency", "days", "low"),
    ("REVG", "Revenue growth", "Growth and cash", "pct", "high"),
    ("CFOE", "Cash from operations / EBITDA", "Growth and cash", "pct", "high"),
    ("FCFM", "Free cash flow margin (CFO - capex)", "Growth and cash", "pct", "high"),
    ("OIPBT", "Other income excl. one-offs, % of PBT", "Growth and cash", "pct", ""),
]
DUPONT = [
    ("D3_NPM", "Net profit margin", "pct"),
    ("D3_AT", "x Asset turnover", "x"),
    ("D3_EM", "x Equity multiplier (avg assets / avg equity)", "x"),
    ("D3_ROE", "= ROE (3-step product)", "pct"),
    ("D5_TB", "Tax burden (PAT to owners / PBT)", "x"),
    ("D5_IB", "x Interest burden (PBT / EBIT)", "x"),
    ("D5_EBITM", "x EBIT margin (EBIT / revenue)", "pct"),
    ("D5_AT", "x Asset turnover", "x"),
    ("D5_EM", "x Equity multiplier", "x"),
    ("D5_ROE", "= ROE (5-step product)", "pct"),
]
# Weighted scorecard used for the overall ranking (judgment; the workbook shows each weight with a reason).
# Returns and margins drive value in a branded consumer business, so they carry 65%; all five companies are
# net-cash, so balance-sheet safety separates them little and carries 5%.
SCORECARD = {
    "ROE_ADJ": (0.20, "Return to shareholders, excluding one-off gains and losses"),
    "ROCE": (0.20, "Return on all capital, independent of how it is financed"),
    "EBITDAM": (0.15, "Pricing power and cost control before other income"),
    "GM": (0.10, "Brand premium and product mix after raw-material costs"),
    "REVG": (0.10, "Growth: FY2026 year-on-year; 5-year table uses FY2021-26 CAGR"),
    "AT": (0.10, "How hard the asset base works"),
    "CCC": (0.05, "Working-capital discipline (fewer days is better)"),
    "CFOE": (0.05, "Quality of earnings: how much EBITDA turns into cash"),
    "NDEBITDA": (0.025, "Balance-sheet strength (all five are net cash, so low weight)"),
    "CR": (0.025, "Short-term liquidity (all five are above 1.4x, so low weight)"),
}


def load_inputs(path: Path | None = None) -> dict[str, pd.DataFrame]:
    df = pd.read_csv(path or ROOT / "data" / "ratio_inputs.csv")
    out = {}
    for sym in COMPANIES:
        sub = df[df.company == sym].set_index("code")[ALL_FY].astype(float)
        out[sym] = sub
    return out


def _avg(s: pd.Series) -> pd.Series:
    """(opening + closing)/2 for FY2022..FY2026 from a FY2021..FY2026 series."""
    return pd.Series([(s[ALL_FY[i]] + s[ALL_FY[i + 1]]) / 2 for i in range(5)], index=FY)


def compute_company(x: pd.DataFrame) -> pd.DataFrame:
    g = lambda c: x.loc[c, FY]  # noqa: E731
    eq = x.loc["EQCAP", ALL_FY] + x.loc["RES", ALL_FY]
    cap = eq + x.loc["NCI", ALL_FY] + x.loc["BORR", ALL_FY]
    rev, cogs, pbt, pat, patown = g("REV"), g("COGS"), g("PBT"), g("PAT"), g("PATOWN")
    excep = g("EXCEP") + g("ONEOFF")          # all one-off items, pre-tax
    intr, dep, ebitda = g("INT"), g("DEP"), g("EBITDA")
    adj_pat = patown - excep * pat / pbt
    avg_eq, avg_ta, avg_cap = _avg(eq), _avg(x.loc["TA", ALL_FY]), _avg(cap)
    r = {
        "GM": (rev - cogs) / rev,
        "EBITDAM": ebitda / rev,
        "NPM": patown / rev,
        "NPM_ADJ": adj_pat / rev,
        "ROE": patown / avg_eq,
        "ROE_ADJ": adj_pat / avg_eq,
        "ROA": patown / avg_ta,
        "ROCE": (pbt + intr - excep) / avg_cap,
        "CR": g("CA") / g("CL"),
        "QR": (g("CA") - g("INV")) / g("CL"),
        "CASHR": g("CASHSTI") / g("CL"),
        "DE": g("BORR") / eq[FY],
        "NDEBITDA": (g("BORR") - g("CASHSTI")) / ebitda,
        "ICR": (ebitda - dep) / intr,
        "AT": rev / avg_ta,
        "FAT": rev / _avg(x.loc["FA", ALL_FY]),
        "INVD": _avg(x.loc["INV", ALL_FY]) / cogs * DAYS,
        "RECD": _avg(x.loc["REC", ALL_FY]) / rev * DAYS,
        "PAYD": _avg(x.loc["PAY", ALL_FY]) / cogs * DAYS,
        "REVG": pd.Series([x.loc["REV", ALL_FY[i + 1]] / x.loc["REV", ALL_FY[i]] - 1 for i in range(5)], index=FY),
        "CFOE": g("CFO") / ebitda,
        "FCFM": (g("CFO") - g("CAPEX")) / rev,
        "OIPBT": (g("OTHINC") - excep) / pbt,
    }
    r["CCC"] = r["INVD"] + r["RECD"] - r["PAYD"]
    ebit = pbt + intr
    r["D3_NPM"], r["D3_AT"], r["D3_EM"] = r["NPM"], r["AT"], avg_ta / avg_eq
    r["D3_ROE"] = r["D3_NPM"] * r["D3_AT"] * r["D3_EM"]
    r["D5_TB"], r["D5_IB"], r["D5_EBITM"] = patown / pbt, pbt / ebit, ebit / rev
    r["D5_AT"], r["D5_EM"] = r["AT"], r["D3_EM"]
    r["D5_ROE"] = r["D5_TB"] * r["D5_IB"] * r["D5_EBITM"] * r["D5_AT"] * r["D5_EM"]
    df = pd.DataFrame(r).T[FY]
    df["AVG5"] = df[FY].mean(axis=1)
    return df


def compute_all(inputs: dict[str, pd.DataFrame] | None = None) -> dict[str, pd.DataFrame]:
    inputs = inputs or load_inputs()
    return {sym: compute_company(inputs[sym]) for sym in COMPANIES}


def cagr(inputs: dict[str, pd.DataFrame], sym: str) -> float:
    s = inputs[sym].loc["REV"]
    return (s["FY2026"] / s["FY2021"]) ** (1 / 5) - 1


def peer_table(res: dict[str, pd.DataFrame], col: str, inputs=None) -> pd.DataFrame:
    """Values for one column ('FY2026' or 'AVG5') with ranks (1 = best) among the five companies."""
    rows = []
    for code, label, group, fmt, better in RATIOS:
        vals = {NAMES[s]: res[s].loc[code, col] for s in COMPANIES}
        if col == "AVG5" and code == "REVG" and inputs is not None:
            vals = {NAMES[s]: cagr(inputs, s) for s in COMPANIES}
        ser = pd.Series(vals)
        peers = ser.drop("Asian Paints")
        row = {"code": code, "ratio": label, "group": group, "better": better, **vals,
               "peer_median": float(np.median(peers.values))}
        if better:
            rk = ser.rank(ascending=(better == "low"), method="min")
            for k, v in rk.items():
                row[f"rank_{k}"] = int(v)
        rows.append(row)
    return pd.DataFrame(rows)


def composite(pt: pd.DataFrame) -> pd.Series:
    """Weighted average rank across the scorecard metrics (1 = best possible)."""
    sub = pt.set_index("code")
    wsum = sum(w for w, _ in SCORECARD.values())
    return pd.Series({NAMES[s]: sum(w * sub.loc[c, f"rank_{NAMES[s]}"] for c, (w, _) in SCORECARD.items()) / wsum
                      for s in COMPANIES})


if __name__ == "__main__":
    inp = load_inputs()
    res = compute_all(inp)
    for s in COMPANIES:
        print(NAMES[s])
        print(res[s].round(4).to_string())
    pt = peer_table(res, "FY2026")
    print(pt.round(3).to_string())
    print(composite(pt))
    pt5 = peer_table(res, "AVG5", inp)
    print(composite(pt5))
