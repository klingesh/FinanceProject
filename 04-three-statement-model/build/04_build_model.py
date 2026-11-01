"""Build UltraTech_3Statement_Model.xlsx (openpyxl, live formulas) from the tidy files in data/.

Sheets: Cover, Historical, Drivers, Income_Statement, Balance_Sheet, Cash_Flow, Debt_Schedule,
Scenario_Summary, Checks. Every forecast number is an Excel formula that traces back to an input cell
(blue font; judgment inputs also have a light-yellow fill and a one-line reason).
The scenario data table on the Cover sheet is created afterwards by build/05_verify_model.py (Excel COM).

Run:  python build/04_build_model.py   then   python build/05_verify_model.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "UltraTech_3Statement_Model.xlsx"
MAP_OUT = ROOT / "build" / "model_map.json"

HY = ["FY2022", "FY2023", "FY2024", "FY2025", "FY2026"]  # Historical sheet columns C..G
HC = ["C", "D", "E", "F", "G"]
FY = ["FY2027E", "FY2028E", "FY2029E", "FY2030E", "FY2031E"]  # forecast columns D..H, FY2026A in C
FC = ["D", "E", "F", "G", "H"]
PREV = {"D": "C", "E": "D", "F": "E", "G": "F", "H": "G"}
NEXT = {"D": "E", "E": "F", "F": "G", "G": "H"}

BLUE, BLACK, GREEN = "0000FF", "000000", "008000"
YELLOW = PatternFill("solid", fgColor="FFF2CC")
HEAD = PatternFill("solid", fgColor="1F3864")
SECT = PatternFill("solid", fgColor="D9E1F2")
THIN = Side(style="thin", color="808080")
F_CR, F_CR1, F_PCT, F_X, F_RS, F_EPS = "#,##0", "#,##0.0", "0.0%", '0.00"x"', "#,##0", "#,##0.0"
F_DAYS = "0.0"
LINK_RE = re.compile(r"^=-?[A-Za-z_]+!\$?[A-Z]+\$?\d+$")

wb = Workbook()
SHEETS = ["Cover", "Historical", "Drivers", "Income_Statement", "Balance_Sheet", "Cash_Flow",
          "Debt_Schedule", "Scenario_Summary", "Checks"]
ws_ = {}
for i, name in enumerate(SHEETS):
    ws_[name] = wb.active if i == 0 else wb.create_sheet(name)
    ws_[name].title = name
ROW: dict[str, dict[str, int]] = {n: {} for n in SHEETS}


def cell(ws, ref: str, value=None, color: str | None = None, fmt: str | None = None, bold: bool = False,
         fill: PatternFill | None = None, wrap: bool = False, italic: bool = False, size: int | None = None):
    """Write one cell with font colour, number format and optional fill."""
    c = ws[ref]
    c.value = value
    if color or bold or italic or size:
        c.font = Font(color=color or BLACK, bold=bold, italic=italic, size=size or 11)
    if fmt:
        c.number_format = fmt
    if fill:
        c.fill = fill
    if wrap:
        c.alignment = Alignment(wrap_text=True, vertical="top")
    return c


def title(ws, text: str, sub: str | None = None) -> None:
    cell(ws, "A1", text, bold=True, size=14)
    if sub is not None:
        cell(ws, "A2", sub, italic=True, color="404040")


def header(ws, r: int, labels: list[str], start_col: int = 1) -> None:
    """Dark header row."""
    for j, lab in enumerate(labels):
        c = ws.cell(row=r, column=start_col + j, value=lab)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = HEAD
        c.alignment = Alignment(horizontal="center" if j >= 2 else "left", vertical="center", wrap_text=True)


def section(ws, r: int, text: str, ncols: int = 9) -> None:
    for j in range(1, ncols + 1):
        ws.cell(row=r, column=j).fill = SECT
    ws.cell(row=r, column=1, value=text).font = Font(bold=True)


def widths(ws, spec: dict[str, float]) -> None:
    for col, w in spec.items():
        ws.column_dimensions[col].width = w


def ref(sheet: str, key: str, col: str, absolute: bool = False) -> str:
    """Cross-sheet reference to a registered row, e.g. ref('Drivers', 'g_rm', 'F', True) -> Drivers!$F$40."""
    r = ROW[sheet][key]
    return f"{sheet}!${col}${r}" if absolute else f"{sheet}!{col}{r}"


def line(ws, sheet: str, r: int, key: str, label: str, unit: str, values: dict[str, object], fmt: str,
         note: str = "", bold: bool = False, top_border: bool = False) -> int:
    """Write a time-series row: values maps column letter -> constant or formula. Colours: constants blue,
    formulas that start with '=' and reference another sheet green, other formulas black."""
    ROW[sheet][key] = r
    cell(ws, f"A{r}", label, bold=bold)
    cell(ws, f"B{r}", unit, color="404040")
    for col, v in values.items():
        if isinstance(v, str) and v.startswith("="):
            color = GREEN if LINK_RE.match(v) else BLACK  # green = pure link to another sheet
        else:
            color = BLUE
        c = cell(ws, f"{col}{r}", v, color=color, fmt=fmt, bold=bold)
        if top_border:
            c.border = Border(top=THIN)
    if note:
        cell(ws, f"I{r}", note, color="404040", italic=True)
    return r + 1


# ============================================================== Historical
is_df = pd.read_csv(DATA / "hist_income_statement.csv")
bs_df = pd.read_csv(DATA / "hist_balance_sheet.csv")
cf_df = pd.read_csv(DATA / "hist_cash_flow.csv")
kpi_df = pd.read_csv(DATA / "operating_kpis.csv")
guid_df = pd.read_csv(DATA / "company_guidance.csv")
debt_df = pd.read_csv(DATA / "debt_maturities.csv")
mkt = json.loads((DATA / "market_inputs.json").read_text(encoding="utf-8"))

H = ws_["Historical"]
title(H, "Historical financial statements, UltraTech Cement (consolidated, as reported), FY2022-FY2026",
      "Rs crore unless stated. Transcribed from the audited consolidated results (page extracts in "
      "source_data/company_filings/). Blue = transcribed input, black = formula.")
header(H, 4, ["Line item", "Model line / unit"] + HY + ["Source"])
IS_KEYS = {"Revenue from operations": "rev", "Other income": "oi", "Cost of materials consumed": "rm1",
           "Purchases of stock-in-trade": "rm2", "Changes in inventories of FG, WIP and stock-in-trade": "rm3",
           "Employee benefits expense": "emp", "Finance costs": "fin", "Depreciation and amortisation": "da",
           "Power and fuel": "pf", "Freight and forwarding": "fr", "Other expenses": "oth",
           "Exceptional items (charge)": "exc", "Share in profit/(loss) of associates and JV": "jv",
           "Current tax": "tax_c", "Deferred tax": "tax_d",
           "Profit from discontinued operations (net)": "disc",
           "Profit attributable to non-controlling interest": "nci"}
IS_SRC = "FY22-FY23: FY23 results p.1; FY24: FY24 results p.1; FY25-FY26: FY26 results p.8"
section(H, 5, "1. Income statement (as reported)", 8)
r = 6
for _, row in is_df.iterrows():
    k = IS_KEYS[row["line"]]
    ROW["Historical"][k] = r
    cell(H, f"A{r}", row["line"])
    cell(H, f"B{r}", row["group"], color="404040")
    for col, y in zip(HC, HY):
        cell(H, f"{col}{r}", float(row[y]), color=BLUE, fmt="#,##0.00")
    cell(H, f"H{r}", IS_SRC, color="404040", italic=True)
    r += 1
REP = {"Total expenses": [44743.94, 56330.84, 62052.88, 69063.17, 78007.47],
       "Profit before tax": [8364.40, 7416.25, 9422.22, 7528.13, 10927.19],
       "Profit attributable to owners": [7344.31, 5063.96, 7005.00, 6039.11, 8165.64],
       "Basic EPS": [254.64, 175.63, 243.05, 205.30, 277.62]}
hr = ROW["Historical"]


def hline(key: str, label: str, unit: str, formula, fmt: str = "#,##0.00", cols=HC, note: str = "",
          bold: bool = False) -> None:
    """Historical-sheet computed row; formula is a function col -> formula string, or a list of constants."""
    global r
    hr[key] = r
    cell(H, f"A{r}", label, bold=bold)
    cell(H, f"B{r}", unit, color="404040")
    for i, col in enumerate(cols):
        v = formula[i] if isinstance(formula, list) else formula(col)
        cell(H, f"{col}{r}", v, color=BLUE if isinstance(formula, list) else BLACK, fmt=fmt, bold=bold)
    if note:
        cell(H, f"H{r}", note, color="404040", italic=True)
    r += 1


hline("rm_sum", "Raw materials incl. traded goods and inventory change", "Rs crore",
      lambda c: f"=SUM({c}{hr['rm1']}:{c}{hr['rm3']})")
hline("opex", "Operating costs (excl. D&A and finance costs)", "Rs crore",
      lambda c: f"={c}{hr['rm_sum']}+{c}{hr['emp']}+{c}{hr['pf']}+{c}{hr['fr']}+{c}{hr['oth']}")
hline("texp", "Total expenses (computed)", "Rs crore", lambda c: f"={c}{hr['opex']}+{c}{hr['fin']}+{c}{hr['da']}")
hline("texp_rep", "Total expenses (reported)", "Rs crore", REP["Total expenses"], note=IS_SRC)
hline("ebitda", "EBITDA (revenue - operating costs)", "Rs crore", lambda c: f"={c}{hr['rev']}-{c}{hr['opex']}",
      bold=True)
hline("pbt", "Profit before tax (computed)", "Rs crore",
      lambda c: f"={c}{hr['rev']}+{c}{hr['oi']}-{c}{hr['texp']}-{c}{hr['exc']}+{c}{hr['jv']}")
hline("pbt_rep", "Profit before tax (reported)", "Rs crore", REP["Profit before tax"], note=IS_SRC)
hline("tax", "Tax expense (current + deferred)", "Rs crore", lambda c: f"={c}{hr['tax_c']}+{c}{hr['tax_d']}")
hline("pat", "Net profit incl. discontinued operations (computed)", "Rs crore",
      lambda c: f"={c}{hr['pbt']}-{c}{hr['tax']}+{c}{hr['disc']}")
hline("own", "Profit attributable to owners (computed)", "Rs crore", lambda c: f"={c}{hr['pat']}-{c}{hr['nci']}",
      bold=True)
hline("own_rep", "Profit attributable to owners (reported)", "Rs crore", REP["Profit attributable to owners"],
      note=IS_SRC)
hline("eps_rep", "Basic EPS (reported)", "Rs", REP["Basic EPS"], note=IS_SRC)
hline("is_chk", "Check: |computed - reported| for total expenses, PBT and owners' profit", "Rs crore",
      lambda c: f"=ABS({c}{hr['texp']}-{c}{hr['texp_rep']})+ABS({c}{hr['pbt']}-{c}{hr['pbt_rep']})"
                f"+ABS({c}{hr['own']}-{c}{hr['own_rep']})", note="must be below 0.5 (Checks sheet)")

r += 1
section(H, r, "2. Operating data and ratios (drivers history)", 8)
r += 1
kp = kpi_df.set_index("kpi")
hline("vol", "Sales volume (consolidated)", "MnT", [float(x) for x in kp.loc["Sales volume (consolidated)", HY]],
      fmt=F_CR1, note=kp.loc["Sales volume (consolidated)", "source"])
cap_key = "Grey cement capacity at year end (incl. 5.4 MTPA overseas)"
hline("cap", "Grey cement capacity at year end (incl. 5.4 MTPA overseas)", "MTPA",
      [float(x) for x in kp.loc[cap_key, HY]], fmt=F_CR1, note=kp.loc[cap_key, "source"])
hline("cap_avg", "Average capacity in the year", "MTPA", lambda c: f"=AVERAGE({PREV[c]}{hr['cap']},{c}{hr['cap']})",
      fmt=F_CR1, cols=HC[1:])
hline("util", "Utilisation (volume / average capacity)", "%", lambda c: f"={c}{hr['vol']}/{c}{hr['cap_avg']}",
      fmt=F_PCT, cols=HC[1:], note="FY25 is depressed by mid-year acquisitions (India Cements from Dec-2024)")
hline("ns", "Net sales", "Rs crore", [float(x) for x in kp.loc["Net sales", HY]], fmt=F_CR,
      note=kp.loc["Net sales", "source"])
hline("ooi", "Other operating income (revenue - net sales)", "Rs crore", lambda c: f"={c}{hr['rev']}-{c}{hr['ns']}",
      fmt=F_CR)
hline("ooi_pct", "Other operating income % of net sales", "%", lambda c: f"={c}{hr['ooi']}/{c}{hr['ns']}", fmt=F_PCT)
hline("real", "Realisation (net sales per tonne)", "Rs/t", lambda c: f"={c}{hr['ns']}/{c}{hr['vol']}*10", fmt=F_RS)
for k, lab, src in [("rmt", "Raw materials per tonne", "rm_sum"), ("pft", "Power and fuel per tonne", "pf"),
                    ("frt", "Freight and forwarding per tonne", "fr"), ("otht", "Other expenses per tonne", "oth"),
                    ("empt", "Employee cost per tonne", "emp"), ("ebitdat", "EBITDA per tonne", "ebitda")]:
    hline(k, lab, "Rs/t", lambda c, s=src: f"={c}{hr[s]}/{c}{hr['vol']}*10", fmt=F_RS, bold=(k == "ebitdat"))
hline("vol_g", "Volume growth", "%", lambda c: f"={c}{hr['vol']}/{PREV[c]}{hr['vol']}-1", fmt=F_PCT, cols=HC[1:])
hline("rev_g", "Revenue growth", "%", lambda c: f"={c}{hr['rev']}/{PREV[c]}{hr['rev']}-1", fmt=F_PCT, cols=HC[1:])
hline("ebitda_m", "EBITDA margin", "%", lambda c: f"={c}{hr['ebitda']}/{c}{hr['rev']}", fmt=F_PCT)
hline("capex_rep", "Capex reported by the company (accrual basis, memo)", "Rs crore",
      lambda c: {"E": 9187.0, "F": 9428.0, "G": 10064.0}.get(c, None), fmt=F_CR, cols=["E", "F", "G"],
      note="Q4FY26 investor presentation p.36 (differs from cash capex in the cash-flow statement)")
for col in ["E", "F", "G"]:
    H[f"{col}{hr['capex_rep']}"].font = Font(color=BLUE)

r += 1
section(H, r, "3. Balance sheet (as reported, 31 March)", 8)
r += 1
BS_SRC = "Mar-22: FY23 results p.2; Mar-23/24: FY24 results p.2; Mar-25/26: FY26 results p.9"
hr["bs_first"] = r
for _, row in bs_df.iterrows():
    key = "bs_" + row["line"].lower().replace(" ", "_").replace(",", "").replace("(", "").replace(")", "")
    hr[key] = r
    cell(H, f"A{r}", row["line"])
    cell(H, f"B{r}", row["model_line"], color="404040")
    for col, y in zip(HC, HY):
        cell(H, f"{col}{r}", float(row[y]), color=BLUE, fmt="#,##0.00")
    cell(H, f"H{r}", BS_SRC, color="404040", italic=True)
    r += 1
hr["bs_last"] = r - 1
r += 1
cell(H, f"A{r}", "Aggregated to the model's balance-sheet lines (SUMIF on column B)", bold=True)
r += 1
ASSET_LINES = [("agg_nfa", "Net fixed assets"), ("agg_cwip", "Capital work-in-progress"),
               ("agg_invest", "Investments"), ("agg_inv", "Inventories"), ("agg_rec", "Trade receivables"),
               ("agg_cash", "Cash and cash equivalents"), ("agg_bank", "Other bank balances"),
               ("agg_oth", "Other assets")]
EL_LINES = [("agg_cap", "Equity share capital"), ("agg_oe", "Other equity"), ("agg_nci", "Non-controlling interest"),
            ("agg_debt", "Borrowings"), ("agg_lease", "Lease liabilities"), ("agg_pay", "Trade payables"),
            ("agg_dtl", "Deferred tax liabilities"), ("agg_othl", "Other liabilities")]
rng_b = f"$B${hr['bs_first']}:$B${hr['bs_last']}"
for key, lab in ASSET_LINES:
    hline(key, lab, "Rs crore", lambda c, l=lab: f'=SUMIF({rng_b},"{l}",{c}${hr["bs_first"]}:{c}${hr["bs_last"]})',
          fmt=F_CR)
hline("ta", "Total assets (computed)", "Rs crore", lambda c: f"=SUM({c}{hr['agg_nfa']}:{c}{hr['agg_oth']})",
      fmt=F_CR, bold=True)
hline("ta_rep", "Total assets (reported)", "Rs crore", [83827.79, 91386.96, 100802.01, 133697.15, 141376.05],
      fmt=F_CR, note=BS_SRC)
for key, lab in EL_LINES:
    hline(key, lab, "Rs crore", lambda c, l=lab: f'=SUMIF({rng_b},"{l}",{c}${hr["bs_first"]}:{c}${hr["bs_last"]})',
          fmt=F_CR)
hline("tel", "Total equity and liabilities (computed)", "Rs crore",
      lambda c: f"=SUM({c}{hr['agg_cap']}:{c}{hr['agg_othl']})", fmt=F_CR, bold=True)
hline("bs_chk", "Check: |assets - equity - liabilities| + |computed - reported total assets|", "Rs crore",
      lambda c: f"=ABS({c}{hr['ta']}-{c}{hr['tel']})+ABS({c}{hr['ta']}-{c}{hr['ta_rep']})",
      note="must be below 0.5 (Checks sheet)")
hline("ce", "Capital employed (total equity + borrowings + lease liabilities)", "Rs crore",
      lambda c: f"=SUM({c}{hr['agg_cap']}:{c}{hr['agg_lease']})", fmt=F_CR)
cur_inv = hr["bs_investments_current"]
hline("nd", "Net debt (borrowings - cash - other bank balances - current investments)", "Rs crore",
      lambda c: f"={c}{hr['agg_debt']}-{c}{hr['agg_cash']}-{c}{hr['agg_bank']}-{c}{cur_inv}", fmt=F_CR,
      note="excludes lease liabilities; the company's own figure also nets some non-current treasury investments")
hline("nde", "Net debt / EBITDA", "x", lambda c: f"={c}{hr['nd']}/{c}{hr['ebitda']}", fmt=F_X)

r += 1
section(H, r, "4. Cash flow statement (as reported, Ind AS indirect method)", 8)
r += 1
CF_KEYS = {"Net cash from operating activities": "cfo", "Purchase of property, plant and equipment": "capex_cf",
           "Net cash from investing activities": "cfi", "Net proceeds from/(repayment of) borrowings": "cf_debt",
           "Interest paid (excl. lease interest)": "cf_int", "Dividends paid": "cf_div",
           "Net cash from financing activities": "cff", "Cash and cash equivalents at beginning of year": "cf_open",
           "Cash acquired/transferred (acquisitions, discontinued ops) and FX": "cf_other",
           "Cash and cash equivalents at end of year": "cf_close"}
CF_SRC = "FY22-FY23: FY23/FY24 results p.3; FY24: FY24 results p.3; FY25-FY26: FY26 results p.10"
for _, row in cf_df.iterrows():
    k = CF_KEYS[row["line"]]
    hr[k] = r
    cell(H, f"A{r}", row["line"])
    cell(H, f"B{r}", "Rs crore", color="404040")
    for col, y in zip(HC, HY):
        cell(H, f"{col}{r}", float(row[y]), color=BLUE, fmt="#,##0.00")
    note = row["note"] if isinstance(row["note"], str) and row["note"] else CF_SRC
    cell(H, f"H{r}", note, color="404040", italic=True)
    r += 1
hline("cf_net", "Net change in cash (CFO + CFI + CFF)", "Rs crore",
      lambda c: f"={c}{hr['cfo']}+{c}{hr['cfi']}+{c}{hr['cff']}")
hline("cf_close_c", "Closing cash (computed: opening + net change + other)", "Rs crore",
      lambda c: f"={c}{hr['cf_open']}+{c}{hr['cf_net']}+{c}{hr['cf_other']}")
hline("cf_chk", "Check: |computed - reported closing cash| + |reported closing cash - balance-sheet cash|",
      "Rs crore", lambda c: f"=ABS({c}{hr['cf_close_c']}-{c}{hr['cf_close']})+ABS({c}{hr['cf_close']}-{c}{hr['agg_cash']})",
      note="must be below 0.5 (Checks sheet)")
hline("fcf_rep", "Free cash flow, reported basis (CFO - purchase of PP&E)", "Rs crore",
      lambda c: f"={c}{hr['cfo']}+{c}{hr['capex_cf']}", fmt=F_CR)
hline("cfo_post", "CFO after interest paid (model basis: interest inside operating cash flow)", "Rs crore",
      lambda c: f"={c}{hr['cfo']}+{c}{hr['cf_int']}", fmt=F_CR)

r += 1
section(H, r, "5. Balance-sheet ratios used to set the drivers", 8)
r += 1
hline("rec_days", "Receivable days (trade receivables / revenue x 365)", "days",
      lambda c: f"={c}{hr['agg_rec']}/{c}{hr['rev']}*365", fmt=F_DAYS)
hline("inv_days", "Inventory days (inventories / operating costs x 365)", "days",
      lambda c: f"={c}{hr['agg_inv']}/{c}{hr['opex']}*365", fmt=F_DAYS)
hline("pay_days", "Payable days (trade payables / operating costs x 365)", "days",
      lambda c: f"={c}{hr['agg_pay']}/{c}{hr['opex']}*365", fmt=F_DAYS)
hline("da_rate", "D&A % of opening net fixed assets", "%",
      lambda c: f"={c}{hr['da']}/{PREV[c]}{hr['agg_nfa']}", fmt=F_PCT, cols=HC[1:],
      note="FY25 is high because acquired assets (India Cements, Kesoram) were added during the year")
hline("cwip_pct", "Capital work-in-progress % of the year's cash capex", "%",
      lambda c: f"={c}{hr['agg_cwip']}/-{c}{hr['capex_cf']}", fmt=F_PCT)
hline("etr", "Effective tax rate (tax / PBT)", "%", lambda c: f"={c}{hr['tax']}/{c}{hr['pbt']}", fmt=F_PCT,
      note="FY22 includes a tax reversal; FY25 lower on acquisition-related deferred tax")
hline("payout", "Dividends paid / prior-year profit to owners", "%",
      lambda c: f"=-{c}{hr['cf_div']}/{PREV[c]}{hr['own']}", fmt=F_PCT, cols=HC[1:])
hline("int_rate", "Finance costs / average borrowings", "%",
      lambda c: f"={c}{hr['fin']}/AVERAGE({PREV[c]}{hr['agg_debt']},{c}{hr['agg_debt']})", fmt=F_PCT, cols=HC[1:])
hline("oi_yield", "Other income / opening cash, bank balances and investments", "%",
      lambda c: f"={c}{hr['oi']}/({PREV[c]}{hr['agg_cash']}+{PREV[c]}{hr['agg_bank']}+{PREV[c]}{hr['agg_invest']})",
      fmt=F_PCT, cols=HC[1:])
widths(H, {"A": 66, "B": 26, "C": 13, "D": 13, "E": 13, "F": 13, "G": 13, "H": 90})
H.freeze_panes = "C5"

# ============================================================== Drivers
D = ws_["Drivers"]
dr = ROW["Drivers"]
SCN = "Scenario"  # defined name -> Cover!$C$6
title(D, "Drivers and assumptions: Base, Bull and Bear")
cell(D, "A2", '="Selected scenario: "&Cover!$D$6&"  (change it on the Cover sheet, cell C6)"', bold=True)
cell(D, "A3", "Blue = input. Light-yellow fill = judgment assumption, with the reason in the last column. "
              "Black = formula. The 'Selected' rows/column feed the model through CHOOSE(Scenario, Base, Bull, Bear).",
     italic=True, color="404040")
YEAR_DRIVERS = [  # key, label, unit, fmt, {case: values}, {case: reason}
    ("adds", "Capacity additions", "MTPA", F_CR1,
     {"Base": [16.3, 29.8, 12, 12, 12], "Bull": [16.3, 29.8, 15, 15, 15], "Bear": [16.3, 22.8, 12, 6, 6]},
     {"Base": "Company roadmap 196.8 -> 213.1 (FY27E) -> 242.9 MTPA (FY28E), Q2FY27 presentation p.12; "
              "then ~12 MTPA a year, in line with Rs 8,000-10,000 cr annual capex guidance",
      "Bull": "Next organic phase beyond 240 MTPA (Q2FY27 call) runs at 15 MTPA a year",
      "Bear": "7 MTPA of the FY28E plan slips by a year; slower expansion after FY29E"}),
    ("util", "Capacity utilisation (volume / average capacity)", "%", F_PCT,
     {"Base": [0.82, 0.80, 0.80, 0.81, 0.82], "Bull": [0.84, 0.83, 0.83, 0.84, 0.85],
      "Bear": [0.79, 0.75, 0.75, 0.76, 0.77]},
     {"Base": "FY26A 80%; H1FY27 volume +12% YoY; dips in FY28E when 29.8 MTPA arrives; volume grows 6-9% a year "
              "vs 7-8% guidance (Q4FY26 call p.5)",
      "Bull": "Demand stays strong (infrastructure, housing), share gains from new capacity",
      "Bear": "Demand slows and new industry capacity weighs on utilisation"}),
    ("greal", "Realisation growth (net sales per tonne)", "% YoY", F_PCT,
     {"Base": [0.04, 0.02, 0.02, 0.02, 0.02], "Bull": [0.055, 0.025, 0.025, 0.025, 0.025],
      "Bear": [0.02, 0.015, 0.015, 0.015, 0.015]},
     {"Base": "H1FY27 revenue per tonne ~5% above the FY26 average and spot prices 5% above the Q2 average "
              "(Q2FY27 call p.8); long run +2% a year",
      "Bull": "Price increases stick; better trade mix and premium products",
      "Bear": "Price hikes roll back; competition from new capacity"}),
    ("gpf", "Power and fuel cost per tonne growth", "% YoY", F_PCT,
     {"Base": [0.06, 0.015, 0.015, 0.015, 0.015], "Bull": [0.03, 0.005, 0.005, 0.005, 0.005],
      "Bear": [0.08, 0.01, 0.01, 0.01, 0.01]},
     {"Base": "Fuel costs up on the West Asia crisis in FY27E (Q2FY27 call); green power and waste-heat recovery "
              "keep later increases below inflation",
      "Bull": "Fuel prices ease and the green power share rises faster",
      "Bear": "Fuel shock lasts longer"}),
]
section(D, 5, "A. Scenario drivers that change by year", 9)
header(D, 6, ["Driver", "Unit", "Case"] + FY + ["Reason / source"])
r = 7
for key, lab, unit, fmt, vals, why in YEAR_DRIVERS:
    for case in ("Base", "Bull", "Bear"):
        dr[f"{key}_{case}"] = r
        cell(D, f"A{r}", lab if case == "Base" else "")
        cell(D, f"B{r}", unit, color="404040")
        cell(D, f"C{r}", case)
        for col, v in zip(FC, vals[case]):
            cell(D, f"{col}{r}", v, color=BLUE, fmt=fmt, fill=YELLOW)
        cell(D, f"I{r}", why[case], color="404040", italic=True)
        r += 1
    dr[key] = r
    cell(D, f"C{r}", "Selected", bold=True)
    for col in FC:
        cell(D, f"{col}{r}", f"=CHOOSE({SCN},{col}{dr[key + '_Base']},{col}{dr[key + '_Bull']},{col}{dr[key + '_Bear']})",
             fmt=fmt, bold=True)
    r += 2

SCALAR = [  # key, label, unit, fmt, base, bull, bear, judgment?, reason
    ("adds_after", "Capacity additions after FY2031E (only for FY2031E capex phasing)", "MTPA/yr", F_CR1,
     12, 15, 6, True, "Same pace as FY29E-FY31E in each case"),
    ("g_rm", "Raw material cost per tonne growth", "% YoY", F_PCT, 0.025, 0.02, 0.025, True,
     "Near inflation; FY22-FY26 rise (847 -> 1,114 Rs/t) was lifted by traded building products, which also add revenue"),
    ("g_fr", "Freight cost per tonne growth", "% YoY", F_PCT, 0.025, 0.02, 0.025, True,
     "FY22-FY26 freight per tonne was flat (1,246 -> 1,243) as new plants cut lead distance; diesel inflation ahead"),
    ("g_oth", "Other expenses per tonne growth", "% YoY", F_PCT, 0.025, 0.02, 0.025, True,
     "FY22-FY26 other expenses per tonne rose 0.7% a year; inflation-like"),
    ("g_emp", "Employee cost growth (total)", "% YoY", F_PCT, 0.09, 0.08, 0.10, True,
     "Wage inflation ~7% plus staff for new plants; FY22-FY26 CAGR of 13% included acquisitions"),
    ("ooi", "Other operating income % of net sales", "%", F_PCT, 0.0129, 0.0129, 0.0129, True,
     "FY26A 1.29% (FY22-FY26 range 1.29%-1.72%)"),
    ("cost_mtpa", "Expansion cost per MTPA", "Rs crore/MTPA", F_CR, 432, 410, 475, True,
     "Rs 16,000 cr for 37 MTPA (Integrated Report FY26 p.46) = Rs 432 cr; Bull more brownfield, Bear 10% overrun"),
    ("lead", "Share of expansion capex spent in the year before commissioning", "%", F_PCT, 0.5, 0.5, 0.5, True,
     "Projects take 18-24 months; split 50/50 between the year before and the year of commissioning"),
    ("maint", "Maintenance and other capex per tonne of opening capacity", "Rs/t", F_RS, 75, 75, 75, True,
     "Sustaining, efficiency and green-power capex; puts FY27E total near the H1FY27 run-rate (Rs 5,882 cr in H1)"),
    ("cwip_pct", "Capital work-in-progress at year end % of the year's capex", "%", F_PCT, 0.75, 0.75, 0.75, True,
     "FY22-FY26 range 65%-86%, average 76% (Historical sheet, section 5)"),
    ("da_rate", "D&A % of opening net fixed assets", "%", F_PCT, 0.05, 0.05, 0.05, True,
     "FY26A 4.9%; H1FY27 D&A of Rs 2,414 cr annualises to about 5.0%"),
    ("rec_days", "Receivable days (on revenue)", "days", F_DAYS, 25, 24, 28, True, "FY26A 24.9 days; FY22-FY26 range 21-28"),
    ("inv_days", "Inventory days (on operating costs)", "days", F_DAYS, 50, 48, 54, True,
     "FY26A 49.5 days; FY22-FY26 range 46-55"),
    ("pay_days", "Payable days (on operating costs)", "days", F_DAYS, 52, 53, 50, True,
     "FY26A 52.3 days; FY22-FY26 range 50-54"),
    ("tax", "Tax rate", "%", F_PCT, "=MACRO:tax", "=MACRO:tax", "=MACRO:tax", False,
     "Section 115BAA rate 25.17% (link to section C); FY26A effective rate 25.1%"),
    ("nci", "Non-controlling interest share of profit after tax", "%", F_PCT, 0.005, 0.005, 0.005, True,
     "FY26A 0.3%; rises as India Cements (25% minority) becomes profitable"),
    ("payout", "Dividend payout (paid in year t, % of profit to owners of year t-1), FY28E on", "%", F_PCT,
     0.5, 0.5, 0.5, True, "FY25 37%, FY26 87% (Rs 240/share); CFO: payout can stay high if results allow (Q4FY26 call p.6)"),
    ("dps_fy26", "FY2026 dividend per share, paid in FY2027E", "Rs/share", F_EPS, 240, 240, 240, False,
     "Declared Apr-2026, ex-date 30-Jul-2026 (Q4FY26 call p.5; Yahoo dividend history)"),
    ("min_cash", "Minimum cash balance", "Rs crore", F_CR, 500, 500, 500, True,
     "Operating buffer; Mar-26 cash 354 plus Rs 4,766 cr bank balances and current investments (held flat)"),
    ("yld", "Yield on opening cash, bank balances and investments", "%", F_PCT, "=MACRO:tbill", "=MACRO:tbill",
     "=MACRO:tbill", False, "91-day T-bill 5.93% (link to section C); H1FY27 other income annualises to ~6%"),
    ("rate_term", "Interest rate on term debt (incl. other finance charges), on average balance", "%", F_PCT,
     0.082, 0.080, 0.086, True, "FY26A finance costs / average borrowings 8.2%; new NCDs at 7.25%; 10Y G-sec 7.41%"),
    ("rev_spread", "Revolver spread over the repo rate", "%", F_PCT, 0.03, 0.03, 0.03, True,
     "Short-term bank lines priced at repo + ~3%"),
    ("rate_rev", "Revolver interest rate (repo + spread), on opening balance", "%", F_PCT,
     "=MACRO:repo+C", "=MACRO:repo+D", "=MACRO:repo+E", False, "Formula: repo rate (section C) + spread above"),
    ("refi", "Share of each scheduled maturity refinanced with new term debt", "%", F_PCT, 0.5, 0.5, 0.5, True,
     "Half refinanced, half repaid from cash flow; company keeps net debt / EBITDA below 1x (Q4FY26 call p.5)"),
    ("new_fy27", "New term debt drawn in FY2027E", "Rs crore", F_CR, 5000, 5000, 5000, False,
     "Rs 5,000 cr NCDs at 7.25% raised in Q2FY27 (Q2FY27 call p.7)"),
]
section(D, r, "B. Scenario drivers that are the same in every year", 9)
r += 1
header(D, r, ["Driver", "Unit", "Base", "Bull", "Bear", "Selected", "Reason / source", "", ""])
r += 1
pending = []
for key, lab, unit, fmt, b, u, e, judg, why in SCALAR:
    dr[key] = r
    cell(D, f"A{r}", lab)
    cell(D, f"B{r}", unit, color="404040")
    for col, v in zip(["C", "D", "E"], [b, u, e]):
        if isinstance(v, str) and v.startswith("=MACRO:"):
            pending.append((f"{col}{r}", v, fmt))
        else:
            cell(D, f"{col}{r}", v, color=BLUE, fmt=fmt, fill=YELLOW if judg else None)
    cell(D, f"F{r}", f"=CHOOSE({SCN},C{r},D{r},E{r})", fmt=fmt, bold=True)
    cell(D, f"G{r}", why, color="404040", italic=True)
    r += 1
r += 1
section(D, r, "C. Market and macro inputs (sourced facts, same in every scenario)", 9)
r += 1
header(D, r, ["Input", "Unit", "Value", "Source (saved copy in source_data/)", "", "", "", "", ""])
r += 1
m = mkt["macro"]
MACRO = [("repo", "RBI repo rate", "%", F_PCT, m["repo_rate"]),
         ("tbill", "91-day T-bill cut-off yield", "%", F_PCT, m["tbill_91d"]),
         ("gsec", "India 10-year G-sec yield", "%", "0.00%", m["gsec_10y"]),
         ("tax", "Corporate tax rate (new regime, s.115BAA)", "%", F_PCT, m["tax_rate"]),
         ("usdinr", "USD/INR", "Rs per USD", "0.00", m["usd_inr"])]
for key, lab, unit, fmt, (val, src, path) in MACRO:
    dr["m_" + key] = r
    cell(D, f"A{r}", lab)
    cell(D, f"B{r}", unit, color="404040")
    cell(D, f"C{r}", val, color=BLUE, fmt=fmt)
    cell(D, f"D{r}", f"{src} | {path}", color="404040", italic=True)
    r += 1
for key, lab, unit, fmt, val, src in [
        ("price", "UltraTech share price, 30-Oct-2026 close", "Rs", F_RS, mkt["share_price_rs"], mkt["share_price_source"]),
        ("shares_eps", "Shares for EPS and dividends (net of treasury shares)", "crore", "0.00",
         mkt["shares_for_eps_crore"], "FY26 profit to owners 8,165.64 / basic EPS Rs 277.62 (FY26 results p.8)"),
        ("shares_issued", "Shares issued", "crore", "0.000", mkt["shares_issued_crore"],
         "Equity share capital Rs 294.68 cr / Rs 10 face value (FY26 results p.9)")]:
    dr[key] = r
    cell(D, f"A{r}", lab)
    cell(D, f"B{r}", unit, color="404040")
    cell(D, f"C{r}", val, color=BLUE, fmt=fmt)
    cell(D, f"D{r}", src, color="404040", italic=True)
    r += 1
for addr, v, fmt in pending:
    body = v[len("=MACRO:"):]
    name, _, plus = body.partition("+")
    f = f"=$C${dr['m_' + name]}" + (f"+{plus}{dr['rev_spread']}" if plus else "")
    cell(D, addr, f, fmt=fmt)
r += 1
section(D, r, "D. Company guidance and H1 FY2027 actuals (reference only: used to set the judgments above)", 9)
r += 1
header(D, r, ["Fact", "Unit", "Value", "Source", "", "", "", "", ""])
r += 1
for _, g in guid_df.iterrows():
    cell(D, f"A{r}", g["fact"])
    cell(D, f"B{r}", g["unit"], color="404040")
    cell(D, f"C{r}", float(g["value"]), color=BLUE, fmt="#,##0.0#")
    cell(D, f"D{r}", g["source"], color="404040", italic=True)
    r += 1
widths(D, {"A": 70, "B": 14, "C": 11, "D": 11, "E": 11, "F": 11, "G": 11, "H": 11, "I": 110})
D.freeze_panes = "D7"


# ============================================================== Income statement
S_IS, S_BS, S_CF, S_DS = "Income_Statement", "Balance_Sheet", "Cash_Flow", "Debt_Schedule"
I = ws_[S_IS]
ir = ROW[S_IS]
br = ROW[S_BS]
cr_ = ROW[S_CF]
dsr = ROW[S_DS]
# row numbers of the other statements are fixed up front so formulas can point forward
BS_ORDER = ["sec_capex", "capex_exp", "capex_mnt", "capex", "sp1", "cwip_open", "cwip_add", "capz", "cwip_close",
            "sp2", "nfa_open", "nfa_capz", "da", "nfa_close", "sp3", "sec_wc", "inv", "rec", "pay", "nwc", "sp4",
            "sec_bs", "a_nfa", "a_cwip", "a_invest", "a_inv", "a_rec", "a_cash", "a_bank", "a_oth", "ta", "sp5",
            "e_cap", "e_oe", "e_nci", "te", "l_debt", "l_lease", "l_pay", "l_dtl", "l_oth", "tl", "tel", "bal", "sp6",
            "sec_eq", "oe_open", "oe_pat", "oe_div", "oe_close", "dps", "sp7", "sec_memo", "liq_inv", "nd", "nd_e",
            "ce", "roce"]
for i, k in enumerate(BS_ORDER):
    br[k] = 5 + i
CF_ORDER = ["sec_cfo", "pat", "da", "d_inv", "d_rec", "d_pay", "cfo", "sp1", "sec_cfi", "capex", "cfi", "sp2",
            "sec_cff", "new", "rep", "rev", "div", "cff", "sp3", "net", "open", "other", "close", "sp4", "fcf", "pre"]
for i, k in enumerate(CF_ORDER):
    cr_[k] = 5 + i
DS_ORDER = ["sec_term", "t_open", "t_new", "t_rep", "t_close", "t_int", "sp1", "sec_rev", "r_open", "pre", "minc",
            "r_draw", "r_close", "r_int", "sp2", "sec_tot", "fin_total", "debt_total", "sp3", "sec_credit", "nd",
            "nd_e", "icov", "ebitda_cov", "d_e"]
for i, k in enumerate(DS_ORDER):
    dsr[k] = 5 + i


def fsheet(ws, name: str, ttl: str) -> None:
    title(ws, ttl)
    cell(ws, "A2", '="Scenario: "&Cover!$D$6&"  |  Rs crore unless stated  |  FY = year to 31 March"', italic=True,
         color="404040")
    header(ws, 4, ["Line item", "Unit", "FY2026A"] + FY + ["Notes"])
    widths(ws, {"A": 62, "B": 11, "C": 12, "D": 12, "E": 12, "F": 12, "G": 12, "H": 12, "I": 95})
    ws.freeze_panes = "C5"


def drv(key: str, col: str | None = None) -> str:
    """Selected driver: year-by-year rows use the same column; scalar drivers use column F (absolute)."""
    return f"Drivers!{col}{dr[key]}" if col else f"Drivers!$F${dr[key]}"


def hist(key: str, col: str = "G") -> str:
    return f"Historical!{col}{hr[key]}"


fsheet(I, S_IS, "Income statement forecast, UltraTech Cement (consolidated)")
r = 5
section(I, r, "Operating build (volume x price, cost per tonne)", 9); r += 1
v = {"C": f"={hist('cap', 'F')}"}; v.update({c: f"={PREV[c]}{r + 2}" for c in FC})
r = line(I, S_IS, r, "cap_open", "Capacity at start of year", "MTPA", v, F_CR1, "Opening = previous year-end capacity")
v = {"C": f"=C{r + 1}-C{r - 1}"}; v.update({c: f"={drv('adds', c)}" for c in FC})
r = line(I, S_IS, r, "adds", "Capacity additions", "MTPA", v, F_CR1, "Drivers, section A (selected case)")
v = {"C": f"={hist('cap')}"}; v.update({c: f"={c}{ir['cap_open']}+{c}{ir['adds']}" for c in FC})
r = line(I, S_IS, r, "cap_close", "Capacity at end of year", "MTPA", v, F_CR1, "FY2026A: Q2FY27 presentation p.12")
v = {c: f"=AVERAGE({c}{ir['cap_open']},{c}{ir['cap_close']})" for c in ["C"] + FC}
r = line(I, S_IS, r, "cap_avg", "Average capacity", "MTPA", v, F_CR1)
v = {"C": f"=C{r + 1}/C{ir['cap_avg']}"}; v.update({c: f"={drv('util', c)}" for c in FC})
r = line(I, S_IS, r, "util", "Capacity utilisation", "%", v, F_PCT, "Drivers, section A")
v = {"C": f"={hist('vol')}"}; v.update({c: f"={c}{ir['util']}*{c}{ir['cap_avg']}" for c in FC})
r = line(I, S_IS, r, "vol", "Sales volume", "MnT", v, F_CR1, "Utilisation x average capacity", bold=True)
v = {"C": f"=C{ir['vol']}/{hist('vol', 'F')}-1"}; v.update({c: f"={c}{ir['vol']}/{PREV[c]}{ir['vol']}-1" for c in FC})
r = line(I, S_IS, r, "vol_g", "Volume growth", "% YoY", v, F_PCT)
IS_ORDER = ["real", "real_g", "rm_t", "pf_t", "fr_t", "oth_t", "emp_t", "ebitda_t", "sp1", "sec_is", "ns", "ooi",
            "rev", "rev_g", "rm", "pf", "fr", "emp", "oth", "opex", "ebitda", "ebitda_m", "da", "ebit", "oi", "fin",
            "exc", "jv", "pbt", "tax", "etr", "pat", "nci", "own", "own_g", "eps"]
for i, k in enumerate(IS_ORDER):
    ir[k] = r + i
PRE = {S_IS: dict(ir), S_BS: dict(br), S_CF: dict(cr_), S_DS: dict(dsr)}  # planned rows, checked after writing
v = {"C": f"=C{ir['ns']}/C{ir['vol']}*10"}; v.update({c: f"={PREV[c]}{ir['real']}*(1+{c}{ir['real_g']})" for c in FC})
r = line(I, S_IS, r, "real", "Realisation (net sales per tonne)", "Rs/t", v, F_RS, "Net sales / volume", bold=True)
v = {"C": f"=C{ir['real']}/({hist('ns', 'F')}/{hist('vol', 'F')}*10)-1"}; v.update({c: f"={drv('greal', c)}" for c in FC})
r = line(I, S_IS, r, "real_g", "Realisation growth", "% YoY", v, F_PCT, "Drivers, section A")
for key, lab, src, g in [("rm_t", "Raw materials per tonne (incl. traded goods)", "rm", "g_rm"),
                         ("pf_t", "Power and fuel per tonne", "pf", None),
                         ("fr_t", "Freight and forwarding per tonne", "fr", "g_fr"),
                         ("oth_t", "Other expenses per tonne", "oth", "g_oth")]:
    v = {"C": f"=C{ir[src]}/C{ir['vol']}*10"}
    v.update({c: f"={PREV[c]}{ir[key]}*(1+{drv(g) if g else drv('gpf', c)})" for c in FC})
    r = line(I, S_IS, r, key, lab, "Rs/t", v, F_RS, "Previous year x (1 + growth driver)")
v = {c: f"={c}{ir['emp']}/{c}{ir['vol']}*10" for c in ["C"] + FC}
r = line(I, S_IS, r, "emp_t", "Employee cost per tonne (memo)", "Rs/t", v, F_RS, "Employee cost is driven by total growth")
v = {c: f"={c}{ir['ebitda']}/{c}{ir['vol']}*10" for c in ["C"] + FC}
r = line(I, S_IS, r, "ebitda_t", "EBITDA per tonne", "Rs/t", v, F_RS, "Key cement industry metric", bold=True)
r += 1
section(I, r, "Income statement", 9); r += 1
v = {"C": f"={hist('ns')}"}; v.update({c: f"={c}{ir['vol']}*{c}{ir['real']}/10" for c in FC})
r = line(I, S_IS, r, "ns", "Net sales", "Rs crore", v, F_CR, "Volume (MnT) x realisation (Rs/t) / 10")
v = {"C": f"={hist('ooi')}"}; v.update({c: f"={c}{ir['ns']}*{drv('ooi')}" for c in FC})
r = line(I, S_IS, r, "ooi", "Other operating income", "Rs crore", v, F_CR, "% of net sales (Drivers)")
v = {c: f"={c}{ir['ns']}+{c}{ir['ooi']}" for c in ["C"] + FC}
r = line(I, S_IS, r, "rev", "Revenue from operations", "Rs crore", v, F_CR, bold=True)
v = {"C": f"=C{ir['rev']}/{hist('rev', 'F')}-1"}; v.update({c: f"={c}{ir['rev']}/{PREV[c]}{ir['rev']}-1" for c in FC})
r = line(I, S_IS, r, "rev_g", "Revenue growth", "% YoY", v, F_PCT)
for key, lab, hk, tk in [("rm", "Raw materials (incl. traded goods and inventory change)", "rm_sum", "rm_t"),
                         ("pf", "Power and fuel", "pf", "pf_t"), ("fr", "Freight and forwarding", "fr", "fr_t")]:
    v = {"C": f"={hist(hk)}"}; v.update({c: f"={c}{ir[tk]}*{c}{ir['vol']}/10" for c in FC})
    r = line(I, S_IS, r, key, lab, "Rs crore", v, F_CR, "Cost per tonne x volume / 10")
v = {"C": f"={hist('emp')}"}; v.update({c: f"={PREV[c]}{ir['emp']}*(1+{drv('g_emp')})" for c in FC})
r = line(I, S_IS, r, "emp", "Employee benefits", "Rs crore", v, F_CR, "Previous year x (1 + growth)")
v = {"C": f"={hist('oth')}"}; v.update({c: f"={c}{ir['oth_t']}*{c}{ir['vol']}/10" for c in FC})
r = line(I, S_IS, r, "oth", "Other expenses", "Rs crore", v, F_CR, "Cost per tonne x volume / 10")
v = {c: f"=SUM({c}{ir['rm']}:{c}{ir['oth']})" for c in ["C"] + FC}
r = line(I, S_IS, r, "opex", "Total operating costs", "Rs crore", v, F_CR, top_border=True)
v = {c: f"={c}{ir['rev']}-{c}{ir['opex']}" for c in ["C"] + FC}
r = line(I, S_IS, r, "ebitda", "EBITDA", "Rs crore", v, F_CR, bold=True)
v = {c: f"={c}{ir['ebitda']}/{c}{ir['rev']}" for c in ["C"] + FC}
r = line(I, S_IS, r, "ebitda_m", "EBITDA margin", "%", v, F_PCT)
v = {"C": f"={hist('da')}"}; v.update({c: f"={S_BS}!{c}{br['da']}" for c in FC})
r = line(I, S_IS, r, "da", "Depreciation and amortisation", "Rs crore", v, F_CR, "Balance_Sheet fixed-asset schedule")
v = {c: f"={c}{ir['ebitda']}-{c}{ir['da']}" for c in ["C"] + FC}
r = line(I, S_IS, r, "ebit", "EBIT", "Rs crore", v, F_CR, bold=True)
v = {"C": f"={hist('oi')}"}
v.update({c: f"={drv('yld')}*({S_BS}!{PREV[c]}{br['a_cash']}+{S_BS}!{PREV[c]}{br['a_bank']}+{S_BS}!{PREV[c]}{br['a_invest']})"
          for c in FC})
r = line(I, S_IS, r, "oi", "Other income", "Rs crore", v, F_CR, "Yield x opening cash, bank balances and investments")
v = {"C": f"={hist('fin')}"}; v.update({c: f"={S_DS}!{c}{dsr['fin_total']}" for c in FC})
r = line(I, S_IS, r, "fin", "Finance costs", "Rs crore", v, F_CR, "Debt_Schedule (interest on opening/average balances)")
v = {"C": f"={hist('exc')}"}; v.update({c: 0 for c in FC})
r = line(I, S_IS, r, "exc", "Exceptional items (charge)", "Rs crore", v, F_CR, "Not forecast")
v = {"C": f"={hist('jv')}"}; v.update({c: 0 for c in FC})
r = line(I, S_IS, r, "jv", "Share of profit/(loss) of associates and JV", "Rs crore", v, F_CR, "Not forecast (FY26A -16)")
v = {c: f"={c}{ir['ebit']}+{c}{ir['oi']}-{c}{ir['fin']}-{c}{ir['exc']}+{c}{ir['jv']}" for c in ["C"] + FC}
r = line(I, S_IS, r, "pbt", "Profit before tax", "Rs crore", v, F_CR, bold=True, top_border=True)
v = {"C": f"={hist('tax')}"}; v.update({c: f"={c}{ir['pbt']}*{drv('tax')}" for c in FC})
r = line(I, S_IS, r, "tax", "Tax expense", "Rs crore", v, F_CR, "PBT x 25.17% (all tax treated as paid in the year)")
v = {c: f"={c}{ir['tax']}/{c}{ir['pbt']}" for c in ["C"] + FC}
r = line(I, S_IS, r, "etr", "Effective tax rate", "%", v, F_PCT)
v = {c: f"={c}{ir['pbt']}-{c}{ir['tax']}" for c in ["C"] + FC}
r = line(I, S_IS, r, "pat", "Profit after tax", "Rs crore", v, F_CR, bold=True)
v = {"C": f"={hist('nci')}"}; v.update({c: f"={c}{ir['pat']}*{drv('nci')}" for c in FC})
r = line(I, S_IS, r, "nci", "Non-controlling interest", "Rs crore", v, F_CR, "Mainly the 25% minority in India Cements")
v = {c: f"={c}{ir['pat']}-{c}{ir['nci']}" for c in ["C"] + FC}
r = line(I, S_IS, r, "own", "Profit attributable to owners", "Rs crore", v, F_CR, bold=True)
v = {"C": f"=C{ir['own']}/{hist('own', 'F')}-1"}; v.update({c: f"={c}{ir['own']}/{PREV[c]}{ir['own']}-1" for c in FC})
r = line(I, S_IS, r, "own_g", "Growth in profit to owners", "% YoY", v, F_PCT)
v = {c: f"={c}{ir['own']}/Drivers!$C${dr['shares_eps']}" for c in ["C"] + FC}
r = line(I, S_IS, r, "eps", "EPS (basic)", "Rs", v, F_EPS, "Profit to owners / 29.41 crore shares", bold=True)
assert all(ROW[S_IS][k] == PRE[S_IS][k] for k in IS_ORDER), "Income_Statement rows moved"


# ============================================================== Balance sheet
B = ws_[S_BS]
fsheet(B, S_BS, "Balance sheet forecast with fixed-asset and working-capital schedules")
ISr = lambda k, c: f"{S_IS}!{c}{ir[k]}"  # noqa: E731


def bl(key, label, unit, values, fmt=F_CR, note="", bold=False, top=False):
    line(B, S_BS, br[key], key, label, unit, values, fmt, note, bold, top)


section(B, br["sec_capex"], "Capex and fixed assets (Rs crore)", 9)
v = {c: f"={drv('cost_mtpa')}*((1-{drv('lead')})*{ISr('adds', c)}+{drv('lead')}*"
        f"{ISr('adds', NEXT[c]) if c in NEXT else drv('adds_after')})" for c in FC}
bl("capex_exp", "Expansion capex", "Rs crore", v,
   note="Cost per MTPA x (50% of this year's additions + 50% of next year's additions)")
v = {c: f"={drv('maint')}*{ISr('cap_open', c)}/10" for c in FC}
bl("capex_mnt", "Maintenance and other capex", "Rs crore", v, note="Rs per tonne x opening capacity (MTPA) / 10")
v = {"C": f"=-{hist('capex_cf')}"}; v.update({c: f"={c}{br['capex_exp']}+{c}{br['capex_mnt']}" for c in FC})
bl("capex", "Total capex", "Rs crore", v, note="FY2026A = cash purchase of PP&E", bold=True, top=True)
v = {c: f"={PREV[c]}{br['cwip_close']}" for c in FC}
bl("cwip_open", "Capital work-in-progress at start of year", "Rs crore", v)
v = {c: f"={c}{br['capex']}" for c in FC}
bl("cwip_add", "+ Capex", "Rs crore", v)
v = {c: f"={c}{br['cwip_open']}+{c}{br['cwip_add']}-{c}{br['cwip_close']}" for c in FC}
bl("capz", "- Capitalised into fixed assets", "Rs crore", v, note="Balancing item of the CWIP roll-forward")
v = {"C": f"={hist('agg_cwip')}"}; v.update({c: f"={c}{br['capex']}*{drv('cwip_pct')}" for c in FC})
bl("cwip_close", "Capital work-in-progress at end of year", "Rs crore", v, note="% of the year's capex", bold=True)
v = {c: f"={PREV[c]}{br['nfa_close']}" for c in FC}
bl("nfa_open", "Net fixed assets at start of year", "Rs crore", v)
v = {c: f"={c}{br['capz']}" for c in FC}
bl("nfa_capz", "+ Capitalised from CWIP", "Rs crore", v)
v = {"C": f"={hist('da')}"}; v.update({c: f"={c}{br['nfa_open']}*{drv('da_rate')}" for c in FC})
bl("da", "- Depreciation and amortisation", "Rs crore", v, note="% of opening net fixed assets")
v = {"C": f"={hist('agg_nfa')}"}
v.update({c: f"={c}{br['nfa_open']}+{c}{br['nfa_capz']}-{c}{br['da']}" for c in FC})
bl("nfa_close", "Net fixed assets at end of year", "Rs crore", v, bold=True,
   note="PP&E, right-of-use assets, goodwill and intangibles")
section(B, br["sec_wc"], "Working capital (Rs crore)", 9)
v = {"C": f"={hist('agg_inv')}"}; v.update({c: f"={drv('inv_days')}*{ISr('opex', c)}/365" for c in FC})
bl("inv", "Inventories", "Rs crore", v, note="Inventory days x operating costs / 365")
v = {"C": f"={hist('agg_rec')}"}; v.update({c: f"={drv('rec_days')}*{ISr('rev', c)}/365" for c in FC})
bl("rec", "Trade receivables", "Rs crore", v, note="Receivable days x revenue / 365")
v = {"C": f"={hist('agg_pay')}"}; v.update({c: f"={drv('pay_days')}*{ISr('opex', c)}/365" for c in FC})
bl("pay", "Trade payables", "Rs crore", v, note="Payable days x operating costs / 365")
v = {c: f"={c}{br['inv']}+{c}{br['rec']}-{c}{br['pay']}" for c in ["C"] + FC}
bl("nwc", "Trade working capital (inventories + receivables - payables)", "Rs crore", v, bold=True, top=True)
section(B, br["sec_bs"], "Balance sheet at 31 March (Rs crore)", 9)


def flat_line(key, label, hk, note="Held flat at the 31-Mar-2026 level"):
    vals = {"C": f"={hist(hk)}"}
    vals.update({c: f"={PREV[c]}{br[key]}" for c in FC})
    bl(key, label, "Rs crore", vals, note=note)


bl("a_nfa", "Net fixed assets", "Rs crore", {c: f"={c}{br['nfa_close']}" for c in ["C"] + FC})
bl("a_cwip", "Capital work-in-progress", "Rs crore", {c: f"={c}{br['cwip_close']}" for c in ["C"] + FC})
flat_line("a_invest", "Investments (treasury and strategic, incl. equity-accounted)", "agg_invest")
bl("a_inv", "Inventories", "Rs crore", {c: f"={c}{br['inv']}" for c in ["C"] + FC})
bl("a_rec", "Trade receivables", "Rs crore", {c: f"={c}{br['rec']}" for c in ["C"] + FC})
v = {"C": f"={hist('agg_cash')}"}; v.update({c: f"={S_CF}!{c}{cr_['close']}" for c in FC})
bl("a_cash", "Cash and cash equivalents", "Rs crore", v, note="From the cash-flow statement (closing cash)")
flat_line("a_bank", "Other bank balances", "agg_bank")
flat_line("a_oth", "Other assets (loans, other financial assets, tax assets, other)", "agg_oth")
bl("ta", "Total assets", "Rs crore", {c: f"=SUM({c}{br['a_nfa']}:{c}{br['a_oth']})" for c in ["C"] + FC},
   bold=True, top=True)
flat_line("e_cap", "Equity share capital", "agg_cap", note="No new shares assumed")
v = {"C": f"={hist('agg_oe')}"}; v.update({c: f"={c}{br['oe_close']}" for c in FC})
bl("e_oe", "Other equity (reserves)", "Rs crore", v, note="Roll-forward below")
v = {"C": f"={hist('agg_nci')}"}; v.update({c: f"={PREV[c]}{br['e_nci']}+{ISr('nci', c)}" for c in FC})
bl("e_nci", "Non-controlling interest", "Rs crore", v, note="Opening + minority share of profit (no minority dividends)")
bl("te", "Total equity", "Rs crore", {c: f"=SUM({c}{br['e_cap']}:{c}{br['e_nci']})" for c in ["C"] + FC},
   bold=True, top=True)
v = {"C": f"={hist('agg_debt')}"}; v.update({c: f"={S_DS}!{c}{dsr['debt_total']}" for c in FC})
bl("l_debt", "Borrowings (term debt + revolver)", "Rs crore", v, note="From the debt schedule")
flat_line("l_lease", "Lease liabilities", "agg_lease")
bl("l_pay", "Trade payables", "Rs crore", {c: f"={c}{br['pay']}" for c in ["C"] + FC})
flat_line("l_dtl", "Deferred tax liabilities (net)", "agg_dtl", note="Held flat: tax expense treated as cash tax")
flat_line("l_oth", "Other liabilities (provisions, other financial and current liabilities)", "agg_othl")
bl("tl", "Total liabilities", "Rs crore", {c: f"=SUM({c}{br['l_debt']}:{c}{br['l_oth']})" for c in ["C"] + FC},
   bold=True, top=True)
bl("tel", "Total equity and liabilities", "Rs crore", {c: f"={c}{br['te']}+{c}{br['tl']}" for c in ["C"] + FC},
   bold=True)
bl("bal", "Balance check: assets - equity - liabilities (must be 0)", "Rs crore",
   {c: f"=ROUND({c}{br['ta']}-{c}{br['tel']},2)" for c in ["C"] + FC}, fmt="#,##0.00", bold=True)
section(B, br["sec_eq"], "Other equity roll-forward and dividends (Rs crore)", 9)
bl("oe_open", "Other equity at start of year", "Rs crore", {c: f"={PREV[c]}{br['e_oe']}" for c in FC})
bl("oe_pat", "+ Profit attributable to owners", "Rs crore", {c: f"={ISr('own', c)}" for c in FC})
v = {"C": f"=-{hist('cf_div')}", "D": f"={drv('dps_fy26')}*Drivers!$C${dr['shares_eps']}"}
v.update({c: f"={drv('payout')}*{ISr('own', PREV[c])}" for c in FC[1:]})
bl("oe_div", "- Dividends paid", "Rs crore", v,
   note="FY27E: Rs 240/share declared for FY26; later years: payout x previous year's profit to owners")
bl("oe_close", "Other equity at end of year", "Rs crore",
   {c: f"={c}{br['oe_open']}+{c}{br['oe_pat']}-{c}{br['oe_div']}" for c in FC}, bold=True)
bl("dps", "Dividend per share paid in the year", "Rs", {c: f"={c}{br['oe_div']}/Drivers!$C${dr['shares_eps']}"
                                                         for c in ["C"] + FC}, fmt=F_EPS)
section(B, br["sec_memo"], "Memo: leverage and returns", 9)
v = {"C": f"=Historical!G{hr['bs_investments_current']}"}; v.update({c: f"={PREV[c]}{br['liq_inv']}" for c in FC})
bl("liq_inv", "Current (liquid) investments, part of investments above", "Rs crore", v, note="Held flat")
bl("nd", "Net debt (borrowings - cash - other bank balances - current investments)", "Rs crore",
   {c: f"={c}{br['l_debt']}-{c}{br['a_cash']}-{c}{br['a_bank']}-{c}{br['liq_inv']}" for c in ["C"] + FC}, bold=True,
   note="Excludes leases. Company definition (also nets other treasury assets) gave 0.94x at Mar-26")
bl("nd_e", "Net debt / EBITDA", "x", {c: f"={c}{br['nd']}/{ISr('ebitda', c)}" for c in ["C"] + FC}, fmt=F_X,
   bold=True)
bl("ce", "Capital employed (total equity + borrowings + lease liabilities)", "Rs crore",
   {c: f"={c}{br['te']}+{c}{br['l_debt']}+{c}{br['l_lease']}" for c in ["C"] + FC})
v = {"C": f"=({ISr('ebit', 'C')}+{ISr('oi', 'C')})/AVERAGE(Historical!F{hr['ce']},C{br['ce']})"}
v.update({c: f"=({ISr('ebit', c)}+{ISr('oi', c)})/AVERAGE({PREV[c]}{br['ce']},{c}{br['ce']})" for c in FC})
bl("roce", "ROCE (EBIT + other income) / average capital employed", "%", v, fmt=F_PCT, bold=True)
assert all(ROW[S_BS][k] == PRE[S_BS][k] for k in PRE[S_BS]), "Balance_Sheet rows moved"


# ============================================================== Cash flow
C_ = ws_[S_CF]
fsheet(C_, S_CF, "Cash flow statement forecast (indirect method)")
BSr = lambda k, c: f"{S_BS}!{c}{br[k]}"  # noqa: E731
DSr = lambda k, c: f"{S_DS}!{c}{dsr[k]}"  # noqa: E731


def cl(key, label, values, fmt=F_CR, note="", bold=False, top=False):
    line(C_, S_CF, cr_[key], key, label, "Rs crore", values, fmt, note, bold, top)


section(C_, cr_["sec_cfo"], "Operating activities", 9)
cl("pat", "Profit after tax (incl. minority share)", {c: f"={ISr('pat', c)}" for c in FC})
cl("da", "+ Depreciation and amortisation", {c: f"={ISr('da', c)}" for c in FC})
cl("d_inv", "- Increase in inventories", {c: f"={BSr('inv', PREV[c])}-{BSr('inv', c)}" for c in FC})
cl("d_rec", "- Increase in trade receivables", {c: f"={BSr('rec', PREV[c])}-{BSr('rec', c)}" for c in FC})
cl("d_pay", "+ Increase in trade payables", {c: f"={BSr('pay', c)}-{BSr('pay', PREV[c])}" for c in FC})
v = {"C": f"={hist('cfo')}"}; v.update({c: f"=SUM({c}{cr_['pat']}:{c}{cr_['d_pay']})" for c in FC})
cl("cfo", "Cash flow from operations (CFO)", v, bold=True, top=True,
   note="FY2026A as reported (interest paid sits in financing); forecasts: PAT + D&A - change in working capital")
section(C_, cr_["sec_cfi"], "Investing activities", 9)
v = {"C": f"={hist('capex_cf')}"}; v.update({c: f"=-{BSr('capex', c)}" for c in FC})
cl("capex", "Capital expenditure", v, note="From the capex schedule on Balance_Sheet")
v = {"C": f"={hist('cfi')}"}; v.update({c: f"={c}{cr_['capex']}" for c in FC})
cl("cfi", "Cash flow from investing (CFI)", v, bold=True, top=True,
   note="Investments held flat, so capex is the only investing flow in the forecast")
section(C_, cr_["sec_cff"], "Financing activities", 9)
cl("new", "+ New term debt drawn", {c: f"={DSr('t_new', c)}" for c in FC})
cl("rep", "- Scheduled repayments", {c: f"=-{DSr('t_rep', c)}" for c in FC})
cl("rev", "+ Revolver drawn / (repaid)", {c: f"={DSr('r_draw', c)}" for c in FC})
cl("div", "- Dividends paid", {c: f"=-{BSr('oe_div', c)}" for c in FC})
v = {"C": f"={hist('cff')}"}; v.update({c: f"=SUM({c}{cr_['new']}:{c}{cr_['div']})" for c in FC})
cl("cff", "Cash flow from financing (CFF)", v, bold=True, top=True)
v = {c: f"={c}{cr_['cfo']}+{c}{cr_['cfi']}+{c}{cr_['cff']}" for c in ["C"] + FC}
cl("net", "Net change in cash", v, bold=True)
v = {"C": f"={hist('cf_open')}"}; v.update({c: f"={PREV[c]}{cr_['close']}" for c in FC})
cl("open", "Cash at start of year", v)
v = {"C": f"={hist('cf_other')}"}; v.update({c: 0 for c in FC})
cl("other", "Cash acquired and FX effects", v, note="Historical only; not forecast")
v = {c: f"={c}{cr_['open']}+{c}{cr_['net']}+{c}{cr_['other']}" for c in ["C"] + FC}
cl("close", "Cash at end of year", v, bold=True, top=True, note="Feeds the balance sheet")
v = {c: f"={c}{cr_['cfo']}+{c}{cr_['capex']}" for c in ["C"] + FC}
cl("fcf", "Free cash flow (CFO - capex)", v, bold=True,
   note="FY2026A on the reported basis (before interest); forecasts are after interest")
v = {c: f"={c}{cr_['open']}+{c}{cr_['cfo']}+{c}{cr_['cfi']}+{c}{cr_['new']}+{c}{cr_['rep']}+{c}{cr_['div']}"
     for c in FC}
cl("pre", "Memo: cash before revolver (used by the debt schedule)", v, note="No circularity: the revolver "
   "covers any shortfall below the minimum cash balance and is repaid from any surplus")
assert all(ROW[S_CF][k] == PRE[S_CF][k] for k in PRE[S_CF]), "Cash_Flow rows moved"


# ============================================================== Debt schedule
G_ = ws_[S_DS]
fsheet(G_, S_DS, "Debt schedule: term debt, revolver, interest and credit statistics")


def dl(key, label, values, fmt=F_CR, note="", bold=False, top=False, unit="Rs crore"):
    line(G_, S_DS, dsr[key], key, label, unit, values, fmt, note, bold, top)


section(G_, dsr["sec_term"], "Term debt (all borrowings outstanding at 31-Mar-2026, incl. short-term lines rolled over)", 9)
v = {"D": f"={BSr('l_debt', 'C')}"}; v.update({c: f"={PREV[c]}{dsr['t_close']}" for c in FC[1:]})
dl("t_open", "Term debt at start of year", v)
v = {"D": f"={drv('new_fy27')}"}; v.update({c: f"={drv('refi')}*{c}{dsr['t_rep']}" for c in FC[1:]})
dl("t_new", "+ New term debt drawn", v, note="FY27E: Rs 5,000 cr NCDs raised in Q2FY27; later: refinancing share x maturities")
rep = dict(zip(debt_df["fiscal_year"], debt_df["repayment_rs_crore"]))
dl("t_rep", "- Scheduled repayments", {c: float(rep[y.replace("E", "")]) for c, y in zip(FC, FY)},
   note="Integrated Report FY26 Note 17 (PDF p.509-512): FY28E USD 500m loan + SBI 2,000 + NCD 1,000; "
        "FY31E USD 400m bond")
v = {"C": f"={hist('agg_debt')}"}; v.update({c: f"={c}{dsr['t_open']}+{c}{dsr['t_new']}-{c}{dsr['t_rep']}" for c in FC})
dl("t_close", "Term debt at end of year", v, bold=True, top=True)
v = {c: f"={drv('rate_term')}*AVERAGE({c}{dsr['t_open']},{c}{dsr['t_close']})" for c in FC}
dl("t_int", "Interest on term debt (rate x average balance)", v,
   note="Draws and repayments are inputs, so the average balance creates no circularity")
section(G_, dsr["sec_rev"], "Revolving credit facility (cash sweep)", 9)
v = {"D": 0}; v.update({c: f"={PREV[c]}{dsr['r_close']}" for c in FC[1:]})
dl("r_open", "Revolver at start of year", v, note="No revolver drawn at 31-Mar-2026")
dl("pre", "Cash before revolver", {c: f"={S_CF}!{c}{cr_['pre']}" for c in FC})
dl("minc", "Minimum cash balance", {c: f"={drv('min_cash')}" for c in FC})
dl("r_draw", "Revolver drawn / (repaid)", {c: f"=MAX({c}{dsr['minc']}-{c}{dsr['pre']},-{c}{dsr['r_open']})" for c in FC},
   note="MAX(minimum cash - cash before revolver, -opening revolver): draws any shortfall, repays from surplus")
v = {"C": 0}; v.update({c: f"={c}{dsr['r_open']}+{c}{dsr['r_draw']}" for c in FC})
dl("r_close", "Revolver at end of year", v, bold=True, top=True)
dl("r_int", "Interest on revolver (rate x opening balance)", {c: f"={drv('rate_rev')}*{c}{dsr['r_open']}" for c in FC},
   note="Opening balance only, which avoids a circular reference")
section(G_, dsr["sec_tot"], "Totals", 9)
v = {"C": f"={hist('fin')}"}; v.update({c: f"={c}{dsr['t_int']}+{c}{dsr['r_int']}" for c in FC})
dl("fin_total", "Total finance costs (to the income statement)", v, bold=True)
dl("debt_total", "Total borrowings (to the balance sheet)",
   {c: f"={c}{dsr['t_close']}+{c}{dsr['r_close']}" for c in ["C"] + FC}, bold=True)
section(G_, dsr["sec_credit"], "Credit statistics", 9)
dl("nd", "Net debt", {c: f"={BSr('nd', c)}" for c in ["C"] + FC})
dl("nd_e", "Net debt / EBITDA", {c: f"={BSr('nd_e', c)}" for c in ["C"] + FC}, fmt=F_X, unit="x",
   note="Company aims to stay below 1x (Q4FY26 call p.5)")
dl("icov", "Interest cover (EBIT / finance costs)", {c: f"={ISr('ebit', c)}/{c}{dsr['fin_total']}" for c in ["C"] + FC},
   fmt=F_X, unit="x")
dl("ebitda_cov", "EBITDA / finance costs", {c: f"={ISr('ebitda', c)}/{c}{dsr['fin_total']}" for c in ["C"] + FC},
   fmt=F_X, unit="x")
dl("d_e", "Gross debt / total equity", {c: f"={c}{dsr['debt_total']}/{BSr('te', c)}" for c in ["C"] + FC},
   fmt=F_X, unit="x")
assert all(ROW[S_DS][k] == PRE[S_DS][k] for k in PRE[S_DS]), "Debt_Schedule rows moved"


# ============================================================== Cover (selector, key outputs, scenario engine)
CV = ws_["Cover"]
cvr = ROW["Cover"]
title(CV, "UltraTech Cement Ltd (NSE: ULTRACEMCO): three-statement model with Base / Bull / Bear scenarios",
      "Consolidated, Rs crore unless stated. Fiscal year ends 31 March. History FY2022-FY2026 (audited), "
      "forecast FY2027E-FY2031E. Market data as of the 30-Oct-2026 close. Built 1-Nov-2026.")
cell(CV, "A4", "Purpose: link the income statement, balance sheet and cash flow so that one set of operating "
               "drivers (capacity, utilisation, price and cost per tonne, capex, working capital, debt terms) "
               "produces all three statements, with a balance check and three scenarios. Educational model, "
               "not investment advice.", wrap=True)
CV.merge_cells("A4:I4")
CV.row_dimensions[4].height = 48
cell(CV, "A6", "Scenario selector: type 1 = Base, 2 = Bull, 3 = Bear", bold=True)
cell(CV, "C6", 1, color=BLUE, fill=YELLOW, bold=True)
cell(CV, "D6", '=CHOOSE(C6,"Base","Bull","Bear")', bold=True)
dv = DataValidation(type="list", formula1='"1,2,3"', allow_blank=False, showErrorMessage=True,
                    errorTitle="Scenario", error="Enter 1 (Base), 2 (Bull) or 3 (Bear)")
CV.add_data_validation(dv)
dv.add("C6")
cell(CV, "A7", "Model checks (Checks sheet): all must say PASS", bold=True)
cvr["sel"], cvr["status"] = 6, 7
KEY = [("vol", "Sales volume", "MnT", S_IS, "vol", F_CR1), ("rev", "Revenue from operations", "Rs crore", S_IS, "rev", F_CR),
       ("ebitda", "EBITDA", "Rs crore", S_IS, "ebitda", F_CR), ("ebitda_t", "EBITDA per tonne", "Rs/t", S_IS, "ebitda_t", F_RS),
       ("own", "Profit attributable to owners", "Rs crore", S_IS, "own", F_CR), ("eps", "EPS", "Rs", S_IS, "eps", F_EPS),
       ("capex", "Capex", "Rs crore", S_BS, "capex", F_CR), ("fcf", "Free cash flow (CFO - capex)", "Rs crore", S_CF, "fcf", F_CR),
       ("nd", "Net debt", "Rs crore", S_BS, "nd", F_CR), ("nd_e", "Net debt / EBITDA", "x", S_BS, "nd_e", F_X),
       ("roce", "ROCE", "%", S_BS, "roce", F_PCT)]
header(CV, 9, ["Key outputs for the selected scenario", "Unit", "FY2026A"] + FY + [""])
r = 10
for key, lab, unit, sh, k, fmt in KEY:
    line(CV, "Cover", r, "k_" + key, lab, unit, {c: f"={sh}!{c}{ROW[sh][k]}" for c in ["C"] + FC}, fmt)
    r += 1
cvr["key_first"], cvr["key_last"] = 10, r - 1
r += 1
cell(CV, f"A{r}", "How to use", bold=True); r += 1
for txt in ["1. Pick a scenario in cell C6 (1 = Base, 2 = Bull, 3 = Bear). Every sheet recalculates.",
            "2. Change assumptions only on the Drivers sheet (blue cells). Yellow cells are judgment calls; the reason "
            "is written next to each one.",
            "3. Confirm cell C7 says PASS. The Checks sheet lists every test (balance sheet balances, cash ties, "
            "roll-forwards, no errors).",
            "4. Scenario_Summary shows Base, Bull and Bear side by side. It reads the Excel data table at the bottom of "
            "this sheet, which recalculates the model for each scenario.",
            "5. Historical holds the audited FY2022-FY2026 statements with page references; the FY2026A column of "
            "each forecast sheet links to it.",
            "6. Rebuild from scratch: python build/04_build_model.py, then python build/05_verify_model.py "
            "(needs Excel; it creates the data table and runs all checks in all three scenarios)."]:
    cell(CV, f"A{r}", txt); r += 1
r += 1
cell(CV, f"A{r}", "Sheet map", bold=True); r += 1
for name, txt in [("Historical", "Reported IS, BS and CFS FY2022-FY2026, aggregated to model lines, with checks"),
                  ("Drivers", "Base / Bull / Bear inputs, selected via CHOOSE; macro inputs; company guidance"),
                  ("Income_Statement", "Capacity -> volume -> price and cost per tonne -> EBITDA -> PAT -> EPS"),
                  ("Balance_Sheet", "Capex, CWIP and fixed-asset roll-forward, working capital, balance sheet, equity"),
                  ("Cash_Flow", "Indirect cash flow; closing cash feeds the balance sheet"),
                  ("Debt_Schedule", "Term debt maturities, refinancing, revolver (cash sweep), interest, credit stats"),
                  ("Scenario_Summary", "Base, Bull and Bear side by side, FY2027E-FY2031E (live data table)"),
                  ("Checks", "PASS / FAIL tests that must hold in every scenario")]:
    cell(CV, f"A{r}", name, bold=True)
    cell(CV, f"B{r}", txt)
    r += 1
r += 2
METRICS = [("rev", "Revenue from operations", "Rs crore", S_IS, "rev", F_CR),
           ("ebitda", "EBITDA", "Rs crore", S_IS, "ebitda", F_CR),
           ("ebitda_t", "EBITDA per tonne", "Rs/t", S_IS, "ebitda_t", F_RS),
           ("own", "Profit attributable to owners (PAT)", "Rs crore", S_IS, "own", F_CR),
           ("eps", "EPS", "Rs", S_IS, "eps", F_EPS),
           ("fcf", "Free cash flow (CFO - capex)", "Rs crore", S_CF, "fcf", F_CR),
           ("nd", "Net debt", "Rs crore", S_BS, "nd", F_CR),
           ("nd_e", "Net debt / EBITDA", "x", S_BS, "nd_e", F_X),
           ("roce", "ROCE", "%", S_BS, "roce", F_PCT)]
section(CV, r, "Scenario engine: Excel data table (Data > What-If Analysis > Data Table, row input cell C6). "
               "Created by build/05_verify_model.py. Do not type over it.", 9)
r += 1
header(CV, r, ["Metric | year", "Live (selected)", "Base (1)", "Bull (2)", "Bear (3)"])
r += 1
cvr["dt_top"] = r
for col, val in zip(["C", "D", "E"], [1, 2, 3]):
    cell(CV, f"{col}{r}", val, color=BLUE, bold=True)
r += 1
cvr["dt_first"] = r
ENGINE = {}
for key, lab, unit, sh, k, fmt in METRICS:
    for c, y in zip(FC, FY):
        ENGINE[(key, y)] = r
        cell(CV, f"A{r}", f"{lab} | {y}")
        cell(CV, f"B{r}", f"={sh}!{c}{ROW[sh][k]}", fmt=fmt)
        for col in ["C", "D", "E"]:
            CV[f"{col}{r}"].number_format = fmt
        r += 1
cvr["dt_last"] = r - 1
widths(CV, {"A": 58, "B": 16, "C": 12, "D": 12, "E": 12, "F": 12, "G": 12, "H": 12, "I": 12})

# ============================================================== Scenario_Summary
SS = ws_["Scenario_Summary"]
title(SS, "Scenario summary: Base, Bull and Bear side by side, FY2027E-FY2031E",
      "Live values from the Excel data table on the Cover sheet (rows "
      f"{cvr['dt_first']}-{cvr['dt_last']}), which recalculates the whole model for scenario 1, 2 and 3.")
header(SS, 4, ["Metric", "Unit", "Case"] + FY + ["Notes"])
r = 5
ssr = ROW["Scenario_Summary"]
for key, lab, unit, sh, k, fmt in METRICS:
    for case, col in [("Base", "C"), ("Bull", "D"), ("Bear", "E")]:
        ssr[f"{key}_{case}"] = r
        cell(SS, f"A{r}", lab if case == "Base" else "", bold=(case == "Base"))
        cell(SS, f"B{r}", unit, color="404040")
        cell(SS, f"C{r}", case)
        for c, y in zip(FC, FY):
            cell(SS, f"{c}{r}", f"=Cover!{col}{ENGINE[(key, y)]}", color=GREEN, fmt=fmt)
        r += 1
    r += 1
cell(SS, f"A{r}", "What drives the differences", bold=True); r += 1
for txt in ["Bull: higher utilisation (83-85%), faster price growth, lower fuel inflation, 15 MTPA a year of new "
            "capacity after FY28E at a lower cost per MTPA.",
            "Bear: utilisation falls to 75-77%, prices grow 1.5% a year, a longer fuel shock in FY27E, 7 MTPA of "
            "the FY28E plan delayed and a 10% capex overrun.",
            "Financing policy (refinancing share, payout, minimum cash) is the same in all three cases, so differences "
            "in net debt come from operations and capex."]:
    cell(SS, f"A{r}", txt); r += 1
widths(SS, {"A": 40, "B": 10, "C": 9, "D": 12, "E": 12, "F": 12, "G": 12, "H": 12, "I": 40})
SS.freeze_panes = "D5"


# ============================================================== Checks
from openpyxl.formatting.rule import CellIsRule  # noqa: E402
from openpyxl.worksheet.formula import ArrayFormula  # noqa: E402

K = ws_["Checks"]
title(K, "Checks: every test must say PASS in all three scenarios")
cell(K, "A3", "Overall status", bold=True)
header(K, 5, ["#", "Check", "Max abs difference or count", "Tolerance", "Result", "What it tests"])
X = lambda sh, key, c1="D", c2="H": f"{sh}!{c1}{ROW[sh][key]}:{c2}{ROW[sh][key]}"  # noqa: E731
mx = lambda expr: f"SUMPRODUCT(MAX(ABS({expr})))"  # noqa: E731
hx = lambda key: f"Historical!C{hr[key]}:G{hr[key]}"  # noqa: E731
eng = f"Cover!B{cvr['dt_first']}:B{cvr['dt_last']}"
engC = lambda col: f"Cover!{col}{cvr['dt_first']}:{col}{cvr['dt_last']}"  # noqa: E731
CHECKS = [
    ("Historical balance sheets balance and tie to reported total assets (FY2022-FY2026)", mx(hx("bs_chk")), 0.5,
     "Transcription of the audited statements"),
    ("Historical P&L subtotals tie to reported total expenses, PBT and owners' profit", mx(hx("is_chk")), 0.5,
     "Transcription of the audited statements"),
    ("Historical cash flow: closing cash ties to reported and to balance-sheet cash", mx(hx("cf_chk")), 0.5,
     "Transcription of the audited statements"),
    ("Forecast balance sheet balances every year: |assets - equity - liabilities| < 0.5",
     mx(X(S_BS, "bal", "C")), 0.5, "The three statements are fully linked"),
    ("Cash-flow closing cash = balance-sheet cash every year",
     mx(f"{X(S_CF, 'close', 'C')}-{X(S_BS, 'a_cash', 'C')}"), 0.5, "Cash flow drives the balance sheet"),
    ("Other equity roll-forward: closing = opening + profit to owners - dividends",
     mx(f"{X(S_BS, 'e_oe')}-{X(S_BS, 'e_oe', 'C', 'G')}-{X(S_IS, 'own')}+{X(S_BS, 'oe_div')}"), 0.5,
     "Retained earnings tie to the income statement and dividends"),
    ("Minority interest roll-forward: closing = opening + minority share of profit",
     mx(f"{X(S_BS, 'e_nci')}-{X(S_BS, 'e_nci', 'C', 'G')}-{X(S_IS, 'nci')}"), 0.5, "Equity roll-forward"),
    ("Fixed assets and CWIP roll-forwards tie (opening + additions - D&A / capitalisation = closing)",
     mx(f"{X(S_BS, 'nfa_close')}-{X(S_BS, 'nfa_close', 'C', 'G')}-{X(S_BS, 'capz')}+{X(S_IS, 'da')}") + "+" +
     mx(f"{X(S_BS, 'cwip_close')}-{X(S_BS, 'cwip_close', 'C', 'G')}-{X(S_BS, 'capex')}+{X(S_BS, 'capz')}"), 0.5,
     "Capex flows through CWIP into fixed assets"),
    ("No negative capitalisation or CWIP (count of cells)",
     f"SUMPRODUCT(--({X(S_BS, 'capz')}<0))+SUMPRODUCT(--({X(S_BS, 'cwip_close')}<0))", 0.5, "Sensible capex timing"),
    ("Cash never falls below the minimum balance (count of years)",
     f"SUMPRODUCT(--({X(S_BS, 'a_cash')}<Drivers!$F${dr['min_cash']}-0.5))", 0.5, "Revolver logic works"),
    ("Debt is never negative: term debt and revolver (count of years)",
     f"SUMPRODUCT(--({X(S_DS, 't_close')}<-0.001))+SUMPRODUCT(--({X(S_DS, 'r_close')}<-0.001))", 0.5, "Debt >= 0"),
    ("Revolver is repaid before surplus cash builds up (count of years with both)",
     f"SUMPRODUCT(({X(S_DS, 'r_close')}>0.5)*({X(S_BS, 'a_cash')}>Drivers!$F${dr['min_cash']}+0.5))", 0.5,
     "Cash sweep logic"),
    ("Borrowings and finance costs equal the debt schedule",
     mx(f"{X(S_BS, 'l_debt')}-{X(S_DS, 'debt_total')}") + "+" + mx(f"{X(S_IS, 'fin')}-{X(S_DS, 'fin_total')}"), 0.5,
     "Debt schedule feeds the BS and the IS"),
    ("Sum checks: cost buckets add to total costs; revenue = net sales + other operating income",
     mx(f"{X(S_IS, 'opex', 'C')}-{X(S_IS, 'rm', 'C')}-{X(S_IS, 'pf', 'C')}-{X(S_IS, 'fr', 'C')}-{X(S_IS, 'emp', 'C')}"
        f"-{X(S_IS, 'oth', 'C')}") + "+" + mx(f"{X(S_IS, 'rev', 'C')}-{X(S_IS, 'ns', 'C')}-{X(S_IS, 'ooi', 'C')}"),
     0.5, "Totals reconcile"),
    ("Sum checks: net change in cash = CFO + CFI + CFF = closing - opening - other",
     mx(f"{X(S_CF, 'net', 'C')}-{X(S_CF, 'cfo', 'C')}-{X(S_CF, 'cfi', 'C')}-{X(S_CF, 'cff', 'C')}") + "+" +
     mx(f"{X(S_CF, 'close', 'C')}-{X(S_CF, 'open', 'C')}-{X(S_CF, 'net', 'C')}-{X(S_CF, 'other', 'C')}"), 0.5,
     "Cash-flow arithmetic"),
    ("Volume never exceeds capacity (count of years with utilisation above 100%)",
     f"SUMPRODUCT(--({X(S_IS, 'util')}>1))", 0.5, "Physical limit"),
    ("FY2026A column equals the reported figures (revenue, PBT, PAT, total assets)",
     f"ABS({S_IS}!C{ir['rev']}-Historical!G{hr['rev']})+ABS({S_IS}!C{ir['pbt']}-Historical!G{hr['pbt_rep']})"
     f"+ABS({S_IS}!C{ir['pat']}-Historical!G{hr['pat']})+ABS({S_BS}!C{br['ta']}-Historical!G{hr['ta_rep']})", 0.5,
     "Forecast starts from the audited base year"),
    ("Scenario data table matches the live model for the selected scenario",
     f"SUMPRODUCT(ABS(CHOOSE(Scenario,{engC('C')},{engC('D')},{engC('E')})-{eng}))", 0.5,
     "Scenario_Summary is live and consistent"),
    ("No error values (#REF!, #DIV/0!, #VALUE!, #NAME?, #N/A) on any sheet (count)",
     "+".join(f"SUMPRODUCT(--ISERROR({rng}))" for rng in [
         "Historical!A1:H200", "Drivers!A1:I140", f"{S_IS}!A1:I60", f"{S_BS}!A1:I70", f"{S_CF}!A1:I40",
         f"{S_DS}!A1:I40", "Scenario_Summary!A1:I60", f"Cover!A{cvr['key_first']}:H{cvr['key_last']}",
         f"Cover!A{cvr['dt_top']}:E{cvr['dt_last']}"]), 0.5, "Clean workbook"),
]
r = 6
for n, (lab, f, tol, what) in enumerate(CHECKS, 1):
    ROW["Checks"][f"c{n}"] = r
    cell(K, f"A{r}", n)
    cell(K, f"B{r}", lab)
    # array (Ctrl+Shift+Enter) formulas: Excel otherwise applies implicit intersection to ranges inside MAX/ABS
    K[f"C{r}"] = ArrayFormula(f"C{r}", "=" + f)
    K[f"C{r}"].number_format = "#,##0.000"
    cell(K, f"D{r}", tol, color=BLUE, fmt="0.0")
    cell(K, f"E{r}", f'=IF(ISNUMBER(C{r}),IF(ABS(C{r})<D{r},"PASS","FAIL"),"FAIL")', bold=True)
    cell(K, f"F{r}", what, color="404040", italic=True)
    r += 1
ROW["Checks"]["first"], ROW["Checks"]["last"] = 6, r - 1
cell(K, "C3", f'=IF(COUNTIF(E6:E{r - 1},"PASS")={len(CHECKS)},"PASS","FAIL")', bold=True)
cell(K, "D3", f'=COUNTIF(E6:E{r - 1},"PASS")&" of {len(CHECKS)} checks pass"', italic=True)
ROW["Checks"]["overall"] = 3
cell(CV, "C7", "=Checks!C3", bold=True)
green, red = PatternFill("solid", fgColor="C6EFCE"), PatternFill("solid", fgColor="FFC7CE")
for ws, rng in [(K, f"E6:E{r - 1}"), (K, "C3"), (CV, "C7")]:
    ws.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=['"PASS"'], fill=green))
    ws.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=['"FAIL"'], fill=red))
widths(K, {"A": 5, "B": 92, "C": 16, "D": 11, "E": 10, "F": 48})
K.freeze_panes = "A6"


# ============================================================== names, calc settings, save
from openpyxl.workbook.defined_name import DefinedName  # noqa: E402

dn = DefinedName("Scenario", attr_text="Cover!$C$6")
try:
    wb.defined_names["Scenario"] = dn  # openpyxl >= 3.1
except TypeError:
    wb.defined_names.append(dn)  # older openpyxl
wb.calculation.fullCalcOnLoad = True
wb.calculation.calcMode = "auto"
for name in SHEETS:
    ws_[name].sheet_view.zoomScale = 90
ws_["Cover"].sheet_properties.tabColor = "1F3864"
ws_["Checks"].sheet_properties.tabColor = "70AD47"
wb.active = 0
wb.save(OUT)
model_map = {"rows": ROW, "engine": {f"{k}|{y}": v for (k, y), v in ENGINE.items()}, "cover": cvr,
             "forecast_cols": dict(zip(FY, FC)), "metrics": [m[:3] for m in METRICS],
             "scenario_cell": "C6", "datatable": f"B{cvr['dt_top']}:E{cvr['dt_last']}"}
MAP_OUT.write_text(json.dumps(model_map, indent=1), encoding="utf-8")
n_formulas = sum(1 for ws in wb.worksheets for row in ws.iter_rows() for c in row
                 if isinstance(c.value, str) and c.value.startswith("="))
print(f"saved {OUT.name}: {len(wb.sheetnames)} sheets, {n_formulas} formulas; data table range "
      f"{model_map['datatable']}")
print("EXIT_OK")
