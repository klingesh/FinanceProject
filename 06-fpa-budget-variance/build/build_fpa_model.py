"""Build Vriddhi_Foods_FPA_FY2027.xlsx: a driver-based FP&A model with live formulas.

Vriddhi Foods Pvt. Ltd. is a fictional company. All inputs come from inputs.py.
Every calculated cell in the workbook is an Excel formula that refers back to
input cells, so changing a driver updates the budget, actuals, forecast,
variances, bridges, dashboard, commentary and checks.

Run:  python build/build_fpa_model.py
Then: python build/recalc_verify.py   (Excel recalculation + verification)
"""
from __future__ import annotations

import csv
import datetime as dt
import math
import os
import re

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.chart.data_source import NumFmt
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

import inputs as I
from xlhelpers import (BLUE, FAIL_FILL, FMT_CR, FMT_CR2, FMT_DATE, FMT_DAY, FMT_HC, FMT_PCT, FMT_PCT2, FMT_PP,
                       FMT_RS, FMT_SCI, FMT_T, FMT_T1, HDR_FILL, PASS_FILL, TOT_FILL, TOP_BORDER, YELLOW, bold_row,
                       col, header_row, put, section, title, widths)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "Vriddhi_Foods_FPA_FY2027.xlsx")
DATA = os.path.join(ROOT, "data")

LK = [k for k, _ in I.LINES]
LN = dict(I.LINES)
CK = [k for k, _ in I.CHANNELS]
CN = dict(I.CHANNELS)
RK = [k for k, _ in I.RMS]
RN = dict(I.RMS)
FK = [k for k, _ in I.FUNCS]
FN = dict(I.FUNCS)
MC = [col(4 + i) for i in range(12)]  # D..O = Apr-26..Mar-27
AC = MC[:6]                           # D..I = Apr..Sep
HC_ = MC[6:]                          # J..O = Oct..Mar
ASM, SB, SA, SF = "Assumptions_Budget", "Budget_PL", "Actuals_H1", "Forecast_6plus6"
CASE_CELL = "Cover!$D$10"
TOL = 1e-9
MIXCOL = {"GT": "D", "MT": "E", "EQC": "F"}
BOMCOL = {"OIL": "D", "WHT": "E", "SUG": "F", "POT": "G", "FRP": "H"}
FC_FILL = PatternFill("solid", fgColor="FCE4D6")
SHORT = {"NAM": "Namkeen", "BIS": "Biscuits", "BEV": "Beverages"}

CHECKS: list = []  # (area, description, value formula, tolerance)


def add_check(area, desc, formula, tol=TOL):
    CHECKS.append((area, desc, formula, tol))


# ---------------------------------------------------------------------------
# Generic row writer
# ---------------------------------------------------------------------------
def mrow(ws, r, label, unit, values, kind="input", fmt=None, yellow=False, reason=None, agg=None,
         cols=MC, code=None, aggcol="P", reasoncol="Q", bold=False):
    if code:
        put(ws, f"A{r}", code, "note", size=8)
    put(ws, f"B{r}", label, "text", bold=bold)
    if unit:
        put(ws, f"C{r}", unit, "note")
    for c, v in zip(cols, values):
        if v is None:
            continue
        put(ws, f"{c}{r}", v, kind, fmt, yellow=yellow, bold=bold)
    if agg == "sum":
        put(ws, f"{aggcol}{r}", f"=SUM({cols[0]}{r}:{cols[-1]}{r})", "calc", fmt, bold=bold)
    elif agg == "avg":
        put(ws, f"{aggcol}{r}", f"=AVERAGE({cols[0]}{r}:{cols[-1]}{r})", "calc", fmt)
    if reason:
        put(ws, f"{reasoncol}{r}", reason, "note", italic=True)


def sub(ws, r, text, last_col=18):
    put(ws, f"B{r}", text, "text", bold=True, italic=True)


# ---------------------------------------------------------------------------
# 2. Assumptions_Budget
# ---------------------------------------------------------------------------
def build_assumptions(ws) -> dict:
    B = I.BUDGET
    A = {}
    title(ws, "Assumptions_Budget: FY2027 budget drivers",
          f"{I.COMPANY} (fictional company). Budget approved Feb-2026. Blue font = input; yellow fill = judgment "
          "assumption, reason in the next column; black = formula.",
          "Fiscal months Apr-2026 to Mar-2027. Volumes in tonnes (beverages: 1 kL counted as 1 t). Prices and unit costs "
          "in ₹ per kg of finished product. Money in ₹ crore.")
    hdr = {"A": "Ref", "B": "Driver", "C": "Unit"}
    hdr.update({c: I.MONTHS[i] for i, c in enumerate(MC)})
    hdr.update({"P": "FY / check", "Q": "Basis / reason"})
    header_row(ws, 4, hdr)
    for c in MC:
        ws[f"{c}4"].number_format = FMT_DATE
        ws[f"{c}4"].font = Font(bold=True, color=BLUE, size=10)
    r = 6
    section(ws, r, "1. General", 1, 17)
    r += 1
    A["tax"] = r
    mrow(ws, r, "Corporate tax rate (s.115BAA; s.200 of the Income-tax Act 2025)", "%", [I.TAX_RATE], fmt=FMT_PCT2,
         cols=["D"])
    put(ws, f"E{r}", "22% base + 10% surcharge + 4% cess = 25.168%", "note", italic=True)
    r += 1
    A["conv"] = r
    mrow(ws, r, "Unit conversion: tonnes × ₹/kg to ₹ crore", "factor", [I.CONV], fmt="0.0000", cols=["D"])
    put(ws, f"E{r}", "1,000 kg per tonne ÷ 1,00,00,000 ₹ per crore", "note", italic=True)
    r += 1
    A["status"] = r
    mrow(ws, r, "Status date", "date", [I.STATUS_DATE], fmt=FMT_DAY, cols=["D"])
    put(ws, f"E{r}", "Apr-Sep 2026 closed (actuals); Oct-2026 to Mar-2027 forecast", "note", italic=True)
    r += 1
    A["nclosed"] = r
    mrow(ws, r, "Months of actuals closed", "months", [I.N_ACT], fmt=FMT_INT_SAFE, cols=["D"])
    r += 2

    section(ws, r, "2. Volume", 1, 17)
    r += 1
    for l in LK:
        A[f"fyvol_{l}"] = r
        mrow(ws, r, f"FY volume: {LN[l]}", "t", [B["fy_volume"][l]], fmt=FMT_T, yellow=True, cols=["D"])
        put(ws, f"E{r}", B["fy_volume_reason"][l], "note", italic=True)
        r += 1
    r += 1
    for l in LK:
        A[f"seas_{l}"] = r
        mrow(ws, r, f"Seasonality: {LN[l]}", "% of FY", B["seasonality"][l], fmt=FMT_PCT, yellow=True,
             agg="sum", reason=B["seasonality_reason"][l])
        r += 1
    for l in LK:
        A[f"mvol_{l}"] = r
        vals = [f"=$D${A[f'fyvol_{l}']}*{c}{A[f'seas_{l}']}" for c in MC]
        mrow(ws, r, f"Monthly volume: {LN[l]}", "t", vals, kind="calc", fmt=FMT_T, agg="sum")
        r += 1
    r += 1
    header_row(ws, r, {"B": "Channel mix (share of line volume)", "D": "GT", "E": "MT", "F": "E-com & QC",
                       "G": "Total", "H": "Reason"})
    r += 1
    for l in LK:
        A[f"mix_{l}"] = r
        mix = B["channel_mix"][l]
        mrow(ws, r, LN[l], "% of volume", [mix["GT"], mix["MT"], mix["EQC"]], fmt=FMT_PCT, yellow=True,
             cols=["D", "E", "F"])
        put(ws, f"G{r}", f"=SUM(D{r}:F{r})", "calc", FMT_PCT)
        put(ws, f"H{r}", B["channel_mix_reason"][l], "note", italic=True)
        r += 1
    r += 1

    section(ws, r, "3. Price and trade terms", 1, 17)
    r += 1
    for l in LK:
        A[f"price_{l}"] = r
        mrow(ws, r, f"List price to trade (ex-GST): {LN[l]}", "₹/kg", [B["list_price"][l]] * 12, fmt=FMT_RS,
             yellow=True, agg="avg", reason=B["list_price_reason"][l])
        r += 1
    for ch in CK:
        A[f"ts_{ch}"] = r
        mrow(ws, r, f"Trade spend: {CN[ch]}", "% of gross sales", B["trade_spend"][ch], fmt=FMT_PCT, yellow=True,
             agg="avg", reason=B["trade_spend_reason"][ch])
        r += 1
    r += 1

    section(ws, r, "4. Materials and conversion", 1, 17)
    r += 1
    for rk in RK:
        A[f"rm_{rk}"] = r
        mrow(ws, r, f"Raw material price: {RN[rk]}", "₹/kg", B["rm_price"][rk], fmt=FMT_RS, yellow=True,
             agg="avg", reason=B["rm_price_reason"][rk])
        r += 1
    r += 1
    header_row(ws, r, {"B": "Standard bill of materials (kg of input per kg of finished product)",
                       **{BOMCOL[rk]: RN[rk] for rk in RK}, "I": "Notes"})
    r += 1
    bom_note = {"NAM": "Chips need about 3.5 kg potato per kg; namkeen is gram-flour based (in other ingredients)",
                "BIS": "Palm-based bakery fat counted as edible oil",
                "BEV": "Nectars at about 22% fruit content"}
    for l in LK:
        A[f"bom_{l}"] = r
        mrow(ws, r, LN[l], "kg/kg", [B["bom"][l][rk] for rk in RK], fmt="0.00", cols=[BOMCOL[rk] for rk in RK])
        put(ws, f"I{r}", bom_note[l], "note", italic=True)
        r += 1
    r += 1
    header_row(ws, r, {"B": "Other unit costs (₹ per kg of finished product)", "D": "Other ingredients",
                       "E": "Packaging", "F": "Conversion", "G": "Reason"})
    r += 1
    cost_note = {"NAM": "Spices, gram flour, salt; laminates; fryer lines are power-intensive",
                 "BIS": "Milk solids, invert syrup; wrappers and cartons; oven lines",
                 "BEV": "Flavours, acids; aseptic cartons and PET; filling lines"}
    for l in LK:
        A[f"cost_{l}"] = r
        mrow(ws, r, LN[l], "₹/kg", [B["other_ingr"][l], B["packaging"][l], B["conversion"][l]], fmt=FMT_RS,
             yellow=True, cols=["D", "E", "F"])
        put(ws, f"G{r}", cost_note[l], "note", italic=True)
        r += 1
    r += 1
    for l in LK:
        A[f"matkg_{l}"] = r
        vals = []
        for c in MC:
            terms = [f"$" + BOMCOL[rk] + f"${A[f'bom_{l}']}*{c}${A[f'rm_{rk}']}" for rk in RK]
            vals.append("=" + "+".join(terms) + f"+$D${A[f'cost_{l}']}")
        mrow(ws, r, f"Standard material cost: {LN[l]}", "₹/kg", vals, kind="calc", fmt=FMT_RS, agg="avg",
             reason="BOM × raw material prices + other ingredients")
        r += 1
    r += 1

    section(ws, r, "5. Operating costs, payroll and finance", 1, 17)
    r += 1
    A["freight"] = r
    mrow(ws, r, "Freight & distribution", "% of net revenue", [B["freight_pct"]], fmt=FMT_PCT, yellow=True, cols=["D"])
    put(ws, f"E{r}", B["freight_reason"], "note", italic=True)
    r += 1
    A["ap"] = r
    mrow(ws, r, "Advertising & promotion (A&P) budget", "₹ cr", B["ap"], fmt=FMT_CR2, yellow=True, agg="sum",
         reason=B["ap_reason"])
    r += 1
    for f in FK:
        A[f"hc_{f}"] = r
        mrow(ws, r, f"Headcount: {FN[f]}", "heads", B["headcount"][f], fmt=FMT_HC, agg="avg",
             reason="Hiring plan" if f != "FAC" else "Second shift for the new cookie line from Oct-26")
        r += 1
    header_row(ws, r, {"B": "Payroll rates", "D": "CTC ₹ lakh/head/yr", "E": "Increment %", "F": "Reason"})
    r += 1
    for f in FK:
        A[f"ctc_{f}"] = r
        mrow(ws, r, FN[f], "₹ lakh, %", [B["ctc"][f], B["increment"][f]], fmt="0.00", yellow=True, cols=["D", "E"])
        ws[f"E{r}"].number_format = FMT_PCT
        put(ws, f"F{r}", "Cost to company before increment; increments of 8-10% vs 8.6% for FMCG and 9.1% for "
                         "India in 2026 (Moneycontrol, Aon)", "note", italic=True)
        r += 1
    A["incdate"] = r
    mrow(ws, r, "Annual increment effective from", "date", [B["increment_date"]], fmt=FMT_DAY, yellow=True, cols=["D"])
    put(ws, f"E{r}", B["increment_reason"], "note", italic=True)
    r += 1
    A["oth"] = r
    mrow(ws, r, "Other overheads", "₹ cr", B["other_oh"], fmt=FMT_CR2, agg="sum",
         reason="Rent, IT, travel, insurance, professional fees")
    r += 1
    A["da"] = r
    mrow(ws, r, "Depreciation & amortisation", "₹ cr", B["da"], fmt=FMT_CR2, agg="sum",
         reason="Step-up when the new cookie line is capitalised in Oct-26")
    r += 1
    A["borr"] = r
    mrow(ws, r, "Average borrowings", "₹ cr", B["borrowings"], fmt=FMT_CR, agg="avg",
         reason="Working-capital build before the festive season")
    r += 1
    A["rate"] = r
    mrow(ws, r, "Interest rate on borrowings", "% p.a.", B["int_rate"], fmt=FMT_PCT2, yellow=True, agg="avg",
         reason="Blended term-loan and working-capital rate at Feb-2026")
    r += 2
    r = build_benchmarks(ws, r, A)
    widths(ws, {"A": 6, "B": 46, "C": 15, **{c: 10.5 for c in MC}, "P": 11, "Q": 60})
    ws.freeze_panes = "D5"
    add_check("Inputs", "Budget seasonality sums to 100% for each product line",
              "=" + "+".join(f"ABS({ASM}!P{A[f'seas_{l}']}-1)" for l in LK))
    add_check("Inputs", "Budget channel mix sums to 100% for each product line",
              "=" + "+".join(f"ABS({ASM}!G{A[f'mix_{l}']}-1)" for l in LK))
    add_check("Inputs", "Budget monthly volumes add up to the FY volume input",
              "=" + "+".join(f"ABS({ASM}!P{A[f'mvol_{l}']}-{ASM}!D{A[f'fyvol_{l}']})" for l in LK))
    return A


FMT_INT_SAFE = "0"


def build_benchmarks(ws, r, A) -> int:
    """Section 6 of Assumptions_Budget: listed-peer benchmarks (inputs) next to Vriddhi's budget and forecast."""
    path = os.path.join(DATA, "peer_benchmarks.csv")
    with open(path, encoding="utf-8") as fh:
        peers = list(csv.DictReader(fh))
    latest_fy = max(p["fiscal_year"] for p in peers)
    section(ws, r, "6. Real-world benchmarks: listed Indian packaged-food companies, latest full year (Screener.in, "
                   "downloaded Nov-2026; files in source_data/screener/)", 1, 17)
    A["bench_section"] = r
    r += 1
    header_row(ws, r, {"B": "Company", "C": "Fiscal year", "D": "Revenue (₹ cr)", "E": "Revenue growth",
                       "F": "Material cost % of sales", "G": "Employee cost % of sales",
                       "H": "Operating margin (≈ EBITDA)", "I": "Net profit margin", "J": "Latest quarter",
                       "K": "Latest quarter growth (YoY)", "L": "Latest quarter operating margin",
                       "M": "Segment and source file"})
    ws.row_dimensions[r].height = 42
    r += 1
    first = r
    cur_rows = []

    def num(v, pct=True):
        if v in ("", None):
            return None
        x = float(v)
        return x / 100 if pct else x

    for p in peers:
        is_cur = p["fiscal_year"] == latest_fy
        if is_cur:
            cur_rows.append(r)
        put(ws, f"B{r}", p["company"], "text")
        put(ws, f"C{r}", p["fiscal_year"], "input")
        vals = [("D", num(p["revenue_rs_cr"], False), "#,##0"), ("E", num(p["revenue_growth_pct"]), FMT_PCT),
                ("F", num(p["material_cost_pct"]), FMT_PCT), ("G", num(p["employee_cost_pct"]), FMT_PCT),
                ("H", num(p["opm_pct"]), FMT_PCT), ("I", num(p["net_margin_pct"]), FMT_PCT),
                ("K", num(p["latest_q_growth_pct"]), FMT_PCT), ("L", num(p["latest_q_opm_pct"]), FMT_PCT)]
        for cc, v, fmt in vals:
            if v is None:
                put(ws, f"{cc}{r}", "n/a", "note", align="right")
            else:
                put(ws, f"{cc}{r}", v, "input", fmt)
        put(ws, f"J{r}", p["latest_quarter"], "input", align="right")
        note = p["segment"] + " | " + p["source_file"] + ("" if is_cur else " | excluded from the median")
        put(ws, f"M{r}", note, "note", italic=True)
        r += 1
    last = r - 1
    A["bench_median"] = r
    put(ws, f"B{r}", f"Median of current peers ({latest_fy})", "text", bold=True)
    for cc, fmt in (("E", FMT_PCT), ("F", FMT_PCT), ("G", FMT_PCT), ("H", FMT_PCT), ("I", FMT_PCT),
                    ("K", FMT_PCT), ("L", FMT_PCT)):
        refs = ",".join(f"{cc}{x}" for x in cur_rows)
        put(ws, f"{cc}{r}", f"=MEDIAN({refs})", "calc", fmt, bold=True, fill=TOT_FILL)
    r += 1
    for key, sheet, lab in (("bench_bud", SB, "Vriddhi Foods FY2027 budget (Budget_PL)"),
                            ("bench_fc", SF, "Vriddhi Foods FY2027 6+6 forecast (Forecast_6plus6)")):
        A[key] = r
        g = lambda k: f"{sheet}!$R${R[k]}"
        put(ws, f"B{r}", lab, "text", bold=True)
        put(ws, f"C{r}", "FY2027", "text")
        put(ws, f"D{r}", "=" + g("nr_tot"), "link", "#,##0", bold=True)
        put(ws, f"E{r}", "n/a", "note", align="right")
        put(ws, f"F{r}", f"=IF({g('nr_tot')}=0,0,({g('mat')}+{g('pack')})/{g('nr_tot')})", "calc", FMT_PCT, bold=True)
        put(ws, f"G{r}", f"=IF({g('nr_tot')}=0,0,{g('emp')}/{g('nr_tot')})", "calc", FMT_PCT, bold=True)
        put(ws, f"H{r}", "=" + g("r_ebitda"), "link", FMT_PCT, bold=True)
        put(ws, f"I{r}", "=" + g("r_pat"), "link", FMT_PCT, bold=True)
        r += 1
    notes = ["Screener's material cost includes packaging, so Vriddhi's comparable figure is (material + packaging) "
             "÷ net revenue. Operating margin = operating profit before other income ÷ sales, close to EBITDA margin.",
             "Reading: Vriddhi's budget material share is close to the peer median, and its EBITDA margin is below the "
             "median, which fits a smaller company with less scale in A&P and overheads.",
             f"Vriddhi has no FY2026 revenue in the model; budget volume growth is +6% to +9% by line (section 2), "
             f"against peer revenue growth of {min(float(p['revenue_growth_pct']) for p in peers if p['fiscal_year'] == latest_fy):.0f}%"
             f" to {max(float(p['revenue_growth_pct']) for p in peers if p['fiscal_year'] == latest_fy):.0f}% in {latest_fy}."]
    for t in notes:
        put(ws, f"B{r}", t, "note", italic=True)
        r += 1
    return r


