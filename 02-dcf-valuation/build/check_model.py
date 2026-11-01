"""Independent checks of the Project 2 DCF workbook, plus tidy CSV outputs for the README and figures.

The script reads the author's workbook (values saved by LibreOffice) and:
  1. rebuilds the whole DCF in Python from the input cells (history, WACC, forecast, stub period, terminal
     value, equity bridge, exit-multiple cross-check) and compares every result with the workbook;
  2. recomputes all 100 cells of the four sensitivity grids;
  3. re-solves both reverse-DCF blocks with a root finder (the workbook used Goal Seek);
  4. compares the Historical inputs with the StockAnalysis exports they were typed from, the share price with
     Yahoo Finance, and two cited facts with the TCS PDFs;
  5. compares the numbers in the two-page PDF report with the workbook and scans for Excel error values.
It writes outputs/*.csv and exits with code 1 if any check fails.

Usage:  python build/check_model.py
"""
from __future__ import annotations

import csv
import re
import sys
from datetime import datetime

import fitz  # PyMuPDF
import numpy as np
import openpyxl
import pandas as pd
from scipy.optimize import brentq

from common import DCF_COLS, FILINGS, HIST_COLS, OUTPUTS, REPORT_PDF, SA, SOURCE, WORKBOOK

OUTPUTS.mkdir(exist_ok=True)
results: list[dict] = []


def check(area, name, result, target, ok, detail=None):
    status = "PASS" if ok else ("INFO" if ok is None else "FAIL")
    results.append({"area": area, "check": name, "result": result, "target": target, "status": status})
    for line in (detail or [])[:15]:
        print(f"  detail ({name[:40]}...): {line}")


def close(a, b, tol=1e-9):
    return abs(a - b) <= tol * max(1.0, abs(b))


wb = openpyxl.load_workbook(WORKBOOK, data_only=True)
wbf = openpyxl.load_workbook(WORKBOOK, data_only=False)
H, A, W, D, S, R, SUM = (wb[s] for s in ("Historical", "Assumptions", "WACC", "DCF", "Sensitivity", "Reverse_DCF",
                                          "Summary"))
YRS = [2027, 2028, 2029, 2030, 2031]
FC = ["C", "D", "E", "F", "G"]  # forecast columns on Assumptions / DCF / Reverse_DCF

# ---------------------------------------------------------------- inputs (typed cells)
hist = {fy: {r: float(H[f"{c}{r}"].value) for r in range(5, 19)} for fy, c in HIST_COLS.items()}
drv = {k: [float(A[f"{c}{row}"].value) for c in FC] for k, row in
       (("growth", 5), ("margin", 6), ("tax", 7), ("da", 8), ("capex", 9), ("nwc", 10))}
g, exit_mult, price = float(A["B14"].value), float(A["B15"].value), float(A["B16"].value)
shares, cash, debt, minority, pref = (float(A[c].value) for c in ("B18", "B19", "B20", "B21", "B25"))
bs_date, fy27_end, price_date = A["B22"].value, A["B23"].value, A["B17"].value
rf, beta, erp = float(W["B5"].value), float(W["B6"].value), float(W["B7"].value)

# ---------------------------------------------------------------- 1a. history
bad, n_hist = [], 0
for fy, c in HIST_COLS.items():
    h = hist[fy]
    t = h[8] / h[7]
    fcff = h[6] * (1 - t) + h[9] - h[11] - h[12] + h[13]
    exp = {21: (h[5] / hist[fy - 1][5] - 1) if fy > 2022 else None, 22: h[6] / h[5], 23: t, 24: h[9] / h[5],
           25: (h[11] + h[12]) / h[5], 26: -h[13] / h[5], 27: fcff, 28: fcff / h[5], 29: h[15] - h[11]}
    for row, v in exp.items():
        if v is None:
            continue
        n_hist += 1
        wbv = H[f"{c}{row}"].value
        if not close(v, float(wbv)):
            bad.append(f"Historical!{c}{row}: {wbv} vs {v}")
check("History", "Historical ratios and FCFF (FY2022-FY2026, rows 21-29) recomputed from the typed statement lines",
      f"{n_hist - len(bad)} of {n_hist} cells", "all, gap < 1e-9", not bad, bad)

