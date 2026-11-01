"""Independent checks of the Project 1 workbook, plus tidy CSV outputs for the README and figures.

The script reads the author's workbook (values saved by Excel) and:
  1. recomputes every ratio on the Ratios sheet in Python from the Raw_Data inputs and compares;
  2. tests the identities the workbook relies on (DuPont, the two balance checks);
  3. compares the Raw_Data inputs with the Screener Excel exports they were typed from (15-Oct-2026)
     and with the Screener web pages saved on 1-Nov-2026 (source_data/screener/);
  4. compares the typed numbers on the Summary sheet and in the one-page PDF with the recomputed ratios;
  5. scans every sheet for Excel error values.
It writes outputs/*.csv and exits with code 1 if any check fails.

Usage:  python build/check_workbook.py
"""
from __future__ import annotations

import csv
import re
import statistics
import sys
from datetime import datetime

import fitz  # PyMuPDF
import openpyxl
import pandas as pd

from common import (COMPANIES, OUTPUTS, RATIO_ROWS, RAW_YEARS, SOURCE, SUMMARY_PDF, YEARS, load_ratios,
                    load_raw, open_workbook)

OUTPUTS.mkdir(exist_ok=True)
results: list[dict] = []


def check(area: str, name: str, result, target: str, ok: bool | None, detail: list[str] | None = None):
    status = "PASS" if ok else ("INFO" if ok is None else "FAIL")
    results.append({"area": area, "check": name, "result": result, "target": target, "status": status})
    for line in (detail or [])[:15]:
        print(f"  detail ({name[:40]}...): {line}")


# ---------------------------------------------------------------- 1. recompute ratios from Raw_Data
def avg(a, b):
    return (a + b) / 2


def recompute(raw: dict, name: str, fy: int) -> dict[str, float]:
    c, p = raw[(name, fy)], raw[(name, fy - 1)]
    rev, cm, purch, cinv = c["REV"], c["CM"], c["PURCH"], c["CINV"]
    oi, fin, da, pbt, pat = c["OTHINC"], c["FINCOST"], c["DA"], c["PBT"], c["PAT"]
    eq, eq0 = c["ESC"] + c["RES"], p["ESC"] + p["RES"]
    ta, ta0, b, b0 = c["TA"], p["TA"], c["BORROW"], p["BORROW"]
    oneoff = (c.get("REMEAS") or 0.0) + (c.get("FCTREC") or 0.0)
    ebitda, ebit = pbt + fin + da - oi, pbt + fin - oi
    cogs = cm + purch + cinv
    npm, at, em = pat / rev, rev / avg(ta0, ta), avg(ta0, ta) / avg(eq0, eq)
    return {
        "gross_margin": (rev - cogs) / rev,
        "ebitda_margin": ebitda / rev,
        "net_margin": npm,
        "roe": pat / avg(eq0, eq),
        "roa": pat / avg(ta0, ta),
        "roce_proxy": ebit / avg(eq0 + b0, eq + b),
        "int_cover_ebit": ebit / fin,
        "int_cover_ebitda": ebitda / fin,
        "asset_turnover": at,
        "inventory_days": avg(p["INV"], c["INV"]) / cogs * 365,
        "receivable_days": avg(p["REC"], c["REC"]) / rev * 365,
        "dupont_net_margin": npm,
        "dupont_asset_turnover": at,
        "dupont_equity_multiplier": em,
        "dupont_roe": npm * at * em,
        "de_proxy": b / eq,
        "cash_to_debt": c["CASHBANK"] / b,
        "ebitda_margin_incl_oi": (pbt + fin + da) / rev,
        "roce_incl_oi": (pbt + fin) / avg(eq0 + b0, eq + b),
        "oi_share_pbt": oi / pbt,
        "net_margin_ex_oneoff": (pat - oneoff) / rev,
        "roe_ex_oneoff": (pat - oneoff) / avg(eq0, eq),
    }


wb_v = open_workbook(data_only=True)
wb_f = open_workbook(data_only=False)
raw = load_raw(wb_v)
cached = load_ratios(wb_v)
calc = {(n, fy): recompute(raw, n, fy) for n, *_ in COMPANIES for fy in YEARS}

worst, n_cmp, n_bad = 0.0, 0, 0
for key in calc[(COMPANIES[0][0], YEARS[0])]:
    for n, *_ in COMPANIES:
        for fy in YEARS:
            a, b = calc[(n, fy)][key], cached[(n, fy)][key]
            n_cmp += 1
            if not isinstance(b, (int, float)):
                n_bad += 1
                continue
            rel = abs(a - b) / max(1.0, abs(b))
            worst = max(worst, rel)
            n_bad += rel > 1e-9