# ---------------------------------------------------------------------------
# Scenario engine (shared by Budget_PL, Actuals_H1, Forecast_6plus6)
# ---------------------------------------------------------------------------
def pl_spec():
    """(key, label, unit, type, sign, fmt). type: sub, derived, dtotal, base, ratio."""
    s = [("h_vol", "Volume", None, "sub", 0, None)]
    for l in LK:
        s.append((f"vol_{l}", LN[l], "t", "derived", 1, FMT_T))
    s.append(("vol_tot", "Total volume", "t", "dtotal", 1, FMT_T))
    for key, lab, sign in (("gs", "Gross sales (before trade spend)", 1), ("ts", "Trade spend", -1),
                           ("nr", "Net revenue", 1)):
        s.append((f"h_{key}", lab, None, "sub", 0, None))
        for l in LK:
            s.append((f"{key}_{l}", LN[l], "₹ cr", "derived", sign, FMT_CR))
        s.append((f"{key}_tot", "Total " + lab.split(" (")[0].lower() if key != "nr" else "Net revenue", "₹ cr",
                  "dtotal", sign, FMT_CR))
    s += [("h_cogs", "Cost of goods sold", None, "sub", 0, None),
          ("mat", "Material cost", "₹ cr", "derived", -1, FMT_CR),
          ("pack", "Packaging cost", "₹ cr", "derived", -1, FMT_CR),
          ("conv", "Conversion cost", "₹ cr", "derived", -1, FMT_CR),
          ("cogs", "Total COGS", "₹ cr", "dtotal", -1, FMT_CR),
          ("gp", "Gross profit", "₹ cr", "dtotal", 1, FMT_CR),
          ("h_opex", "Operating costs", None, "sub", 0, None),
          ("freight", "Freight & distribution", "₹ cr", "derived", -1, FMT_CR),
          ("ap", "Advertising & promotion (A&P)", "₹ cr", "base", -1, FMT_CR),
          ("emp", "Employee cost", "₹ cr", "derived", -1, FMT_CR),
          ("oth", "Other overheads", "₹ cr", "base", -1, FMT_CR),
          ("ebitda", "EBITDA", "₹ cr", "dtotal", 1, FMT_CR),
          ("da", "Depreciation & amortisation", "₹ cr", "base", -1, FMT_CR),
          ("ebit", "EBIT", "₹ cr", "dtotal", 1, FMT_CR),
          ("int", "Interest", "₹ cr", "base", -1, FMT_CR),
          ("pbt", "Profit before tax", "₹ cr", "dtotal", 1, FMT_CR),
          ("tax", "Tax", "₹ cr", "derived", -1, FMT_CR),
          ("pat", "Profit after tax", "₹ cr", "dtotal", 1, FMT_CR),
          ("h_ratio", "Key ratios", None, "sub", 0, None),
          ("r_nrkg", "Net realisation per kg", "₹/kg", "ratio", 1, FMT_RS),
          ("r_ts", "Trade spend % of gross sales", "%", "ratio", -1, FMT_PCT),
          ("r_gm", "Gross margin % of net revenue", "%", "ratio", 1, FMT_PCT),
          ("r_mat", "Material cost % of net revenue", "%", "ratio", -1, FMT_PCT),
          ("r_ap", "A&P % of net revenue", "%", "ratio", -1, FMT_PCT),
          ("r_emp", "Employee cost % of net revenue", "%", "ratio", -1, FMT_PCT),
          ("r_ebitda", "EBITDA margin", "%", "ratio", 1, FMT_PCT),
          ("r_pat", "PAT margin", "%", "ratio", 1, FMT_PCT),
          ("r_eqc", "E-com & QC share of net revenue", "%", "ratio", 1, FMT_PCT)]
    return s


def calc_spec():
    s = [("h_vlc", "Volume by product line and channel", None, "sub", 0, None)]
    for l in LK:
        for ch in CK:
            s.append((f"vlc_{l}_{ch}", f"{LN[l]} | {CN[ch]}", "t", "base", 1, FMT_T))
    s.append(("h_gslc", "Gross sales by product line and channel", None, "sub", 0, None))
    for l in LK:
        for ch in CK:
            s.append((f"gslc_{l}_{ch}", f"{LN[l]} | {CN[ch]}", "₹ cr", "base", 1, FMT_CR))
    s.append(("h_tslc", "Trade spend by product line and channel", None, "sub", 0, None))
    for l in LK:
        for ch in CK:
            s.append((f"tslc_{l}_{ch}", f"{LN[l]} | {CN[ch]}", "₹ cr", "base", -1, FMT_CR))
    s.append(("h_nrc", "Net revenue by channel", None, "sub", 0, None))
    for ch in CK:
        s.append((f"nrc_{ch}", CN[ch], "₹ cr", "derived", 1, FMT_CR))
    s.append(("nrc_tot", "Net revenue (sum of channels)", "₹ cr", "dtotal", 1, FMT_CR))
    s.append(("h_mat", "Material cost by product line and input", None, "sub", 0, None))
    for l in LK:
        for rk in RK:
            s.append((f"matlr_{l}_{rk}", f"{LN[l]} | {RN[rk]}", "₹ cr", "base", -1, FMT_CR2))
        s.append((f"oth_{l}", f"{LN[l]} | Other ingredients", "₹ cr", "base", -1, FMT_CR2))
        s.append((f"matl_{l}", f"{LN[l]} | Total material", "₹ cr", "dtotal", -1, FMT_CR))
    s.append(("h_cl", "Packaging, conversion and gross profit by product line", None, "sub", 0, None))
    for l in LK:
        s.append((f"pack_{l}", f"Packaging: {LN[l]}", "₹ cr", "base", -1, FMT_CR))
    for l in LK:
        s.append((f"conv_{l}", f"Conversion: {LN[l]}", "₹ cr", "base", -1, FMT_CR))
    for l in LK:
        s.append((f"gpl_{l}", f"Gross profit: {LN[l]}", "₹ cr", "derived", 1, FMT_CR))
    s.append(("h_unit", "Unit economics by product line", None, "sub", 0, None))
    for l in LK:
        s.append((f"nrkg_{l}", f"Net realisation: {LN[l]}", "₹/kg", "ratio", 1, FMT_RS))
    for l in LK:
        s.append((f"gpkg_{l}", f"Gross profit per kg: {LN[l]}", "₹/kg", "ratio", 1, FMT_RS))
    s.append(("h_rmq", "Raw material consumed at standard BOM", None, "sub", 0, None))
    for rk in RK:
        s.append((f"rmq_{rk}", RN[rk], "t", "base", 1, FMT_T))
    s.append(("h_emp", "Employee cost by function", None, "sub", 0, None))
    for f in FK:
        s.append((f"empf_{f}", FN[f], "₹ cr", "base", -1, FMT_CR2))
    s.append(("h_fr", "Freight", None, "sub", 0, None))
    s.append(("frv", "Freight at % of net revenue", "₹ cr", "base", -1, FMT_CR2))
    s.append(("fro", "One-off freight surcharge", "₹ cr", "base", -1, FMT_CR2))
    return s


PL_SPEC = pl_spec()
CALC_SPEC = calc_spec()
PL_START = 6


def layout():
    R = {}
    r = PL_START
    for key, *_ in PL_SPEC:
        R[key] = r
        r += 1
    r += 1
    R["calc_section"] = r
    r += 1
    for key, *_ in CALC_SPEC:
        R[key] = r
        r += 1
    R["calc_end"] = r - 1
    R["drivers_start"] = r + 1
    return R


R = layout()
PL_FIRST, PL_LAST = R["h_vol"], R["r_eqc"]
PL_MONEY_LAST = R["pat"]
CALC_FIRST, CALC_LAST = R["h_vlc"], R["calc_end"]


class Ctx:
    """Shared references used inside engine formulas."""
    conv = f"{ASM}!$D${{conv}}"
    tax = f"{ASM}!$D${{tax}}"


def engine_formula(key, c, drv, A):
    """Month-column formula (also used for derived rows in aggregate columns)."""
    CONV = f"{ASM}!$D${A['conv']}"
    TAX = f"{ASM}!$D${A['tax']}"
    g = lambda k: f"{c}{R[k]}"
    p = key.split("_")
    if key.startswith("vol_") and key != "vol_tot":
        l = p[1]
        return f"=SUM({g(f'vlc_{l}_GT')}:{g(f'vlc_{l}_EQC')})"
    if key == "vol_tot":
        return f"=SUM({g('vol_NAM')}:{g('vol_BEV')})"
    for pre, src in (("gs", "gslc"), ("ts", "tslc")):
        if key.startswith(pre + "_"):
            if p[1] == "tot":
                return f"=SUM({g(pre + '_NAM')}:{g(pre + '_BEV')})"
            return f"=SUM({g(f'{src}_{p[1]}_GT')}:{g(f'{src}_{p[1]}_EQC')})"
    if key.startswith("nr_"):
        if p[1] == "tot":
            return f"=SUM({g('nr_NAM')}:{g('nr_BEV')})"
        return f"={g('gs_' + p[1])}-{g('ts_' + p[1])}"
    simple = {
        "mat": "=" + "+".join(g(f"matl_{l}") for l in LK),
        "pack": f"=SUM({g('pack_NAM')}:{g('pack_BEV')})",
        "conv": f"=SUM({g('conv_NAM')}:{g('conv_BEV')})",
        "cogs": f"=SUM({g('mat')}:{g('conv')})",
        "gp": f"={g('nr_tot')}-{g('cogs')}",
        "freight": f"={g('frv')}+{g('fro')}",
        "emp": f"=SUM({g('empf_FAC')}:{g('empf_COR')})",
        "ebitda": f"={g('gp')}-SUM({g('freight')}:{g('oth')})",
        "ebit": f"={g('ebitda')}-{g('da')}",
        "pbt": f"={g('ebit')}-{g('int')}",
        "tax": f"={g('pbt')}*{TAX}",
        "pat": f"={g('pbt')}-{g('tax')}",
        "r_nrkg": f"=IF({g('vol_tot')}=0,0,{g('nr_tot')}/({g('vol_tot')}*{CONV}))",
        "r_ts": f"=IF({g('gs_tot')}=0,0,{g('ts_tot')}/{g('gs_tot')})",
        "r_gm": f"=IF({g('nr_tot')}=0,0,{g('gp')}/{g('nr_tot')})",
        "r_mat": f"=IF({g('nr_tot')}=0,0,{g('mat')}/{g('nr_tot')})",
        "r_ap": f"=IF({g('nr_tot')}=0,0,{g('ap')}/{g('nr_tot')})",
        "r_emp": f"=IF({g('nr_tot')}=0,0,{g('emp')}/{g('nr_tot')})",
        "r_ebitda": f"=IF({g('nr_tot')}=0,0,{g('ebitda')}/{g('nr_tot')})",
        "r_pat": f"=IF({g('nr_tot')}=0,0,{g('pat')}/{g('nr_tot')})",
        "r_eqc": f"=IF({g('nr_tot')}=0,0,{g('nrc_EQC')}/{g('nr_tot')})",
        "nrc_tot": f"=SUM({g('nrc_GT')}:{g('nrc_EQC')})",
    }
    if key in simple:
        return simple[key]
    if key == "ap":
        return "=" + drv.ap(c)
    if key == "oth":
        return "=" + drv.oth(c)
    if key == "da":
        return "=" + drv.da(c)
    if key == "int":
        return f"={drv.borr(c)}*{drv.rate(c)}/12"
    if key.startswith("vlc_"):
        return "=" + drv.vol_lc(p[1], p[2], c)
    if key.startswith("gslc_"):
        return f"={g(f'vlc_{p[1]}_{p[2]}')}*{drv.price(p[1], c)}*{CONV}"
    if key.startswith("tslc_"):
        return f"={g(f'gslc_{p[1]}_{p[2]}')}*{drv.ts(p[2], c)}"
    if key.startswith("nrc_"):
        ch = p[1]
        return "=" + "+".join(f"({g(f'gslc_{l}_{ch}')}-{g(f'tslc_{l}_{ch}')})" for l in LK)
    if key.startswith("matlr_"):
        l, rk = p[1], p[2]
        bom = f"{ASM}!${BOMCOL[rk]}${A[f'bom_{l}']}"
        return f"={g('vol_' + l)}*{bom}*{drv.rm(rk, c)}*{CONV}"
    if key.startswith("oth_"):
        return f"={g('vol_' + p[1])}*{drv.other(p[1], c)}*{CONV}"
    if key.startswith("matl_"):
        return f"=SUM({g(f'matlr_{p[1]}_OIL')}:{g('oth_' + p[1])})"
    if key.startswith("pack_"):
        return f"={g('vol_' + p[1])}*{drv.pack(p[1], c)}*{CONV}"
    if key.startswith("conv_"):
        return f"={g('vol_' + p[1])}*{drv.conv(p[1], c)}*{CONV}"
    if key.startswith("gpl_"):
        l = p[1]
        return f"={g('nr_' + l)}-{g('matl_' + l)}-{g('pack_' + l)}-{g('conv_' + l)}"
    if key.startswith("nrkg_"):
        l = p[1]
        return f"=IF({g('vol_' + l)}=0,0,{g('nr_' + l)}/({g('vol_' + l)}*{CONV}))"
    if key.startswith("gpkg_"):
        l = p[1]
        return f"=IF({g('vol_' + l)}=0,0,{g('gpl_' + l)}/({g('vol_' + l)}*{CONV}))"
    if key.startswith("rmq_"):
        rk = p[1]
        return "=" + "+".join(f"{g('vol_' + l)}*{ASM}!${BOMCOL[rk]}${A[f'bom_{l}']}" for l in LK)
    if key.startswith("empf_"):
        f = p[1]
        return (f"={drv.hc(f, c)}*{drv.ctc(f, c)}/1200*IF({drv.date(c)}>={drv.inc_date(c)},"
                f"1+{drv.inc(f, c)},1)")
    if key == "frv":
        return f"={g('nr_tot')}*{drv.freight_pct(c)}"
    if key == "fro":
        return "=" + drv.oneoff(c)
    raise KeyError(key)


def write_engine(ws, drv, A, mcols, aggs, helper_col, period_note):
    """Write the P&L block and supporting-calculation block.

    aggs: list of (agg_col, first_col, last_col). helper_col: column for the months-vs-totals check.
    """
    last_col_idx = ord(aggs[-1][0]) - 64
    section(ws, PL_START - 1, f"Profit and loss (₹ crore unless stated). {period_note}", 1, last_col_idx + 1)
    section(ws, R["calc_section"], "Supporting calculations (feed the P&L above)", 1, last_col_idx + 1)
    for spec in (PL_SPEC, CALC_SPEC):
        for key, label, unit, typ, sign, fmt in spec:
            r = R[key]
            if typ == "sub":
                put(ws, f"B{r}", label, "text", bold=True, italic=True)
                continue
            indent = "   " if typ in ("derived", "base", "ratio") and spec is PL_SPEC and key not in (
                "mat", "pack", "conv", "freight", "ap", "emp", "oth", "da", "int", "tax") else ""
            put(ws, f"B{r}", indent + label, "text", bold=(typ == "dtotal"))
            put(ws, f"C{r}", unit, "note")
            for c in mcols:
                put(ws, f"{c}{r}", engine_formula(key, c, drv, A), "calc", fmt, bold=(typ == "dtotal"))
            for ac, c1, c2 in aggs:
                if typ == "base":
                    fml = f"=SUM({c1}{r}:{c2}{r})"
                else:
                    fml = engine_formula(key, ac, drv, A)
                put(ws, f"{ac}{r}", fml, "calc", fmt, bold=(typ == "dtotal"), fill=TOT_FILL)
            if typ == "dtotal":
                for ci in range(2, last_col_idx + 1):
                    ws.cell(row=r, column=ci).border = TOP_BORDER
            if typ != "ratio":
                parts = [f"ABS(SUM({c1}{r}:{c2}{r})-{ac}{r})" for ac, c1, c2 in aggs]
                fml = "=" + (parts[0] if len(parts) == 1 else "MAX(" + ",".join(parts) + ")")
                put(ws, f"{helper_col}{r}", fml, "calc", FMT_SCI, color="808080")
    put(ws, f"{helper_col}4", "Check: Σ months vs totals", "text", bold=True, fill=HDR_FILL, wrap=True)


class BudgetDrv:
    def __init__(self, A):
        self.A = A
        self.S = ASM + "!"

    def _m(self, key, c):
        return f"{self.S}{c}{self.A[key]}"

    def vol_lc(self, l, ch, c):
        return f"{self._m('mvol_' + l, c)}*{self.S}${MIXCOL[ch]}${self.A['mix_' + l]}"

    def price(self, l, c): return self._m("price_" + l, c)
    def ts(self, ch, c): return self._m("ts_" + ch, c)
    def rm(self, rk, c): return self._m("rm_" + rk, c)
    def other(self, l, c): return f"{self.S}$D${self.A['cost_' + l]}"
    def pack(self, l, c): return f"{self.S}$E${self.A['cost_' + l]}"
    def conv(self, l, c): return f"{self.S}$F${self.A['cost_' + l]}"
    def freight_pct(self, c): return f"{self.S}$D${self.A['freight']}"
    def oneoff(self, c): return "0"
    def ap(self, c): return self._m("ap", c)
    def hc(self, f, c): return self._m("hc_" + f, c)
    def ctc(self, f, c): return f"{self.S}$D${self.A['ctc_' + f]}"
    def inc(self, f, c): return f"{self.S}$E${self.A['ctc_' + f]}"
    def inc_date(self, c): return f"{self.S}$D${self.A['incdate']}"
    def oth(self, c): return self._m("oth", c)
    def da(self, c): return self._m("da", c)
    def borr(self, c): return self._m("borr", c)
    def rate(self, c): return self._m("rate", c)
    def date(self, c): return f"{c}$4"


class RowDrv:
    """Driver rows that live on the same sheet (Actuals_H1, Forecast_6plus6)."""

    def __init__(self, D, sheet_prefix=""):
        self.D = D
        self.S = sheet_prefix

    def _m(self, key, c):
        return f"{self.S}{c}{self.D[key]}"

    def vol_lc(self, l, ch, c): return self._m(f"vol_{l}_{ch}", c)
    def price(self, l, c): return self._m("price_" + l, c)
    def ts(self, ch, c): return self._m("ts_" + ch, c)
    def rm(self, rk, c): return self._m("rm_" + rk, c)
    def other(self, l, c): return self._m("other_" + l, c)
    def pack(self, l, c): return self._m("pack_" + l, c)
    def conv(self, l, c): return self._m("conv_" + l, c)
    def freight_pct(self, c): return self._m("frpct", c)
    def oneoff(self, c): return self._m("fro", c)
    def ap(self, c): return self._m("ap", c)
    def hc(self, f, c): return self._m("hc_" + f, c)
    def ctc(self, f, c): return self._m("ctc_" + f, c)
    def inc(self, f, c): return f"$D${self.D['inc_' + f]}"
    def inc_date(self, c): return f"$D${self.D['incdate']}"
    def oth(self, c): return self._m("oth", c)
    def da(self, c): return self._m("da", c)
    def borr(self, c): return self._m("borr", c)
    def rate(self, c): return self._m("rate", c)
    def date(self, c): return f"{c}$4"


class ForecastDrv(RowDrv):
    """Forecast: Apr-Sep use the actual increment terms, Oct-Mar the forecast terms."""

    def inc(self, f, c):
        if c in AC:
            return f"{SA}!$D${self.actD['inc_' + f]}"
        return f"$D${self.D['inc_' + f]}"

    def inc_date(self, c):
        if c in AC:
            return f"{SA}!$D${self.actD['incdate']}"
        return f"$D${self.D['incdate']}"


def scenario_header(ws, mcols, aggs, fc_cols=()):
    hdr = {"A": "Ref", "B": "Line item", "C": "Unit"}
    header_row(ws, 4, hdr)
    for c in mcols:
        put(ws, f"{c}4", f"={ASM}!{c}$4", "link", FMT_DATE, bold=True, fill=FC_FILL if c in fc_cols else HDR_FILL,
            align="center")
    labels = {"P": "H1 (Apr-Sep)", "Q": "H2 (Oct-Mar)", "R": "FY2027", "J": "H1 (Apr-Sep)"}
    for ac, _, _ in aggs:
        header_row(ws, 4, {ac: labels[ac]})