# ---------------------------------------------------------------- 1b. WACC
re_ = rf + beta * erp
rd = hist[2026][16] / ((hist[2025][17] + hist[2026][17]) / 2)
rd_at = rd * (1 - drv["tax"][0])
mcap = price * shares
we, wd = mcap / (mcap + debt), debt / (mcap + debt)
wacc = we * re_ + wd * rd_at
check("WACC", "WACC = E/(D+E) x (Rf + beta x ERP) + D/(D+E) x Rd x (1 - t)",
      f"{wacc:.6%} (workbook {W['B20'].value:.6%}; cost of equity {re_:.2%}, debt weight {wd:.2%})",
      "equal to the workbook", close(wacc, W["B20"].value))


# ---------------------------------------------------------------- 1c. DCF
def project(growth, w, gg=g):
    rev, out = hist[2026][5], []
    stub = (fy27_end - bs_date).days / 365
    for k in range(5):
        rev = rev * (1 + growth[k])
        ebit = rev * drv["margin"][k]
        fcff = ebit * (1 - drv["tax"][k]) + rev * drv["da"][k] - rev * drv["capex"][k] - rev * drv["nwc"][k]
        frac, t = (stub, stub) if k == 0 else (1.0, stub + k)
        out.append({"revenue": rev, "ebit": ebit, "da": rev * drv["da"][k], "fcff": fcff, "counted": fcff * frac,
                    "period": t, "df": (1 + w) ** -t})
    pv = sum(o["counted"] * o["df"] for o in out)
    tv = out[-1]["fcff"] * (1 + gg) / (w - gg)
    ev = pv + tv * out[-1]["df"]
    eq = ev + cash - debt - minority - pref
    return out, pv, tv, ev, eq, eq / shares


base, pv_sum, tv, ev, eqv, vps = project(drv["growth"], wacc)
stub = (fy27_end - bs_date).days / 365
bad, n = [], 0
for k, c in enumerate(FC):
    for row, key in ((6, "revenue"), (8, "ebit"), (12, "da"), (17, "fcff"), (20, "counted"), (21, "period"),
                     (22, "df")):
        n += 1
        if not close(base[k][key], float(D[f"{c}{row}"].value)):
            bad.append(f"DCF!{c}{row}: {D[f'{c}{row}'].value} vs {base[k][key]}")
for cell, v in (("B26", pv_sum), ("B29", tv), ("B30", tv * base[-1]["df"]), ("B31", ev), ("B35", eqv), ("B37", vps),
                ("B39", vps / price - 1), ("B42", tv * base[-1]["df"] / ev)):
    n += 1
    if not close(v, float(D[cell].value)):
        bad.append(f"DCF!{cell}: {D[cell].value} vs {v}")
check("DCF", "Forecast, stub-period discounting, terminal value and equity bridge rebuilt in Python",
      f"{n - len(bad)} of {n} cells; value per share Rs {vps:,.2f}", "all, gap < 1e-9", not bad, bad)
check("DCF", "Stub period: share of FY2027 left after the 30-Sep-2026 balance sheet", f"{stub:.4f} years "
      f"({(fy27_end - bs_date).days} days / 365)", "about 0.5", abs(stub - 0.5) < 0.01)

ebitda31 = base[-1]["ebit"] + base[-1]["da"]
tv_exit = ebitda31 * exit_mult
vps_exit = (pv_sum + tv_exit * base[-1]["df"] + cash - debt - minority - pref) / shares
g_exit = (tv_exit * wacc - base[-1]["fcff"]) / (tv_exit + base[-1]["fcff"])
mkt_ev = price * shares + debt + minority - cash
ebitda27 = base[0]["ebit"] + base[0]["da"]
bad = [f"DCF!{c}: {D[c].value} vs {v}" for c, v in
       (("B43", ebitda31), ("B44", tv / ebitda31), ("B46", tv_exit), ("B48", vps_exit), ("B49", g_exit),
        ("B50", mkt_ev), ("B51", mkt_ev / ebitda27), ("B52", ev / ebitda27)) if not close(v, float(D[c].value))]
check("DCF", "Exit-multiple cross-check, implied multiples and market EV rebuilt", f"{8 - len(bad)} of 8 cells; "
      f"exit-multiple value Rs {vps_exit:,.2f}, implied g {g_exit:.2%}", "all, gap < 1e-9", not bad, bad)