check("Ratios", f"Python re-computation of {len(RATIO_ROWS)} ratio rows x 4 companies x 5 years "
      f"({n_cmp} cells) matches the Ratios sheet", f"{n_cmp - n_bad} of {n_cmp} (largest gap {worst:.1e})",
      "all, gap < 1e-9", n_bad == 0)

# ---------------------------------------------------------------- 2. identities
dup = max(abs(calc[k]["dupont_net_margin"] * calc[k]["dupont_asset_turnover"] * calc[k]["dupont_equity_multiplier"]
              - calc[k]["roe"]) for k in calc)
check("Identities", "DuPont: net margin x asset turnover x equity multiplier = ROE (20 company-years)",
      f"largest gap {dup:.1e}", "< 1e-12", dup < 1e-12)
c1 = max(abs(v["ESC"] + v["RES"] + v["BORROW"] + v["OTHLIAB"] - v["TA"]) for v in raw.values())
c2 = max(abs(v["NETBLOCK"] + v["CWIP"] + v["INVEST"] + v["OTHASSET"] - v["TA"]) for v in raw.values())
check("Identities", "Balance check 1: equity + borrowings + other liabilities = total assets (24 company-years)",
      f"largest gap Rs {c1:.2e} cr", "< Rs 0.01 cr", c1 < 0.01)
check("Identities", "Balance check 2: net block + CWIP + investments + other assets = total assets (24 company-years)",
      f"largest gap Rs {c2:.2e} cr", "< Rs 0.01 cr", c2 < 0.01)
eq_rows = max(abs((v["EQ"] or 0) - (v["ESC"] + v["RES"])) for v in raw.values())
check("Identities", "Raw_Data equity row = share capital + reserves", f"largest gap {eq_rows:.1e}", "0", eq_rows < 1e-9)

# ---------------------------------------------------------------- 3a. inputs vs the Screener exports (15-Oct-2026)
EXPORT_MAP = {  # Data Sheet label -> (Raw_Data code, sign)
    "Sales": ("REV", 1), "Raw Material Cost": ("CM", 1), "Change in Inventory": ("CINV", -1),
    "Other Income": ("OTHINC", 1), "Depreciation": ("DA", 1), "Interest": ("FINCOST", 1),
    "Profit before tax": ("PBT", 1), "Net profit": ("PAT", 1), "Equity Share Capital": ("ESC", 1),
    "Reserves": ("RES", 1), "Borrowings": ("BORROW", 1), "Other Liabilities": ("OTHLIAB", 1),
    "Net Block": ("NETBLOCK", 1), "Capital Work in Progress": ("CWIP", 1), "Investments": ("INVEST", 1),
    "Other Assets": ("OTHASSET", 1), "Receivables": ("REC", 1), "Inventory": ("INV", 1),
    "Cash & Bank": ("CASHBANK", 1), "Cash from Operating Activity": ("CFO", 1),
}


def read_export(sym: str) -> dict[tuple[str, int], float]:
    path = SOURCE / "screener" / "exports" / f"{sym}_Screener_DataSheet_export_15Oct2026.xlsx"
    ws = openpyxl.load_workbook(path, data_only=True)["Data Sheet"]
    out, years, block = {}, {}, 0
    for r in range(1, ws.max_row + 1):
        label = ws.cell(r, 1).value
        if label == "Report Date":
            block += 1
            years = {c: ws.cell(r, c).value.year for c in range(2, 12) if isinstance(ws.cell(r, c).value, datetime)}
            continue
        if block == 2:  # the quarterly block reuses the P&L labels; skip it
            continue
        if (label in EXPORT_MAP or label == "Total") and years:
            for c, fy in years.items():
                v = ws.cell(r, c).value
                if isinstance(v, (int, float)):
                    out.setdefault((label, fy), float(v))  # first block wins (the two BS totals are equal)
    return out


n_cmp, bad = 0, []
for name, short, sym, *_ in COMPANIES:
    ex = read_export(sym)
    for label, (code, sign) in list(EXPORT_MAP.items()) + [("Total", ("TA", 1))]:
        for fy in RAW_YEARS:
            mine = raw[(name, fy)].get(code)
            if mine is None or (label, fy) not in ex:
                continue
            n_cmp += 1
            if abs(mine - sign * ex[(label, fy)]) > 0.005:
                bad.append(f"{short} FY{fy} {code}: workbook {mine} vs export {sign * ex[(label, fy)]}")