def scenario_checks(sheet, aggs, helper_col):
    last = aggs[-1][0]
    add_check(sheet, "Sum of months = H1/H2/FY totals for every P&L line (cross-foot)",
              f"=MAX({sheet}!{helper_col}{PL_FIRST}:{helper_col}{PL_MONEY_LAST})")
    add_check(sheet, "Sum of months = totals for every supporting-calculation line",
              f"=MAX({sheet}!{helper_col}{CALC_FIRST}:{helper_col}{CALC_LAST})")
    add_check(sheet, "Net revenue by product line = net revenue by channel (all columns)",
              f"=SUMPRODUCT(ABS({sheet}!D{R['nr_tot']}:{last}{R['nr_tot']}-{sheet}!D{R['nrc_tot']}:{last}{R['nrc_tot']}))")
    add_check(sheet, "Gross profit by product line adds up to P&L gross profit",
              f"=SUMPRODUCT(ABS({sheet}!D{R['gpl_NAM']}:{last}{R['gpl_NAM']}+{sheet}!D{R['gpl_BIS']}:{last}{R['gpl_BIS']}"
              f"+{sheet}!D{R['gpl_BEV']}:{last}{R['gpl_BEV']}-{sheet}!D{R['gp']}:{last}{R['gp']}))")


# ---------------------------------------------------------------------------
# 3. Budget_PL
# ---------------------------------------------------------------------------
def build_budget(ws, A):
    title(ws, "Budget_PL: FY2027 monthly budget P&L",
          f"{I.COMPANY} (fictional). Every number is a formula on Assumptions_Budget drivers.",
          "Volumes in tonnes; money in ₹ crore. H1 = Apr-Sep 2026, H2 = Oct-2026 to Mar-2027.")
    aggs = [("P", "D", "I"), ("Q", "J", "O"), ("R", "D", "O")]
    scenario_header(ws, MC, aggs)
    write_engine(ws, BudgetDrv(A), A, MC, aggs, "S", "Budget approved Feb-2026.")
    widths(ws, {"A": 5, "B": 46, "C": 8, **{c: 10 for c in MC}, "P": 11, "Q": 11, "R": 11, "S": 12})
    ws.freeze_panes = "D5"
    scenario_checks(SB, aggs, "S")


# ---------------------------------------------------------------------------
# 4. Actuals_H1 (ERP extract + P&L)
# ---------------------------------------------------------------------------
def write_actual_drivers(ws, A, r0):
    Ac = I.ACTUAL
    av = I.actual_volumes()
    D = {}
    r = r0
    section(ws, r, "ERP extract (fictional): actual drivers Apr-Sep 2026 from the month-end close. Blue = loaded "
                   "from ERP; these cells drive the actual P&L above.", 1, 11)
    r += 1
    hdr = {"A": "ERP code", "B": "Description", "C": "Unit", "J": "H1 total", "K": "Source system"}
    header_row(ws, r, hdr)
    for c in AC:
        put(ws, f"{c}{r}", f"={ASM}!{c}$4", "link", FMT_DATE, bold=True, fill=HDR_FILL, align="center")
    r += 1

    def block(label):
        nonlocal r
        sub(ws, r, label)
        r += 1

    block("A. Sales volume billed")
    for l in LK:
        for ch in CK:
            D[f"vol_{l}_{ch}"] = r
            mrow(ws, r, f"{LN[l]} | {CN[ch]}", "t", av[(l, ch)], fmt=FMT_T1, cols=AC, agg="sum", aggcol="J",
                 code=f"SD.VOL.{l}.{ch}", reasoncol="K", reason="SD billing register")
            r += 1
    block("B. Realised list price (ex-GST)")
    for l in LK:
        D[f"price_{l}"] = r
        mrow(ws, r, LN[l], "₹/kg", Ac["list_price"][l], fmt=FMT_RS, cols=AC, code=f"SD.PRC.{l}", reasoncol="K",
             reason="SD condition records" + ("; +4% from 1-Aug-2026" if l == "NAM" else ""))
        r += 1
    block("C. Trade spend rate")
    for ch in CK:
        D[f"ts_{ch}"] = r
        mrow(ws, r, CN[ch], "% of gross sales", Ac["trade_spend"][ch], fmt=FMT_PCT, cols=AC, code=f"FI.TSP.{ch}",
             reasoncol="K", reason="Trade-claims ledger")
        r += 1
    block("D. Raw material price (moving-average purchase price)")
    for rk in RK:
        D[f"rm_{rk}"] = r
        mrow(ws, r, RN[rk], "₹/kg", Ac["rm_price"][rk], fmt=FMT_RS, cols=AC, code=f"MM.MAP.{rk}", reasoncol="K",
             reason="MM material ledger")
        r += 1
    block("E. Other ingredients, packaging and conversion (product costing)")
    for key, lab, src in (("other", "Other ingredients", "other_ingr"), ("pack", "Packaging", "packaging"),
                          ("conv", "Conversion", "conversion")):
        for l in LK:
            D[f"{key}_{l}"] = r
            mrow(ws, r, f"{lab}: {LN[l]}", "₹/kg", Ac[src][l], fmt=FMT_RS, cols=AC,
                 code=f"CO.{key.upper()[:3]}.{l}", reasoncol="K", reason="CO actual product cost")
            r += 1
    block("F. Freight")
    D["frpct"] = r
    mrow(ws, r, "Freight & distribution rate", "% of net revenue", Ac["freight_pct"], fmt=FMT_PCT2, cols=AC,
         code="FI.6110", reasoncol="K", reason="GL 6110 outward freight ÷ net revenue")
    r += 1
    D["fro"] = r
    mrow(ws, r, "One-off freight surcharge", "₹ cr", Ac["freight_oneoff"], fmt=FMT_CR2, cols=AC, agg="sum",
         aggcol="J", code="FI.6115", reasoncol="K", reason="GL 6115: July monsoon route-disruption surcharge")
    r += 1
    block("G. Advertising & promotion")
    D["ap"] = r
    mrow(ws, r, "A&P spend", "₹ cr", Ac["ap"], fmt=FMT_CR2, cols=AC, agg="sum", aggcol="J", code="FI.6300",
         reasoncol="K", reason="GL 6300; festive launch spend pulled into Aug-Sep")
    r += 1
    block("H. Payroll")
    for f in FK:
        D[f"hc_{f}"] = r
        mrow(ws, r, f"Headcount: {FN[f]}", "heads", Ac["headcount"][f], fmt=FMT_HC, cols=AC, code=f"HR.HC.{f}",
             reasoncol="K", reason="HR payroll, month-end")
        r += 1
    for f in FK:
        D[f"ctc_{f}"] = r
        mrow(ws, r, f"CTC per head: {FN[f]}", "₹ lakh/yr", [Ac["ctc"][f]] * 6, fmt="0.00", cols=AC,
             code=f"HR.CTC.{f}", reasoncol="K", reason="HR payroll, before increment")
        r += 1
    for f in FK:
        D[f"inc_{f}"] = r
        mrow(ws, r, f"Increment approved: {FN[f]}", "%", [f"={ASM}!$E${A['ctc_' + f]}"], kind="link",
             fmt=FMT_PCT, cols=["D"], code=f"HR.INC.{f}")
        put(ws, f"K{r}", "Same % as budget", "note", italic=True)
        r += 1
    D["incdate"] = r
    mrow(ws, r, "Increment effective from", "date", [Ac["increment_date"]], fmt=FMT_DAY, cols=["D"],
         code="HR.INC.DATE")
    put(ws, f"K{r}", "Board deferred the increment from 1-Jul to 1-Oct-2026", "note", italic=True)
    r += 1
    block("I. Overheads, depreciation and finance cost")
    D["oth"] = r
    mrow(ws, r, "Other overheads", "₹ cr", Ac["other_oh"], fmt=FMT_CR2, cols=AC, agg="sum", aggcol="J",
         code="FI.6900", reasoncol="K", reason="GL 6900 series")
    r += 1
    D["da"] = r
    mrow(ws, r, "Depreciation & amortisation", "₹ cr", Ac["da"], fmt=FMT_CR2, cols=AC, agg="sum", aggcol="J",
         code="FI.7100", reasoncol="K", reason="Fixed-asset register")
    r += 1
    D["borr"] = r
    mrow(ws, r, "Average borrowings", "₹ cr", Ac["borrowings"], fmt=FMT_CR, cols=AC, code="TR.BORR",
         reasoncol="K", reason="Treasury: daily average of term loan + working capital")
    r += 1
    D["rate"] = r
    mrow(ws, r, "Interest rate on borrowings", "% p.a.", Ac["int_rate"], fmt=FMT_PCT2, cols=AC, code="TR.RATE",
         reasoncol="K", reason="Treasury: blended rate")
    r += 1
    return D


def build_actuals(ws, A):
    title(ws, "Actuals_H1: actual P&L Apr-Sep 2026 built from the ERP driver extract",
          f"{I.COMPANY} (fictional). The P&L is calculated by formulas from the ERP extract further down this "
          "sheet, with the same logic as the budget, so every variance can be bridged.",
          "Volumes in tonnes; money in ₹ crore. Months closed: Apr-Sep 2026 (status date 31-Oct-2026).")
    aggs = [("J", "D", "I")]
    scenario_header(ws, AC, aggs)
    D = write_actual_drivers(ws, A, R["drivers_start"])
    write_engine(ws, RowDrv(D), A, AC, aggs, "K", "Actuals Apr-Sep 2026.")
    widths(ws, {"A": 13, "B": 46, "C": 13, **{c: 10.5 for c in AC}, "J": 12, "K": 44})
    ws.freeze_panes = "D5"
    scenario_checks(SA, aggs, "K")
    return D


# ---------------------------------------------------------------------------
# 5. Forecast_6plus6
# ---------------------------------------------------------------------------
def write_forecast_drivers(ws, A, AD, r0):
    Fc, B = I.FORECAST, I.BUDGET
    D = {}
    r = r0
    section(ws, r, "Forecast drivers: Apr-Sep = actual drivers (green links to Actuals_H1); Oct-Mar = reforecast "
                   "(blue inputs, yellow = judgment, reason in column S).", 1, 19)
    r += 1
    hdr = {"B": "Driver", "C": "Unit", "P": "H1", "Q": "H2", "R": "FY", "S": "Basis / reason"}
    header_row(ws, r, hdr)
    for c in MC:
        put(ws, f"{c}{r}", f"={ASM}!{c}$4", "link", FMT_DATE, bold=True, fill=FC_FILL if c in HC_ else HDR_FILL,
            align="center")
    r += 1

    def link_act(key, c):
        return f"={SA}!{c}{AD[key]}"

    # A. case overlays
    sub(ws, r, "A. Forecast case overlays (case selected on the Cover sheet; applied to Oct-Mar only)")
    r += 1
    header_row(ws, r, {"B": "Overlay", "C": "Unit", "D": "Base", "E": "Downside", "F": "Upside",
                       "G": "Applies from", "H": "Selected", "I": "Reason"})
    r += 1
    ov_reason = {"oil": "Downside: oil returns to the Sep-26 peak; upside: more duty-cut pass-through",
                 "gtvol": "Downside: weaker rural demand after the deficient monsoon (ICRA, Sep-2026)",
                 "bisprice": "Upside: a second 2% biscuit price increase from Jan-27"}
    for key, lab, unit, base, down, up, start in I.CASE_OVERLAYS:
        D[f"ov_{key}"] = r
        fmt = FMT_RS if unit == "Rs/kg" else FMT_PCT
        put(ws, f"B{r}", lab, "text")
        put(ws, f"C{r}", "₹/kg" if unit == "Rs/kg" else unit, "note")
        for cc, v in zip("DEF", (base, down, up)):
            put(ws, f"{cc}{r}", v, "input", fmt, yellow=True)
        put(ws, f"G{r}", start, "input", FMT_DATE, yellow=True)
        put(ws, f"H{r}", f"=CHOOSE({CASE_CELL},D{r},E{r},F{r})", "calc", fmt)
        put(ws, f"I{r}", ov_reason[key], "note", italic=True)
        r += 1
    for key, lab, unit, *_ in I.CASE_OVERLAYS:
        D[f"ovm_{key}"] = r
        fmt = FMT_RS if unit == "Rs/kg" else FMT_PCT
        vals = [f"=IF({c}$4>=$G${D['ov_' + key]},$H${D['ov_' + key]},0)" for c in HC_]
        mrow(ws, r, f"Overlay applied: {lab}", "₹/kg" if unit == "Rs/kg" else unit, vals, kind="calc", fmt=fmt,
             cols=HC_, reasoncol="S")
        r += 1
    r += 1

    # B. volume
    sub(ws, r, "B. Volume")
    r += 1
    for l in LK:
        D[f"vadj_{l}"] = r
        mrow(ws, r, f"Volume change vs budget: {LN[l]}", "%", Fc["vol_adj"][l], fmt=FMT_PCT, yellow=True, cols=HC_,
             reasoncol="S", reason=Fc["vol_adj_reason"][l])
        r += 1
    for l in LK:
        D[f"lvol_{l}"] = r
        vals = [f"={SA}!{c}{R['vol_' + l]}" for c in AC] + \
               [f"={ASM}!{c}{A['mvol_' + l]}*(1+{c}{D['vadj_' + l]})" for c in HC_]
        mrow(ws, r, f"Line volume: {LN[l]}", "t", vals, kind="calc", fmt=FMT_T, reasoncol="S")
        for c in AC:
            ws[f"{c}{r}"].font = Font(color="008000", size=10)
        put(ws, f"P{r}", f"=SUM(D{r}:I{r})", "calc", FMT_T)
        put(ws, f"Q{r}", f"=SUM(J{r}:O{r})", "calc", FMT_T)
        put(ws, f"R{r}", f"=SUM(D{r}:O{r})", "calc", FMT_T)
        r += 1
    header_row(ws, r, {"B": "H2 channel mix (share of line volume)", "D": "GT", "E": "MT", "F": "E-com & QC",
                       "G": "Total", "H": "Reason"})
    r += 1
    for l in LK:
        D[f"fmix_{l}"] = r
        mx = Fc["mix"][l]
        mrow(ws, r, LN[l], "% of volume", [mx["GT"], mx["MT"], mx["EQC"]], fmt=FMT_PCT, yellow=True,
             cols=["D", "E", "F"])
        put(ws, f"G{r}", f"=SUM(D{r}:F{r})", "calc", FMT_PCT)
        put(ws, f"H{r}", Fc["mix_reason"][l], "note", italic=True)
        r += 1
    for l in LK:
        for ch in CK:
            D[f"vol_{l}_{ch}"] = r
            vals = [link_act(f"vol_{l}_{ch}", c) for c in AC]
            for c in HC_:
                f = f"={c}{D['lvol_' + l]}*${MIXCOL[ch]}${D['fmix_' + l]}"
                if ch == "GT":
                    f += f"*(1+{c}{D['ovm_gtvol']})"
                vals.append(f)
            mrow(ws, r, f"Volume: {LN[l]} | {CN[ch]}", "t", vals, kind="calc", fmt=FMT_T1, reasoncol="S")
            for c in AC:
                ws[f"{c}{r}"].font = Font(color="008000", size=10)
            r += 1
    r += 1

    # C. price and trade terms
    sub(ws, r, "C. Price and trade terms")
    r += 1
    for l in LK:
        D[f"pchg_{l}"] = r
        mrow(ws, r, f"List price change vs budget (Oct-Mar): {LN[l]}", "%", [Fc["price_chg"][l]], fmt=FMT_PCT,
             yellow=True, cols=["D"])
        put(ws, f"E{r}", Fc["price_chg_reason"][l], "note", italic=True)
        r += 1
    for l in LK:
        D[f"price_{l}"] = r
        vals = [link_act(f"price_{l}", c) for c in AC]
        for c in HC_:
            f = f"={ASM}!{c}{A['price_' + l]}*(1+$D${D['pchg_' + l]})"
            if l == "BIS":
                f += f"*(1+{c}{D['ovm_bisprice']})"
            vals.append(f)
        mrow(ws, r, f"List price: {LN[l]}", "₹/kg", vals, kind="calc", fmt=FMT_RS)
        for c in AC:
            ws[f"{c}{r}"].font = Font(color="008000", size=10)
        r += 1
    for ch in CK:
        D[f"tsadj_{ch}"] = r
        mrow(ws, r, f"Trade spend change vs budget (Oct-Mar): {CN[ch]}", "pp", [Fc["ts_adj"][ch]], fmt=FMT_PCT,
             yellow=True, cols=["D"])
        put(ws, f"E{r}", Fc["ts_adj_reason"][ch], "note", italic=True)
        r += 1
    for ch in CK:
        D[f"ts_{ch}"] = r
        vals = [link_act(f"ts_{ch}", c) for c in AC] + \
               [f"={ASM}!{c}{A['ts_' + ch]}+$D${D['tsadj_' + ch]}" for c in HC_]
        mrow(ws, r, f"Trade spend: {CN[ch]}", "% of gross sales", vals, kind="calc", fmt=FMT_PCT)
        for c in AC:
            ws[f"{c}{r}"].font = Font(color="008000", size=10)
        r += 1
    r += 1

    # D. materials
    sub(ws, r, "D. Materials, packaging and conversion")
    r += 1
    D["oilbase"] = r
    mrow(ws, r, "Edible oil: base-case forecast price", "₹/kg", Fc["rm_price"]["OIL"], fmt=FMT_RS, yellow=True,
         cols=HC_, reasoncol="S", reason=Fc["rm_price_reason"]["OIL"])
    r += 1
    for rk in RK:
        D[f"rm_{rk}"] = r
        vals = [link_act(f"rm_{rk}", c) for c in AC]
        if rk == "OIL":
            vals += [f"={c}{D['oilbase']}+{c}{D['ovm_oil']}" for c in HC_]
            mrow(ws, r, f"Raw material price: {RN[rk]} (incl. case overlay)", "₹/kg", vals, kind="calc", fmt=FMT_RS)
        else:
            mrow(ws, r, f"Raw material price: {RN[rk]}", "₹/kg", vals[:6], kind="link", fmt=FMT_RS, cols=AC)
            mrow(ws, r, f"Raw material price: {RN[rk]}", "₹/kg", Fc["rm_price"][rk], fmt=FMT_RS, yellow=True,
                 cols=HC_, reasoncol="S", reason=Fc["rm_price_reason"][rk])
        for c in AC:
            ws[f"{c}{r}"].font = Font(color="008000", size=10)
        r += 1
    header_row(ws, r, {"B": "H2 unit costs (₹ per kg of finished product)", "D": "Other ingredients",
                       "E": "Packaging", "F": "Conversion", "G": "Reason"})
    r += 1
    for l in LK:
        D[f"fcost_{l}"] = r
        mrow(ws, r, LN[l], "₹/kg", [Fc["other_ingr"][l], Fc["packaging"][l], Fc["conversion"][l]], fmt=FMT_RS,
             yellow=True, cols=["D", "E", "F"])
        put(ws, f"G{r}", "Sep-26 exit rates for ingredients and packaging; conversion at budget", "note",
            italic=True)
        r += 1
    for key, lab, cc in (("other", "Other ingredients", "D"), ("pack", "Packaging", "E"), ("conv", "Conversion", "F")):
        for l in LK:
            D[f"{key}_{l}"] = r
            vals = [link_act(f"{key}_{l}", c) for c in AC] + [f"=${cc}${D['fcost_' + l]}" for c in HC_]
            mrow(ws, r, f"{lab}: {LN[l]}", "₹/kg", vals, kind="calc", fmt=FMT_RS)
            for c in AC:
                ws[f"{c}{r}"].font = Font(color="008000", size=10)
            r += 1
    r += 1

    # E. opex
    sub(ws, r, "E. Operating costs, payroll and finance")
    r += 1
    D["frpct_in"] = r
    mrow(ws, r, "Freight rate (Oct-Mar)", "% of net revenue", [Fc["freight_pct"]], fmt=FMT_PCT2, yellow=True,
         cols=["D"])
    put(ws, f"E{r}", "H1 run-rate excluding the July one-off surcharge", "note", italic=True)
    r += 1
    D["frpct"] = r
    vals = [link_act("frpct", c) for c in AC] + [f"=$D${D['frpct_in']}" for c in HC_]
    mrow(ws, r, "Freight & distribution rate", "% of net revenue", vals, kind="calc", fmt=FMT_PCT2)
    r += 1
    D["fro"] = r
    mrow(ws, r, "One-off freight surcharge", "₹ cr", [link_act("fro", c) for c in AC], kind="link", fmt=FMT_CR2,
         cols=AC)
    mrow(ws, r, "One-off freight surcharge", "₹ cr", [0.0] * 6, fmt=FMT_CR2, cols=HC_, reasoncol="S",
         reason="None expected")
    r += 1
    D["ap"] = r
    mrow(ws, r, "A&P spend", "₹ cr", [link_act("ap", c) for c in AC], kind="link", fmt=FMT_CR2, cols=AC)
    mrow(ws, r, "A&P spend", "₹ cr", Fc["ap"], fmt=FMT_CR2, yellow=True, cols=HC_, reasoncol="S",
         reason=Fc["ap_reason"])
    put(ws, f"P{r}", f"=SUM(D{r}:I{r})", "calc", FMT_CR2)
    put(ws, f"Q{r}", f"=SUM(J{r}:O{r})", "calc", FMT_CR2)
    put(ws, f"R{r}", f"=SUM(D{r}:O{r})", "calc", FMT_CR2)
    r += 1
    for f in FK:
        D[f"hc_{f}"] = r
        vals = [link_act(f"hc_{f}", c) for c in AC] + [f"={ASM}!{c}{A['hc_' + f]}" for c in HC_]
        mrow(ws, r, f"Headcount: {FN[f]}", "heads", vals, kind="link", fmt=FMT_HC, reasoncol="S",
             reason="Oct-Mar at budget hiring plan" if f == "FAC" else None)
        r += 1
    for f in FK:
        D[f"ctc_{f}"] = r
        vals = [link_act(f"ctc_{f}", c) for c in AC] + [f"={SA}!$I${AD['ctc_' + f]}" for c in HC_]
        mrow(ws, r, f"CTC per head: {FN[f]}", "₹ lakh/yr", vals, kind="link", fmt="0.00", reasoncol="S",
             reason="Sep-26 actual, before increment" if f == "FAC" else None)
        r += 1
    for f in FK:
        D[f"inc_{f}"] = r
        mrow(ws, r, f"Increment (Oct-Mar): {FN[f]}", "%", [f"={ASM}!$E${A['ctc_' + f]}"], kind="link",
             fmt=FMT_PCT, cols=["D"])
        r += 1
    D["incdate"] = r
    mrow(ws, r, "Increment effective from (Oct-Mar)", "date", [I.FORECAST["increment_date"]], fmt=FMT_DAY,
         yellow=True, cols=["D"])
    put(ws, f"E{r}", "Deferred increment paid from 1-Oct-2026, not retrospective", "note", italic=True)
    r += 1
    D["oth"] = r
    vals = [link_act("oth", c) for c in AC] + [f"={ASM}!{c}{A['oth']}" for c in HC_]
    mrow(ws, r, "Other overheads", "₹ cr", vals, kind="link", fmt=FMT_CR2, reasoncol="S",
         reason="Oct-Mar at budget")
    r += 1
    D["da"] = r
    vals = [link_act("da", c) for c in AC] + [f"={ASM}!{c}{A['da']}" for c in HC_]
    mrow(ws, r, "Depreciation & amortisation", "₹ cr", vals, kind="link", fmt=FMT_CR2, reasoncol="S",
         reason="Oct-Mar at budget")
    r += 1
    D["borr"] = r
    mrow(ws, r, "Average borrowings", "₹ cr", [link_act("borr", c) for c in AC], kind="link", fmt=FMT_CR, cols=AC)
    mrow(ws, r, "Average borrowings", "₹ cr", Fc["borrowings"], fmt=FMT_CR, yellow=True, cols=HC_, reasoncol="S",
         reason="Festive inventory peaks in Oct, then unwinds")
    r += 1
    D["rate"] = r
    mrow(ws, r, "Interest rate on borrowings", "% p.a.", [link_act("rate", c) for c in AC], kind="link",
         fmt=FMT_PCT2, cols=AC)
    mrow(ws, r, "Interest rate on borrowings", "% p.a.", Fc["int_rate"], fmt=FMT_PCT2, yellow=True, cols=HC_,
         reasoncol="S", reason=Fc["int_rate_reason"])
    r += 1
    return D