# ---------------------------------------------------------------- 2. sensitivity grids
def value_at(w, gg=g, growth=None):
    return project(growth or drv["growth"], w, gg)[5]


waccs = [wacc + d for d in (-0.01, -0.005, 0, 0.005, 0.01)]
gs = [g + d for d in (-0.01, -0.005, 0, 0.005, 0.01)]
grid1 = np.array([[value_at(w, gg) for gg in gs] for w in waccs])
betas, erps = [beta + d for d in (-0.2, -0.1, 0, 0.1, 0.2)], [erp + d for d in (-0.01, -0.005, 0, 0.005, 0.01)]
grid3 = np.array([[we * (rf + b * e) + wd * rd_at for e in erps] for b in betas])
grid4 = np.array([[value_at(w) for w in row] for row in grid3])
bad = []
for i in range(5):
    for j, c in enumerate(FC):
        for grid, r0, nm in ((grid1, 7, "1"), (grid1 / price - 1, 15, "2"), (grid3, 23, "3"), (grid4, 31, "4")):
            if not close(grid[i, j], float(S[f"{c}{r0 + i}"].value)):
                bad.append(f"grid {nm} Sensitivity!{c}{r0 + i}: {S[f'{c}{r0 + i}'].value} vs {grid[i, j]}")
check("Sensitivity", "All 100 cells of the four sensitivity grids recomputed (WACC x g value and gap, "
      "beta x ERP WACC and value)", f"{100 - len(bad)} of 100; WACC x g range Rs {grid1.min():,.0f} to "
      f"Rs {grid1.max():,.0f}", "all, gap < 1e-9", not bad, bad)
above = int((grid1 > price).sum())
check("Sensitivity", "Cells of the WACC x g grid above the market price", f"{above} of 25", "information", None)

# ---------------------------------------------------------------- 3. reverse DCF (Goal Seek re-solved)
uplift_wb, wacc_wb = float(R["B5"].value), float(R["B28"].value)
u_star = brentq(lambda u: value_at(wacc, growth=[x + u for x in drv["growth"]]) - price, 0.0, 0.2, xtol=1e-12)
w_star = brentq(lambda w: value_at(w) - price, g + 0.005, 0.2, xtol=1e-12)
beta_star = ((w_star - wd * rd_at) / we - rf) / erp
check("Reverse DCF", "Block A: extra revenue growth every year that makes the DCF equal the price "
      "(root finder vs Goal Seek)", f"{u_star:.6%} vs workbook {uplift_wb:.6%}", "within 0.001 pp",
      abs(u_star - uplift_wb) < 1e-5)
check("Reverse DCF", "Block B: WACC that makes the DCF equal the price (root finder vs Goal Seek)",
      f"{w_star:.6%} vs workbook {wacc_wb:.6%}; implied beta {beta_star:.3f}", "within 0.001 pp",
      abs(w_star - wacc_wb) < 1e-5)
check("Reverse DCF", "Goal Seek residuals in the workbook (difference cells B24 and B47)",
      f"Rs {R['B24'].value:.1e} and Rs {R['B47'].value:.1e} per share", "below Rs 0.5 (the workbook's own test)",
      abs(R["B24"].value) < 0.5 and abs(R["B47"].value) < 0.5)
summary_checks = [SUM[f"B{r}"].value for r in range(27, 35)]
check("Workbook", "The workbook's own Summary checks (rows 27-34)", f"{summary_checks.count('PASS')} of "
      f"{len(summary_checks)} PASS", "all PASS", summary_checks.count("PASS") == len(summary_checks))


# ---------------------------------------------------------------- 4a. inputs vs StockAnalysis exports (23-Oct-2026)
def sa_table(file, sheet, label_col, first_data_col):
    ws = openpyxl.load_workbook(SA / file, data_only=True)[sheet]
    head = {}
    for c in range(first_data_col, ws.max_column + 1):
        m = re.search(r"FY (\d{4})", str(ws.cell(4, c).value))
        if m:
            head[int(m.group(1))] = c
        elif "Sep 2026" in str(ws.cell(4, c).value) or "Q2" in str(ws.cell(4, c).value):
            head["Sep2026"] = c
    rows = {}
    for r in range(5, ws.max_row + 1):
        lab = ws.cell(r, label_col).value
        if lab:
            rows.setdefault(str(lab).strip(), {k: ws.cell(r, c).value for k, c in head.items()})
    return rows, [str(ws.cell(4, c).value) for c in range(first_data_col, ws.max_column + 1)]