check("Source data", "Raw_Data inputs equal the author's Screener Excel exports of 15-Oct-2026 "
      "(21 lines, FY2021-FY2026, 4 companies)", f"{n_cmp - len(bad)} of {n_cmp}", "all, within Rs 0.005 cr",
      not bad and n_cmp > 400, bad)

# ---------------------------------------------------------------- 3b. inputs vs the Screener web pages (1-Nov-2026)
WEB_MAP = {  # (section, item) -> Raw_Data code
    ("profit-loss", "Sales"): "REV", ("profit-loss", "Revenue"): "REV", ("profit-loss", "Other Income"): "OTHINC",
    ("profit-loss", "Interest"): "FINCOST", ("profit-loss", "Depreciation"): "DA",
    ("profit-loss", "Profit before tax"): "PBT", ("profit-loss", "Net Profit"): "PAT",
    ("balance-sheet", "Equity Capital"): "ESC", ("balance-sheet", "Reserves"): "RES",
    ("balance-sheet", "Borrowings"): "BORROW", ("balance-sheet", "Other Liabilities"): "OTHLIAB",
    ("balance-sheet", "Total Liabilities"): "TA", ("balance-sheet", "Fixed Assets"): "NETBLOCK",
    ("balance-sheet", "CWIP"): "CWIP", ("balance-sheet", "Investments"): "INVEST",
    ("balance-sheet", "Other Assets"): "OTHASSET", ("balance-sheet", "Total Assets"): "TA",
    ("cash-flow", "Cash from Operating Activity"): "CFO",
}
n_cmp, bad, roce_rows, np_rows = 0, [], [], []
for name, short, sym, *_ in COMPANIES:
    for sec in ("profit-loss", "balance-sheet", "cash-flow", "ratios"):
        path = SOURCE / "screener" / f"{sym}_{sec}.csv"
        if not path.exists():
            continue
        df = pd.read_csv(path)
        for _, row in df.iterrows():
            item = str(row["item"]).strip()
            for col in df.columns[1:]:
                m = re.match(r"Mar (\d{4})", str(col))
                if not m or int(m.group(1)) not in RAW_YEARS or pd.isna(row[col]):
                    continue
                fy = int(m.group(1))
                if sec == "ratios" and item.startswith("ROCE") and fy in YEARS:
                    roce_rows.append((short, fy, float(row[col]), calc[(name, fy)]["roce_incl_oi"] * 100))
                code = WEB_MAP.get((sec, item))
                mine = raw[(name, fy)].get(code) if code else None
                if mine is None:
                    continue
                if code == "PAT":  # the page shows profit incl. minority interests; see the INFO line below
                    np_rows.append((short, fy, mine, float(row[col])))
                    continue
                n_cmp += 1
                if abs(mine - float(row[col])) > 0.51:
                    bad.append(f"{short} FY{fy} {item}: workbook {mine} vs page {row[col]}")
check("Source data", "Raw_Data inputs agree with the Screener pages saved on 1-Nov-2026 "
      "(16 lines; the pages round to whole Rs crore)", f"{n_cmp - len(bad)} of {n_cmp}",
      "all, within Rs 0.51 cr", not bad and n_cmp > 300, bad)
np26 = {s: page - mine for s, fy, mine, page in np_rows if fy == 2026}
check("Source data", "Net profit: the workbook (and Screener's Excel export) uses profit attributable to owners; "
      "the Screener page shows profit including minority interests. FY2026 page minus workbook, Rs crore",
      "; ".join(f"{s} {v:+,.0f}" for s, v in np26.items()), "information (definition difference)", None)
if roce_rows:
    gaps = [abs(a - b) for _, _, a, b in roce_rows]
    check("Source data", "Screener's own ROCE % (pages of 1-Nov-2026) vs the workbook's ROCE incl. other income "
          "(Ratios row 49), FY2022-FY2026", f"{sum(g <= 1.0 for g in gaps)} of {len(gaps)} within 1 pp; "
          f"largest gap {max(gaps):.1f} pp", "information (Screener's capital base is not published)", None)

# ---------------------------------------------------------------- 4a. Summary sheet typed values
SUMMARY_MAP = {  # Summary row label -> (ratio key, scale, decimals)
    "Gross margin %": ("gross_margin", 100, 1), "EBITDA margin % (ex-OI)": ("ebitda_margin", 100, 1),
    "Net profit margin %": ("net_margin", 100, 1), "ROE %": ("roe", 100, 1), "ROA %": ("roa", 100, 1),
    "ROCE (proxy) %": ("roce_proxy", 100, 1), "Interest coverage (EBIT/Int) x": ("int_cover_ebit", 1, 0),
    "Asset turnover x": ("asset_turnover", 1, 2), "Inventory days": ("inventory_days", 1, 1),
    "Other income as % of PBT": ("oi_share_pbt", 100, 1),
}