def build_forecast(ws, A, AD):
    title(ws, "Forecast_6plus6: 6 months actual + 6 months reforecast for FY2027",
          f"{I.COMPANY} (fictional). Apr-Sep = actuals (driver links to Actuals_H1). Oct-Mar = reforecast drivers "
          "below. Shaded month headers are forecast months.",
          "Volumes in tonnes; money in ₹ crore. Forecast case (Base / Downside / Upside) is selected on the Cover.")
    aggs = [("P", "D", "I"), ("Q", "J", "O"), ("R", "D", "O")]
    scenario_header(ws, MC, aggs, fc_cols=HC_)
    D = write_forecast_drivers(ws, A, AD, R["drivers_start"])
    drv = ForecastDrv(D)
    drv.actD = AD
    write_engine(ws, drv, A, MC, aggs, "S", "Apr-Sep actual, Oct-Mar forecast.")
    widths(ws, {"A": 5, "B": 50, "C": 13, **{c: 10 for c in MC}, "P": 11, "Q": 11, "R": 11, "S": 14})
    ws.freeze_panes = "D5"
    scenario_checks(SF, aggs, "S")
    add_check(SF, "Forecast Apr-Sep equals actual Apr-Sep for every P&L line and ratio",
              f"=SUMPRODUCT(ABS({SF}!D{PL_FIRST}:I{PL_LAST}-{SA}!D{PL_FIRST}:I{PL_LAST}))")
    add_check(SF, "Forecast H1 column equals Actuals_H1 H1 column",
              f"=SUMPRODUCT(ABS({SF}!P{PL_FIRST}:P{PL_LAST}-{SA}!J{PL_FIRST}:J{PL_LAST}))")
    add_check(SF, "Forecast H2 channel mix sums to 100% for each product line",
              "=" + "+".join(f"ABS({SF}!G{D[f'fmix_{l}']}-1)" for l in LK))
    return D


# ---------------------------------------------------------------------------
# 6. Variance sheets
# ---------------------------------------------------------------------------
TOLS = "0.000000001"
GREEN_FILL = PatternFill("solid", fgColor="C6EFCE")
RED_FILL = PatternFill("solid", fgColor="FFC7CE")
GREEN_FONT = Font(color="006100")
RED_FONT = Font(color="9C0006")
FMT_VAR = '#,##0.0;(#,##0.0);"-"'
FMT_VAR_T = '#,##0;(#,##0);"-"'
FMT_VAR_RS = '+#,##0.00;-#,##0.00;0.00'


def var_fmt(key, typ, fmt):
    if typ == "ratio":
        return FMT_VAR_RS if key == "r_nrkg" else FMT_PP
    return FMT_VAR_T if fmt == FMT_T else FMT_VAR


def cf_sign(ws, rng, r1, c1):
    tl = f"{c1}{r1}"
    ws.conditional_formatting.add(rng, FormulaRule(formula=[f"AND(ISNUMBER({tl}),$A{r1}*{tl}>{TOLS})"],
                                                   fill=GREEN_FILL, font=GREEN_FONT))
    ws.conditional_formatting.add(rng, FormulaRule(formula=[f"AND(ISNUMBER({tl}),$A{r1}*{tl}<-{TOLS})"],
                                                   fill=RED_FILL, font=RED_FONT))


def cf_fu(ws, rng):
    ws.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=['"F"'], fill=GREEN_FILL, font=GREEN_FONT))
    ws.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=['"U"'], fill=RED_FILL, font=RED_FONT))


def fu_formula(vcell, r):
    return f'=IF(ABS({vcell})<{TOLS},"-",IF($A{r}*{vcell}>0,"F","U"))'


def pct_formula(a, b):
    return f'=IF({b}=0,"n/a",({a}-{b})/ABS({b}))'


def build_var_monthly(ws):
    title(ws, "Variance_Monthly: actual vs budget by month, Apr-Sep 2026",
          "Variance = actual − budget. F = favourable, U = unfavourable: revenue, profit or volume above budget is F; "
          "a cost above budget is U. Column A holds the sign used (+1 revenue/profit, −1 cost).",
          "₹ crore unless stated; volume in tonnes; ratio variances in percentage points.")
    put(ws, "D4", "Actual − budget", "text", bold=True)
    put(ws, "L4", "Variance % of budget", "text", bold=True)
    put(ws, "T4", "Favourable / unfavourable", "text", bold=True)
    hdr = {"A": "Sign", "B": "Line item", "C": "Unit", "J": "H1", "R": "H1", "Z": "H1",
           "AB": "Check: Σ months − H1"}
    header_row(ws, 5, hdr)
    for i, c in enumerate(AC):
        for base in (4, 12, 20):
            put(ws, f"{col(base + i)}5", f"={ASM}!{c}$4", "link", FMT_DATE, bold=True, fill=HDR_FILL, align="center")
    VR = {}
    r = 6
    for key, label, unit, typ, sign, fmt in PL_SPEC:
        VR[key] = r
        if typ == "sub":
            put(ws, f"B{r}", label, "text", bold=True, italic=True)
            r += 1
            continue
        put(ws, f"A{r}", sign, "note", "0")
        put(ws, f"B{r}", label, "text", bold=(typ == "dtotal"))
        put(ws, f"C{r}", "pp" if typ == "ratio" and key != "r_nrkg" else unit, "note")
        vf = var_fmt(key, typ, fmt)
        pr = R[key]
        for i, c in enumerate(AC):
            vc = col(4 + i)
            put(ws, f"{vc}{r}", f"={SA}!{c}{pr}-{SB}!{c}{pr}", "calc", vf, bold=(typ == "dtotal"))
            if typ != "ratio":
                put(ws, f"{col(12 + i)}{r}", pct_formula(f"{SA}!{c}{pr}", f"{SB}!{c}{pr}"), "calc", FMT_PCT)
            put(ws, f"{col(20 + i)}{r}", fu_formula(f"{vc}{r}", r), "calc", align="center")
        put(ws, f"J{r}", f"={SA}!J{pr}-{SB}!P{pr}", "calc", vf, bold=True, fill=TOT_FILL)
        if typ != "ratio":
            put(ws, f"R{r}", pct_formula(f"{SA}!J{pr}", f"{SB}!P{pr}"), "calc", FMT_PCT, fill=TOT_FILL)
            put(ws, f"AB{r}", f"=ABS(SUM(D{r}:I{r})-J{r})", "calc", FMT_SCI, color="808080")
        put(ws, f"Z{r}", fu_formula(f"J{r}", r), "calc", align="center", fill=TOT_FILL)
        r += 1
    last = r - 1
    cf_sign(ws, f"D6:J{last}", 6, "D")
    cf_sign(ws, f"L6:R{last}", 6, "L")
    cf_fu(ws, f"T6:Z{last}")
    widths(ws, {"A": 5, "B": 34, "C": 7, **{col(i): 8.5 for i in range(4, 27)}, "K": 2, "S": 2, "AA": 2, "AB": 12})
    for i in range(20, 27):
        ws.column_dimensions[col(i)].width = 7.5
    ws.freeze_panes = "D6"
    add_check("Variance_Monthly", "Sum of monthly variances = H1 variance for every ₹ and volume line",
              f"=MAX(Variance_Monthly!AB6:AB{last})")
    return VR


def build_var_ytd(ws, VR):
    title(ws, "Variance_YTD: September 2026 month and year to date (Apr-Sep) vs budget",
          "Variance = actual − budget; F/U sign logic as in Variance_Monthly (revenue up = F, cost up = U).",
          "₹ crore unless stated; volume in tonnes; ratio variances in percentage points.")
    put(ws, "D4", "Month: Sep-2026", "text", bold=True)
    put(ws, "J4", "Year to date: Apr-Sep 2026 (H1)", "text", bold=True)
    header_row(ws, 5, {"A": "Sign", "B": "Line item", "C": "Unit", "D": "Budget", "E": "Actual", "F": "Variance",
                       "G": "Var %", "H": "F/U", "J": "Budget", "K": "Actual", "L": "Variance", "M": "Var %",
                       "N": "F/U", "O": "Check: YTD − Σ months"})
    YR = {}
    r = 6
    for key, label, unit, typ, sign, fmt in PL_SPEC:
        YR[key] = r
        if typ == "sub":
            put(ws, f"B{r}", label, "text", bold=True, italic=True)
            r += 1
            continue
        pr = R[key]
        bold = typ == "dtotal"
        vf = var_fmt(key, typ, fmt)
        put(ws, f"A{r}", sign, "note", "0")
        put(ws, f"B{r}", label, "text", bold=bold)
        put(ws, f"C{r}", unit, "note")
        put(ws, f"D{r}", f"={SB}!I{pr}", "link", fmt, bold=bold)
        put(ws, f"E{r}", f"={SA}!I{pr}", "link", fmt, bold=bold)
        put(ws, f"F{r}", f"=E{r}-D{r}", "calc", vf, bold=bold)
        put(ws, f"J{r}", f"={SB}!P{pr}", "link", fmt, bold=bold)
        put(ws, f"K{r}", f"={SA}!J{pr}", "link", fmt, bold=bold)
        put(ws, f"L{r}", f"=K{r}-J{r}", "calc", vf, bold=bold)
        if typ != "ratio":
            put(ws, f"G{r}", pct_formula(f"E{r}", f"D{r}"), "calc", FMT_PCT)
            put(ws, f"M{r}", pct_formula(f"K{r}", f"J{r}"), "calc", FMT_PCT)
        put(ws, f"H{r}", fu_formula(f"F{r}", r), "calc", align="center")
        put(ws, f"N{r}", fu_formula(f"L{r}", r), "calc", align="center")
        put(ws, f"O{r}", f"=ABS(L{r}-Variance_Monthly!J{VR[key]})", "calc", FMT_SCI, color="808080")
        r += 1
    last = r - 1
    cf_sign(ws, f"F6:G{last}", 6, "F")
    cf_sign(ws, f"L6:M{last}", 6, "L")
    cf_fu(ws, f"H6:H{last}")
    cf_fu(ws, f"N6:N{last}")
    widths(ws, {"A": 5, "B": 34, "C": 7, "D": 10, "E": 10, "F": 10, "G": 8, "H": 5, "I": 2, "J": 10, "K": 10,
                "L": 10, "M": 8, "N": 5, "O": 14})
    ws.freeze_panes = "D6"
    add_check("Variance_YTD", "YTD variance = sum of monthly variances (Variance_Monthly H1) for every line",
              f"=MAX(Variance_YTD!O6:O{last})")
    return YR