inc, _ = sa_table("TCS_Income_Statement_StockAnalysis.xlsx", "Income Statement", 1, 2)
inc_add, _ = sa_table("TCS_Income_Statement_StockAnalysis.xlsx", "Additional Metrics", 1, 2)
cfs, _ = sa_table("TCS_Cash_Flow_Statement_StockAnalysis.xlsx", "Cash Flow Statement", 2, 3)
bal, bal_head = sa_table("TCS_Balance_Sheet_StockAnalysis.xlsx", "Balance Sheet", 2, 3)


def num(x):
    return 0.0 if x in (None, "", "-") else float(x)


MAP = {  # Historical row -> function(fy) giving Rs million from the exports
    5: lambda fy: num(inc["Revenue"][fy]), 6: lambda fy: num(inc["Operating Income"][fy]),
    7: lambda fy: num(inc["Pretax Income"][fy]), 8: lambda fy: num(inc["Income Tax Expense"][fy]),
    9: lambda fy: num(inc_add["D&A For EBITDA"][fy]), 10: lambda fy: num(cfs["Depreciation & Amortization"][fy]),
    11: lambda fy: -num(cfs["Capital Expenditures"][fy]), 12: lambda fy: -num(cfs["Sale (Purchase) of Intangibles"][fy]),
    13: lambda fy: sum(num(cfs[k][fy]) for k in ("Change in Accounts Receivable", "Change in Inventory",
                                               "Change in Accounts Payable", "Change in Unearned Revenue",
                                               "Change in Other Net Operating Assets")),
    14: lambda fy: -num(cfs["Cash Acquisitions"][fy]), 15: lambda fy: num(cfs["Operating Cash Flow"][fy]),
    16: lambda fy: -num(inc["Interest Expense"][fy]),
    17: lambda fy: num(bal["Current Portion of Leases"][fy]) + num(bal["Long-Term Leases"][fy]),
    18: lambda fy: num(bal["Cash & Short-Term Investments"][fy]),
}
bad, n = [], 0
for row, f in MAP.items():
    for fy in HIST_COLS:
        n += 1
        mine, theirs = hist[fy][row], f(fy) / 10
        if abs(mine - theirs) > 0.5:
            bad.append(f"Historical row {row} FY{fy}: model {mine:,.0f} vs export {theirs:,.1f}")
check("Source data", "Historical inputs (14 lines x FY2022-FY2026) equal the StockAnalysis exports / 10 "
      "(Rs million to Rs crore)", f"{n - len(bad)} of {n}", "all, within Rs 0.5 crore", not bad, bad)
sep = "Sep2026" if "Sep2026" in bal["Total Debt"] else None
if sep:
    c_ok = abs(num(bal["Cash & Short-Term Investments"][sep]) / 10 - cash) <= 0.5
    d_ok = abs(num(bal["Total Debt"][sep]) / 10 - debt) <= 0.5
    m_sep = num(bal["Minority Interest"][sep]) / 10
    check("Source data", "Cash (Rs 51,024 cr) and lease debt (Rs 11,808 cr) at 30-Sep-2026 equal the balance-sheet "
          "export", f"cash {c_ok}, debt {d_ok}", "both equal", c_ok and d_ok)
    check("Source data", "Minority interests: model uses Rs 995 cr (30-Jun-2026, the latest figure on 20-Oct); the "
          "23-Oct export shows the 30-Sep-2026 figure", f"Rs {m_sep:,.0f} cr; effect on value "
          f"Rs {(m_sep - minority) / shares:,.2f} per share", "information", None)
sh_ok = abs(num(inc["Shares Outstanding (Diluted)"][2026]) / 10 - shares) < 0.05
check("Source data", "Diluted shares 361.8 crore = 3,618 million in the income-statement export",
      f"{num(inc['Shares Outstanding (Diluted)'][2026]):,.0f} million", "equal", sh_ok)