def as_float(v):
    try:
        return float(str(v).replace(",", "").replace("\u2212", "-"))
    except ValueError:
        return None


ws = wb_v["Summary"]
n_cmp, bad, notes = 0, [], []
for r in range(6, 16):
    label = ws.cell(r, 2).value
    if label not in SUMMARY_MAP:
        continue
    key, scale, dp = SUMMARY_MAP[label]
    vals = [calc[(n, 2026)][key] * scale for n, *_ in COMPANIES]
    rounded_median = statistics.median(round(v, dp) for v in vals)  # a median typed from the rounded values
    vals.append(statistics.median(vals))
    for j, v in enumerate(vals):
        typed = as_float(ws.cell(r, 3 + j).value)
        if typed is None:
            continue
        n_cmp += 1
        tol = 0.5 * 10 ** -dp + 1e-9
        if abs(typed - v) > tol and not (j == 4 and abs(typed - rounded_median) <= tol):
            bad.append(f"{label} col {j}: typed {typed} vs {v:.4f}")
        elif abs(typed - v) > tol:
            notes.append(f"{label} median typed {typed}: median of the rounded values; unrounded median {v:.2f}")
check("Write-up", "Typed FY2026 table on the Summary sheet (section 1) matches the recomputed ratios",
      f"{n_cmp - len(bad)} of {n_cmp}" + (f" ({len(notes)} median taken from rounded values)" if notes else ""),
      "all, to the decimals shown", not bad, bad + notes)

# ---------------------------------------------------------------- 4b. the one-page PDF
PDF_MAP = {
    "Gross margin %": ("gross_margin", 100, 1), "EBITDA margin % (ex other income)": ("ebitda_margin", 100, 1),
    "Net profit margin %": ("net_margin", 100, 1), "NPM ex one-off gains (approx.)": ("net_margin_ex_oneoff", 100, 1),
    "ROE %": ("roe", 100, 1), "ROE ex one-off gains (approx.)": ("roe_ex_oneoff", 100, 1), "ROA %": ("roa", 100, 1),
    "ROCE (proxy) %": ("roce_proxy", 100, 1), "Interest cover (EBIT) x": ("int_cover_ebit", 1, 0),
    "Asset turnover x": ("asset_turnover", 1, 2), "D/E (ex leases, proxy) x": ("de_proxy", 1, 2),
    "Other income % of PBT": ("oi_share_pbt", 100, 1),
}
lines = [l.strip() for l in "".join(p.get_text() for p in fitz.open(SUMMARY_PDF)).splitlines() if l.strip()]
n_cmp, bad = 0, []
i = lines.index("Gross margin %")
while i < len(lines) and lines[i] in PDF_MAP:
    key, scale, dp = PDF_MAP[lines[i]]
    vals = [calc[(n, 2026)][key] * scale for n, *_ in COMPANIES]
    vals.append(statistics.median(vals))
    for j, cell in enumerate(lines[i + 1:i + 6]):
        typed = as_float(cell)
        if typed is None:
            continue
        n_cmp += 1
        if abs(typed - vals[j]) > 0.5 * 10 ** -dp + 1e-9:
            bad.append(f"{lines[i]} col {j}: PDF {typed} vs {vals[j]:.4f}")
    i += 8
trend_keys = [None, ("net_margin", 100, 1), ("ebitda_margin", 100, 1), ("roe", 100, 1), ("roce_proxy", 100, 1),
              ("de_proxy", 1, 2)]
for name, short, *_ in COMPANIES:
    k = lines.index(name)
    for j, cell in enumerate(lines[k + 1:k + 7]):
        a, b = [as_float(x) for x in cell.split("\u2192")]
        if j == 0:
            exp = (raw[(name, 2022)]["REV"], raw[(name, 2026)]["REV"])
            ok = abs(a - exp[0]) <= 0.5 and abs(b - exp[1]) <= 0.5
        else:
            key, scale, dp = trend_keys[j]
            exp = (calc[(name, 2022)][key] * scale, calc[(name, 2026)][key] * scale)
            ok = all(abs(x - y) <= 0.5 * 10 ** -dp + 1e-9 for x, y in zip((a, b), exp))
        n_cmp += 2
        if not ok:
            bad.append(f"{short} trend col {j}: PDF {cell} vs {exp}")