# ---------------------------------------------------------------------------
# 7. Bridges (used for H1 actual vs budget and FY forecast vs budget)
# ---------------------------------------------------------------------------
def write_bridge_detail(ws, top, Aref, Bref, labA, labB, A, sheet):
    CONV = f"{ASM}!$D${A['conv']}"
    out = {}
    r = top
    section(ws, r, f"Bridge workings: {labA} vs {labB} by product line (links to the P&L sheets)", 1, 16)
    r += 1
    # T1 inputs
    sub(ws, r, "T1. Inputs by product line (₹ crore unless stated)")
    r += 1
    heads = {"B": "Product line", "C": f"{labB} volume (t)", "D": f"{labA} volume (t)", "E": f"{labB} net revenue",
             "F": f"{labA} net revenue", "G": f"{labB} gross sales", "H": f"{labA} gross sales",
             "I": f"{labB} trade spend", "J": f"{labA} trade spend", "K": f"{labB} material",
             "L": f"{labA} material", "M": f"{labB} packaging + conversion", "N": f"{labA} packaging + conversion",
             "O": f"{labB} gross profit", "P": f"{labA} gross profit"}
    header_row(ws, r, heads)
    ws.row_dimensions[r].height = 42
    r += 1
    t1 = {}
    for l in LK:
        t1[l] = r
        put(ws, f"B{r}", LN[l], "text")
        pairs = [("C", Bref(f"vol_{l}")), ("D", Aref(f"vol_{l}")), ("E", Bref(f"nr_{l}")), ("F", Aref(f"nr_{l}")),
                 ("G", Bref(f"gs_{l}")), ("H", Aref(f"gs_{l}")), ("I", Bref(f"ts_{l}")), ("J", Aref(f"ts_{l}")),
                 ("K", Bref(f"matl_{l}")), ("L", Aref(f"matl_{l}")),
                 ("M", f"{Bref(f'pack_{l}')}+{Bref(f'conv_{l}')}"), ("N", f"{Aref(f'pack_{l}')}+{Aref(f'conv_{l}')}"),
                 ("O", Bref(f"gpl_{l}")), ("P", Aref(f"gpl_{l}"))]
        for cc, ref in pairs:
            put(ws, f"{cc}{r}", "=" + ref, "link", FMT_T if cc in "CD" else FMT_CR2)
        r += 1
    rt1 = r
    put(ws, f"B{r}", "Total", "text", bold=True)
    for cc in "CDEFGHIJKLMNOP":
        put(ws, f"{cc}{r}", f"=SUM({cc}{t1['NAM']}:{cc}{t1['BEV']})", "calc", FMT_T if cc in "CD" else FMT_CR2,
            bold=True, fill=TOT_FILL)
    r += 2

    # T2 PVM
    sub(ws, r, "T2. Net revenue price-volume-mix (PVM) by product line")
    r += 1
    header_row(ws, r, {"B": "Product line", "C": f"{labB} volume share", "D": f"{labA} volume share",
                       "E": f"{labB} net price (₹/kg)", "F": f"{labA} net price (₹/kg)", "G": "Net revenue variance",
                       "H": "Volume effect", "I": "Mix effect", "J": "Price effect", "K": "Volume + mix + price",
                       "L": "Difference"})
    ws.row_dimensions[r].height = 42
    r += 1
    t2 = {}
    for l in LK:
        t2[l] = r
        a = t1[l]
        put(ws, f"B{r}", LN[l], "text")
        put(ws, f"C{r}", f"=IF(C${rt1}=0,0,C{a}/C${rt1})", "calc", FMT_PCT)
        put(ws, f"D{r}", f"=IF(D${rt1}=0,0,D{a}/D${rt1})", "calc", FMT_PCT)
        put(ws, f"E{r}", f"=IF(C{a}=0,0,E{a}/(C{a}*{CONV}))", "calc", FMT_RS)
        put(ws, f"F{r}", f"=IF(D{a}=0,0,F{a}/(D{a}*{CONV}))", "calc", FMT_RS)
        put(ws, f"G{r}", f"=F{a}-E{a}", "calc", FMT_CR2)
        put(ws, f"H{r}", f"=(D${rt1}-C${rt1})*C{r}*E{r}*{CONV}", "calc", FMT_CR2)
        put(ws, f"I{r}", f"=(D{r}-C{r})*D${rt1}*E{r}*{CONV}", "calc", FMT_CR2)
        put(ws, f"J{r}", f"=(F{r}-E{r})*D{a}*{CONV}", "calc", FMT_CR2)
        put(ws, f"K{r}", f"=H{r}+I{r}+J{r}", "calc", FMT_CR2)
        put(ws, f"L{r}", f"=K{r}-G{r}", "calc", FMT_SCI)
        r += 1
    rt2 = r
    put(ws, f"B{r}", "Total", "text", bold=True)
    put(ws, f"C{r}", f"=SUM(C{t2['NAM']}:C{t2['BEV']})", "calc", FMT_PCT, bold=True, fill=TOT_FILL)
    put(ws, f"D{r}", f"=SUM(D{t2['NAM']}:D{t2['BEV']})", "calc", FMT_PCT, bold=True, fill=TOT_FILL)
    put(ws, f"E{r}", f"=IF(C{rt1}=0,0,E{rt1}/(C{rt1}*{CONV}))", "calc", FMT_RS, bold=True, fill=TOT_FILL)
    put(ws, f"F{r}", f"=IF(D{rt1}=0,0,F{rt1}/(D{rt1}*{CONV}))", "calc", FMT_RS, bold=True, fill=TOT_FILL)
    for cc in "GHIJK":
        put(ws, f"{cc}{r}", f"=SUM({cc}{t2['NAM']}:{cc}{t2['BEV']})", "calc", FMT_CR2, bold=True, fill=TOT_FILL)
    put(ws, f"L{r}", f"=K{r}-G{r}", "calc", FMT_SCI, bold=True, fill=TOT_FILL)
    r += 1
    rv2 = r
    put(ws, f"B{r}", "Volume effect by the total formula: (actual − budget total volume) × budget average net price",
        "note", italic=True)
    put(ws, f"H{r}", f"=(D{rt1}-C{rt1})*E{rt2}*{CONV}", "calc", FMT_CR2)
    put(ws, f"L{r}", f"=H{r}-H{rt2}", "calc", FMT_SCI)
    r += 2

    # T3 price split
    sub(ws, r, "T3. Price effect split: list price vs trade-spend rate and channel mix")
    r += 1
    header_row(ws, r, {"B": "Product line", "C": f"{labB} list price (₹/kg)", "D": f"{labA} list price (₹/kg)",
                       "E": f"{labB} trade-spend rate", "F": f"{labA} trade-spend rate",
                       "G": "List price effect", "H": "Trade-spend rate & channel mix effect", "I": "Sum",
                       "J": "Price effect (T2)", "K": "Difference"})
    ws.row_dimensions[r].height = 42
    r += 1
    t3 = {}
    for l in LK:
        t3[l] = r
        a = t1[l]
        put(ws, f"B{r}", LN[l], "text")
        put(ws, f"C{r}", f"=IF(C{a}=0,0,G{a}/(C{a}*{CONV}))", "calc", FMT_RS)
        put(ws, f"D{r}", f"=IF(D{a}=0,0,H{a}/(D{a}*{CONV}))", "calc", FMT_RS)
        put(ws, f"E{r}", f"=IF(G{a}=0,0,I{a}/G{a})", "calc", FMT_PCT2)
        put(ws, f"F{r}", f"=IF(H{a}=0,0,J{a}/H{a})", "calc", FMT_PCT2)
        put(ws, f"G{r}", f"=(D{r}-C{r})*(1-E{r})*D{a}*{CONV}", "calc", FMT_CR2)
        put(ws, f"H{r}", f"=D{r}*(E{r}-F{r})*D{a}*{CONV}", "calc", FMT_CR2)
        put(ws, f"I{r}", f"=G{r}+H{r}", "calc", FMT_CR2)
        put(ws, f"J{r}", f"=J{t2[l]}", "calc", FMT_CR2)
        put(ws, f"K{r}", f"=I{r}-J{r}", "calc", FMT_SCI)
        r += 1
    rt3 = r
    put(ws, f"B{r}", "Total", "text", bold=True)
    put(ws, f"C{r}", f"=IF(C{rt1}=0,0,G{rt1}/(C{rt1}*{CONV}))", "calc", FMT_RS, bold=True, fill=TOT_FILL)
    put(ws, f"D{r}", f"=IF(D{rt1}=0,0,H{rt1}/(D{rt1}*{CONV}))", "calc", FMT_RS, bold=True, fill=TOT_FILL)
    put(ws, f"E{r}", f"=IF(G{rt1}=0,0,I{rt1}/G{rt1})", "calc", FMT_PCT2, bold=True, fill=TOT_FILL)
    put(ws, f"F{r}", f"=IF(H{rt1}=0,0,J{rt1}/H{rt1})", "calc", FMT_PCT2, bold=True, fill=TOT_FILL)
    for cc in "GHIJ":
        put(ws, f"{cc}{r}", f"=SUM({cc}{t3['NAM']}:{cc}{t3['BEV']})", "calc", FMT_CR2, bold=True, fill=TOT_FILL)
    put(ws, f"K{r}", f"=I{r}-J{r}", "calc", FMT_SCI, bold=True, fill=TOT_FILL)
    r += 2

    # T4 GP bridge
    sub(ws, r, "T4. Gross-profit bridge by product line")
    r += 1
    header_row(ws, r, {"B": "Product line", "C": f"{labB} gross profit (₹/kg)", "D": f"{labB} material (₹/kg)",
                       "E": f"{labA} material (₹/kg)", "F": f"{labB} pack + conv (₹/kg)",
                       "G": f"{labA} pack + conv (₹/kg)", "H": "Volume effect", "I": "Mix effect",
                       "J": "Price effect", "K": "Material rate", "L": "Packaging & conversion rate", "M": "Sum",
                       "N": "Gross profit variance", "O": "Difference"})
    ws.row_dimensions[r].height = 42
    r += 1
    t4 = {}
    for l in LK:
        t4[l] = r
        a = t1[l]
        put(ws, f"B{r}", LN[l], "text")
        put(ws, f"C{r}", f"=IF(C{a}=0,0,O{a}/(C{a}*{CONV}))", "calc", FMT_RS)
        put(ws, f"D{r}", f"=IF(C{a}=0,0,K{a}/(C{a}*{CONV}))", "calc", FMT_RS)
        put(ws, f"E{r}", f"=IF(D{a}=0,0,L{a}/(D{a}*{CONV}))", "calc", FMT_RS)
        put(ws, f"F{r}", f"=IF(C{a}=0,0,M{a}/(C{a}*{CONV}))", "calc", FMT_RS)
        put(ws, f"G{r}", f"=IF(D{a}=0,0,N{a}/(D{a}*{CONV}))", "calc", FMT_RS)
        put(ws, f"H{r}", f"=(D${rt1}-C${rt1})*C{t2[l]}*C{r}*{CONV}", "calc", FMT_CR2)
        put(ws, f"I{r}", f"=(D{t2[l]}-C{t2[l]})*D${rt1}*C{r}*{CONV}", "calc", FMT_CR2)
        put(ws, f"J{r}", f"=J{t2[l]}", "calc", FMT_CR2)
        put(ws, f"K{r}", f"=-(E{r}-D{r})*D{a}*{CONV}", "calc", FMT_CR2)
        put(ws, f"L{r}", f"=-(G{r}-F{r})*D{a}*{CONV}", "calc", FMT_CR2)
        put(ws, f"M{r}", f"=SUM(H{r}:L{r})", "calc", FMT_CR2)
        put(ws, f"N{r}", f"=P{a}-O{a}", "calc", FMT_CR2)
        put(ws, f"O{r}", f"=M{r}-N{r}", "calc", FMT_SCI)
        r += 1
    rt4 = r
    put(ws, f"B{r}", "Total", "text", bold=True)
    put(ws, f"C{r}", f"=IF(C{rt1}=0,0,O{rt1}/(C{rt1}*{CONV}))", "calc", FMT_RS, bold=True, fill=TOT_FILL)
    put(ws, f"D{r}", f"=IF(C{rt1}=0,0,K{rt1}/(C{rt1}*{CONV}))", "calc", FMT_RS, bold=True, fill=TOT_FILL)
    put(ws, f"E{r}", f"=IF(D{rt1}=0,0,L{rt1}/(D{rt1}*{CONV}))", "calc", FMT_RS, bold=True, fill=TOT_FILL)
    put(ws, f"F{r}", f"=IF(C{rt1}=0,0,M{rt1}/(C{rt1}*{CONV}))", "calc", FMT_RS, bold=True, fill=TOT_FILL)
    put(ws, f"G{r}", f"=IF(D{rt1}=0,0,N{rt1}/(D{rt1}*{CONV}))", "calc", FMT_RS, bold=True, fill=TOT_FILL)
    for cc in "HIJKLMN":
        put(ws, f"{cc}{r}", f"=SUM({cc}{t4['NAM']}:{cc}{t4['BEV']})", "calc", FMT_CR2, bold=True, fill=TOT_FILL)
    put(ws, f"O{r}", f"=M{r}-N{r}", "calc", FMT_SCI, bold=True, fill=TOT_FILL)
    r += 1
    rv4 = r
    put(ws, f"B{r}", "Volume effect by the total formula: (actual − budget total volume) × budget average gross "
                     "profit per kg", "note", italic=True)
    put(ws, f"H{r}", f"=(D{rt1}-C{rt1})*C{rt4}*{CONV}", "calc", FMT_CR2)
    put(ws, f"O{r}", f"=H{r}-H{rt4}", "calc", FMT_SCI)
    r += 2

    # T5 material by input
    sub(ws, r, "T5. Material rate effect by input (standard BOM, so the whole material variance is price)")
    r += 1
    rcols = dict(zip(RK + ["OTH"], "CDEFGH"))
    header_row(ws, r, {"B": "Product line", **{rcols[rk]: RN[rk] for rk in RK}, "H": "Other ingredients",
                       "I": "Total", "J": "Material rate (T4)", "K": "Difference"})
    ws.row_dimensions[r].height = 30
    r += 1
    t5 = {}
    for l in LK:
        t5[l] = r
        a = t1[l]
        put(ws, f"B{r}", LN[l], "text")
        for rk in RK + ["OTH"]:
            key = f"matlr_{l}_{rk}" if rk != "OTH" else f"oth_{l}"
            put(ws, f"{rcols[rk]}{r}", f"=-({Aref(key)}-IF(C{a}=0,0,{Bref(key)}*D{a}/C{a}))", "calc", FMT_CR2)
        put(ws, f"I{r}", f"=SUM(C{r}:H{r})", "calc", FMT_CR2)
        put(ws, f"J{r}", f"=K{t4[l]}", "calc", FMT_CR2)
        put(ws, f"K{r}", f"=I{r}-J{r}", "calc", FMT_SCI)
        r += 1
    rt5 = r
    put(ws, f"B{r}", "Total", "text", bold=True)
    for cc in "CDEFGHIJ":
        put(ws, f"{cc}{r}", f"=SUM({cc}{t5['NAM']}:{cc}{t5['BEV']})", "calc", FMT_CR2, bold=True, fill=TOT_FILL)
    put(ws, f"K{r}", f"=I{r}-J{r}", "calc", FMT_SCI, bold=True, fill=TOT_FILL)
    r += 1
    out.update(dict(t1=t1, rt1=rt1, t2=t2, rt2=rt2, rv2=rv2, t3=t3, rt3=rt3, t4=t4, rt4=rt4, rv4=rv4, t5=t5, rt5=rt5,
                    rcols=rcols, end=r))
    s = f"'{ws.title}'!" if " " in ws.title else f"{ws.title}!"
    add_check(sheet, f"{labA} vs {labB}: revenue PVM volume + mix + price = net revenue variance (total)",
              f"={s}L{rt2}")
    add_check(sheet, f"{labA} vs {labB}: revenue PVM reconciles for each product line",
              f"=SUMPRODUCT(ABS({s}L{t2['NAM']}:L{t2['BEV']}))")
    add_check(sheet, f"{labA} vs {labB}: volume effect by line = total formula (ΔV × budget average price)",
              f"={s}L{rv2}")
    add_check(sheet, f"{labA} vs {labB}: list price + trade-spend effects = price effect",
              f"=SUMPRODUCT(ABS({s}K{t3['NAM']}:K{rt3}))")
    add_check(sheet, f"{labA} vs {labB}: gross-profit bridge reconciles (each line and total)",
              f"=SUMPRODUCT(ABS({s}O{t4['NAM']}:O{rt4}))+ABS({s}O{rv4})")
    add_check(sheet, f"{labA} vs {labB}: material rate by input = material rate effect",
              f"=SUMPRODUCT(ABS({s}K{t5['NAM']}:K{rt5}))")
    return out


EB_ITEMS = [("vol", "Volume (at budget gross profit per kg)"), ("mix", "Mix (product lines)"),
            ("lp", "List price"), ("tsr", "Trade-spend rate & channel mix"), ("mrate", "Material rate"),
            ("pcrate", "Packaging & conversion rate"), ("freight", "Freight & distribution"),
            ("ap", "Advertising & promotion"), ("emp", "Employee cost"), ("oth", "Other overheads")]


def write_bridge_summary(ws, top, det, Aref, Bref, labA_, labB_, sheet, period):
    t = det
    out = {}
    labA, labB = labA_[:1].upper() + labA_[1:], labB_[:1].upper() + labB_[1:]
    r = top
    section(ws, r, f"{period} bridges: {labB_} to {labA_} (₹ crore; positive = adds to profit)", 1, 16)
    r += 1
    # revenue bridge
    header_row(ws, r, {"B": "Net revenue bridge", "C": "₹ crore", "D": "Basis"})
    r += 1
    rows = [("start", f"{labB} net revenue", f"=E{t['rt1']}", "T1"),
            ("vol", "Volume", f"=H{t['rt2']}", "Σ lines: (ΔV total) × budget share × budget net price"),
            ("mix", "Mix (product lines)", f"=I{t['rt2']}", "Σ lines: (actual − budget share) × actual total volume × budget price"),
            ("lp", "List price", f"=G{t['rt3']}", "Σ lines: Δ list price × (1 − budget trade rate) × actual volume"),
            ("tsr", "Trade-spend rate & channel mix", f"=H{t['rt3']}", "Σ lines: actual list price × Δ trade rate × actual volume")]
    rev = {}
    first = r
    for k, lab, f, basis in rows:
        rev[k] = r
        put(ws, f"B{r}", lab, "text", bold=(k == "start"))
        put(ws, f"C{r}", f, "calc", FMT_CR2, bold=(k == "start"))
        put(ws, f"D{r}", basis, "note", italic=True)
        r += 1
    rev["end"] = r
    put(ws, f"B{r}", f"{labA} net revenue (bridge)", "text", bold=True)
    put(ws, f"C{r}", f"=SUM(C{first}:C{r - 1})", "calc", FMT_CR2, bold=True, fill=TOT_FILL)
    r += 1
    rev["pl"] = r
    put(ws, f"B{r}", f"{labA} net revenue (P&L)", "text")
    put(ws, f"C{r}", "=" + Aref("nr_tot"), "link", FMT_CR2)
    r += 1
    rev["diff"] = r
    put(ws, f"B{r}", "Difference (must be zero)", "note", italic=True)
    put(ws, f"C{r}", f"=C{rev['end']}-C{rev['pl']}", "calc", FMT_SCI)
    r += 2
    out["rev"] = rev
    # gross profit bridge
    header_row(ws, r, {"B": "Gross-profit bridge", "C": "₹ crore", "D": "Basis"})
    r += 1
    rows = [("start", f"{labB} gross profit", f"=O{t['rt1']}", "T1"),
            ("vol", "Volume", f"=H{t['rt4']}", "Σ lines: (ΔV total) × budget share × budget gross profit per kg"),
            ("mix", "Mix (product lines)", f"=I{t['rt4']}", "Σ lines: Δ share × actual total volume × budget gross profit per kg"),
            ("price", "Price (net of trade spend)", f"=J{t['rt4']}", "Same as the PVM price effect"),
            ("mrate", "Material rate", f"=K{t['rt4']}", "−Σ lines: Δ material ₹/kg × actual volume"),
            ("pcrate", "Packaging & conversion rate", f"=L{t['rt4']}", "−Σ lines: Δ (packaging + conversion) ₹/kg × actual volume")]
    gp = {}
    first = r
    for k, lab, f, basis in rows:
        gp[k] = r
        put(ws, f"B{r}", lab, "text", bold=(k == "start"))
        put(ws, f"C{r}", f, "calc", FMT_CR2, bold=(k == "start"))
        put(ws, f"D{r}", basis, "note", italic=True)
        r += 1
    gp["end"] = r
    put(ws, f"B{r}", f"{labA} gross profit (bridge)", "text", bold=True)
    put(ws, f"C{r}", f"=SUM(C{first}:C{r - 1})", "calc", FMT_CR2, bold=True, fill=TOT_FILL)
    r += 1
    gp["pl"] = r
    put(ws, f"B{r}", f"{labA} gross profit (P&L)", "text")
    put(ws, f"C{r}", "=" + Aref("gp"), "link", FMT_CR2)
    r += 1
    gp["diff"] = r
    put(ws, f"B{r}", "Difference (must be zero)", "note", italic=True)
    put(ws, f"C{r}", f"=C{gp['end']}-C{gp['pl']}", "calc", FMT_SCI)
    r += 2
    out["gp"] = gp
    # EBITDA bridge
    header_row(ws, r, {"B": "EBITDA bridge", "C": "₹ crore", "D": "Basis"})
    r += 1
    src = {"vol": f"=H{t['rt4']}", "mix": f"=I{t['rt4']}", "lp": f"=G{t['rt3']}", "tsr": f"=H{t['rt3']}",
           "mrate": f"=K{t['rt4']}", "pcrate": f"=L{t['rt4']}",
           "freight": f"=-({Aref('freight')}-{Bref('freight')})", "ap": f"=-({Aref('ap')}-{Bref('ap')})",
           "emp": f"=-({Aref('emp')}-{Bref('emp')})", "oth": f"=-({Aref('oth')}-{Bref('oth')})"}
    basis = {"vol": "Revenue and COGS volume effect at budget gross profit per kg",
             "mix": "Shift between product lines at budget gross profit per kg",
             "lp": "T3: list price changes (namkeen +4% from 1-Aug-2026; biscuits +3% from 1-Oct-2026 in the forecast)",
             "tsr": "T3: trade-spend rate changes, including the channel shift to e-com & QC",
             "mrate": "T5: input prices (edible oil, sugar, wheat flour, potato, fruit pulp, other)",
             "pcrate": "T4: packaging and conversion cost per kg",
             "freight": "−(actual − budget) freight, incl. one-off surcharge",
             "ap": "−(actual − budget) A&P", "emp": "−(actual − budget) employee cost",
             "oth": "−(actual − budget) other overheads"}
    eb = {}
    eb["start"] = r
    put(ws, f"B{r}", f"{labB} EBITDA", "text", bold=True)
    put(ws, f"C{r}", "=" + Bref("ebitda"), "link", FMT_CR2, bold=True)
    r += 1
    for k, lab in EB_ITEMS:
        eb[k] = r
        put(ws, f"B{r}", lab, "text")
        put(ws, f"C{r}", src[k], "calc", FMT_CR2)
        put(ws, f"D{r}", basis[k], "note", italic=True)
        r += 1
    eb["end"] = r
    put(ws, f"B{r}", f"{labA} EBITDA (bridge)", "text", bold=True)
    put(ws, f"C{r}", f"=SUM(C{eb['start']}:C{r - 1})", "calc", FMT_CR2, bold=True, fill=TOT_FILL)
    r += 1
    eb["pl"] = r
    put(ws, f"B{r}", f"{labA} EBITDA (P&L)", "text")
    put(ws, f"C{r}", "=" + Aref("ebitda"), "link", FMT_CR2)
    r += 1
    eb["diff"] = r
    put(ws, f"B{r}", "Difference (must be zero)", "note", italic=True)
    put(ws, f"C{r}", f"=C{eb['end']}-C{eb['pl']}", "calc", FMT_SCI)
    r += 1
    out["eb"] = eb
    out["end"] = r
    s = f"{ws.title}!"
    add_check(sheet, f"{period}: net revenue bridge reconciles to the P&L", f"={s}C{rev['diff']}")
    add_check(sheet, f"{period}: gross-profit bridge reconciles to the P&L", f"={s}C{gp['diff']}")
    add_check(sheet, f"{period}: EBITDA bridge reconciles to the P&L", f"={s}C{eb['diff']}")
    return out