px = pd.read_csv(SOURCE / "yahoo_finance" / "TCS_NS_daily_2026-09-01_to_2026-10-30.csv", parse_dates=["Date"])
day = px[px["Date"] == pd.Timestamp(price_date)]
if len(day):
    lo, hi, cl = float(day["Low"].iloc[0]), float(day["High"].iloc[0]), float(day["Close"].iloc[0])
    check("Source data", f"Model price Rs {price:,.2f} (intraday, {price_date:%d-%b-%Y}) lies inside that day's "
          "NSE trading range (Yahoo Finance)", f"low {lo:,.2f}, high {hi:,.2f}, close {cl:,.2f}",
          "low <= price <= high", lo <= price <= hi)
last = px.iloc[-1]
check("Source data", "Context: DCF value against the latest close in the saved price file",
      f"close Rs {last['Close']:,.2f} on {last['Date']:%d-%b-%Y}; gap {vps / last['Close'] - 1:+.1%}",
      "information", None)


def pdf_text(name):
    return "".join(p.get_text() for p in fitz.open(FILINGS / name))


fs = pdf_text("TCS_Q2FY27_Fact_Sheet_8Oct2026.pdf")
pr = pdf_text("TCS_Q1FY27_Press_Release_INR_9Jul2026.pdf")
ok = "731,880" in fs and "24.0%" in fs and "72,275" in pr and 72275 + 73188 == 145463
check("Source data", "Cited facts in the TCS PDFs: Q2 FY27 revenue Rs 731,880 mn and 24.0% operating margin "
      "(fact sheet), Q1 FY27 revenue Rs 72,275 cr (press release); H1 = 72,275 + 73,188 = 145,463",
      "found" if ok else "not found", "all found", ok)

# ---------------------------------------------------------------- 5. the PDF report and Excel errors
lines = [l.strip() for l in "".join(p.get_text() for p in fitz.open(REPORT_PDF)).splitlines() if l.strip()]
bad, n = [], 0
k = lines.index("WACC \\ g")
cells = lines[k + 1:k + 1 + 5 + 30]
gs_pdf = [float(x.strip("%")) / 100 for x in cells[:5]]
for i in range(5):
    row = cells[5 + i * 6: 5 + (i + 1) * 6]
    for j in range(5):
        n += 1
        if abs(float(row[1 + j].replace(",", "")) - round(grid1[i, j])) > 0.5:
            bad.append(f"grid row {i} col {j}: PDF {row[1 + j]} vs {grid1[i, j]:.1f}")
for label, n_vals, series in (("Revenue", 10, [hist[y][5] for y in HIST_COLS] + [o["revenue"] for o in base]),
                              ("FCFF", 10, [float(H[f"{c}27"].value) for c in HIST_COLS.values()]
                               + [o["fcff"] for o in base]),
                              ("PV of FCFF", 5, [o["counted"] * o["df"] for o in base])):
    k = lines.index(label)
    for j, cell in enumerate(lines[k + 1:k + 1 + n_vals]):
        n += 1
        if abs(float(cell.replace(",", "")) - series[j]) > 0.5:
            bad.append(f"{label} col {j}: PDF {cell} vs {series[j]:.1f}")
headline = {"2,072": f"{vps:,.0f}", "-15.7%": f"{vps / price - 1:.1%}", "11.91%": f"{wacc:.2%}",
            "711,529": f"{ev:,.0f}", "749,750": f"{eqv:,.0f}", "74.0%": f"{tv * base[-1]['df'] / ev:.1%}",
            "2,403": f"{vps_exit:,.0f}", "10.70%": f"{w_star:.2%}", "1,696 – 2,725": f"{grid1.min():,.0f} – {grid1.max():,.0f}"}
for shown, mine in headline.items():
    n += 1
    if shown != mine or shown not in "\n".join(lines):
        bad.append(f"headline {shown} vs {mine}")
check("Write-up", "Numbers in the two-page PDF report (sensitivity grid, revenue, FCFF and PV rows, nine "
      "headline results) match the workbook", f"{n - len(bad)} of {n}", "all, to the digits shown", not bad, bad)

errors, n_formula = [], 0
for wsf in wbf.worksheets:
    for row in wsf.iter_rows():
        for c in row:
            if isinstance(c.value, str) and c.value.startswith("="):
                n_formula += 1
                v = wb[wsf.title][c.coordinate].value
                if isinstance(v, str) and v.startswith("#"):
                    errors.append(f"{wsf.title}!{c.coordinate}={v}")