check("Write-up", "Numbers in the one-page PDF (FY2026 table and FY2022-FY2026 trend table) match the workbook",
      f"{n_cmp - len(bad)} of {n_cmp}", "all, to the decimals shown", not bad, bad)

# ---------------------------------------------------------------- 5. Excel errors and structure
errors, n_formula, n_const = [], 0, 0
for wsf in wb_f.worksheets:
    wsv = wb_v[wsf.title]
    for row in wsf.iter_rows():
        for c in row:
            if c.value is None:
                continue
            if isinstance(c.value, str) and c.value.startswith("="):
                n_formula += 1
                v = wsv[c.coordinate].value
                if isinstance(v, str) and v.startswith("#"):
                    errors.append(f"{wsf.title}!{c.coordinate}={v}")
            else:
                n_const += 1
check("Workbook", "Excel error values (#REF!, #DIV/0!, #VALUE!, #N/A, ...) in any formula cell",
      f"{len(errors)} in {n_formula} formulas", "0", not errors)
check("Workbook", "Formula cells / typed cells (all sheets)", f"{n_formula} / {n_const}", "information", None)

# ---------------------------------------------------------------- outputs
long_rows = []
for (n, fy), d in calc.items():
    for row, (key, label, unit) in RATIO_ROWS.items():
        long_rows.append({"company": n, "fiscal_year": f"FY{fy}", "ratio": key, "label": label, "unit": unit,
                          "value": round(d[key], 6), "workbook_row": row})
pd.DataFrame(long_rows).to_csv(OUTPUTS / "ratios_FY2022-FY2026.csv", index=False)

raw_rows = [{"company": n, "fiscal_year": f"FY{fy}", "code": k, "value_rs_crore": v}
            for (n, fy), d in raw.items() for k, v in d.items()
            if k in {"REV", "CM", "PURCH", "CINV", "OTHINC", "FINCOST", "DA", "PBT", "PAT", "INV", "REC", "TA",
                     "BORROW", "ESC", "RES", "OTHLIAB", "NETBLOCK", "CWIP", "INVEST", "OTHASSET", "CASHBANK", "CFO",
                     "REMEAS", "FCTREC"} and v is not None]
pd.DataFrame(raw_rows).to_csv(OUTPUTS / "raw_inputs_rs_crore.csv", index=False)

HIGHER_BETTER = {"gross_margin": True, "ebitda_margin": True, "net_margin": True, "net_margin_ex_oneoff": True,
                 "roe": True, "roe_ex_oneoff": True, "roa": True, "roce_proxy": True, "int_cover_ebit": True,
                 "asset_turnover": True, "de_proxy": False, "inventory_days": False, "receivable_days": False,
                 "ebitda_margin_incl_oi": True, "oi_share_pbt": None, "cash_to_debt": True}
peer = []
for key, hb in HIGHER_BETTER.items():
    vals = {short: calc[(n, 2026)][key] for n, short, *_ in COMPANIES}
    rec = {"ratio": key, **{s: round(v, 6) for s, v in vals.items()}, "median": round(statistics.median(vals.values()), 6)}
    if hb is not None:
        order = sorted(vals, key=lambda s: vals[s], reverse=hb)
        rec["best"] = order[0]
        rec["hero_rank"] = order.index("Hero") + 1
    peer.append(rec)
pd.DataFrame(peer).to_csv(OUTPUTS / "peer_comparison_FY2026.csv", index=False)

dupont = [{"company": n, "fiscal_year": f"FY{fy}", "net_margin": round(calc[(n, fy)]["net_margin"], 6),
           "asset_turnover": round(calc[(n, fy)]["asset_turnover"], 6),
           "equity_multiplier": round(calc[(n, fy)]["dupont_equity_multiplier"], 6),
           "roe": round(calc[(n, fy)]["roe"], 6)} for n, *_ in COMPANIES for fy in YEARS]
pd.DataFrame(dupont).to_csv(OUTPUTS / "dupont_FY2022-FY2026.csv", index=False)

with open(OUTPUTS / "validation_results.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["area", "check", "result", "target", "status"])
    w.writeheader()
    w.writerows(results)

n_fail = sum(r["status"] == "FAIL" for r in results)
n_pass = sum(r["status"] == "PASS" for r in results)
for r in results:
    print(f"{r['status']:4}  {r['check']}: {r['result']}")
print(f"\n{n_pass} PASS, {n_fail} FAIL, {len(results) - n_pass - n_fail} INFO")
sys.exit(1 if n_fail else 0)