def build_pvm(ws, A):
    title(ws, "PVM_Bridge: H1 FY2027 actual vs budget (Apr-Sep 2026)",
          "Net revenue split into volume, mix and price; gross-profit and EBITDA bridges from budget to actual. "
          "Every component is a formula on the P&L sheets; each bridge must reconcile to zero difference.",
          "Formulas: volume = (ΔV total) × budget average price; mix = Σ (Δ share) × actual total volume × budget "
          "line price; price = Σ (Δ price) × actual line volume. ₹ crore.")
    Aref = lambda k: f"{SA}!$J${R[k]}"
    Bref = lambda k: f"{SB}!$P${R[k]}"
    det = write_bridge_detail(ws, 50, Aref, Bref, "Actual", "Budget", A, "PVM_Bridge")
    summ = write_bridge_summary(ws, 5, det, Aref, Bref, "actual", "budget", "PVM_Bridge", "H1")
    widths(ws, {"A": 3, "B": 44, "C": 12, "D": 12, **{col(i): 12 for i in range(5, 17)}})
    ws.column_dimensions["D"].width = 12
    return det, summ


# ---------------------------------------------------------------------------
# 8. FY_Outlook
# ---------------------------------------------------------------------------
def build_outlook(ws, A, AD, FD):
    CONV = f"{ASM}!$D${A['conv']}"
    title(ws, "FY_Outlook: FY2027 budget vs 6+6 forecast, risks and opportunities",
          "6+6 forecast = Apr-Sep actuals + Oct-Mar reforecast (case selected on the Cover). Variance = forecast − "
          "budget; F/U sign logic as in the variance sheets.",
          "₹ crore unless stated; volume in tonnes; ratio variances in percentage points.")
    section(ws, 5, "Full-year P&L", 1, 16)
    header_row(ws, 6, {"A": "Sign", "B": "Line item", "C": "Unit", "D": "Budget FY", "E": "6+6 forecast FY",
                       "F": "Variance", "G": "Var %", "H": "F/U", "J": "Budget H1", "K": "Actual H1",
                       "L": "Variance H1", "N": "Budget H2", "O": "Forecast H2", "P": "Variance H2"})
    OL = {}
    r = 7
    for key, label, unit, typ, sign, fmt in PL_SPEC:
        OL[key] = r
        if typ == "sub":
            put(ws, f"B{r}", label, "text", bold=True, italic=True)
            r += 1
            continue
        pr = R[key]
        bold = typ == "dtotal"
        vf = var_fmt(key, typ, fmt)
        put(ws, f"A{r}", sign, "note", "0")
        put(ws, f"B{r}", label, "text", bold=bold)
        put(ws, f"C{r}", unit, "note")
        for cc, ref in (("D", f"{SB}!R{pr}"), ("E", f"{SF}!R{pr}"), ("J", f"{SB}!P{pr}"), ("K", f"{SF}!P{pr}"),
                        ("N", f"{SB}!Q{pr}"), ("O", f"{SF}!Q{pr}")):
            put(ws, f"{cc}{r}", "=" + ref, "link", fmt, bold=bold)
        put(ws, f"F{r}", f"=E{r}-D{r}", "calc", vf, bold=bold)
        put(ws, f"L{r}", f"=K{r}-J{r}", "calc", vf, bold=bold)
        put(ws, f"P{r}", f"=O{r}-N{r}", "calc", vf, bold=bold)
        if typ != "ratio":
            put(ws, f"G{r}", pct_formula(f"E{r}", f"D{r}"), "calc", FMT_PCT)
        put(ws, f"H{r}", fu_formula(f"F{r}", r), "calc", align="center")
        r += 1
    last = r - 1
    cf_sign(ws, f"F7:G{last}", 7, "F")
    cf_sign(ws, f"L7:L{last}", 7, "L")
    cf_sign(ws, f"P7:P{last}", 7, "P")
    cf_fu(ws, f"H7:H{last}")
    add_check("FY_Outlook", "FY variance = H1 variance + H2 variance for every ₹ and volume line",
              f"=SUMPRODUCT(ABS(FY_Outlook!F{OL['vol_NAM']}:F{OL['pat']}-FY_Outlook!L{OL['vol_NAM']}:L{OL['pat']}"
              f"-FY_Outlook!P{OL['vol_NAM']}:P{OL['pat']}))")
    r += 1

    # Risks and opportunities
    section(ws, r, "Risks and opportunities (not included in the 6+6 forecast; sized against the Base case)", 1, 16)
    OL["ro_section"] = r
    r += 1
    put(ws, f"B{r}", f'=IF({CASE_CELL}=1,"Base case selected: R&O sizes are on the same basis as the forecast.",'
                     f'"Note: a non-Base case is selected; some R&O items overlap with the case overlays.")',
        "calc", italic=True)
    r += 1
    header_row(ws, r, {"B": "Item", "C": "Type", "D": "Assumption", "E": "Unit", "F": "FY EBITDA impact (₹ cr)",
                       "G": "Probability", "H": "Probability-weighted (₹ cr)", "I": "How it is sized"})
    ws.row_dimensions[r].height = 30
    r += 1
    ro = {}
    qc_rows = {}
    # helper table for QC economics placed after the R&O block; reserve row numbers now
    n_items = 6
    first_item = r
    tot_row = first_item + n_items
    qc_top = tot_row + 8
    for i, l in enumerate(LK):
        qc_rows[l] = qc_top + 1 + i
    oil_rng = f"{SF}!J{FD['rm_OIL']}:O{FD['rm_OIL']}"
    oilq_rng = f"{SF}!J{R['rmq_OIL']}:O{R['rmq_OIL']}"
    sug_rng = f"{SF}!J{FD['rm_SUG']}:O{FD['rm_SUG']}"
    sugq_rng = f"{SF}!J{R['rmq_SUG']}:O{R['rmq_SUG']}"
    gt_terms = "+".join(f"SUM({SF}!L{R[f'vlc_{l}_GT']}:O{R[f'vlc_{l}_GT']})*{SF}!Q{R[f'gpkg_{l}']}" for l in LK)
    items = [
        ("oil", "Edible oil stays at the Sep-26 price for Oct-Mar", "Risk", f"={SA}!$I${AD['rm_OIL']}", "link",
         "₹/kg", FMT_RS, f"=-SUMPRODUCT((D{{r}}-{oil_rng})*{oilq_rng})*{CONV}", 0.30,
         "Oil consumed Oct-Mar at standard BOM × (assumed − forecast price)"),
        ("sug", "Sugar stays at the Sep-26 price for Oct-Mar", "Risk", f"={SA}!$I${AD['rm_SUG']}", "link",
         "₹/kg", FMT_RS, f"=-SUMPRODUCT((D{{r}}-{sug_rng})*{sugq_rng})*{CONV}", 0.30,
         "Sugar consumed Oct-Mar × (assumed − forecast price); new-season supply from Nov makes this less likely"),
        ("gt", "Rural slowdown: General Trade volume below forecast, Dec-Mar", "Risk", -0.03, "input",
         "% of GT t", FMT_PCT, f"=D{{r}}*({gt_terms})*{CONV}", 0.40,
         "GT tonnes Dec-Mar × H2 gross profit per kg by line (ICRA, Sep-2026: weak rural demand)"),
        ("bis", "Second biscuit price increase from Jan-27, no volume loss", "Opportunity", 0.02, "input",
         "%", FMT_PCT, f"=D{{r}}*SUM({SF}!M{R['nr_BIS']}:O{R['nr_BIS']})", 0.40,
         "Jan-Mar biscuit net revenue × price change (trade spend scales with price); on top of the Oct-26 increase"),
        ("qc", "E-com & quick-commerce volume above forecast in H2", "Opportunity", 0.10, "input",
         "% of QC t", FMT_PCT, f"=D{{r}}*SUMPRODUCT(C{qc_rows['NAM']}:C{qc_rows['BEV']},I{qc_rows['NAM']}:I{qc_rows['BEV']})*{CONV}",
         0.40, "H2 QC tonnes × QC contribution per kg (table below)"),
        ("ap", "Festive A&P campaign extended into Dec-26", "Risk", 1.5, "input", "₹ cr", FMT_CR2,
         "=-D{r}", 0.50, "Management decision pending; spend would be incremental to the forecast"),
    ]
    for k, lab, typ, assum, akind, unit, afmt, impact, prob, how in items:
        ro[k] = r
        put(ws, f"B{r}", lab, "text")
        put(ws, f"C{r}", typ, "text")
        put(ws, f"D{r}", assum, akind, afmt, yellow=(akind == "input"))
        put(ws, f"E{r}", unit, "note")
        put(ws, f"F{r}", impact.replace("{r}", str(r)), "calc", FMT_CR2)
        put(ws, f"G{r}", prob, "input", FMT_PCT, yellow=True)
        put(ws, f"H{r}", f"=F{r}*G{r}", "calc", FMT_CR2)
        put(ws, f"I{r}", how, "note", italic=True)
        r += 1
    assert r == tot_row
    ro["risks"] = r
    put(ws, f"B{r}", "Total EBITDA risks", "text", bold=True)
    put(ws, f"F{r}", f'=SUMIF(C{first_item}:C{r - 1},"Risk",F{first_item}:F{r - 1})', "calc", FMT_CR2, bold=True)
    put(ws, f"H{r}", f'=SUMIF(C{first_item}:C{r - 1},"Risk",H{first_item}:H{r - 1})', "calc", FMT_CR2, bold=True)
    r += 1
    ro["opps"] = r
    put(ws, f"B{r}", "Total EBITDA opportunities", "text", bold=True)
    put(ws, f"F{r}", f'=SUMIF(C{first_item}:C{r - 2},"Opportunity",F{first_item}:F{r - 2})', "calc", FMT_CR2,
        bold=True)
    put(ws, f"H{r}", f'=SUMIF(C{first_item}:C{r - 2},"Opportunity",H{first_item}:H{r - 2})', "calc", FMT_CR2,
        bold=True)
    r += 1
    ro["net"] = r
    put(ws, f"B{r}", "Net risks and opportunities", "text", bold=True)
    put(ws, f"F{r}", f"=F{r - 2}+F{r - 1}", "calc", FMT_CR2, bold=True, fill=TOT_FILL)
    put(ws, f"H{r}", f"=H{r - 2}+H{r - 1}", "calc", FMT_CR2, bold=True, fill=TOT_FILL)
    r += 1
    ro["fc"] = r
    put(ws, f"B{r}", "6+6 forecast FY EBITDA (selected case)", "text")
    put(ws, f"H{r}", f"={SF}!R{R['ebitda']}", "link", FMT_CR2)
    r += 1
    ro["adj"] = r
    put(ws, f"B{r}", "Risk-adjusted FY EBITDA (forecast + probability-weighted net R&O)", "text", bold=True)
    put(ws, f"H{r}", f"=H{r - 1}+H{ro['net']}", "calc", FMT_CR2, bold=True, fill=TOT_FILL)
    r += 1
    ro["int"] = r
    put(ws, f"B{r}", "Below EBITDA: +25 bp rate rise from Feb-27 (PBT impact)", "text")
    put(ws, f"C{r}", "Risk", "text")
    put(ws, f"D{r}", 0.0025, "input", FMT_PCT2, yellow=True)
    put(ws, f"E{r}", "% p.a.", "note")
    put(ws, f"F{r}", f"=-D{r}*({SF}!N{FD['borr']}+{SF}!O{FD['borr']})/12", "calc", FMT_CR2)
    put(ws, f"G{r}", 0.40, "input", FMT_PCT, yellow=True)
    put(ws, f"H{r}", f"=F{r}*G{r}", "calc", FMT_CR2)
    put(ws, f"I{r}", "Feb-Mar average borrowings × rate change ÷ 12 (RBI raised repo 25 bp on 7-Oct-2026)", "note",
        italic=True)
    r += 1
    assert r <= qc_top, (r, qc_top)
    r = qc_top
    header_row(ws, r, {"B": "QC economics, H2 forecast", "C": "QC volume (t)", "D": "List price (₹/kg)",
                       "E": "QC trade rate", "F": "QC net price (₹/kg)", "G": "COGS (₹/kg)", "H": "Freight rate",
                       "I": "Contribution (₹/kg)"})
    ws.row_dimensions[r].height = 30
    r += 1
    qc_ts = "+".join(f"{SF}!Q{R[f'tslc_{l}_EQC']}" for l in LK)
    qc_gs = "+".join(f"{SF}!Q{R[f'gslc_{l}_EQC']}" for l in LK)
    for l in LK:
        put(ws, f"B{r}", LN[l], "text")
        put(ws, f"C{r}", f"={SF}!Q{R[f'vlc_{l}_EQC']}", "link", FMT_T)
        put(ws, f"D{r}", f"=IF({SF}!Q{R['vol_' + l]}=0,0,{SF}!Q{R['gs_' + l]}/({SF}!Q{R['vol_' + l]}*{CONV}))",
            "calc", FMT_RS)
        put(ws, f"E{r}", f"=IF(({qc_gs})=0,0,({qc_ts})/({qc_gs}))", "calc", FMT_PCT)
        put(ws, f"F{r}", f"=D{r}*(1-E{r})", "calc", FMT_RS)
        put(ws, f"G{r}", f"=IF({SF}!Q{R['vol_' + l]}=0,0,({SF}!Q{R['matl_' + l]}+{SF}!Q{R['pack_' + l]}"
                         f"+{SF}!Q{R['conv_' + l]})/({SF}!Q{R['vol_' + l]}*{CONV}))", "calc", FMT_RS)
        put(ws, f"H{r}", f"={SF}!$D${FD['frpct_in']}", "link", FMT_PCT2)
        put(ws, f"I{r}", f"=F{r}-G{r}-H{r}*F{r}", "calc", FMT_RS)
        r += 1
    OL["ro"] = ro
    r += 2

    # FY bridge
    Aref = lambda k: f"{SF}!$R${R[k]}"
    Bref = lambda k: f"{SB}!$R${R[k]}"
    summ_top = r
    det_top = summ_top + 45
    det = write_bridge_detail(ws, det_top, Aref, Bref, "Forecast", "Budget", A, "FY_Outlook")
    summ = write_bridge_summary(ws, summ_top, det, Aref, Bref, "6+6 forecast", "budget", "FY_Outlook", "FY2027")
    OL["det"], OL["summ"] = det, summ
    widths(ws, {"A": 5, "B": 52, "C": 12, "D": 12, "E": 12, "F": 12, "G": 11, "H": 12, "I": 12, "J": 11, "K": 11,
                "L": 11, "M": 11, "N": 11, "O": 11, "P": 11})
    ws.freeze_panes = "D7"
    return OL


# ---------------------------------------------------------------------------
# 9. Dashboard
# ---------------------------------------------------------------------------
def _axes(ch):
    """Show both axes, keep title and legend outside the plot area, no inverted fills."""
    ch.x_axis.delete = False
    ch.y_axis.delete = False
    if ch.title is not None:
        ch.title.overlay = False
    ch.legend.position = "b"
    ch.legend.overlay = False
    for s in ch.series:
        if isinstance(ch, BarChart):
            s.invertIfNegative = False
    for sub_chart in getattr(ch, "_charts", []):
        for s in sub_chart.series:
            if isinstance(sub_chart, LineChart):
                s.smooth = False