check("Workbook", "Excel error values in any formula cell", f"{len(errors)} in {n_formula} formulas", "0", not errors)

# ---------------------------------------------------------------- outputs
rows = []
for fy, c in HIST_COLS.items():
    h = hist[fy]
    rows.append({"year": f"FY{fy}A", "revenue": h[5], "ebit": h[6], "fcff": float(H[f"{c}27"].value),
                 "fcff_margin": float(H[f"{c}28"].value), "counted_in_valuation": None, "discount_factor": None,
                 "pv_fcff": None})
for fy, o in zip(YRS, base):
    rows.append({"year": f"FY{fy}E", "revenue": o["revenue"], "ebit": o["ebit"], "fcff": o["fcff"],
                 "fcff_margin": o["fcff"] / o["revenue"], "counted_in_valuation": o["counted"],
                 "discount_factor": o["df"], "pv_fcff": o["counted"] * o["df"]})
pd.DataFrame(rows).round(4).to_csv(OUTPUTS / "fcff_history_and_forecast.csv", index=False)
pd.DataFrame(grid1, index=[f"{w:.4%}" for w in waccs], columns=[f"g={x:.1%}" for x in gs]).round(2) \
    .rename_axis("WACC").to_csv(OUTPUTS / "sensitivity_value_per_share_wacc_x_g.csv")
pd.DataFrame(grid4, index=[f"beta={b:.1f}" for b in betas], columns=[f"ERP={e:.1%}" for e in erps]).round(2) \
    .rename_axis("beta").to_csv(OUTPUTS / "sensitivity_value_per_share_beta_x_erp.csv")
summary = {
    "valuation_date": f"{bs_date:%Y-%m-%d}", "price_date": f"{price_date:%Y-%m-%d}", "price_rs": price,
    "wacc": wacc, "cost_of_equity": re_, "after_tax_cost_of_debt": rd_at, "debt_weight": wd,
    "terminal_growth": g, "sum_pv_fcff_rs_cr": pv_sum, "terminal_value_rs_cr": tv,
    "pv_terminal_value_rs_cr": tv * base[-1]["df"], "enterprise_value_rs_cr": ev, "cash_rs_cr": cash,
    "lease_debt_rs_cr": debt, "minority_interests_rs_cr": minority, "equity_value_rs_cr": eqv,
    "diluted_shares_cr": shares, "value_per_share_rs": vps, "gap_vs_price": vps / price - 1,
    "terminal_value_share_of_ev": tv * base[-1]["df"] / ev, "implied_ev_ebitda_of_tv": tv / ebitda31,
    "exit_multiple": exit_mult, "value_per_share_exit_multiple_rs": vps_exit, "growth_implied_by_exit_multiple": g_exit,
    "market_ev_rs_cr": mkt_ev, "market_ev_to_fy27e_ebitda": mkt_ev / ebitda27, "dcf_ev_to_fy27e_ebitda": ev / ebitda27,
    "reverse_dcf_extra_growth_pp": u_star, "reverse_dcf_wacc": w_star, "reverse_dcf_beta": beta_star,
    "sensitivity_min_rs": grid1.min(), "sensitivity_max_rs": grid1.max(), "sensitivity_cells_above_price": above,
}
pd.DataFrame(list(summary.items()), columns=["item", "value"]).to_csv(OUTPUTS / "dcf_summary.csv", index=False)
rev_path = [{"year": f"FY{fy}E", "base_growth": gr, "market_implied_growth": gr + u_star}
            for fy, gr in zip(YRS, drv["growth"])]
pd.DataFrame(rev_path).round(6).to_csv(OUTPUTS / "reverse_dcf_growth_path.csv", index=False)

with open(OUTPUTS / "validation_results.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["area", "check", "result", "target", "status"])
    w.writeheader()
    w.writerows(results)
n_fail = sum(r["status"] == "FAIL" for r in results)
n_pass = sum(r["status"] == "PASS" for r in results)
for r in results:
    print(f"{r['status']:4}  {r['check']}: {r['result']}")
print(f"\n{n_pass} PASS, {n_fail} FAIL, {len(results) - n_pass - n_fail} INFO")
print("balance-sheet export columns:", bal_head)
sys.exit(1 if n_fail else 0)