def build_dashboard(ws, summ, YR):
    title(ws, "Dashboard: H1 FY2027 actual vs budget and the 6+6 outlook",
          "Native Excel charts on the chart-data tables in columns B-H (all formulas).", "₹ crore unless stated.")
    DB = {}
    # Table 1 monthly revenue and GM%
    put(ws, "B4", "Chart data 1-2: net revenue and gross margin by month", "text", bold=True)
    header_row(ws, 5, {"B": "Month", "C": "Budget", "D": "Actual", "E": "Forecast", "F": "Budget GM %",
                       "G": "Actual GM %", "H": "Forecast GM %"})
    for i, c in enumerate(MC):
        r = 6 + i
        put(ws, f"B{r}", f"={ASM}!{c}$4", "link", FMT_DATE)
        put(ws, f"C{r}", f"={SB}!{c}{R['nr_tot']}", "link", FMT_CR)
        put(ws, f"F{r}", f"={SB}!{c}{R['r_gm']}", "link", FMT_PCT)
        if c in AC:
            put(ws, f"D{r}", f"={SA}!{c}{R['nr_tot']}", "link", FMT_CR)
            put(ws, f"G{r}", f"={SA}!{c}{R['r_gm']}", "link", FMT_PCT)
        else:
            put(ws, f"E{r}", f"={SF}!{c}{R['nr_tot']}", "link", FMT_CR)
        if c in HC_ or c == "I":
            put(ws, f"H{r}", f"={SF}!{c}{R['r_gm']}", "link", FMT_PCT)
    # Table 2 EBITDA waterfall
    eb = summ["eb"]
    put(ws, "B20", "Chart data 3: H1 EBITDA bridge, budget to actual (stacked-column waterfall)", "text", bold=True)
    header_row(ws, 21, {"B": "Step", "C": "Value", "D": "Running total", "E": "Base (hidden)", "F": "Increase",
                        "G": "Decrease", "H": "Total"})
    short = {"vol": "Volume", "mix": "Mix", "lp": "List price", "tsr": "Trade spend & channel", "mrate": "Material rate",
             "pcrate": "Pack & conversion", "freight": "Freight", "ap": "A&P", "emp": "Employee", "oth": "Other overheads"}
    steps = [("Budget EBITDA", eb["start"])] + [(short[k], eb[k]) for k, _ in EB_ITEMS] + \
            [("Actual EBITDA", eb["pl"])]
    r = 22
    first = r
    for i, (lab, src_row) in enumerate(steps):
        put(ws, f"B{r}", lab, "text")
        put(ws, f"C{r}", f"=PVM_Bridge!C{src_row}", "link", FMT_CR2)
        if i == 0 or i == len(steps) - 1:
            put(ws, f"D{r}", f"=C{r}", "calc", FMT_CR2)
            put(ws, f"E{r}", 0, "calc", FMT_CR2)
            put(ws, f"F{r}", 0, "calc", FMT_CR2)
            put(ws, f"G{r}", 0, "calc", FMT_CR2)
            put(ws, f"H{r}", f"=C{r}", "calc", FMT_CR2)
        else:
            put(ws, f"D{r}", f"=D{r - 1}+C{r}", "calc", FMT_CR2)
            put(ws, f"E{r}", f"=MAX(0,MIN(D{r - 1},D{r}))", "calc", FMT_CR2)
            put(ws, f"F{r}", f"=MAX(C{r},0)", "calc", FMT_CR2)
            put(ws, f"G{r}", f"=MAX(-C{r},0)", "calc", FMT_CR2)
            put(ws, f"H{r}", 0, "calc", FMT_CR2)
        r += 1
    wf_last = r - 1
    put(ws, f"B{r}", "Check: running total = actual EBITDA", "note", italic=True)
    put(ws, f"D{r}", f"=D{wf_last - 1}-C{wf_last}", "calc", FMT_SCI)
    add_check("Dashboard", "EBITDA waterfall running total ends at actual H1 EBITDA", f"=Dashboard!D{r}")
    DB["wf"] = (first, wf_last)
    # Table 3 YTD variance by line
    lines = [("Gross sales", "gs_tot"), ("Trade spend", "ts_tot"), ("Material", "mat"), ("Packaging", "pack"),
             ("Conversion", "conv"), ("Freight", "freight"), ("A&P", "ap"), ("Employee cost", "emp"),
             ("Other overheads", "oth"), ("EBITDA", "ebitda")]
    put(ws, "B37", "Chart data 4: H1 variance by P&L line, favourable (+) / unfavourable (−)", "text", bold=True)
    header_row(ws, 38, {"B": "P&L line", "C": "Favourable variance", "D": "Favourable", "E": "Unfavourable"})
    r = 39
    for lab, key in lines:
        put(ws, f"B{r}", lab, "text")
        put(ws, f"C{r}", f"=Variance_YTD!$A{YR[key]}*Variance_YTD!L{YR[key]}", "calc", FMT_CR2)
        put(ws, f"D{r}", f"=MAX(C{r},0)", "calc", FMT_CR2)
        put(ws, f"E{r}", f"=MIN(C{r},0)", "calc", FMT_CR2)
        r += 1
    yv_last = r - 1
    # Table 4 revenue PVM
    rev = summ["rev"]
    put(ws, "B52", "Chart data 5: H1 net revenue variance by component", "text", bold=True)
    header_row(ws, 53, {"B": "Component", "C": "₹ crore", "D": "Positive", "E": "Negative"})
    comps = [("Volume", f"=PVM_Bridge!C{rev['vol']}"), ("Mix", f"=PVM_Bridge!C{rev['mix']}"),
             ("List price", f"=PVM_Bridge!C{rev['lp']}"), ("Trade-spend rate & channel mix", f"=PVM_Bridge!C{rev['tsr']}"),
             ("Total variance", f"=PVM_Bridge!C{rev['end']}-PVM_Bridge!C{rev['start']}")]
    r = 54
    for lab, f in comps:
        put(ws, f"B{r}", lab, "text")
        put(ws, f"C{r}", f, "link", FMT_CR2)
        put(ws, f"D{r}", f"=MAX(C{r},0)", "calc", FMT_CR2)
        put(ws, f"E{r}", f"=MIN(C{r},0)", "calc", FMT_CR2)
        r += 1
    pv_last = r - 1
    widths(ws, {"A": 2, "B": 30, "C": 11, "D": 11, "E": 11, "F": 12, "G": 12, "H": 13, "I": 2})

    # Chart 1: revenue bars (actual, forecast stacked) + budget line
    c1 = BarChart()
    c1.type = "col"
    c1.grouping = "stacked"
    c1.overlap = 100
    c1.title = "Net revenue by month (₹ crore)"
    c1.add_data(Reference(ws, min_col=4, max_col=5, min_row=5, max_row=17), titles_from_data=True)
    c1.set_categories(Reference(ws, min_col=2, min_row=6, max_row=17))
    c1.series[0].graphicalProperties.solidFill = "1F4E79"
    c1.series[1].graphicalProperties.solidFill = "9DC3E6"
    l1 = LineChart()
    l1.add_data(Reference(ws, min_col=3, min_row=5, max_row=17), titles_from_data=True)
    l1.series[0].graphicalProperties.line.solidFill = "C00000"
    l1.series[0].graphicalProperties.line.width = 22000
    l1.series[0].graphicalProperties.line.dashStyle = "dash"
    c1 += l1
    c1.y_axis.numFmt = NumFmt(formatCode="#,##0", sourceLinked=False)
    c1.x_axis.numFmt = NumFmt(formatCode="mmm-yy", sourceLinked=False)
    _axes(c1)
    c1.width, c1.height = 17, 8.5
    ws.add_chart(c1, "J4")

    # Chart 2: GM%
    c2 = LineChart()
    c2.title = "Gross margin % of net revenue by month"
    c2.add_data(Reference(ws, min_col=6, max_col=8, min_row=5, max_row=17), titles_from_data=True)
    c2.set_categories(Reference(ws, min_col=2, min_row=6, max_row=17))
    colors = ["C00000", "1F4E79", "9DC3E6"]
    for s, colr in zip(c2.series, colors):
        s.graphicalProperties.line.solidFill = colr
        s.graphicalProperties.line.width = 22000
        s.smooth = False
    c2.series[0].graphicalProperties.line.dashStyle = "dash"
    c2.y_axis.numFmt = NumFmt(formatCode="0%", sourceLinked=False)
    c2.x_axis.numFmt = NumFmt(formatCode="mmm-yy", sourceLinked=False)
    _axes(c2)
    c2.width, c2.height = 17, 8.5
    ws.add_chart(c2, "T4")

    # Chart 3: EBITDA waterfall
    c3 = BarChart()
    c3.type = "col"
    c3.grouping = "stacked"
    c3.overlap = 100
    c3.gapWidth = 40
    c3.title = "H1 EBITDA bridge, budget to actual (₹ crore): green = favourable, red = unfavourable"
    c3.add_data(Reference(ws, min_col=5, max_col=8, min_row=21, max_row=wf_last), titles_from_data=True)
    c3.set_categories(Reference(ws, min_col=2, min_row=22, max_row=wf_last))
    c3.series[0].graphicalProperties.noFill = True
    c3.series[0].graphicalProperties.line.noFill = True
    c3.series[1].graphicalProperties.solidFill = "70AD47"
    c3.series[2].graphicalProperties.solidFill = "C00000"
    c3.series[3].graphicalProperties.solidFill = "1F4E79"
    c3.y_axis.numFmt = NumFmt(formatCode="#,##0", sourceLinked=False)
    _axes(c3)
    c3.legend = None  # the colour key is in the title; a legend would also list the hidden base series
    c3.width, c3.height = 17, 9
    ws.add_chart(c3, "J22")

    # Chart 4: YTD variance by line
    c4 = BarChart()
    c4.type = "bar"
    c4.grouping = "stacked"
    c4.overlap = 100
    c4.title = "H1 variance by P&L line, favourable (+) / unfavourable (−), ₹ crore"
    c4.add_data(Reference(ws, min_col=4, max_col=5, min_row=38, max_row=yv_last), titles_from_data=True)
    c4.set_categories(Reference(ws, min_col=2, min_row=39, max_row=yv_last))
    c4.series[0].graphicalProperties.solidFill = "70AD47"
    c4.series[1].graphicalProperties.solidFill = "C00000"
    c4.x_axis.scaling.orientation = "maxMin"
    c4.x_axis.tickLblPos = "low"
    c4.y_axis.crosses = "max"
    c4.y_axis.numFmt = NumFmt(formatCode="#,##0.0", sourceLinked=False)
    _axes(c4)
    c4.width, c4.height = 17, 9
    ws.add_chart(c4, "T22")

    # Chart 5: revenue PVM components
    c5 = BarChart()
    c5.type = "col"
    c5.grouping = "stacked"
    c5.overlap = 100
    c5.title = "H1 net revenue variance: volume, mix and price (₹ crore)"
    c5.add_data(Reference(ws, min_col=4, max_col=5, min_row=53, max_row=pv_last), titles_from_data=True)
    c5.set_categories(Reference(ws, min_col=2, min_row=54, max_row=pv_last))
    c5.series[0].graphicalProperties.solidFill = "70AD47"
    c5.series[1].graphicalProperties.solidFill = "C00000"
    c5.x_axis.tickLblPos = "low"
    c5.y_axis.numFmt = NumFmt(formatCode="#,##0.0", sourceLinked=False)
    _axes(c5)
    c5.width, c5.height = 17, 8.5
    ws.add_chart(c5, "J41")
    return DB


# ---------------------------------------------------------------------------
# 10. Commentary (live text formulas)
# ---------------------------------------------------------------------------
def tx(*parts):
    out = []
    for p in parts:
        if isinstance(p, str):
            out.append('"' + p.replace('"', '""') + '"')
        else:
            kind, ref = p
            fmt = {"cr": "#,##0.0", "scr": "+#,##0.0;-#,##0.0", "pct": "0.0%", "spct": "+0.0%;-0.0%",
                   "rs": "#,##0", "rs1": "#,##0.0", "t": "#,##0", "st": "+#,##0;-#,##0", "int": "0"}.get(kind)
            if kind == "pp":
                out.append(f'TEXT(({ref})*100,"+0.0;-0.0")&" pp"')
            elif kind == "eff":  # sign-aware wording for a profit effect
                out.append(f'IF(({ref})<0,"cost ₹"&TEXT(-({ref}),"#,##0.0"),"added ₹"&TEXT({ref},"#,##0.0"))'
                           f'&" crore"')
            elif kind == "ou":   # over / under budget for a cost variance (actual − budget)
                out.append(f'IF(({ref})>0,"over","under")')
            elif kind == "abscr":
                out.append(f'TEXT(ABS({ref}),"#,##0.0")')
            elif kind == "raw":
                out.append(ref)
            else:
                out.append(f'TEXT({ref},"{fmt}")')
    return "=" + "&".join(out)


def build_commentary(ws, A, AD, FD, VR, YR, det, summ, OL):
    title(ws, "Commentary: FP&A monthly pack, H1 FY2027 (period ended 30-Sep-2026)",
          f"{I.COMPANY} (fictional). Prepared 31-Oct-2026 for the CEO and CFO. Numbers in the text are live formulas "
          "on the model; the Source column names the cells used.",
          "₹ crore unless stated.")
    Y = lambda k, c: f"Variance_YTD!{c}{YR[k]}"         # J budget, K actual, L var, M var%
    O = lambda k, c: f"FY_Outlook!{c}{OL[k]}"           # D budget, E forecast, F var, G var%
    P = lambda key: f"PVM_Bridge!C{summ['rev'][key]}"
    E = lambda key: f"PVM_Bridge!C{summ['eb'][key]}"
    t2, t3, t5 = det["t2"], det["t3"], det["rt5"]
    ro = OL["ro"]
    oil_avg = f"AVERAGE({SA}!D{AD['rm_OIL']}:I{AD['rm_OIL']})"
    oil_bud = f"AVERAGE({ASM}!D{A['rm_OIL']}:I{A['rm_OIL']})"
    hc_a = f"SUM({SA}!D{AD['hc_FAC']}:I{AD['hc_COR']})/6"
    hc_b = f"SUM({ASM}!D{A['hc_FAC']}:I{A['hc_COR']})/6"
    qc_1pp = "0.01*(" + "+".join(f"{SF}!Q{R[f'gslc_{l}_EQC']}" for l in LK) + ")"
    ap_fc = f"SUM({SF}!L{FD['ap']}:O{FD['ap']})"
    ap_bud = f"SUM({ASM}!L{A['ap']}:O{A['ap']})"
    oil_q4 = f"SUM({SF}!M{R['rmq_OIL']}:O{R['rmq_OIL']})"
    sug_q4 = f"SUM({SF}!M{R['rmq_SUG']}:O{R['rmq_SUG']})"
    lines = [
        ("h", "1. Headline"),
        ("t", tx("H1 EBITDA was ₹", ("cr", Y("ebitda", "K")), " crore against a budget of ₹", ("cr", Y("ebitda", "J")),
                 " crore (", ("scr", Y("ebitda", "L")), " crore, ", ("spct", Y("ebitda", "M")), "). EBITDA margin was ",
                 ("pct", Y("r_ebitda", "K")), " vs ", ("pct", Y("r_ebitda", "J")), " budget."),
         "Variance_YTD: EBITDA, EBITDA margin"),
        ("t", tx("Net revenue was ₹", ("cr", Y("nr_tot", "K")), " crore, ", ("scr", Y("nr_tot", "L")), " crore (",
                 ("spct", Y("nr_tot", "M")), ") vs budget, on volume of ", ("t", Y("vol_tot", "K")), " t (",
                 ("spct", Y("vol_tot", "M")), "). PAT was ₹", ("cr", Y("pat", "K")), " crore vs ₹",
                 ("cr", Y("pat", "J")), " crore budget."),
         "Variance_YTD: net revenue, volume, PAT"),
        ("t", tx("The 6+6 forecast puts FY2027 EBITDA at ₹", ("cr", O("ebitda", "E")), " crore vs ₹",
                 ("cr", O("ebitda", "D")), " crore budget (", ("scr", O("ebitda", "F")), " crore), and PAT at ₹",
                 ("cr", O("pat", "E")), " crore vs ₹", ("cr", O("pat", "D")), " crore. ",
                 ("raw", f'IF(ABS({O("ebitda", "L")})>=ABS({O("ebitda", "P")}),"Most of the gap was made in H1: ",'
                         f'"Most of the gap is still ahead in H2: ")'),
                 ("scr", O("ebitda", "L")), " crore in H1 and ", ("scr", O("ebitda", "P")), " crore in H2."),
         "FY_Outlook: EBITDA, PAT"),
        ("h", "2. Revenue (H1 net revenue bridge)"),
        ("t", tx("Volume effect ", ("scr", P("vol")), " crore. Beverages volume was ", ("spct", Y("vol_BEV", "M")),
                 " vs budget: distributors loaded stock in a hot, dry June (rainfall 40% below normal), then demand "
                 "cooled when the monsoon arrived in July (103% of normal) and they ran that stock down, cutting "
                 "July-September shipments. Biscuits were ", ("spct", Y("vol_BIS", "M")),
                 " as General Trade slowed (NIQ: rural FMCG volumes fell 5% in April-June 2026); namkeen & chips "
                 "were ", ("spct", Y("vol_NAM", "M")), "."),
         "PVM_Bridge net revenue bridge; Variance_YTD volume lines; ICRA 01-Sep-2026 (rainfall); NIQ via "
         "Moneycontrol 27-Sep-2026"),
        ("t", tx("Mix effect ", ("scr", P("mix")), " crore: lower-priced beverages fell from ",
                 ("pct", f"PVM_Bridge!C{t2['BEV']}"), " to ", ("pct", f"PVM_Bridge!D{t2['BEV']}"),
                 " of volume, while higher-priced namkeen rose from ", ("pct", f"PVM_Bridge!C{t2['NAM']}"), " to ",
                 ("pct", f"PVM_Bridge!D{t2['NAM']}"), "."),
         "PVM_Bridge T2 volume shares"),
        ("t", tx("Price effect ", ("scr", f"{P('lp')}+{P('tsr')}"), " crore. The 4% namkeen price increase from "
                 "1-Aug-2026 ", ("eff", P("lp")), ", while trade-spend rate and channel mix ",
                 ("eff", P("tsr")), ": e-com & quick commerce reached ", ("pct", Y("r_eqc", "K")),
                 " of net revenue vs ", ("pct", Y("r_eqc", "J")), " budget, and its trade terms ran at ",
                 ("pct", f"{SA}!I{AD['ts_EQC']}"), " of gross sales in September (budget ",
                 ("pct", f"{ASM}!I{A['ts_EQC']}"), "). Modern Trade beverage promotions in July-August added to it."),
         "PVM_Bridge T3; Variance_YTD e-com & QC share; Actuals_H1 trade spend rates"),
        ("h", "3. Margins"),
        ("t", tx("Gross margin was ", ("pct", Y("r_gm", "K")), " vs ", ("pct", Y("r_gm", "J")), " budget (",
                 ("pp", Y("r_gm", "L")), "). Material rates ", ("eff", E("mrate")), ", of which edible oil ",
                 ("eff", f"PVM_Bridge!C{t5}"), ": oil averaged ₹", ("rs", oil_avg), "/kg in H1 vs ₹",
                 ("rs", oil_bud), "/kg budget and exited September at ₹", ("rs", f"{SA}!I{AD['rm_OIL']}"),
                 "/kg."),
         "PVM_Bridge EBITDA bridge and T5; Actuals_H1 raw material prices"),
        ("t", tx("Sugar ", ("eff", f"PVM_Bridge!E{t5}"), ", driven by August-September: the ex-mill price rose "
                 "from ₹41.5/kg in early July to a record ₹67/kg in mid-August, before duty-free imports and stock "
                 "limits pulled it back to ₹55. Vriddhi paid ₹", ("rs", f"{SA}!I{AD['rm_SUG']}"),
                 "/kg in September vs ₹", ("rs", f"{ASM}!I{A['rm_SUG']}"), "/kg budget. Potato ",
                 ("eff", f"PVM_Bridge!F{t5}"), " because the large 2026 crop kept prices below the budget path."),
         "PVM_Bridge T5; Actuals_H1 MM.MAP.SUG; Moneycontrol 22-Aug-2026, TOI 25-Aug-2026, TOI Feb-2026"),
        ("t", tx("The namkeen price increase recovered ",
                 ("raw", f'TEXT(IF(PVM_Bridge!C{t5}=0,0,-PVM_Bridge!G{t3["NAM"]}/PVM_Bridge!C{t5}),"0%")'),
                 " of the H1 edible-oil inflation. Retail palm oil was up 16.3% year on year on 23-Sep-2026 (Mint), "
                 "so input costs are a market-wide issue rather than a buying problem."),
         "PVM_Bridge T3 (namkeen list price) ÷ T5 (edible oil)"),
        ("h", "4. Operating costs"),
        ("t", tx("A&P was ₹", ("abscr", Y("ap", "L")), " crore ", ("ou", Y("ap", "L")), " budget, almost all in "
                 "August-September (", ("scr", f"Variance_Monthly!H{VR['ap']}+Variance_Monthly!I{VR['ap']}"),
                 " crore) when festive launches were brought forward."),
         "Variance_YTD and Variance_Monthly: A&P"),
        ("t", tx("Employee cost was ₹", ("abscr", Y("emp", "L")), " crore ", ("ou", Y("emp", "L")),
                 " budget because the annual increment moved from 1-Jul to 1-Oct-2026; average headcount was ",
                 ("t", hc_a), " vs ", ("t", hc_b), " budget. The saving stays because the increment is not paid "
                 "retrospectively; from October the cost runs at the full increment."),
         "Variance_YTD: employee cost; Actuals_H1 payroll block"),
        ("t", tx("Freight was ₹", ("abscr", Y("freight", "L")), " crore ", ("ou", Y("freight", "L")),
                 " budget, including a one-off ₹",
                 ("cr", f"{SA}!J{AD['fro']}"), " crore route-disruption surcharge in July; the rest is quick-commerce "
                 "dark-store replenishment."),
         "Variance_YTD: freight; Actuals_H1 FI.6115"),
        ("h", "5. Outlook (6+6 forecast)"),
        ("t", tx("FY2027 net revenue ₹", ("cr", O("nr_tot", "E")), " crore (", ("spct", O("nr_tot", "G")),
                 " vs budget), EBITDA ₹", ("cr", O("ebitda", "E")), " crore at a ", ("pct", O("r_ebitda", "E")),
                 " margin vs ", ("pct", O("r_ebitda", "D")), " budget."),
         "FY_Outlook"),
        ("t", tx("H2 assumptions: namkeen volume ", ("spct", f"{SF}!J{FD['vadj_NAM']}"), " in October and ",
                 ("spct", f"{SF}!K{FD['vadj_NAM']}"), " in November vs budget for the festive season (Navratri "
                 "11-Oct, Diwali 8-Nov-2026); a ", ("pct", f"{SF}!D{FD['pchg_BIS']}"), " biscuit price increase "
                 "from 1-Oct to recover sugar, which is forecast at ₹", ("rs", f"{SF}!J{FD['rm_SUG']}"),
                 "/kg in October easing to ₹", ("rs", f"{SF}!O{FD['rm_SUG']}"), "/kg by March as the new "
                 "crushing season adds supply; edible oil easing to ₹", ("rs", f"{SF}!O{FD['rm_OIL']}"),
                 "/kg by March after the 24-Sep-2026 import-duty cut."),
         "Forecast_6plus6 drivers; ChiniMandi 31-Oct-2026 (sugar); The Hindu 24-Sep-2026 (duty cut)"),
        ("t", tx("Payroll carries the full increment from 1-Oct, and borrowing cost rises 25 bp from November after "
                 "the RBI repo increase to 5.50% on 7-Oct-2026. Full-year interest is ₹",
                 ("cr", O("int", "E")), " crore vs ₹", ("cr", O("int", "D")), " crore budget."),
         "Forecast_6plus6 drivers; FY_Outlook interest; The Hindu 07-Oct-2026"),
        ("t", tx("Risks and opportunities net to ", ("scr", f"FY_Outlook!F{ro['net']}"),
                 " crore (probability-weighted ", ("scr", f"FY_Outlook!H{ro['net']}"),
                 " crore), giving a risk-adjusted FY EBITDA of ₹", ("cr", f"FY_Outlook!H{ro['adj']}"),
                 " crore. The largest risks are edible oil and sugar staying at their September prices (",
                 ("scr", f"FY_Outlook!F{ro['oil']}"), " and ", ("scr", f"FY_Outlook!F{ro['sug']}"), " crore)."),
         "FY_Outlook risks and opportunities"),
        ("h", "6. Actions proposed"),
        ("t", tx("1. Prepare a second biscuit price increase of 2% from January 2027 in case sugar stays above "
                 "₹50/kg: worth ", ("scr", f"FY_Outlook!F{ro['bis']}"), " crore of EBITDA in Q4 if volumes hold."),
         "FY_Outlook R&O: biscuit price"),
        ("t", tx("2. Buy forward half of the Q4 edible-oil requirement (", ("t", f"0.5*{oil_q4}"),
                 " t) and contract half of Q4 sugar (", ("t", f"0.5*{sug_q4}"), " t) with mills once the new "
                 "crushing season starts in November, to cap the downside."),
         "Forecast_6plus6: raw material consumed"),
        ("t", tx("3. Hold December-March A&P at ₹", ("cr", ap_fc), " crore, ₹", ("cr", f"{ap_bud}-{ap_fc}"),
                 " crore below budget, to recover part of the H1 overspend (already in the forecast)."),
         "Forecast_6plus6 and Assumptions_Budget: A&P"),
        ("t", tx("4. Renegotiate quick-commerce visibility fees: each 1 pp of e-com & QC trade spend is worth ₹",
                 ("cr", qc_1pp), " crore in H2."),
         "Forecast_6plus6: H2 e-com & QC gross sales"),
        ("t", tx("5. Beverages: plan the summer 2027 pipeline on secondary (retailer) sales, so that June loading "
                 "does not repeat the July-September destocking. Full-year beverage volume is forecast ",
                 ("spct", f"FY_Outlook!G{OL['vol_BEV']}"), " vs budget."),
         "FY_Outlook: beverages volume"),
    ]
    header_row(ws, 5, {"B": "Commentary", "C": "Source in the model"})
    r = 6
    for item in lines:
        if item[0] == "h":
            put(ws, f"B{r}", item[1], "text", bold=True, size=11)
            r += 1
            continue
        _, f, src = item
        put(ws, f"B{r}", f, "calc", wrap=True)
        put(ws, f"C{r}", src, "note", italic=True, wrap=True)
        # row height from the text length: literals in the formula plus about 7 characters per number
        literal = sum(len(s.replace('""', '"')) for s in re.findall(r'"((?:[^"]|"")*)"', f))
        n_nums = f.count("TEXT(")
        est = literal - 9 * n_nums + 7 * n_nums  # format strings inside TEXT() are about 9 characters
        lines_b = max(1, math.ceil(est / 135))
        lines_c = max(1, math.ceil(len(src) / 48))
        ws.row_dimensions[r].height = 15 * max(lines_b, lines_c) + 4
        r += 1
    widths(ws, {"A": 2, "B": 120, "C": 42})


# ---------------------------------------------------------------------------
# 11. Checks and 1. Cover
# ---------------------------------------------------------------------------
def build_checks(ws):
    title(ws, "Checks: model integrity tests", "Each test computes a difference that must be zero (within the "
          "tolerance) or a count that must be zero. Overall status feeds the Cover.",
          "Tolerance 1E-9 ₹ crore = ₹0.01 (one paisa).")
    put(ws, "B5", "Number of checks", "text", bold=True)
    put(ws, "B6", "Passed", "text", bold=True)
    put(ws, "B7", "Failed", "text", bold=True)
    put(ws, "B8", "Overall status", "text", bold=True)
    header_row(ws, 10, {"A": "#", "B": "Area", "C": "Check", "D": "Value", "E": "Tolerance", "F": "Result"})
    r = 11
    for i, (area, desc, f, tol) in enumerate(CHECKS, start=1):
        put(ws, f"A{r}", i, "note", "0")
        put(ws, f"B{r}", area, "text")
        put(ws, f"C{r}", desc, "text")
        put(ws, f"D{r}", f, "calc", FMT_SCI)
        put(ws, f"E{r}", tol, "input", FMT_SCI)
        put(ws, f"F{r}", f'=IF(ISERROR(D{r}),"FAIL",IF(ABS(D{r})<=E{r},"PASS","FAIL"))', "calc", align="center",
            bold=True)
        r += 1
    last = r - 1
    put(ws, "D5", f"=COUNTA(F11:F{last})", "calc", "0")
    put(ws, "D6", f'=COUNTIF(F11:F{last},"PASS")', "calc", "0")
    put(ws, "D7", f'=COUNTIF(F11:F{last},"FAIL")', "calc", "0")
    put(ws, "D8", f'=IF(D7=0,"ALL PASS","FAIL")', "calc", bold=True)
    ws.conditional_formatting.add(f"F11:F{last}", CellIsRule(operator="equal", formula=['"PASS"'], fill=PASS_FILL))
    ws.conditional_formatting.add(f"F11:F{last}", CellIsRule(operator="equal", formula=['"FAIL"'], fill=FAIL_FILL))
    ws.conditional_formatting.add("D8", CellIsRule(operator="equal", formula=['"ALL PASS"'], fill=PASS_FILL))
    ws.conditional_formatting.add("D8", CellIsRule(operator="equal", formula=['"FAIL"'], fill=FAIL_FILL))
    widths(ws, {"A": 5, "B": 18, "C": 90, "D": 12, "E": 10, "F": 9})
    ws.freeze_panes = "A11"
    return {"n": "Checks!$D$5", "pass": "Checks!$D$6", "fail": "Checks!$D$7", "status": "Checks!$D$8"}


def build_cover(ws, A, CKS, OL):
    put(ws, "A1", f"{I.COMPANY}: FY2027 budget, H1 actuals and 6+6 forecast (FP&A model)", "text", bold=True,
        size=16)
    put(ws, "A2", "FICTIONAL COMPANY. All business data is invented for an educational FP&A exercise. Real-world "
                  "dates and market facts used in the storyline are listed at the bottom of this sheet.", "text",
        bold=True, color="C00000")
    put(ws, "A3", "Status date 31-Oct-2026: April-September 2026 actuals are closed; October 2026 to March 2027 is "
                  "forecast. Fiscal year FY2027 = Apr-2026 to Mar-2027. Money in ₹ crore.", "note", italic=True)
    section(ws, 5, "Purpose", 1, 11)
    put(ws, "B6", "Driver-based annual budget, monthly actual-vs-budget variance analysis, price-volume-mix and "
                  "margin bridges, and a 6+6 reforecast for an Indian packaged-foods company (namkeen & chips, "
                  "biscuits & cookies, beverages; General Trade, Modern Trade, e-com & quick commerce).", "text",
        wrap=True)
    ws.merge_cells("B6:K7")
    ws.row_dimensions[6].height = 30
    section(ws, 9, "Controls and status", 1, 11)
    put(ws, "B10", "Forecast case (1 = Base, 2 = Downside, 3 = Upside)", "text", bold=True)
    put(ws, "D10", 1, "input", "0", yellow=True, bold=True)
    put(ws, "E10", '=CHOOSE($D$10,"Base","Downside","Upside")&" case selected"', "calc", bold=True)
    put(ws, "G10", "Overlays are defined in Forecast_6plus6 (block A); they change Oct-Mar only.", "note",
        italic=True)
    dv = DataValidation(type="whole", operator="between", formula1="1", formula2="3", allow_blank=False,
                        showErrorMessage=True, errorTitle="Forecast case", error="Enter 1, 2 or 3")
    ws.add_data_validation(dv)
    dv.add("D10")
    put(ws, "B11", "Model checks", "text", bold=True)
    put(ws, "D11", f"={CKS['status']}", "calc", bold=True)
    put(ws, "E11", f'={CKS["pass"]}&" of "&{CKS["n"]}&" checks pass (see Checks)"', "calc")
    ws.conditional_formatting.add("D11", CellIsRule(operator="equal", formula=['"ALL PASS"'], fill=PASS_FILL))
    ws.conditional_formatting.add("D11", CellIsRule(operator="equal", formula=['"FAIL"'], fill=FAIL_FILL))

    section(ws, 13, "KPI summary", 1, 11)
    header_row(ws, 14, {"B": "KPI", "C": "H1 budget", "D": "H1 actual", "E": "Variance", "F": "Var %",
                        "H": "FY budget", "I": "FY 6+6 forecast", "J": "Variance", "K": "Var %"})
    kpis = [("Volume (t)", "vol_tot", FMT_T, False), ("Net revenue (₹ cr)", "nr_tot", FMT_CR, False),
            ("Gross margin % of net revenue", "r_gm", FMT_PCT, True), ("EBITDA (₹ cr)", "ebitda", FMT_CR, False),
            ("EBITDA margin %", "r_ebitda", FMT_PCT, True), ("PAT (₹ cr)", "pat", FMT_CR, False)]
    r = 15
    for lab, key, fmt, is_ratio in kpis:
        pr = R[key]
        put(ws, f"B{r}", lab, "text", bold=True)
        put(ws, f"C{r}", f"={SB}!P{pr}", "link", fmt)
        put(ws, f"D{r}", f"={SA}!J{pr}", "link", fmt)
        put(ws, f"E{r}", f"=D{r}-C{r}", "calc", FMT_PP if is_ratio else (FMT_VAR_T if fmt == FMT_T else FMT_VAR))
        put(ws, f"H{r}", f"={SB}!R{pr}", "link", fmt)
        put(ws, f"I{r}", f"={SF}!R{pr}", "link", fmt)
        put(ws, f"J{r}", f"=I{r}-H{r}", "calc", FMT_PP if is_ratio else (FMT_VAR_T if fmt == FMT_T else FMT_VAR))
        if not is_ratio:
            put(ws, f"F{r}", pct_formula(f"D{r}", f"C{r}"), "calc", FMT_PCT)
            put(ws, f"K{r}", pct_formula(f"I{r}", f"H{r}"), "calc", FMT_PCT)
        r += 1
    put(ws, f"B{r}", "Ratio variances are in percentage points. FY forecast reflects the case selected above.",
        "note", italic=True)
    r += 2
    section(ws, r, "How the model flows", 1, 11)
    r += 1
    flow = [
        ("Assumptions_Budget", "Budget drivers: volumes and seasonality, channel mix, list prices, trade spend, raw "
                               "material prices and bill of materials, unit costs, A&P, payroll, overheads, finance."),
        ("Budget_PL", "Monthly budget P&L (12 months + H1/H2/FY) calculated from the budget drivers."),
        ("Actuals_H1", "Fictional ERP extract of actual drivers for Apr-Sep 2026 and the actual P&L calculated from "
                       "it with the same logic."),
        ("Forecast_6plus6", "Apr-Sep = actuals; Oct-Mar = reforecast drivers (price increase, oil, festive volumes, "
                            "deferred increment, interest rate) and the case overlays."),
        ("Variance_Monthly / _YTD", "Actual vs budget by month, September month and year to date, with F/U flags "
                                    "and colour coding."),
        ("PVM_Bridge", "H1 net revenue price-volume-mix, gross-profit bridge and EBITDA bridge, each reconciled."),
        ("FY_Outlook", "FY budget vs 6+6 forecast, risks and opportunities, FY EBITDA bridge."),
        ("Dashboard", "Native Excel charts: revenue A/B/F, gross margin %, EBITDA waterfall, variance by line, PVM."),
        ("Commentary", "Management commentary with live numbers."),
        ("Checks", "Integrity tests; the status shows on this sheet."),
    ]
    for name, desc in flow:
        put(ws, f"B{r}", name, "text", bold=True)
        put(ws, f"D{r}", desc, "text")
        r += 1
    r += 1
    section(ws, r, "How to use", 1, 11)
    r += 1
    howto = ["Change a budget driver on Assumptions_Budget, an actual driver in the ERP block of Actuals_H1, or a "
             "reforecast driver on Forecast_6plus6 (Oct-Mar columns). Everything else recalculates.",
             "Pick the forecast case in D10. The Downside case adds ₹8/kg to edible oil and cuts General Trade volume "
             "3% from Dec-26; the Upside case lowers oil ₹5/kg and adds a second 2% biscuit price rise from Jan-27.",
             "Check D11 after any change: it must read ALL PASS. The Checks sheet lists every test.",
             "Colour code: blue font = input; yellow fill = judgment assumption (reason next to it); black = "
             "formula; green = link to another sheet. Totals are shaded grey."]
    for t in howto:
        put(ws, f"B{r}", "• " + t, "text", wrap=True)
        ws.merge_cells(f"B{r}:K{r}")
        ws.row_dimensions[r].height = 30
        r += 1
    r += 1
    section(ws, r, "Storyline of H1 (fictional company, real 2026 context)", 1, 11)
    r += 1
    oil_a, sug_a, sug_b = I.ACTUAL["rm_price"]["OIL"], I.ACTUAL["rm_price"]["SUG"], I.BUDGET["rm_price"]["SUG"]
    story = ["Beverages: distributors loaded stock in a hot, dry June (rainfall 40% below normal); when the monsoon "
             "arrived in July (103% of normal) demand cooled and destocking cut July-September shipments.",
             "Namkeen: 4% price increase from 1-Aug-2026 to offset edible-oil inflation; quick-commerce volumes ahead of "
             "plan across all lines, while General Trade slowed with rural demand.",
             f"Costs: edible oil rose from ₹{oil_a[0]:.0f} to ₹{oil_a[5]:.0f}/kg (budget "
             f"₹{I.BUDGET['rm_price']['OIL'][0]:.0f}); sugar spiked in August (record ex-mill ₹67/kg) and cost "
             f"₹{sug_a[5]:.0f}/kg in September (budget ₹{sug_b[5]:.0f}); a large potato crop kept potato below budget; "
             "A&P overspend ahead of festive launches; wage increment deferred from 1-Jul to 1-Oct; one-off July "
             "freight surcharge.",
             f"Forecast: festive season (Navratri 11-Oct, Dussehra 20-Oct, Diwali 8-Nov-2026), biscuit price "
             f"+{I.FORECAST['price_chg']['BIS']:.0%} from 1-Oct, oil easing after the 24-Sep-2026 duty cut, sugar "
             "easing as the new crushing season starts, interest +25 bp from November after the RBI repo rise of "
             "7-Oct-2026."]
    for t in story:
        put(ws, f"B{r}", "• " + t, "text", wrap=True)
        ws.merge_cells(f"B{r}:K{r}")
        ws.row_dimensions[r].height = 30
        r += 1
    r += 1
    section(ws, r, "External facts used (real, cited; saved copies in source_data/, index in source_data/README.md)",
            1, 11)
    r += 1
    for fact, val, src, url, when, fname in I.EXTERNAL_FACTS:
        put(ws, f"B{r}", fact, "text", bold=True)
        put(ws, f"D{r}", f"{val}. Source: {src}, {when}; file: {fname}", "note")
        r += 1
    widths(ws, {"A": 2, "B": 30, "C": 12, "D": 12, "E": 11, "F": 9, "G": 2, "H": 12, "I": 14, "J": 11, "K": 9})


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def export_data(A):
    os.makedirs(DATA, exist_ok=True)
    av = I.actual_volumes()
    Ac = I.ACTUAL
    rows = []
    months = [m.strftime("%Y-%m") for m in I.MONTHS[:I.N_ACT]]
    for (l, ch), vals in av.items():
        for m, v in zip(months, vals):
            rows.append((m, f"SD.VOL.{l}.{ch}", "Sales volume billed", LN[l], CN[ch], "t", v))
    simple = [("price", "SD.PRC", "Realised list price", "Rs/kg", "list_price", LK),
              ("rm", "MM.MAP", "Raw material price", "Rs/kg", "rm_price", RK),
              ("ts", "FI.TSP", "Trade spend rate", "share of gross sales", "trade_spend", CK)]
    for _, code, desc, unit, key, keys in simple:
        for k in keys:
            for m, v in zip(months, Ac[key][k]):
                name = LN.get(k) or RN.get(k) or CN.get(k)
                rows.append((m, f"{code}.{k}", desc, name, "", unit, v))
    for key, code, desc in (("other_ingr", "CO.OTH", "Other ingredients"), ("packaging", "CO.PAC", "Packaging"),
                            ("conversion", "CO.CON", "Conversion")):
        for l in LK:
            for m, v in zip(months, Ac[key][l]):
                rows.append((m, f"{code}.{l}", desc, LN[l], "", "Rs/kg", v))
    for key, code, desc, unit in (("freight_pct", "FI.6110", "Freight rate", "share of net revenue"),
                                  ("freight_oneoff", "FI.6115", "One-off freight surcharge", "Rs crore"),
                                  ("ap", "FI.6300", "A&P spend", "Rs crore"),
                                  ("other_oh", "FI.6900", "Other overheads", "Rs crore"),
                                  ("da", "FI.7100", "Depreciation & amortisation", "Rs crore"),
                                  ("borrowings", "TR.BORR", "Average borrowings", "Rs crore"),
                                  ("int_rate", "TR.RATE", "Interest rate", "per year")):
        for m, v in zip(months, Ac[key]):
            rows.append((m, code, desc, "", "", unit, v))
    for f in FK:
        for m, v in zip(months, Ac["headcount"][f]):
            rows.append((m, f"HR.HC.{f}", "Headcount", FN[f], "", "heads", v))
            rows.append((m, f"HR.CTC.{f}", "CTC per head before increment", FN[f], "", "Rs lakh per year",
                         Ac["ctc"][f]))
    with open(os.path.join(DATA, "erp_extract_h1_fy2027.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["period", "erp_code", "item", "product_line_or_input", "channel", "unit", "value"])
        w.writerows(rows)
    with open(os.path.join(DATA, "external_reference_facts.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["fact", "value", "source", "url", "date", "source_data_file"])
        w.writerows(I.EXTERNAL_FACTS)


def main():
    wb = Workbook()
    names = ["Cover", ASM, SB, SA, SF, "Variance_Monthly", "Variance_YTD", "PVM_Bridge", "FY_Outlook", "Dashboard",
             "Commentary", "Checks"]
    sheets = {"Cover": wb.active}
    wb.active.title = "Cover"
    for n in names[1:]:
        sheets[n] = wb.create_sheet(n)
    A = build_assumptions(sheets[ASM])
    build_budget(sheets[SB], A)
    AD = build_actuals(sheets[SA], A)
    FD = build_forecast(sheets[SF], A, AD)
    VR = build_var_monthly(sheets["Variance_Monthly"])
    YR = build_var_ytd(sheets["Variance_YTD"], VR)
    det, summ = build_pvm(sheets["PVM_Bridge"], A)
    OL = build_outlook(sheets["FY_Outlook"], A, AD, FD)
    build_dashboard(sheets["Dashboard"], summ, YR)
    build_commentary(sheets["Commentary"], A, AD, FD, VR, YR, det, summ, OL)
    build_cover(sheets["Cover"], A, {"status": "Checks!$D$8", "pass": "Checks!$D$6", "n": "Checks!$D$5"}, OL)
    for n in names:
        if n == "Checks":
            continue
        w = sheets[n]
        lc, lr = col(max(w.max_column, 1)), max(w.max_row, 1)
        if n == "Cover":  # row 11 reads the Checks status; scan around it to avoid a circular reference
            f = f"=SUMPRODUCT(--ISERROR(Cover!A1:{lc}10))+SUMPRODUCT(--ISERROR(Cover!A12:{lc}{lr}))"
        else:
            f = f"=SUMPRODUCT(--ISERROR({n}!A1:{lc}{lr}))"
        add_check("Errors", f"No error values (#REF!, #DIV/0!, #VALUE!, #NAME?, #N/A) on {n}", f, 0)
    build_checks(sheets["Checks"])
    tabs = {"Cover": "1F3864", ASM: "0000FF", SB: "808080", SA: "0000FF", SF: "808080", "Variance_Monthly": "70AD47",
            "Variance_YTD": "70AD47", "PVM_Bridge": "70AD47", "FY_Outlook": "70AD47", "Dashboard": "C00000",
            "Commentary": "C00000", "Checks": "FFC000"}
    for n, colr in tabs.items():
        sheets[n].sheet_properties.tabColor = colr
    for w in sheets.values():
        w.sheet_view.showGridLines = False if w.title in ("Cover", "Dashboard", "Commentary") else True
    wb.calculation.fullCalcOnLoad = True
    wb.save(OUT)
    export_data(A)
    meta = {"R": R, "A": A, "AD": AD, "FD": FD, "VR": VR, "YR": YR, "OL_rows": {k: v for k, v in OL.items()
                                                                              if isinstance(v, int)},
            "pvm_summ": summ, "pvm_det": {k: v for k, v in det.items() if k != "rcols"},
            "fy_summ": OL["summ"], "ro": OL["ro"], "n_checks": len(CHECKS)}
    import json
    with open(os.path.join(HERE, "layout.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1, default=str)
    print(f"Saved {OUT} with {len(CHECKS)} checks")


if __name__ == "__main__":
    main()
