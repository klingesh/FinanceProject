"""Build Castrol_India_LBO_Model.xlsx with openpyxl (live Excel formulas only).

Hypothetical take-private of 100% of Castrol India Ltd (NSE: CASTROLIND) by a financial
sponsor. Entry 31-Dec-2026, exit 31-Dec-2031. Rs crore unless stated.

Inputs come from data/castrol_india_financials.csv (filings), data/market_inputs.json,
data/deal_context.json and source_data/screener/CASTROLIND_profit-loss.csv (cross-check).
Every calculation is an Excel formula that points at input cells. After this script, run
build/finalise_with_excel.py (Excel via COM) to add the data tables, calculate, run the
three scenarios and verify the file. build/run_all.py runs everything in order.

Run:  python build/build_lbo_model.py
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, Callable

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference, Series
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT_XLSX = ROOT / "Castrol_India_LBO_Model.xlsx"
LAYOUT_JSON = ROOT / "build" / "layout.json"

# ----------------------------------------------------------------------------- styles
BLUE, GREEN, BLACK = "0000FF", "008000", "000000"
F_IN = Font(name="Calibri", size=10, color=BLUE)
F_CALC = Font(name="Calibri", size=10, color=BLACK)
F_LINK = Font(name="Calibri", size=10, color=GREEN)
F_TXT = Font(name="Calibri", size=10, color=BLACK)
F_NOTE = Font(name="Calibri", size=9, italic=True, color="595959")
F_TITLE = Font(name="Calibri", size=14, bold=True, color="1F4E78")
F_SEC = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
F_HDR = Font(name="Calibri", size=10, bold=True, color=BLACK)
FILL_SEC = PatternFill("solid", fgColor="1F4E78")
FILL_HDR = PatternFill("solid", fgColor="D9E1F2")
FILL_ASSUMP = PatternFill("solid", fgColor="FFF2CC")
FILL_KEY = PatternFill("solid", fgColor="E2EFDA")
FILL_GOOD = PatternFill("solid", fgColor="C6EFCE")
THIN = Side(style="thin", color="808080")
B_TOP = Border(top=THIN)
B_BOTTOM = Border(bottom=THIN)
B_BOX = Border(top=THIN, bottom=THIN, left=THIN, right=THIN)

FMT_CR = '#,##0;(#,##0);"-"'
FMT_CR1 = '#,##0.0;(#,##0.0);"-"'
FMT_CR2 = '#,##0.00;(#,##0.00);"-"'
FMT_PCT = '0.0%'
FMT_PCT2 = '0.00%'
FMT_X = '0.0"x"'
FMT_X2 = '0.00"x"'
FMT_DATE = 'dd-mmm-yyyy'
FMT_INT = '#,##0'
FMT_RS = '#,##0.00'
FMT_DAYS = '0'
FMT_GEN = 'General'

LINK_RE = re.compile(r"^=\$?[A-Za-z_][A-Za-z0-9_]*!\$?[A-Z]{1,3}\$?\d+$")

YC = ["C", "D", "E", "F", "G", "H"]          # CY2026E .. CY2031E on model sheets
FC = ["D", "E", "F", "G", "H"]               # forecast years CY2027E .. CY2031E
YEAR_OF = {"C": 2026, "D": 2027, "E": 2028, "F": 2029, "G": 2030, "H": 2031}
HCOLS = ["C", "D", "E", "F", "G"]            # Historical CY2021 .. CY2025
HPL = ["C", "D", "E", "F", "G", "H", "I", "J", "K"]  # Historical P&L columns incl. 9M, LTM, Q3


def pc(c: str) -> str:
    """Previous column letter (single letters only)."""
    return chr(ord(c) - 1)


# ----------------------------------------------------------------------------- registry
POS: dict[str, tuple[str, int]] = {}   # key -> (sheet, row)
CTX = {"sheet": ""}                    # sheet currently being written (drops self prefixes)


def r(key: str, col: str = "C", ab: bool = False) -> str:
    """Cell reference for a registered row key in a given column."""
    sheet, row = POS[key]
    a = f"${col}${row}" if ab else f"{col}{row}"
    return a if sheet == CTX["sheet"] else f"{sheet}!{a}"


def rg(key: str, c1: str, c2: str, ab: bool = False) -> str:
    """Range reference across columns c1:c2 of a registered row."""
    sheet, row = POS[key]
    a = f"${c1}${row}:${c2}${row}" if ab else f"{c1}{row}:{c2}{row}"
    return a if sheet == CTX["sheet"] else f"{sheet}!{a}"


def rs(k1: str, k2: str, col: str = "C") -> str:
    """Vertical range in one column between two registered rows (same sheet)."""
    s1, r1 = POS[k1]
    s2, r2 = POS[k2]
    assert s1 == s2, (k1, k2)
    a = f"{col}{r1}:{col}{r2}"
    return a if s1 == CTX["sheet"] else f"{s1}!{a}"


def yr(fn: Callable[[str], Any], cols: list[str] = FC) -> dict[str, Callable[[str], Any]]:
    """Same formula builder for several columns."""
    return {c: fn for c in cols}


# ----------------------------------------------------------------------------- sheet model
class Sheet:
    """Row-based layout. Pass 1 assigns rows to keys; pass 2 writes values and formulas."""

    def __init__(self, name: str, note_col: str, widths: dict[str, float], freeze: str | None):
        self.name = name
        self.note_col = note_col
        self.widths = widths
        self.freeze = freeze
        self.items: list[dict] = []

    def add(self, typ: str, **kw: Any) -> None:
        self.items.append(dict(typ=typ, **kw))

    def title(self, text: str) -> None:
        self.add("title", text=text)

    def text(self, text: str, style: str = "note", col: str = "A") -> None:
        self.add("text", text=text, style=style, col=col)

    def blank(self) -> None:
        self.add("blank")

    def section(self, text: str, last_col: str | None = None) -> None:
        self.add("section", text=text, last_col=last_col)

    def header(self, cols: dict[str, str]) -> None:
        self.add("header", cols=cols)

    def row(self, key: str | None, label: str, unit: str = "", cols: dict | None = None,
            fmt: str = FMT_CR, kind: str = "calc", note: str = "", total: bool = False,
            key_out: bool = False) -> None:
        self.add("row", key=key, label=label, unit=unit, cols=cols or {}, fmt=fmt,
                 kind=kind, note=note, total=total, key_out=key_out)


def assign_rows(sheet: Sheet, start: int = 1) -> None:
    rr = start
    for it in sheet.items:
        it["row"] = rr
        if it["typ"] == "row" and it["key"]:
            if it["key"] in POS:
                raise KeyError(f"duplicate key {it['key']}")
            POS[it["key"]] = (sheet.name, rr)
        rr += 1


def style_value(cell, value: Any, kind: str, fmt: str) -> None:
    """Write a value with the colour convention: blue input, black formula, green link."""
    cell.value = value
    if isinstance(value, str) and value.startswith("="):
        cell.font = F_LINK if LINK_RE.match(value) else F_CALC
    elif isinstance(value, (int, float, dt.date, dt.datetime)) and not isinstance(value, bool):
        cell.font = F_IN if kind in ("input", "assump") else F_CALC
        if kind == "assump":
            cell.fill = FILL_ASSUMP
    else:
        cell.font = F_IN if kind in ("input", "assump") else F_TXT
        if kind == "assump":
            cell.fill = FILL_ASSUMP
    if fmt and not (isinstance(value, str) and not value.startswith("=")):
        cell.number_format = fmt
    cell.alignment = Alignment(horizontal="right") if not isinstance(value, str) or value.startswith("=") else Alignment(horizontal="left")


def write_sheet(wb: Workbook, sheet: Sheet) -> None:
    ws = wb[sheet.name]
    CTX["sheet"] = sheet.name
    last_col = max(list(sheet.widths.keys()))
    for it in sheet.items:
        rr = it["row"]
        k = it["typ"]
        if k == "title":
            ws.cell(rr, 1, it["text"]).font = F_TITLE
        elif k == "text":
            c = ws[f"{it['col']}{rr}"]
            c.value = it["text"]
            c.font = F_NOTE if it["style"] == "note" else (F_HDR if it["style"] == "bold" else F_TXT)
            c.alignment = Alignment(wrap_text=False)
        elif k == "section":
            lc = it.get("last_col") or last_col
            for col in range(1, ord(lc) - 64 + 1):
                ws.cell(rr, col).fill = FILL_SEC
            ws.cell(rr, 1, it["text"]).font = F_SEC
        elif k == "header":
            for col, txt in it["cols"].items():
                c = ws[f"{col}{rr}"]
                c.value = txt
                c.font = F_HDR
                c.fill = FILL_HDR
                c.border = B_BOTTOM
                c.alignment = Alignment(horizontal="center" if col not in ("A", "B", sheet.note_col) else "left",
                                        wrap_text=True, vertical="center")
        elif k == "row":
            a = ws[f"A{rr}"]
            a.value = it["label"]
            a.font = Font(name="Calibri", size=10, bold=it["total"] or it["key_out"])
            if it["unit"]:
                b = ws[f"B{rr}"]
                b.value = it["unit"]
                b.font = F_NOTE
            for col, spec in it["cols"].items():
                v = spec(col) if callable(spec) else spec
                if v is None:
                    continue
                c = ws[f"{col}{rr}"]
                style_value(c, v, it["kind"], it["fmt"])
                if it["total"]:
                    c.font = Font(name="Calibri", size=10, bold=True, color=c.font.color.rgb if c.font.color else BLACK)
                    c.border = B_TOP
                if it["key_out"]:
                    c.fill = FILL_KEY
                    c.font = Font(name="Calibri", size=10, bold=True, color=c.font.color.rgb if c.font.color else BLACK)
            if it["note"]:
                n = ws[f"{sheet.note_col}{rr}"]
                n.value = it["note"]
                n.font = F_NOTE
    for col, w in sheet.widths.items():
        ws.column_dimensions[col].width = w
    if sheet.freeze:
        ws.freeze_panes = sheet.freeze
    ws.sheet_view.zoomScale = 90


# ----------------------------------------------------------------------------- data
def load_inputs() -> dict:
    fin = pd.read_csv(DATA / "castrol_india_financials.csv").set_index("item")
    mkt = json.loads((DATA / "market_inputs.json").read_text(encoding="utf-8"))
    deal = json.loads((DATA / "deal_context.json").read_text(encoding="utf-8"))
    scr = pd.read_csv(ROOT / "source_data" / "screener" / "CASTROLIND_profit-loss.csv").set_index("item")
    return {"fin": fin, "mkt": mkt, "deal": deal, "scr": scr}


def fv(fin: pd.DataFrame, item: str, col: str) -> float | None:
    v = fin.loc[item, col]
    if pd.isna(v) or v == "":
        return None
    return float(v)


# ============================================================================= Historical
def build_historical(D: dict) -> Sheet:
    fin = D["fin"]
    scr = D["scr"]
    s = Sheet("Historical", note_col="M",
              widths={"A": 46, "B": 10, "C": 11, "D": 11, "E": 11, "F": 11, "G": 11, "H": 11,
                      "I": 11, "J": 12, "K": 11, "L": 13, "M": 90},
              freeze="C5")
    s.title("Castrol India Ltd: historical financials (standalone, calendar year Jan-Dec)")
    s.text("Rs crore unless stated. Blue = figure from the filing, black = formula. CY2021-CY2025 from the audited "
           "annual reports; 9M, Q3 and H1 columns from the quarterly results of 4-Aug-2026 and 24-Oct-2026.")
    s.blank()
    s.header({"A": "Item", "B": "Unit", "C": "CY2021", "D": "CY2022", "E": "CY2023", "F": "CY2024",
              "G": "CY2025", "H": "9M CY2025", "I": "9M CY2026", "J": "LTM Sep-2026", "K": "Q3 CY2026",
              "L": "30-Jun-2026 / H1 CY2026", "M": "Source"})
    F2 = FMT_CR2

    def src(item: str) -> str:
        return str(fin.loc[item, "source"])

    def flow(item: str, key: str) -> dict:
        d: dict = {}
        for csvc, col in [("CY2021", "C"), ("CY2022", "D"), ("CY2023", "E"), ("CY2024", "F"),
                          ("CY2025", "G"), ("9M_CY2025", "H"), ("9M_CY2026", "I"), ("Q3_CY2026", "K")]:
            v = fv(fin, item, csvc)
            if v is not None:
                d[col] = v
        d["J"] = lambda c, k=key: f"={r(k, 'G')}+{r(k, 'I')}-{r(k, 'H')}"
        return d

    def stock(item: str) -> dict:
        d: dict = {}
        for csvc, col in [("CY2021", "C"), ("CY2022", "D"), ("CY2023", "E"), ("CY2024", "F"),
                          ("CY2025", "G"), ("Q2_CY2026", "L")]:
            v = fv(fin, item, csvc)
            if v is not None:
                d[col] = v
        return d

    s.section("Income statement")
    s.row("h_rev", "Revenue from operations", "Rs crore", flow("revenue", "h_rev"), F2, "input", src("revenue"))
    s.row("h_oi", "Other income", "Rs crore", flow("other_income", "h_oi"), F2, "input", src("other_income"))
    s.row("h_rm", "Cost of raw and packing materials consumed", "Rs crore",
          flow("raw_and_packing_materials", "h_rm"), F2, "input", src("raw_and_packing_materials"))
    s.row("h_tr", "Purchase of traded goods", "Rs crore", flow("purchase_of_traded_goods", "h_tr"), F2, "input",
          src("purchase_of_traded_goods"))
    s.row("h_chg", "Change in inventories (negative = stock build)", "Rs crore",
          flow("change_in_inventories", "h_chg"), F2, "input", src("change_in_inventories"))
    s.row("h_cogs", "Cost of goods sold", "Rs crore",
          yr(lambda c: f"={r('h_rm', c)}+{r('h_tr', c)}+{r('h_chg', c)}", HPL), F2, "calc",
          "Materials + traded goods + change in inventories")
    s.row("h_gp", "Gross profit", "Rs crore", yr(lambda c: f"={r('h_rev', c)}-{r('h_cogs', c)}", HPL), F2,
          total=True)
    s.row("h_emp", "Employee benefits expense", "Rs crore", flow("employee_benefits", "h_emp"), F2, "input",
          src("employee_benefits"))
    s.row("h_oth", "Other expenses (incl. royalty, advertising, freight)", "Rs crore",
          flow("other_expenses", "h_oth"), F2, "input", src("other_expenses"))
    roy = {col: fv(fin, "royalty_to_castrol_ltd_uk", c) for c, col in
           [("CY2021", "C"), ("CY2022", "D"), ("CY2023", "E"), ("CY2024", "F"), ("CY2025", "G")]}
    s.row("h_roy", "  of which royalty to Castrol Ltd (UK)", "Rs crore", roy, F2, "input",
          src("royalty_to_castrol_ltd_uk"))
    s.row("h_ebitda", "EBITDA (before exceptional items)", "Rs crore",
          yr(lambda c: f"={r('h_gp', c)}-{r('h_emp', c)}-{r('h_oth', c)}", HPL), F2, total=True,
          note="Revenue less materials, traded goods, inventory change, employee and other expenses (Ind AS 116 basis: "
               "excludes lease rentals)")
    s.row("h_da", "Depreciation and amortisation (incl. right-of-use assets)", "Rs crore",
          flow("depreciation_amortisation", "h_da"), F2, "input", src("depreciation_amortisation"))
    s.row("h_fin", "Finance costs (mostly lease interest)", "Rs crore", flow("finance_costs", "h_fin"), F2, "input",
          src("finance_costs"))
    s.row("h_exc", "Exceptional items", "Rs crore", flow("exceptional_items", "h_exc"), F2, "input",
          src("exceptional_items") + "; Rs 22.53 crore charge for the new Labour Codes (past service)")
    s.row("h_pbt_calc", "Profit before tax (recomputed)", "Rs crore",
          yr(lambda c: f"={r('h_ebitda', c)}+{r('h_oi', c)}-{r('h_da', c)}-{r('h_fin', c)}+{r('h_exc', c)}", HPL),
          F2, total=True)
    s.row("h_pbt_rep", "Profit before tax (reported)", "Rs crore", flow("pbt_reported", "h_pbt_rep"), F2, "input",
          src("pbt_reported"))
    s.row("h_tax", "Tax expense (current + deferred)", "Rs crore", flow("tax_expense", "h_tax"), F2, "input",
          src("tax_expense"))
    s.row("h_pat_rep", "Profit after tax (reported)", "Rs crore", flow("pat_reported", "h_pat_rep"), F2, "input",
          src("pat_reported"))
    s.row("h_pat_calc", "Profit after tax (recomputed)", "Rs crore",
          yr(lambda c: f"={r('h_pbt_calc', c)}-{r('h_tax', c)}", HPL), F2)
    s.blank()
    s.section("Margins and ratios")
    g = {c: (lambda c: f"={r('h_rev', c)}/{r('h_rev', pc(c))}-1") for c in ["D", "E", "F", "G"]}
    g["I"] = lambda c: f"={r('h_rev', 'I')}/{r('h_rev', 'H')}-1"
    s.row("h_g", "Revenue growth (9M column: vs 9M CY2025)", "%", g, FMT_PCT)
    s.row("h_gm", "Gross margin", "%", yr(lambda c: f"={r('h_gp', c)}/{r('h_rev', c)}", HPL), FMT_PCT)
    s.row("h_em", "EBITDA margin", "%", yr(lambda c: f"={r('h_ebitda', c)}/{r('h_rev', c)}", HPL), FMT_PCT)
    s.row("h_dap", "D&A as % of revenue", "%", yr(lambda c: f"={r('h_da', c)}/{r('h_rev', c)}", HPL), FMT_PCT)
    s.row("h_etr", "Effective tax rate", "%", yr(lambda c: f"={r('h_tax', c)}/{r('h_pbt_rep', c)}", HPL), FMT_PCT)
    s.row("h_royp", "Royalty as % of revenue", "%", yr(lambda c: f"={r('h_roy', c)}/{r('h_rev', c)}", HCOLS),
          FMT_PCT)
    scr_cols = {"C": "Dec 2021", "D": "Dec 2022", "E": "Dec 2023", "F": "Dec 2024", "G": "Dec 2025", "J": "TTM"}
    s.row("h_scr_sales", "Screener.in sales (cross-check, rounded)", "Rs crore",
          {col: float(scr.loc["Sales", sc]) for col, sc in scr_cols.items()}, FMT_CR, "input",
          "source_data/screener/CASTROLIND_profit-loss.csv (standalone page, downloaded 31-Oct-2026)")
    s.row("h_scr_sales_d", "  Difference: revenue minus Screener sales", "Rs crore",
          yr(lambda c: f"={r('h_rev', c)}-{r('h_scr_sales', c)}", HCOLS + ["J"]), F2)
    s.row("h_scr_op", "Screener.in operating profit (cross-check, rounded)", "Rs crore",
          {col: float(scr.loc["Operating Profit", sc]) for col, sc in scr_cols.items()}, FMT_CR, "input",
          "Same file; Screener 'Operating Profit' = sales minus expenses before other income")
    s.row("h_scr_op_d", "  Difference: EBITDA minus Screener operating profit", "Rs crore",
          yr(lambda c: f"={r('h_ebitda', c)}-{r('h_scr_op', c)}", HCOLS + ["J"]), F2)
    s.blank()
    s.section("Balance sheet items (31-Dec; column L = 30-Jun-2026)")
    s.row("h_inv", "Inventories", "Rs crore", stock("inventories"), F2, "input", src("inventories"))
    s.row("h_rec", "Trade receivables", "Rs crore", stock("trade_receivables"), F2, "input", src("trade_receivables"))
    s.row("h_pay", "Trade payables", "Rs crore", stock("trade_payables"), F2, "input", src("trade_payables"))
    s.row("h_nwc", "Trade working capital", "Rs crore",
          yr(lambda c: f"={r('h_inv', c)}+{r('h_rec', c)}-{r('h_pay', c)}", HCOLS + ["L"]), F2, total=True)
    s.row("h_cash", "Cash and cash equivalents", "Rs crore", stock("cash_and_cash_equivalents"), F2, "input",
          src("cash_and_cash_equivalents"))
    s.row("h_bank", "Other bank balances (deposits up to 12 months)", "Rs crore", stock("other_bank_balances"), F2,
          "input", src("other_bank_balances"))
    s.row("h_cash_tot", "Cash and bank balances", "Rs crore",
          yr(lambda c: f"={r('h_cash', c)}+{r('h_bank', c)}", HCOLS + ["L"]), F2, total=True)
    s.row("h_invest", "Non-current investment (TVS Automobile Solutions)", "Rs crore",
          stock("non_current_investment"), F2, "input", src("non_current_investment"))
    s.row("h_lease", "Lease liabilities (current + non-current)", "Rs crore", stock("lease_liabilities"), F2,
          "input", src("lease_liabilities"))
    s.row("h_borrow", "Borrowings", "Rs crore", stock("borrowings"), F2, "input", src("borrowings"))
    s.row("h_equity", "Total equity", "Rs crore", stock("total_equity"), F2, "input", src("total_equity"))
    s.row("h_netcash", "Net cash (cash and bank less borrowings and leases)", "Rs crore",
          yr(lambda c: f"={r('h_cash_tot', c)}-{r('h_borrow', c)}-{r('h_lease', c)}", HCOLS + ["L"]), F2)
    s.blank()
    s.section("Working capital days (column L: 30-Jun-2026 balance on annualised H1 CY2026 flows)")

    def days(bal: str, flow_key: str) -> dict:
        d = {c: (lambda c, b=bal, f=flow_key: f"={r(b, c)}/{r(f, c)}*365") for c in HCOLS}
        d["L"] = lambda c, b=bal, f=flow_key: f"={r(b, 'L')}/(({r(f, 'I')}-{r(f, 'K')})*2)*365"
        return d

    s.row("h_invd", "Inventory days (on cost of goods sold)", "days", days("h_inv", "h_cogs"), FMT_CR1)
    s.row("h_recd", "Receivable days (on revenue)", "days", days("h_rec", "h_rev"), FMT_CR1)
    s.row("h_payd", "Payable days (on cost of goods sold)", "days", days("h_pay", "h_cogs"), FMT_CR1)
    nw = {c: (lambda c: f"={r('h_nwc', c)}/{r('h_rev', c)}") for c in HCOLS}
    nw["L"] = lambda c: f"={r('h_nwc', 'L')}/(({r('h_rev', 'I')}-{r('h_rev', 'K')})*2)"
    s.row("h_nwcp", "Trade working capital as % of revenue", "%", nw, FMT_PCT)
    s.blank()
    s.section("Cash flow (column L = H1 CY2026)")
    s.row("h_cfo", "Cash from operating activities", "Rs crore", stock("cash_from_operations"), F2, "input",
          src("cash_from_operations"))
    s.row("h_capex", "Capital expenditure (PPE, CWIP, intangibles)", "Rs crore", stock("capex"), F2, "input",
          src("capex"))
    s.row("h_fcf", "Free cash flow (CFO less capex)", "Rs crore",
          yr(lambda c: f"={r('h_cfo', c)}-{r('h_capex', c)}", HCOLS + ["L"]), F2, total=True)
    s.row("h_div", "Dividends paid", "Rs crore", stock("dividends_paid"), F2, "input", src("dividends_paid"))
    s.row("h_lprin", "Lease principal paid", "Rs crore", stock("lease_principal_paid"), F2, "input",
          src("lease_principal_paid"))
    s.row("h_lint", "Lease interest paid", "Rs crore", stock("lease_interest_paid"), F2, "input",
          src("lease_interest_paid"))
    cp = {c: (lambda c: f"={r('h_capex', c)}/{r('h_rev', c)}") for c in HCOLS}
    cp["L"] = lambda c: f"={r('h_capex', 'L')}/({r('h_rev', 'I')}-{r('h_rev', 'K')})"
    s.row("h_capexp", "Capex as % of revenue", "%", cp, FMT_PCT)
    fc = {c: (lambda c: f"={r('h_fcf', c)}/{r('h_ebitda', c)}") for c in HCOLS}
    fc["L"] = lambda c: f"={r('h_fcf', 'L')}/({r('h_ebitda', 'I')}-{r('h_ebitda', 'K')})"
    s.row("h_fcfconv", "Free cash flow / EBITDA", "%", fc, FMT_PCT)
    s.row("h_payout", "Dividends paid / profit after tax", "%",
          yr(lambda c: f"={r('h_div', c)}/{r('h_pat_rep', c)}", HCOLS), FMT_PCT,
          note="CY2025 includes the Rs 9.50 final dividend for CY2024 paid in 2025")
    s.row("h_eps", "Earnings per share (reported PAT / diluted shares)", "Rs/share",
          yr(lambda c: f"={r('h_pat_rep', c)}/{r('shares_cr', 'C')}", HPL), FMT_RS)
    return s


# ============================================================================= Assumptions
SCEN = {
    # key: (label, unit, fmt, base, upside, downside, base note, upside note, downside note)
    "vol": ("Volume growth", "% y/y", FMT_PCT,
            [0.040, 0.040, 0.035, 0.030, 0.030], [0.060, 0.060, 0.050, 0.045, 0.045],
            [0.010, 0.005, 0.000, -0.005, -0.010],
            "Lubricant market grows 3-4% a year; target is 1.5-2x market (Q3 CY2026 call); CY2025 volumes +8%; "
            "EV adoption trims later years",
            "Castrol grows at about 1.5x the market", "EV adoption and price-led demand loss shrink volumes"),
    "pm": ("Price and mix growth", "% y/y", FMT_PCT,
           [0.025] * 5, [0.030] * 5, [0.015] * 5,
           "Premium brands and partial pass-through of input costs", "Stronger premium mix",
           "Weaker pricing power"),
    "gm": ("Gross margin", "% of revenue", FMT_PCT,
           [0.460, 0.465, 0.470, 0.470, 0.470], [0.470, 0.480, 0.485, 0.485, 0.485],
           [0.440, 0.440, 0.445, 0.445, 0.445],
           "9M CY2026 45.5%; CY2021-25 average about 49%; partial recovery", "Recovers close to CY2024-25 levels",
           "Base-oil and rupee pressure persists"),
    "em": ("EBITDA margin", "% of revenue", FMT_PCT,
           [0.215, 0.220, 0.225, 0.225, 0.225], [0.225, 0.230, 0.235, 0.240, 0.240],
           [0.190, 0.190, 0.195, 0.195, 0.195],
           "Long-term range 21-24% (Q3 CY2026 call); CY2021-25 average 23.9%", "Top of the 21-24% range by CY2030",
           "Below the range: costs not fully passed on"),
    "cx": ("Capex", "% of revenue", FMT_PCT,
           [0.018] * 5, [0.017] * 5, [0.020] * 5,
           "About Rs 135-170 crore a year vs guidance of Rs 100-150 crore; CY2021-25 average 1.9%",
           "Closer to guidance", "Higher maintenance and EV-fluid spend"),
    "invd": ("Inventory days (on COGS)", "days", FMT_CR1, [72] * 5, [68] * 5, [80] * 5,
             "CY2021-25 average 75 days; 68 days at Dec-2025", "Tighter inventory", "Higher-cost stock held longer"),
    "recd": ("Receivable days (on revenue)", "days", FMT_CR1, [31] * 5, [29] * 5, [35] * 5,
             "CY2021-25 average 29 days", "Faster collection", "Industrial and B2B mix lengthens credit"),
    "payd": ("Payable days (on COGS)", "days", FMT_CR1, [98] * 5, [100] * 5, [92] * 5,
             "CY2021-25 average 100 days", "Slightly longer supplier credit", "Suppliers tighten terms"),
}


def build_assumptions(D: dict) -> Sheet:
    mkt = D["mkt"]
    s = Sheet("Assumptions", note_col="I",
              widths={"A": 62, "B": 16, "C": 12, "D": 11, "E": 11, "F": 11, "G": 11, "H": 11, "I": 100},
              freeze="C5")
    s.title("Assumptions and scenario selector")
    s.text("Rs crore unless stated. Blue = input, black = formula, green = link to another sheet, yellow fill = "
           "judgement assumption (reason in column I). Scenario drivers apply to CY2027E-CY2031E.")
    s.blank()
    s.header({"A": "Item", "B": "Unit", "C": "Value / CY2026E", "D": "CY2027E", "E": "CY2028E", "F": "CY2029E",
              "G": "CY2030E", "H": "CY2031E", "I": "Source or reason"})
    C = "C"
    s.section("Scenario selector")
    s.row("scen_in", "Scenario selected (1 = Base, 2 = Upside, 3 = Downside)", "1 / 2 / 3", {C: 1}, FMT_GEN, "input",
          "Change this cell to switch the operating case. All three cases pass every model check.", key_out=True)
    s.row("scen", "Scenario used by the model", "1 / 2 / 3",
          {C: lambda c: f"=IF(ISNUMBER({r('scen_ovr', 'D', True)}),{r('scen_ovr', 'D', True)},{r('scen_in', C)})"},
          FMT_GEN, note="Equals the selector; only the scenario data table on Sensitivities changes it temporarily")
    s.row("scen_name", "Scenario name", "", {C: lambda c: f'=CHOOSE({r("scen", C)},"Base","Upside","Downside")'},
          FMT_GEN)
    s.blank()
    s.section("Market data and offer price")
    s.row("val_date", "Valuation date (last close used)", "date", {C: dt.datetime(2026, 10, 30)}, FMT_DATE, "input",
          "Friday 30-Oct-2026 close")
    s.row("px", "Share price at the 30-Oct-2026 close", "Rs/share", {C: mkt["share_price_close_30oct2026"]["value"]},
          FMT_RS, "input", "Yahoo Finance CASTROLIND.NS close (source_data/yahoo_finance/quote_30Oct2026.json)")
    s.row("vwap60", "60-day volume-weighted average close", "Rs/share", {C: mkt["vwap_60d_proxy"]["value"]}, FMT_RS,
          "input", "Yahoo Finance daily closes and volumes, 60 trading days to 30-Oct-2026")
    s.row("hi52", "52-week high", "Rs/share", {C: mkt["high_52w"]["value"]}, FMT_RS, "input",
          "Yahoo Finance daily highs, 31-Oct-2025 to 30-Oct-2026")
    s.row("oo_price", "Open-offer price (Stonepeak, SEBI SAST)", "Rs/share",
          {C: mkt["open_offer"]["initial_offer_price"]}, FMT_RS, "input",
          "Public announcement of 24-Dec-2025 (source_data/deal_documents/)")
    s.row("prem_in", "Offer premium to the 30-Oct-2026 close (input)", "%", {C: 0.25}, FMT_PCT, "assump",
          "Judgement: control premium for a take-private; flexed from 5% to 35% on Sensitivities")
    s.row("prem", "Offer premium used (after any sensitivity override)", "%",
          {C: lambda c: f"=IF(ISNUMBER({r('prem_ovr', 'D', True)}),{r('prem_ovr', 'D', True)},{r('prem_in', C)})"},
          FMT_PCT)
    s.row("offer", "Offer price = higher of open-offer price and premium price", "Rs/share",
          {C: lambda c: f"=MAX({r('oo_price', C)},{r('px', C)}*(1+{r('prem', C)}))"}, FMT_RS, key_out=True)
    s.row("shares", "Fully diluted shares", "shares", {C: mkt["fully_diluted_shares"]["value"]}, FMT_INT, "input",
          "Equity Share Capital on a fully diluted basis in the open-offer public announcement (24-Dec-2025)")
    s.row("shares_cr", "Fully diluted shares", "crore", {C: lambda c: f"={r('shares', C)}/10^7"}, '#,##0.0000')
    s.blank()
    s.section("Transaction dates, fees and tax")
    s.row("entry_date", "Entry (closing) date", "date", {C: dt.datetime(2026, 12, 31)}, FMT_DATE, "input",
          "Hypothetical closing date")
    s.row("exit_date", "Exit date (5-year hold, fixed by the model layout)", "date",
          {C: lambda c: f"=EDATE({r('entry_date', C)},60)"}, FMT_DATE)
    s.row("txn_fee", "Transaction fees", "% of entry EV", {C: 0.02}, FMT_PCT, "assump",
          "Advisory, legal, open-offer and stamp costs; about 2% of EV")
    s.row("fin_fee", "Financing fees", "% of funded debt", {C: 0.025}, FMT_PCT, "assump",
          "Arrangement and underwriting fees on the term loans and holdco notes")
    s.row("fin_fee_yrs", "Financing fee amortisation period", "years", {C: 5}, FMT_GEN, "input",
          "Straight-line over the hold; non-cash charge in the income statement")
    s.row("min_cash", "Minimum operating cash", "Rs crore", {C: 300}, FMT_CR, "assump",
          "About 2-3 weeks of CY2027E cash operating costs (about Rs 5,800 crore a year)")
    s.row("mip", "Management incentive pool", "% of equity gain", {C: 0.10}, FMT_PCT, "assump",
          "Share of the equity gain paid to management at exit")
    s.row("hurdle", "Sponsor IRR hurdle (used only for highlighting)", "%", {C: 0.20}, FMT_PCT, "assump",
          "Common buyout target; cells at or above it turn green on Sensitivities")
    s.row("tax", "Corporate tax rate", "%", {C: mkt["corporate_tax_rate"]["value"]}, FMT_PCT2, "input",
          "Income-tax Act s.115BAA: 22% + 10% surcharge + 4% cess = 25.17%")
    s.row("int_ded", "Acquisition interest tax-deductible? (1 = yes, 0 = no)", "switch", {C: 1}, FMT_GEN, "assump",
          "Yes if the bid vehicle merges into Castrol India after delisting (debt push-down); 0 tests the downside")
    s.blank()
    s.section("Financing terms (priced off the 10-year G-sec; spreads are assumptions)")
    s.row("gsec", "India 10-year G-sec yield, 30-Oct-2026", "%", {C: mkt["gsec_10y_yield"]["value"]}, FMT_PCT2,
          "input", "7.4139% (Reuters via ETBFSI, 30-Oct-2026); 7.40% (Trading Economics); 7.412% (Investing.com)")
    s.row("repo", "RBI repo rate (reference only)", "%", {C: mkt["rbi_repo_rate"]["value"]}, FMT_PCT2, "input",
          "Raised 25 bp to 5.50% on 7-Oct-2026 (The Hindu, Mint)")
    s.row("tbill", "91-day T-bill yield (interest earned on cash)", "%", {C: mkt["tbill_91d_yield"]["value"]},
          FMT_PCT2, "input", "RBI auction of 28-Oct-2026 (Economic Times)")
    s.row("tla_x", "Term loan A size", "x CY2026E EBITDA", {C: 1.25}, FMT_X2, "assump",
          "Senior amortising loan (private credit or offshore bank; see README on Indian rules)")
    s.row("tla_spread", "Term loan A spread over the G-sec", "%", {C: 0.020}, FMT_PCT2, "assump",
          "Senior secured, amortising")
    s.row("tla_rate", "Term loan A interest rate", "%", {C: lambda c: f"={r('gsec', C)}+{r('tla_spread', C)}"},
          FMT_PCT2)
    s.row("tla_amort", "Term loan A scheduled repayment (% of original amount)", "%",
          dict(zip(FC, [0.10, 0.15, 0.20, 0.20, 0.20])), FMT_PCT, "assump",
          "85% repaid by CY2031 from cash flow; balance due at maturity")
    s.row("tlb_x", "Term loan B size", "x CY2026E EBITDA", {C: 1.75}, FMT_X2, "assump",
          "Senior secured, mostly bullet; takes the cash sweep first")
    s.row("tlb_spread", "Term loan B spread over the G-sec", "%", {C: 0.030}, FMT_PCT2, "assump",
          "Wider spread for the longer, back-ended loan")
    s.row("tlb_rate", "Term loan B interest rate", "%", {C: lambda c: f"={r('gsec', C)}+{r('tlb_spread', C)}"},
          FMT_PCT2)
    s.row("tlb_amort", "Term loan B scheduled repayment (% of original a year)", "%", {C: 0.01}, FMT_PCT, "input",
          "1% a year plus the cash sweep")
    s.row("mezz_x", "Holdco PIK notes size", "x CY2026E EBITDA", {C: 0.75}, FMT_X2, "assump",
          "Structurally subordinated holdco debt; repaid from exit proceeds")
    s.row("mezz_spread", "Holdco notes cash coupon spread over the G-sec", "%", {C: 0.025}, FMT_PCT2, "assump",
          "Cash part of the coupon")
    s.row("mezz_cash", "Holdco notes cash coupon", "%", {C: lambda c: f"={r('gsec', C)}+{r('mezz_spread', C)}"},
          FMT_PCT2)
    s.row("mezz_pik", "Holdco notes PIK coupon (added to principal)", "%", {C: 0.035}, FMT_PCT2, "assump",
          "Payment-in-kind part of the coupon")
    s.row("mezz_allin", "Holdco notes all-in coupon", "%", {C: lambda c: f"={r('mezz_cash', C)}+{r('mezz_pik', C)}"},
          FMT_PCT2)
    s.row("total_x", "Total funded debt at close (before any sensitivity override)", "x CY2026E EBITDA",
          {C: lambda c: f"={r('tla_x', C)}+{r('tlb_x', C)}+{r('mezz_x', C)}"}, FMT_X2,
          note="Within the 3.0-4.5x range; sized so that EBITDA covers cash interest about 2.6x at close")
    s.row("lev_scale", "Leverage scaling factor (1 unless the leverage data table is running)", "x",
          {C: lambda c: f"=IF(ISNUMBER({r('lev_ovr', 'D', True)}),{r('lev_ovr', 'D', True)}/{r('total_x', C)},1)"},
          FMT_X2)
    s.row("rcf_commit", "Revolving credit facility commitment", "Rs crore", {C: 300}, FMT_CR, "assump",
          "Undrawn at close; draws only if cash would fall below the minimum")
    s.row("rcf_spread", "Revolver spread over the G-sec", "%", {C: 0.020}, FMT_PCT2, "assump", "")
    s.row("rcf_rate", "Revolver interest rate on drawn amounts", "%",
          {C: lambda c: f"={r('gsec', C)}+{r('rcf_spread', C)}"}, FMT_PCT2)
    s.row("rcf_fee", "Revolver commitment fee on the undrawn amount", "%", {C: 0.004}, FMT_PCT2, "assump", "")
    s.row("sweep", "Cash sweep: share of excess cash used to prepay TLB, then TLA", "%", {C: 1.0}, FMT_PCT, "assump",
          "All cash above the minimum repays senior debt; holdco notes are not prepaid")
    s.row("cov_lev", "Covenant: maximum net debt / EBITDA", "x", dict(zip(FC, [4.00, 3.50, 3.00, 2.50, 2.25])),
          FMT_X2, "assump", "Maintenance covenant stepping down; about 30% EBITDA cushion to the base case in "
                            "CY2027E (judgement)")
    s.row("cov_icr", "Covenant: minimum EBITDA / cash interest", "x", dict(zip(FC, [2.25, 2.50, 2.75, 3.00, 3.00])),
          FMT_X2, "assump", "Maintenance covenant stepping up (judgement)")
    s.blank()
    s.section("Balance-sheet items carried through the deal")
    s.row("debt_exist", "Existing borrowings refinanced at close", "Rs crore", {C: 0.0}, FMT_CR, "input",
          "No borrowings at 31-Dec-2025 or 30-Jun-2026 (Historical sheet)")
    s.row("lease", "Lease liabilities (held flat over the hold)", "Rs crore",
          {C: lambda c: f"={r('h_lease', 'L')}"}, FMT_CR2,
          note="30-Jun-2026 balance sheet: Rs 30.32 crore non-current + Rs 22.83 crore current; new leases replace "
               "repaid ones")
    s.row("lease_rate", "Interest rate on lease liabilities", "%", {C: 0.085}, FMT_PCT, "assump",
          "CY2024-25 lease interest / average lease liability is about 8.4%")
    s.row("lease_prin", "Lease principal repaid", "% of revenue", {C: 0.0035}, FMT_PCT2, "assump",
          "CY2025: Rs 20.18 crore = 0.35% of revenue")
    s.row("nonop", "Non-operating investment (TVS Automobile Solutions), held at book", "Rs crore",
          {C: lambda c: f"={r('h_invest', 'L')}"}, FMT_CR2,
          note="Fair value at 30-Jun-2026; excluded from EV at entry and added back at exit")
    s.blank()
    s.section("CY2026E: Q4 estimate and closing balance sheet (same in all scenarios)")
    s.row("q4_25_rev", "Q4 CY2025 revenue (actual = CY2025 less 9M CY2025)", "Rs crore",
          {C: lambda c: f"={r('h_rev', 'G')}-{r('h_rev', 'H')}"}, FMT_CR2)
    s.row("q4_g", "Q4 CY2026E revenue growth y/y", "%", {C: 0.25}, FMT_PCT, "assump",
          "Q3 CY2026 revenue +27% y/y on price increases; assume pricing holds in Q4")
    s.row("q4_rev", "Q4 CY2026E revenue", "Rs crore", {C: lambda c: f"={r('q4_25_rev', C)}*(1+{r('q4_g', C)})"},
          FMT_CR2)
    s.row("q4_gm", "Q4 CY2026E gross margin", "%", {C: 0.395}, FMT_PCT, "assump",
          "Q3 CY2026 36.5%, 9M CY2026 45.5%; small recovery as price increases catch up with costs")
    s.row("q4_em", "Q4 CY2026E EBITDA margin", "%", {C: 0.18}, FMT_PCT, "assump",
          "Q3 CY2026 15.1%, 9M CY2026 21.1%; crude back near US$115/bbl in late October (Q3 call)")
    s.row("q4_da", "Q4 CY2026E depreciation and amortisation", "Rs crore", {C: 31.0}, FMT_CR1, "assump",
          "Q3 CY2026 actual Rs 30.34 crore")
    s.row("q4_oi", "Q4 CY2026E other income", "Rs crore", {C: 13.0}, FMT_CR1, "assump",
          "Q3 CY2026 actual Rs 13.40 crore")
    s.row("q4_fin", "Q4 CY2026E finance costs", "Rs crore", {C: 1.7}, FMT_CR1, "assump",
          "Q3 CY2026 actual Rs 1.72 crore (mostly lease interest)")
    s.row("capex26", "CY2026E capex", "Rs crore", {C: 150.0}, FMT_CR1, "assump",
          "Top of the Rs 100-150 crore annual guidance; H1 CY2026 actual Rs 84.47 crore")
    s.row("inv26", "Inventory days at 31-Dec-2026E (on COGS)", "days", {C: 80}, FMT_CR1, "assump",
          "111 days at 30-Jun-2026 and 68 at 31-Dec-2025; assume a partial unwind")
    s.row("rec26", "Receivable days at 31-Dec-2026E", "days", {C: 33}, FMT_CR1, "assump",
          "40 days at 30-Jun-2026 and 30 at 31-Dec-2025")
    s.row("pay26", "Payable days at 31-Dec-2026E (on COGS)", "days", {C: 100}, FMT_CR1, "assump",
          "130 days at 30-Jun-2026 and 98 at 31-Dec-2025")
    s.row("int_dps", "Interim dividend CY2026 (paid by 2-Sep-2026)", "Rs/share",
          {C: mkt["dividends_paid_cy2026"]["interim_cy2026_dps"]}, FMT_RS, "input",
          "Board outcome of 4-Aug-2026; record date 11-Aug-2026")
    s.blank()
    s.section("Operating drivers by scenario, CY2027E-CY2031E (the 'Selected' row feeds the model)")
    for key, (label, unit, fmt, b, u, d, nb, nu, nd) in SCEN.items():
        s.row(f"{key}_b", f"{label}: Base", unit, dict(zip(FC, b)), fmt, "assump", nb)
        s.row(f"{key}_u", f"{label}: Upside", unit, dict(zip(FC, u)), fmt, "assump", nu)
        s.row(f"{key}_d", f"{label}: Downside", unit, dict(zip(FC, d)), fmt, "assump", nd)
        s.row(key, f"{label}: Selected", unit,
              yr(lambda c, k=key: f"=CHOOSE({r('scen', 'C', True)},{r(k + '_b', c)},{r(k + '_u', c)},"
                                  f"{r(k + '_d', c)})"), fmt, total=True)
    s.row("da_pct", "D&A (% of revenue), all scenarios", "% of revenue", dict(zip(FC, [0.017] * 5)), FMT_PCT2,
          "assump", "CY2025 1.76%, 9M CY2026 1.72%")
    s.row("xd_b", "Exit multiple change vs entry multiple: Base", "x", {C: 0.0}, FMT_X, "assump",
          "Base exits at the entry multiple (no re-rating)")
    s.row("xd_u", "Exit multiple change vs entry multiple: Upside", "x", {C: 0.0}, FMT_X, "assump",
          "No multiple expansion assumed even in the upside")
    s.row("xd_d", "Exit multiple change vs entry multiple: Downside", "x", {C: -2.0}, FMT_X, "assump",
          "Two turns lower: slower growth de-rates the business at exit")
    s.row("xd", "Exit multiple change vs entry multiple: Selected", "x",
          {C: lambda c: f"=CHOOSE({r('scen', 'C', True)},{r('xd_b', C)},{r('xd_u', C)},{r('xd_d', C)})"}, FMT_X,
          total=True)
    return s


# ============================================================================= Sources & Uses
def build_sources_uses(D: dict) -> Sheet:
    s = Sheet("Sources_Uses", note_col="F",
              widths={"A": 62, "B": 16, "C": 13, "D": 12, "E": 13, "F": 90}, freeze="A5")
    s.title("Entry valuation, debt sizing and sources and uses of funds at close (31-Dec-2026)")
    s.text("Rs crore unless stated. Cash at close is estimated from the 30-Jun-2026 balance sheet plus the second half "
           "of CY2026 (Q3 actual + Q4 estimate).")
    s.blank()
    s.header({"A": "Item", "B": "Unit", "C": "Value", "D": "% of total", "E": "x CY2026E EBITDA",
              "F": "Notes"})
    C = "C"
    s.section("Offer price and equity purchase price")
    s.row("su_px", "Share price at the 30-Oct-2026 close", "Rs/share", {C: lambda c: f"={r('px', C)}"}, FMT_RS)
    s.row("su_prem", "Offer premium used", "%", {C: lambda c: f"={r('prem', C)}"}, FMT_PCT)
    s.row("su_oo", "Open-offer price (floor)", "Rs/share", {C: lambda c: f"={r('oo_price', C)}"}, FMT_RS)
    s.row("su_offer", "Offer price per share", "Rs/share", {C: lambda c: f"={r('offer', C)}"}, FMT_RS, key_out=True)
    s.row("su_prem_close", "Premium to the 30-Oct-2026 close", "%", {C: lambda c: f"={r('su_offer', C)}/{r('su_px', C)}-1"},
          FMT_PCT)
    s.row("su_prem_oo", "Premium to the open-offer price", "%", {C: lambda c: f"={r('su_offer', C)}/{r('su_oo', C)}-1"},
          FMT_PCT)
    s.row("su_prem_vwap", "Premium to the 60-day VWAP", "%", {C: lambda c: f"={r('su_offer', C)}/{r('vwap60', C)}-1"},
          FMT_PCT)
    s.row("su_prem_hi", "Premium to the 52-week high", "%", {C: lambda c: f"={r('su_offer', C)}/{r('hi52', C)}-1"},
          FMT_PCT)
    s.row("su_shares", "Fully diluted shares", "crore", {C: lambda c: f"={r('shares_cr', C)}"}, '#,##0.0000')
    s.row("su_eq", "Equity purchase price (100%)", "Rs crore", {C: lambda c: f"={r('su_offer', C)}*{r('su_shares', C)}"},
          FMT_CR, total=True)
    s.blank()
    s.section("Estimated cash at close: second-half CY2026 bridge from the 30-Jun-2026 balance sheet")
    s.row("b_cash_jun", "Cash and bank balances at 30-Jun-2026 (actual)", "Rs crore",
          {C: lambda c: f"={r('h_cash_tot', 'L')}"}, FMT_CR)
    s.row("b_ebitda", "Add: H2 CY2026 EBITDA (Q3 actual + Q4 estimate)", "Rs crore",
          {C: lambda c: f"={r('o_ebitda', 'C')}-({r('h_ebitda', 'I')}-{r('h_ebitda', 'K')})"}, FMT_CR)
    s.row("b_oi", "Add: H2 CY2026 other income", "Rs crore",
          {C: lambda c: f"={r('o_oi', 'C')}-({r('h_oi', 'I')}-{r('h_oi', 'K')})"}, FMT_CR)
    s.row("b_tax", "Less: H2 CY2026 tax (assumed paid as expensed)", "Rs crore",
          {C: lambda c: f"=-({r('o_tax', 'C')}-({r('h_tax', 'I')}-{r('h_tax', 'K')}))"}, FMT_CR)
    s.row("b_nwc", "Less: increase in trade working capital (31-Dec-2026E vs 30-Jun-2026)", "Rs crore",
          {C: lambda c: f"=-({r('o_nwc', 'C')}-{r('h_nwc', 'L')})"}, FMT_CR,
          note="Positive = working capital released as the mid-2026 inventory build unwinds")
    s.row("b_capex", "Less: H2 CY2026 capex", "Rs crore",
          {C: lambda c: f"=-({r('capex26', C)}-{r('h_capex', 'L')})"}, FMT_CR)
    s.row("b_lease", "Less: H2 CY2026 lease payments (= H1 actual)", "Rs crore",
          {C: lambda c: f"=-({r('h_lprin', 'L')}+{r('h_lint', 'L')})"}, FMT_CR)
    s.row("b_div", "Less: interim dividend paid in September 2026", "Rs crore",
          {C: lambda c: f"=-{r('int_dps', C)}*{r('shares_cr', C)}"}, FMT_CR)
    s.row("cash_close", "Estimated cash and bank balances at close", "Rs crore",
          {C: lambda c: f"=SUM({rs('b_cash_jun', 'b_div')})"}, FMT_CR, total=True)
    s.blank()
    s.section("Entry enterprise value and multiples")
    s.row("ev_eq", "Equity purchase price", "Rs crore", {C: lambda c: f"={r('su_eq', C)}"}, FMT_CR)
    s.row("ev_debt", "Add: existing borrowings", "Rs crore", {C: lambda c: f"={r('debt_exist', C)}"}, FMT_CR)
    s.row("ev_lease", "Add: lease liabilities", "Rs crore", {C: lambda c: f"={r('lease', C)}"}, FMT_CR)
    s.row("ev_cash", "Less: cash and bank balances at close", "Rs crore", {C: lambda c: f"=-{r('cash_close', C)}"},
          FMT_CR)
    s.row("ev_inv", "Less: non-operating investment", "Rs crore", {C: lambda c: f"=-{r('nonop', C)}"}, FMT_CR)
    s.row("ev", "Entry enterprise value", "Rs crore", {C: lambda c: f"=SUM({rs('ev_eq', 'ev_inv')})"}, FMT_CR,
          total=True, key_out=True)
    s.row("e_26", "CY2026E EBITDA (LTM at close)", "Rs crore", {C: lambda c: f"={r('o_ebitda', 'C')}"}, FMT_CR)
    s.row("e_ltm", "LTM Sep-2026 EBITDA (reported quarters)", "Rs crore", {C: lambda c: f"={r('h_ebitda', 'J')}"},
          FMT_CR)
    s.row("e_25", "CY2025 EBITDA", "Rs crore", {C: lambda c: f"={r('h_ebitda', 'G')}"}, FMT_CR)
    s.row("m_26", "Entry EV / CY2026E EBITDA (entry multiple)", "x", {C: lambda c: f"={r('ev', C)}/{r('e_26', C)}"},
          FMT_X, key_out=True)
    s.row("m_ltm", "Entry EV / LTM Sep-2026 EBITDA", "x", {C: lambda c: f"={r('ev', C)}/{r('e_ltm', C)}"}, FMT_X)
    s.row("m_25", "Entry EV / CY2025 EBITDA", "x", {C: lambda c: f"={r('ev', C)}/{r('e_25', C)}"}, FMT_X)
    s.row("pe_26", "Offer price / CY2026E EPS", "x",
          {C: lambda c: f"={r('su_offer', C)}/({r('o_ni', 'C')}/{r('su_shares', C)})"}, FMT_X)
    s.row("mkt_ev", "Market EV at the 30-Oct-2026 close (30-Jun-2026 balance sheet)", "Rs crore",
          {C: lambda c: f"={r('px', C)}*{r('shares_cr', C)}+{r('debt_exist', C)}+{r('lease', C)}"
                        f"-{r('h_cash_tot', 'L')}-{r('nonop', C)}"}, FMT_CR)
    s.row("mkt_m", "Market EV / LTM Sep-2026 EBITDA (no premium)", "x", {C: lambda c: f"={r('mkt_ev', C)}/{r('e_ltm', C)}"},
          FMT_X)
    s.blank()
    s.section("Debt sizing (x CY2026E EBITDA)")
    s.row("ds_ebitda", "Sizing EBITDA: CY2026E", "Rs crore", {C: lambda c: f"={r('e_26', C)}"}, FMT_CR)
    s.row("ds_tla_x", "Term loan A", "x", {C: lambda c: f"={r('tla_x', C)}*{r('lev_scale', C)}"}, FMT_X2)
    s.row("ds_tlb_x", "Term loan B", "x", {C: lambda c: f"={r('tlb_x', C)}*{r('lev_scale', C)}"}, FMT_X2)
    s.row("ds_mz_x", "Holdco PIK notes", "x", {C: lambda c: f"={r('mezz_x', C)}*{r('lev_scale', C)}"}, FMT_X2)
    s.row("tla_amt", "Term loan A amount", "Rs crore", {C: lambda c: f"={r('ds_tla_x', C)}*{r('ds_ebitda', C)}"},
          FMT_CR)
    s.row("tlb_amt", "Term loan B amount", "Rs crore", {C: lambda c: f"={r('ds_tlb_x', C)}*{r('ds_ebitda', C)}"},
          FMT_CR)
    s.row("mz_amt", "Holdco PIK notes amount", "Rs crore", {C: lambda c: f"={r('ds_mz_x', C)}*{r('ds_ebitda', C)}"},
          FMT_CR)
    s.row("debt_amt", "Total funded debt", "Rs crore", {C: lambda c: f"=SUM({rs('tla_amt', 'mz_amt')})"}, FMT_CR,
          total=True)
    s.row("debt_x", "Total funded debt / CY2026E EBITDA", "x", {C: lambda c: f"={r('debt_amt', C)}/{r('ds_ebitda', C)}"},
          FMT_X2)
    s.row("rcf_avail", "Revolver commitment (undrawn at close)", "Rs crore", {C: lambda c: f"={r('rcf_commit', C)}"},
          FMT_CR)
    s.blank()
    s.section("Uses of funds")

    def pct(k: str, tot: str) -> Callable[[str], str]:
        return lambda c: f"={r(k, 'C')}/{r(tot, 'C')}"

    s.row("u_eq", "Purchase of 100% of the equity (offer price x diluted shares)", "Rs crore",
          {C: lambda c: f"={r('su_eq', C)}", "D": pct("u_eq", "u_tot")}, FMT_CR)
    s.row("u_refi", "Refinance existing borrowings", "Rs crore",
          {C: lambda c: f"={r('debt_exist', C)}", "D": pct("u_refi", "u_tot")}, FMT_CR,
          note="None: Castrol India has no borrowings; leases stay in place")
    s.row("u_txn", "Transaction fees", "Rs crore",
          {C: lambda c: f"={r('txn_fee', C)}*{r('ev', C)}", "D": pct("u_txn", "u_tot")}, FMT_CR)
    s.row("u_fin", "Financing fees (capitalised, amortised over 5 years)", "Rs crore",
          {C: lambda c: f"={r('fin_fee', C)}*{r('debt_amt', C)}", "D": pct("u_fin", "u_tot")}, FMT_CR)
    s.row("u_tot", "Total uses", "Rs crore", {C: lambda c: f"=SUM({rs('u_eq', 'u_fin')})", "D": pct("u_tot", "u_tot")},
          FMT_CR, total=True)
    s.blank()
    s.section("Sources of funds")

    def xe(k: str) -> Callable[[str], str]:
        return lambda c: f"={r(k, 'C')}/{r('ds_ebitda', 'C')}"

    s.row("s_rcf", "Revolver drawn at close", "Rs crore", {C: 0.0, "D": pct("s_rcf", "s_tot"), "E": xe("s_rcf")},
          FMT_CR, "input", "Undrawn at close")
    s.row("s_tla", "Term loan A (amortising)", "Rs crore",
          {C: lambda c: f"={r('tla_amt', C)}", "D": pct("s_tla", "s_tot"), "E": xe("s_tla")}, FMT_CR)
    s.row("s_tlb", "Term loan B (1% amortisation + cash sweep)", "Rs crore",
          {C: lambda c: f"={r('tlb_amt', C)}", "D": pct("s_tlb", "s_tot"), "E": xe("s_tlb")}, FMT_CR)
    s.row("s_mz", "Holdco notes (cash + PIK coupon)", "Rs crore",
          {C: lambda c: f"={r('mz_amt', C)}", "D": pct("s_mz", "s_tot"), "E": xe("s_mz")}, FMT_CR)
    s.row("s_cash", "Excess balance-sheet cash (cash at close less minimum cash)", "Rs crore",
          {C: lambda c: f"=MAX(0,{r('cash_close', C)}-{r('min_cash', C)})", "D": pct("s_cash", "s_tot"),
           "E": xe("s_cash")}, FMT_CR)
    s.row("s_eq", "Sponsor equity (plug)", "Rs crore",
          {C: lambda c: f"={r('u_tot', C)}-SUM({rs('s_rcf', 's_cash')})", "D": pct("s_eq", "s_tot"), "E": xe("s_eq")},
          FMT_CR, key_out=True)
    s.row("s_tot", "Total sources", "Rs crore",
          {C: lambda c: f"=SUM({rs('s_rcf', 's_eq')})", "D": pct("s_tot", "s_tot"), "E": xe("s_tot")}, FMT_CR,
          total=True)
    s.row("su_diff", "Check: total sources less total uses (must be 0)", "Rs crore",
          {C: lambda c: f"={r('s_tot', C)}-{r('u_tot', C)}"}, FMT_CR2)
    s.blank()
    s.section("Pro-forma position after close")
    s.row("cash_post", "Cash on the balance sheet after close", "Rs crore",
          {C: lambda c: f"={r('cash_close', C)}-{r('s_cash', C)}"}, FMT_CR)
    s.row("nd_post", "Net debt after close (debt + leases - cash)", "Rs crore",
          {C: lambda c: f"={r('debt_amt', C)}+{r('s_rcf', C)}+{r('lease', C)}-{r('cash_post', C)}"}, FMT_CR)
    s.row("nd_x", "Net debt / CY2026E EBITDA", "x", {C: lambda c: f"={r('nd_post', C)}/{r('ds_ebitda', C)}"}, FMT_X2)
    s.row("eq_pct", "Sponsor equity / (sponsor equity + funded debt)", "%",
          {C: lambda c: f"={r('s_eq', C)}/({r('s_eq', C)}+{r('debt_amt', C)}+{r('s_rcf', C)})"}, FMT_PCT)
    s.row("pf_int", "Pro-forma annual cash interest at close", "Rs crore",
          {C: lambda c: f"={r('tla_amt', C)}*{r('tla_rate', C)}+{r('tlb_amt', C)}*{r('tlb_rate', C)}"
                        f"+{r('mz_amt', C)}*{r('mezz_cash', C)}+{r('s_rcf', C)}*{r('rcf_rate', C)}"
                        f"+({r('rcf_commit', C)}-{r('s_rcf', C)})*{r('rcf_fee', C)}+{r('lease', C)}*{r('lease_rate', C)}"},
          FMT_CR)
    s.row("pf_icr", "CY2026E EBITDA / pro-forma cash interest", "x",
          {C: lambda c: f"={r('ds_ebitda', C)}/{r('pf_int', C)}"}, FMT_X2,
          note="Leverage is set so that this stays at or above about 2.5x")
    s.row("d_rate", "Weighted all-in cost of funded debt (incl. PIK)", "%",
          {C: lambda c: f"=({r('tla_amt', C)}*{r('tla_rate', C)}+{r('tlb_amt', C)}*{r('tlb_rate', C)}"
                        f"+{r('mz_amt', C)}*{r('mezz_allin', C)})/{r('debt_amt', C)}"}, FMT_PCT2)
    s.row("d_rate_at", "After-tax cost of funded debt", "%",
          {C: lambda c: f"={r('d_rate', C)}*(1-{r('tax', C)}*{r('int_ded', C)})"}, FMT_PCT2)
    s.row("ebitda_yield", "EBITDA yield on entry EV (1 / entry multiple)", "%",
          {C: lambda c: f"={r('ds_ebitda', C)}/{r('ev', C)}"}, FMT_PCT2,
          note="Compare with the cost of debt: leverage adds most when the asset yields well above the debt cost")
    return s


# ============================================================================= Operating model
def build_operating(D: dict) -> Sheet:
    s = Sheet("Operating_Model", note_col="I",
              widths={"A": 58, "B": 12, "C": 13, "D": 12, "E": 12, "F": 12, "G": 12, "H": 12, "I": 70},
              freeze="C6")
    s.title("Operating model: income statement, working capital and free cash flow")
    s.text("Rs crore unless stated. CY2026E = 9M actual + Q4 estimate (pre-deal). CY2027E-CY2031E = LBO hold years; "
           "interest comes from Debt_Schedule and is charged on opening balances (no circular references).")
    s.blank()
    s.header({"A": "Item", "B": "Unit", "C": "CY2026E", "D": "CY2027E", "E": "CY2028E", "F": "CY2029E",
              "G": "CY2030E", "H": "CY2031E", "I": "Notes"})
    s.header({"A": "", "B": "", "C": "Pre-deal", "D": "Year 1", "E": "Year 2", "F": "Year 3", "G": "Year 4",
              "H": "Year 5 (exit)", "I": ""})
    s.section("Revenue")
    s.row("o_vol", "Volume growth", "% y/y", yr(lambda c: f"={r('vol', c)}"), FMT_PCT)
    s.row("o_pm", "Price and mix growth", "% y/y", yr(lambda c: f"={r('pm', c)}"), FMT_PCT)
    s.row("o_gd", "Sensitivity: revenue growth change (0 unless a data table is running)", "pp",
          yr(lambda c: f"={r('g_delta', 'D', True)}"), FMT_PCT)
    rg_cols = {"C": lambda c: f"={r('o_rev', 'C')}/{r('h_rev', 'G')}-1"}
    rg_cols.update(yr(lambda c: f"=(1+{r('o_vol', c)})*(1+{r('o_pm', c)})-1+{r('o_gd', c)}"))
    s.row("o_g", "Revenue growth", "% y/y", rg_cols, FMT_PCT)
    rv = {"C": lambda c: f"={r('h_rev', 'I')}+{r('q4_rev', 'C')}"}
    rv.update(yr(lambda c: f"={r('o_rev', pc(c))}*(1+{r('o_g', c)})"))
    s.row("o_rev", "Revenue from operations", "Rs crore", rv, FMT_CR, total=True)
    s.blank()
    s.section("Profitability")
    gm = {"C": lambda c: f"={r('o_gp', 'C')}/{r('o_rev', 'C')}"}
    gm.update(yr(lambda c: f"={r('gm', c)}"))
    s.row("o_gm", "Gross margin", "%", gm, FMT_PCT)
    gp = {"C": lambda c: f"={r('h_gp', 'I')}+{r('q4_rev', 'C')}*{r('q4_gm', 'C')}"}
    gp.update(yr(lambda c: f"={r('o_rev', c)}*{r('o_gm', c)}"))
    s.row("o_gp", "Gross profit", "Rs crore", gp, FMT_CR)
    s.row("o_cogs", "Cost of goods sold", "Rs crore", yr(lambda c: f"={r('o_rev', c)}-{r('o_gp', c)}", YC), FMT_CR)
    s.row("o_md", "Sensitivity: EBITDA margin change (0 unless a data table is running)", "pp",
          yr(lambda c: f"={r('m_delta', 'D', True)}"), FMT_PCT)
    em = {"C": lambda c: f"={r('o_ebitda', 'C')}/{r('o_rev', 'C')}"}
    em.update(yr(lambda c: f"={r('em', c)}+{r('o_md', c)}"))
    s.row("o_em", "EBITDA margin", "%", em, FMT_PCT)
    eb = {"C": lambda c: f"={r('h_ebitda', 'I')}+{r('q4_rev', 'C')}*{r('q4_em', 'C')}"}
    eb.update(yr(lambda c: f"={r('o_rev', c)}*{r('o_em', c)}"))
    s.row("o_ebitda", "EBITDA", "Rs crore", eb, FMT_CR, total=True, key_out=True)
    s.row("o_opex", "Employee and other operating costs (incl. royalty)", "Rs crore",
          yr(lambda c: f"={r('o_gp', c)}-{r('o_ebitda', c)}", YC), FMT_CR, note="Gross profit less EBITDA")
    s.row("o_opexp", "Employee and other operating costs as % of revenue", "%",
          yr(lambda c: f"={r('o_opex', c)}/{r('o_rev', c)}", YC), FMT_PCT)
    dap = {"C": lambda c: f"={r('o_da', 'C')}/{r('o_rev', 'C')}"}
    dap.update(yr(lambda c: f"={r('da_pct', c)}"))
    s.row("o_dap", "D&A as % of revenue", "%", dap, FMT_PCT2)
    da = {"C": lambda c: f"={r('h_da', 'I')}+{r('q4_da', 'C')}"}
    da.update(yr(lambda c: f"={r('o_rev', c)}*{r('o_dap', c)}"))
    s.row("o_da", "Depreciation and amortisation", "Rs crore", da, FMT_CR)
    s.row("o_ebit", "EBIT", "Rs crore", yr(lambda c: f"={r('o_ebitda', c)}-{r('o_da', c)}", YC), FMT_CR, total=True)
    s.blank()
    s.section("Finance costs and income (interest on opening balances)")
    s.row("o_oi", "Other income (pre-deal year only)", "Rs crore",
          {"C": lambda c: f"={r('h_oi', 'I')}+{r('q4_oi', 'C')}"}, FMT_CR,
          note="After the deal surplus cash is used at close; only interest on the minimum cash remains")
    s.row("o_fin", "Finance costs (pre-deal year only)", "Rs crore",
          {"C": lambda c: f"={r('h_fin', 'I')}+{r('q4_fin', 'C')}"}, FMT_CR)
    s.row("o_ii", "Interest income on cash", "Rs crore", yr(lambda c: f"={r('ii', c)}"), FMT_CR)
    s.row("o_itla", "Interest: term loan A", "Rs crore", yr(lambda c: f"={r('tla_int', c)}"), FMT_CR)
    s.row("o_itlb", "Interest: term loan B", "Rs crore", yr(lambda c: f"={r('tlb_int', c)}"), FMT_CR)
    s.row("o_imc", "Interest: holdco notes, cash coupon", "Rs crore", yr(lambda c: f"={r('mz_int', c)}"), FMT_CR)
    s.row("o_ipik", "Interest: holdco notes, PIK coupon (non-cash)", "Rs crore", yr(lambda c: f"={r('mz_pik', c)}"),
          FMT_CR)
    s.row("o_ircf", "Revolver interest and commitment fee", "Rs crore",
          yr(lambda c: f"={r('rcf_int', c)}+{r('rcf_cfee', c)}"), FMT_CR)
    s.row("o_ilease", "Interest on lease liabilities", "Rs crore", yr(lambda c: f"={r('ls_int', c)}"), FMT_CR)
    s.row("o_fee", "Amortisation of financing fees (non-cash)", "Rs crore", yr(lambda c: f"={r('ff_am', c)}"), FMT_CR)
    s.row("o_netfin", "Net finance costs", "Rs crore",
          yr(lambda c: f"={r('o_fin', c)}+{r('o_itla', c)}+{r('o_itlb', c)}+{r('o_imc', c)}+{r('o_ipik', c)}"
                       f"+{r('o_ircf', c)}+{r('o_ilease', c)}+{r('o_fee', c)}-{r('o_oi', c)}-{r('o_ii', c)}", YC),
          FMT_CR, total=True)
    s.blank()
    s.section("Profit")
    s.row("o_pbt", "Profit before tax", "Rs crore", yr(lambda c: f"={r('o_ebit', c)}-{r('o_netfin', c)}", YC), FMT_CR)
    s.row("o_acq", "Memo: acquisition debt interest and fee amortisation", "Rs crore",
          yr(lambda c: f"={r('o_itla', c)}+{r('o_itlb', c)}+{r('o_imc', c)}+{r('o_ipik', c)}+{r('o_ircf', c)}"
                       f"+{r('o_fee', c)}"), FMT_CR)
    s.row("o_taxable", "Taxable profit (adds back acquisition interest if not deductible)", "Rs crore",
          yr(lambda c: f"={r('o_pbt', c)}+IF({r('int_ded', 'C', True)}=1,0,{r('o_acq', c)})"), FMT_CR)
    tx = {"C": lambda c: f"={r('h_tax', 'I')}+({r('o_pbt', 'C')}-{r('h_pbt_calc', 'I')})*{r('tax', 'C', True)}"}
    tx.update(yr(lambda c: f"=MAX(0,{r('o_taxable', c)})*{r('tax', 'C', True)}"))
    s.row("o_tax", "Tax", "Rs crore", tx, FMT_CR, note="CY2026E = 9M actual tax + 25.17% of Q4 profit before tax")
    s.row("o_ni", "Net income", "Rs crore", yr(lambda c: f"={r('o_pbt', c)}-{r('o_tax', c)}", YC), FMT_CR, total=True)
    s.row("o_etr", "Effective tax rate", "%", yr(lambda c: f"=IF({r('o_pbt', c)}>0,{r('o_tax', c)}/{r('o_pbt', c)},0)", YC),
          FMT_PCT)
    s.blank()
    s.section("Trade working capital")
    for key, lab, a26, live in [("o_invd", "Inventory days (on COGS)", "inv26", "invd"),
                                ("o_recd", "Receivable days (on revenue)", "rec26", "recd"),
                                ("o_payd", "Payable days (on COGS)", "pay26", "payd")]:
        d = {"C": (lambda c, a=a26: f"={r(a, 'C')}")}
        d.update(yr(lambda c, lv=live: f"={r(lv, c)}"))
        s.row(key, lab, "days", d, FMT_CR1)
    s.row("o_inv", "Inventories", "Rs crore", yr(lambda c: f"={r('o_cogs', c)}*{r('o_invd', c)}/365", YC), FMT_CR)
    s.row("o_rec", "Trade receivables", "Rs crore", yr(lambda c: f"={r('o_rev', c)}*{r('o_recd', c)}/365", YC), FMT_CR)
    s.row("o_pay", "Trade payables", "Rs crore", yr(lambda c: f"={r('o_cogs', c)}*{r('o_payd', c)}/365", YC), FMT_CR)
    s.row("o_nwc", "Trade working capital", "Rs crore",
          yr(lambda c: f"={r('o_inv', c)}+{r('o_rec', c)}-{r('o_pay', c)}", YC), FMT_CR, total=True)
    s.row("o_dnwc", "Increase / (decrease) in trade working capital", "Rs crore",
          yr(lambda c: f"={r('o_nwc', c)}-{r('o_nwc', pc(c))}"), FMT_CR,
          note="CY2026E second-half change is in the cash-at-close bridge on Sources_Uses")
    s.blank()
    s.section("Capex and leases")
    cxp = {"C": lambda c: f"={r('o_capex', 'C')}/{r('o_rev', 'C')}"}
    cxp.update(yr(lambda c: f"={r('cx', c)}"))
    s.row("o_cxp", "Capex as % of revenue", "%", cxp, FMT_PCT)
    cx = {"C": lambda c: f"={r('capex26', 'C')}"}
    cx.update(yr(lambda c: f"={r('o_rev', c)}*{r('o_cxp', c)}"))
    s.row("o_capex", "Capex", "Rs crore", cx, FMT_CR)
    s.row("o_lprin", "Lease principal repaid", "Rs crore", yr(lambda c: f"={r('o_rev', c)}*{r('lease_prin', 'C', True)}"),
          FMT_CR)
    s.blank()
    s.section("Unlevered free cash flow (before financing)")
    s.row("u_ebitda", "EBITDA", "Rs crore", yr(lambda c: f"={r('o_ebitda', c)}"), FMT_CR)
    s.row("u_tax", "Less: tax on EBIT", "Rs crore", yr(lambda c: f"=-{r('o_ebit', c)}*{r('tax', 'C', True)}"), FMT_CR)
    s.row("u_capex", "Less: capex", "Rs crore", yr(lambda c: f"=-{r('o_capex', c)}"), FMT_CR)
    s.row("u_nwc", "Less: increase in trade working capital", "Rs crore", yr(lambda c: f"=-{r('o_dnwc', c)}"), FMT_CR)
    s.row("u_lease", "Less: lease payments (principal + interest)", "Rs crore",
          yr(lambda c: f"=-({r('o_lprin', c)}+{r('o_ilease', c)})"), FMT_CR)
    s.row("o_ufcf", "Unlevered free cash flow", "Rs crore", yr(lambda c: f"=SUM({rs('u_ebitda', 'u_lease', c)})"),
          FMT_CR, total=True)
    s.blank()
    s.section("Levered free cash flow = cash available for debt repayment")
    s.row("l_ni", "Net income", "Rs crore", yr(lambda c: f"={r('o_ni', c)}"), FMT_CR)
    s.row("l_da", "Add: depreciation and amortisation", "Rs crore", yr(lambda c: f"={r('o_da', c)}"), FMT_CR)
    s.row("l_pik", "Add: PIK interest (non-cash)", "Rs crore", yr(lambda c: f"={r('o_ipik', c)}"), FMT_CR)
    s.row("l_fee", "Add: financing fee amortisation (non-cash)", "Rs crore", yr(lambda c: f"={r('o_fee', c)}"), FMT_CR)
    s.row("l_nwc", "Less: increase in trade working capital", "Rs crore", yr(lambda c: f"=-{r('o_dnwc', c)}"), FMT_CR)
    s.row("l_capex", "Less: capex", "Rs crore", yr(lambda c: f"=-{r('o_capex', c)}"), FMT_CR)
    s.row("l_lease", "Less: lease principal repaid", "Rs crore", yr(lambda c: f"=-{r('o_lprin', c)}"), FMT_CR)
    s.row("o_lfcf", "Levered free cash flow (before debt repayment)", "Rs crore",
          yr(lambda c: f"=SUM({rs('l_ni', 'l_lease', c)})"), FMT_CR, total=True, key_out=True)
    s.row("o_lfcf2", "Cross-check: levered FCF from EBITDA (direct method)", "Rs crore",
          yr(lambda c: f"={r('o_ebitda', c)}+{r('o_ii', c)}-({r('o_itla', c)}+{r('o_itlb', c)}+{r('o_imc', c)}"
                       f"+{r('o_ircf', c)}+{r('o_ilease', c)})-{r('o_tax', c)}-{r('o_capex', c)}-{r('o_dnwc', c)}"
                       f"-{r('o_lprin', c)}"), FMT_CR)
    s.row("o_lfcf_diff", "Difference (must be 0)", "Rs crore", yr(lambda c: f"={r('o_lfcf', c)}-{r('o_lfcf2', c)}"),
          FMT_CR2)
    s.row("o_conv", "Levered FCF / EBITDA", "%", yr(lambda c: f"={r('o_lfcf', c)}/{r('o_ebitda', c)}"), FMT_PCT)
    return s


# ============================================================================= Debt schedule
def build_debt(D: dict) -> Sheet:
    s = Sheet("Debt_Schedule", note_col="I",
              widths={"A": 58, "B": 12, "C": 13, "D": 12, "E": 12, "F": 12, "G": 12, "H": 12, "I": 60},
              freeze="C5")
    s.title("Debt schedule, cash sweep, credit statistics and covenant tests")
    s.text("Rs crore unless stated. Repayments are negative. Interest is charged on opening balances, so the model has "
           "no circular references. Column C = balances right after close.")
    s.blank()
    s.header({"A": "Item", "B": "Unit", "C": "Close 31-Dec-2026", "D": "CY2027E", "E": "CY2028E", "F": "CY2029E",
              "G": "CY2030E", "H": "CY2031E", "I": "Notes"})
    s.section("Cash waterfall")
    s.row("d_open_cash", "Opening cash", "Rs crore", yr(lambda c: f"={r('d_close_cash', pc(c))}"), FMT_CR)
    s.row("d_lfcf", "Add: levered free cash flow", "Rs crore", yr(lambda c: f"={r('o_lfcf', c)}"), FMT_CR)
    s.row("d_min", "Less: minimum cash kept on balance sheet", "Rs crore",
          yr(lambda c: f"=-{r('min_cash', 'C', True)}"), FMT_CR)
    s.row("d_avail", "Cash available for debt service", "Rs crore",
          yr(lambda c: f"={r('d_open_cash', c)}+{r('d_lfcf', c)}+{r('d_min', c)}"), FMT_CR, total=True)
    s.row("d_m_tla", "Scheduled repayment: term loan A", "Rs crore",
          yr(lambda c: f"=-MIN({r('tla_open', c)},{r('tla_amort', c)}*{r('tla_close', 'C', True)})"), FMT_CR)
    s.row("d_m_tlb", "Scheduled repayment: term loan B", "Rs crore",
          yr(lambda c: f"=-MIN({r('tlb_open', c)},{r('tlb_amort', 'C', True)}*{r('tlb_close', 'C', True)})"), FMT_CR)
    s.row("d_after_m", "Cash after scheduled repayments", "Rs crore",
          yr(lambda c: f"={r('d_avail', c)}+{r('d_m_tla', c)}+{r('d_m_tlb', c)}"), FMT_CR, total=True)
    s.row("d_rcf_draw", "Revolver draw (only if cash would fall below the minimum)", "Rs crore",
          yr(lambda c: f"=MIN(MAX(0,-{r('d_after_m', c)}),{r('rcf_commit', 'C', True)}-{r('rcf_open', c)})"), FMT_CR)
    s.row("d_rcf_rep", "Revolver repayment", "Rs crore",
          yr(lambda c: f"=-MIN({r('rcf_open', c)},MAX(0,{r('d_after_m', c)}))"), FMT_CR)
    s.row("d_for_sweep", "Excess cash available for the sweep", "Rs crore",
          yr(lambda c: f"=MAX(0,{r('d_after_m', c)}+{r('d_rcf_draw', c)}+{r('d_rcf_rep', c)})"), FMT_CR)
    s.row("d_sweep_amt", "Cash sweep amount", "Rs crore",
          yr(lambda c: f"={r('sweep', 'C', True)}*{r('d_for_sweep', c)}"), FMT_CR)
    s.row("d_s_tlb", "Sweep prepayment: term loan B (first)", "Rs crore",
          yr(lambda c: f"=-MIN({r('tlb_open', c)}+{r('d_m_tlb', c)},{r('d_sweep_amt', c)})"), FMT_CR)
    s.row("d_s_tla", "Sweep prepayment: term loan A (second)", "Rs crore",
          yr(lambda c: f"=-MIN({r('tla_open', c)}+{r('d_m_tla', c)},{r('d_sweep_amt', c)}+{r('d_s_tlb', c)})"), FMT_CR)
    cc = {"C": lambda c: f"={r('cash_post', 'C')}"}
    cc.update(yr(lambda c: f"={r('d_open_cash', c)}+{r('d_lfcf', c)}+{r('d_m_tla', c)}+{r('d_m_tlb', c)}"
                           f"+{r('d_rcf_draw', c)}+{r('d_rcf_rep', c)}+{r('d_s_tlb', c)}+{r('d_s_tla', c)}"))
    s.row("d_close_cash", "Closing cash", "Rs crore", cc, FMT_CR, total=True)
    s.blank()

    def tranche(p: str, name: str, amt_key: str, rate_key: str, mand_key: str, sweep_key: str) -> None:
        s.section(name)
        s.row(f"{p}_open", "Opening balance", "Rs crore", yr(lambda c: f"={r(p + '_close', pc(c))}"), FMT_CR)
        s.row(f"{p}_m", "Scheduled repayment", "Rs crore", yr(lambda c: f"={r(mand_key, c)}"), FMT_CR)
        s.row(f"{p}_s", "Cash sweep prepayment", "Rs crore", yr(lambda c: f"={r(sweep_key, c)}"), FMT_CR)
        cl = {"C": lambda c: f"={r(amt_key, 'C')}"}
        cl.update(yr(lambda c: f"={r(p + '_open', c)}+{r(p + '_m', c)}+{r(p + '_s', c)}"))
        s.row(f"{p}_close", "Closing balance", "Rs crore", cl, FMT_CR, total=True)
        s.row(f"{p}_r", "Interest rate", "%", yr(lambda c: f"={r(rate_key, 'C', True)}"), FMT_PCT2)
        s.row(f"{p}_int", "Interest (on opening balance)", "Rs crore",
              yr(lambda c: f"={r(p + '_open', c)}*{r(p + '_r', c)}"), FMT_CR)
        s.blank()

    tranche("tla", "Term loan A (senior, amortising)", "s_tla", "tla_rate", "d_m_tla", "d_s_tla")
    tranche("tlb", "Term loan B (senior, 1% amortisation + cash sweep)", "s_tlb", "tlb_rate", "d_m_tlb", "d_s_tlb")
    s.section("Holdco PIK notes (structurally subordinated; repaid at exit)")
    s.row("mz_open", "Opening balance", "Rs crore", yr(lambda c: f"={r('mz_close', pc(c))}"), FMT_CR)
    s.row("mz_pik", "PIK interest added to principal", "Rs crore",
          yr(lambda c: f"={r('mz_open', c)}*{r('mezz_pik', 'C', True)}"), FMT_CR)
    mz = {"C": lambda c: f"={r('s_mz', 'C')}"}
    mz.update(yr(lambda c: f"={r('mz_open', c)}+{r('mz_pik', c)}"))
    s.row("mz_close", "Closing balance", "Rs crore", mz, FMT_CR, total=True)
    s.row("mz_int", "Cash interest (on opening balance)", "Rs crore",
          yr(lambda c: f"={r('mz_open', c)}*{r('mezz_cash', 'C', True)}"), FMT_CR)
    s.blank()
    s.section("Revolving credit facility")
    s.row("rcf_open", "Opening balance", "Rs crore", yr(lambda c: f"={r('rcf_close', pc(c))}"), FMT_CR)
    s.row("rcf_dr", "Draw", "Rs crore", yr(lambda c: f"={r('d_rcf_draw', c)}"), FMT_CR)
    s.row("rcf_rp", "Repayment", "Rs crore", yr(lambda c: f"={r('d_rcf_rep', c)}"), FMT_CR)
    rc = {"C": lambda c: f"={r('s_rcf', 'C')}"}
    rc.update(yr(lambda c: f"={r('rcf_open', c)}+{r('rcf_dr', c)}+{r('rcf_rp', c)}"))
    s.row("rcf_close", "Closing balance", "Rs crore", rc, FMT_CR, total=True)
    s.row("rcf_int", "Interest on drawn balance (opening)", "Rs crore",
          yr(lambda c: f"={r('rcf_open', c)}*{r('rcf_rate', 'C', True)}"), FMT_CR)
    s.row("rcf_cfee", "Commitment fee on undrawn amount (opening)", "Rs crore",
          yr(lambda c: f"=({r('rcf_commit', 'C', True)}-{r('rcf_open', c)})*{r('rcf_fee', 'C', True)}"), FMT_CR)
    s.blank()
    s.section("Leases, interest income and financing fees")
    s.row("ls_bal", "Lease liabilities (held flat)", "Rs crore", yr(lambda c: f"={r('lease', 'C', True)}", YC), FMT_CR)
    s.row("ls_int", "Lease interest (on opening balance)", "Rs crore",
          yr(lambda c: f"={r('ls_bal', pc(c))}*{r('lease_rate', 'C', True)}"), FMT_CR)
    s.row("ii", "Interest income on opening cash", "Rs crore",
          yr(lambda c: f"={r('d_open_cash', c)}*{r('tbill', 'C', True)}"), FMT_CR)
    s.row("ff_open", "Unamortised financing fees: opening", "Rs crore", yr(lambda c: f"={r('ff_close', pc(c))}"),
          FMT_CR)
    s.row("ff_am", "Amortisation", "Rs crore",
          yr(lambda c: f"=MIN({r('ff_open', c)},{r('u_fin', 'C', True)}/{r('fin_fee_yrs', 'C', True)})"), FMT_CR)
    ff = {"C": lambda c: f"={r('u_fin', 'C')}"}
    ff.update(yr(lambda c: f"={r('ff_open', c)}-{r('ff_am', c)}"))
    s.row("ff_close", "Unamortised financing fees: closing", "Rs crore", ff, FMT_CR)
    s.blank()
    s.section("Credit statistics")
    s.row("d_tot", "Total debt (TLA + TLB + holdco notes + revolver)", "Rs crore",
          yr(lambda c: f"={r('tla_close', c)}+{r('tlb_close', c)}+{r('mz_close', c)}+{r('rcf_close', c)}", YC), FMT_CR,
          total=True)
    s.row("d_lease", "Lease liabilities", "Rs crore", yr(lambda c: f"={r('ls_bal', c)}", YC), FMT_CR)
    s.row("d_cash", "Cash", "Rs crore", yr(lambda c: f"={r('d_close_cash', c)}", YC), FMT_CR)
    s.row("d_nd", "Net debt (incl. leases)", "Rs crore",
          yr(lambda c: f"={r('d_tot', c)}+{r('d_lease', c)}-{r('d_cash', c)}", YC), FMT_CR, total=True)
    s.row("d_ebitda", "EBITDA", "Rs crore", yr(lambda c: f"={r('o_ebitda', c)}", YC), FMT_CR)
    s.row("d_lev_tot", "Total debt / EBITDA", "x", yr(lambda c: f"={r('d_tot', c)}/{r('d_ebitda', c)}", YC), FMT_X2)
    s.row("d_lev_net", "Net debt / EBITDA", "x", yr(lambda c: f"={r('d_nd', c)}/{r('d_ebitda', c)}", YC), FMT_X2,
          key_out=True)
    s.row("d_lev_sr", "Senior net debt / EBITDA (TLA + TLB + revolver + leases - cash)", "x",
          yr(lambda c: f"=({r('tla_close', c)}+{r('tlb_close', c)}+{r('rcf_close', c)}+{r('d_lease', c)}"
                       f"-{r('d_cash', c)})/{r('d_ebitda', c)}", YC), FMT_X2)
    s.row("d_cint", "Cash interest (TLA + TLB + holdco cash coupon + revolver + leases)", "Rs crore",
          yr(lambda c: f"={r('tla_int', c)}+{r('tlb_int', c)}+{r('mz_int', c)}+{r('rcf_int', c)}+{r('rcf_cfee', c)}"
                       f"+{r('ls_int', c)}"), FMT_CR)
    s.row("d_icr", "EBITDA / cash interest", "x", yr(lambda c: f"={r('d_ebitda', c)}/{r('d_cint', c)}"), FMT_X2,
          key_out=True)
    s.row("d_icr2", "(EBITDA - capex) / cash interest", "x",
          yr(lambda c: f"=({r('d_ebitda', c)}-{r('o_capex', c)})/{r('d_cint', c)}"), FMT_X2)
    s.row("d_paydown", "Senior debt repaid since close (cumulative)", "%",
          yr(lambda c: f"=IF(({r('tla_close', 'C', True)}+{r('tlb_close', 'C', True)})=0,0,1-({r('tla_close', c)}"
                       f"+{r('tlb_close', c)})/({r('tla_close', 'C', True)}+{r('tlb_close', 'C', True)}))"), FMT_PCT)
    s.blank()
    s.section("Covenant tests (maintenance covenants; information, not a model-integrity check)")
    s.row("d_cov_lev", "Maximum net debt / EBITDA", "x", yr(lambda c: f"={r('cov_lev', c)}"), FMT_X2)
    s.row("d_t_lev", "Leverage test", "", yr(lambda c: f'=IF({r("d_lev_net", c)}<={r("d_cov_lev", c)},"PASS","FAIL")'),
          FMT_GEN)
    s.row("d_headroom", "EBITDA headroom to the leverage covenant", "%",
          yr(lambda c: f"=1-{r('d_lev_net', c)}/{r('d_cov_lev', c)}"), FMT_PCT)
    s.row("d_cov_icr", "Minimum EBITDA / cash interest", "x", yr(lambda c: f"={r('cov_icr', c)}"), FMT_X2)
    s.row("d_t_icr", "Interest cover test", "", yr(lambda c: f'=IF({r("d_icr", c)}>={r("d_cov_icr", c)},"PASS","FAIL")'),
          FMT_GEN)
    s.row("d_cov_all", "All covenant tests, CY2027E-CY2031E", "",
          {"C": lambda c: f'=IF(COUNTIF({rg("d_t_lev", "D", "H")},"FAIL")+COUNTIF({rg("d_t_icr", "D", "H")},"FAIL")=0,'
                          f'"PASS","BREACH")'}, FMT_GEN, key_out=True)
    return s


# ============================================================================= Returns
def build_returns(D: dict) -> Sheet:
    s = Sheet("Returns", note_col="I",
              widths={"A": 60, "B": 12, "C": 13, "D": 12, "E": 12, "F": 12, "G": 12, "H": 13, "I": 60},
              freeze="A5")
    s.title("Exit, sponsor returns (XIRR, MOIC) and returns attribution")
    s.text("Rs crore unless stated. Exit on 31-Dec-2031 at the exit multiple x CY2031E EBITDA. Base exit multiple = "
           "entry multiple.")
    s.blank()
    s.header({"A": "Item", "B": "Unit", "C": "Value", "D": "", "E": "", "F": "", "G": "", "H": "", "I": "Notes"})
    C = "C"
    s.section("Exit valuation at 31-Dec-2031")
    s.row("x_ebitda", "CY2031E EBITDA", "Rs crore", {C: lambda c: f"={r('o_ebitda', 'H')}"}, FMT_CR)
    s.row("x_entry_m", "Entry multiple (EV / CY2026E EBITDA)", "x", {C: lambda c: f"={r('m_26', 'C')}"}, FMT_X)
    s.row("x_delta", "Scenario change to the exit multiple", "x", {C: lambda c: f"={r('xd', 'C')}"}, FMT_X)
    s.row("x_mult", "Exit multiple used (EV / CY2031E EBITDA)", "x",
          {C: lambda c: f"=IF(ISNUMBER({r('exit_ovr', 'D', True)}),{r('exit_ovr', 'D', True)},"
                        f"{r('x_entry_m', C)}+{r('x_delta', C)})"}, FMT_X, key_out=True,
          note="A sensitivity data table can override this temporarily")
    s.row("x_ev", "Exit enterprise value", "Rs crore", {C: lambda c: f"={r('x_mult', C)}*{r('x_ebitda', C)}"}, FMT_CR,
          total=True)
    s.row("x_tla", "Less: term loan A at exit", "Rs crore", {C: lambda c: f"=-{r('tla_close', 'H')}"}, FMT_CR)
    s.row("x_tlb", "Less: term loan B at exit", "Rs crore", {C: lambda c: f"=-{r('tlb_close', 'H')}"}, FMT_CR)
    s.row("x_mz", "Less: holdco notes incl. accrued PIK", "Rs crore", {C: lambda c: f"=-{r('mz_close', 'H')}"}, FMT_CR)
    s.row("x_rcf", "Less: revolver", "Rs crore", {C: lambda c: f"=-{r('rcf_close', 'H')}"}, FMT_CR)
    s.row("x_lease", "Less: lease liabilities", "Rs crore", {C: lambda c: f"=-{r('ls_bal', 'H')}"}, FMT_CR)
    s.row("x_cash", "Add: cash", "Rs crore", {C: lambda c: f"={r('d_close_cash', 'H')}"}, FMT_CR)
    s.row("x_inv", "Add: non-operating investment (book value)", "Rs crore", {C: lambda c: f"={r('nonop', 'C')}"},
          FMT_CR)
    s.row("x_eq", "Exit equity value (100%)", "Rs crore", {C: lambda c: f"=SUM({rs('x_ev', 'x_inv')})"}, FMT_CR,
          total=True)
    s.row("nd_exit", "Memo: net debt at exit (incl. leases)", "Rs crore",
          {C: lambda c: f"=-SUM({rs('x_tla', 'x_lease')})-{r('x_cash', C)}"}, FMT_CR)
    s.blank()
    s.section("Sponsor returns")
    s.row("r_inv", "Sponsor equity invested at close", "Rs crore", {C: lambda c: f"={r('s_eq', 'C')}"}, FMT_CR)
    s.row("r_gain", "Equity gain before the management incentive pool", "Rs crore",
          {C: lambda c: f"={r('x_eq', C)}-{r('r_inv', C)}"}, FMT_CR)
    s.row("r_mip", "Management incentive pool", "Rs crore",
          {C: lambda c: f"={r('mip', 'C')}*MAX(0,{r('r_gain', C)})"}, FMT_CR)
    s.row("r_proc", "Sponsor exit proceeds", "Rs crore", {C: lambda c: f"={r('x_eq', C)}-{r('r_mip', C)}"}, FMT_CR,
          total=True)
    s.row("r_moic", "Multiple of invested capital (MOIC)", "x", {C: lambda c: f"={r('r_proc', C)}/{r('r_inv', C)}"},
          FMT_X2, key_out=True)
    s.row("r_years", "Holding period", "years",
          {C: lambda c: f"=({r('exit_date', 'C')}-{r('entry_date', 'C')})/365"}, '0.00')
    s.blank()
    s.section("Sponsor cash flows by date (negative = invested)")
    s.header({"A": "", "B": "", "C": "Close", "D": "CY2027E", "E": "CY2028E", "F": "CY2029E", "G": "CY2030E",
              "H": "CY2031E exit", "I": ""})
    dd = {"C": lambda c: f"={r('entry_date', 'C')}"}
    dd.update(yr(lambda c: f"=EDATE({r('cf_date', pc(c))},12)"))
    s.row("cf_date", "Date", "date", dd, FMT_DATE)
    fl: dict = {"C": lambda c: f"=-{r('r_inv', 'C')}"}
    for c in ["D", "E", "F", "G"]:
        fl[c] = 0.0
    fl["H"] = lambda c: f"={r('r_proc', 'C')}"
    s.row("cf_flow", "Sponsor cash flow", "Rs crore", fl, FMT_CR, "input",
          "No interim distributions: all cash above the minimum repays debt")
    s.row("r_irr", "Sponsor IRR (XIRR on dated cash flows)", "%",
          {C: lambda c: f"=IF({r('cf_flow', 'H')}<=0,-1,XIRR({rg('cf_flow', 'C', 'H')},{rg('cf_date', 'C', 'H')}))"},
          FMT_PCT, key_out=True)
    s.row("r_irr_cf", "IRR check: MOIC^(365/days) - 1", "%",
          {C: lambda c: f"=IF({r('r_proc', C)}<=0,-1,{r('r_moic', C)}^(365/({r('cf_date', 'H')}-{r('cf_date', 'C')}))-1)"},
          FMT_PCT)
    s.row("r_npv", "NPV of sponsor cash flows at the IRR (should be about 0)", "Rs crore",
          {C: lambda c: f"=IF({r('r_irr', C)}<=-1,0,XNPV({r('r_irr', C)},{rg('cf_flow', 'C', 'H')},"
                        f"{rg('cf_date', 'C', 'H')}))"}, FMT_CR2)
    s.blank()
    s.section("Returns attribution: what created the sponsor's gain")
    s.header({"A": "", "B": "", "C": "Rs crore", "D": "% of total", "E": "", "F": "", "G": "", "H": "", "I": ""})

    def share(k: str) -> Callable[[str], str]:
        return lambda c: f'=IF({r("a_tot", "C")}>0,{r(k, "C")}/{r("a_tot", "C")},"n.m.")'

    s.row("a_ebitda", "EBITDA growth (valued at the entry multiple)", "Rs crore",
          {C: lambda c: f"={r('x_entry_m', C)}*({r('x_ebitda', C)}-{r('o_ebitda', 'C')})", "D": share("a_ebitda")},
          FMT_CR)
    s.row("a_mult", "Multiple change (exit less entry multiple, x CY2031E EBITDA)", "Rs crore",
          {C: lambda c: f"=({r('x_mult', C)}-{r('x_entry_m', C)})*{r('x_ebitda', C)}", "D": share("a_mult")}, FMT_CR)
    s.row("a_debt", "Debt paydown and cash build (net debt at close less net debt at exit)", "Rs crore",
          {C: lambda c: f"={r('nd_post', 'C')}-{r('nd_exit', C)}", "D": share("a_debt")}, FMT_CR)
    s.row("a_fees", "Transaction and financing fees paid at close", "Rs crore",
          {C: lambda c: f"=-({r('u_txn', 'C')}+{r('u_fin', 'C')})", "D": share("a_fees")}, FMT_CR)
    s.row("a_mip", "Management incentive pool", "Rs crore", {C: lambda c: f"=-{r('r_mip', C)}", "D": share("a_mip")},
          FMT_CR)
    s.row("a_tot", "Total value created for the sponsor", "Rs crore",
          {C: lambda c: f"=SUM({rs('a_ebitda', 'a_mip')})", "D": share("a_tot")}, FMT_CR, total=True)
    s.row("a_chk", "Sponsor exit proceeds less equity invested", "Rs crore",
          {C: lambda c: f"={r('r_proc', C)}-{r('r_inv', C)}"}, FMT_CR)
    s.row("a_diff", "Difference (must be 0)", "Rs crore", {C: lambda c: f"={r('a_tot', C)}-{r('a_chk', C)}"}, FMT_CR2)
    s.blank()
    s.section("Unlevered return on the business (no debt, before fees) for comparison")
    uf: dict = {"C": lambda c: f"=-{r('ev', 'C')}"}
    for c in ["D", "E", "F", "G"]:
        uf[c] = (lambda c: f"={r('o_ufcf', c)}")
    uf["H"] = lambda c: f"={r('o_ufcf', 'H')}+{r('x_ev', 'C')}"
    s.row("uf_flow", "Entry EV, unlevered free cash flow and exit EV", "Rs crore", uf, FMT_CR)
    s.row("u_irr", "Unlevered IRR", "%", {C: lambda c: f"=XIRR({rg('uf_flow', 'C', 'H')},{rg('cf_date', 'C', 'H')})"},
          FMT_PCT)
    s.row("u_dcost", "After-tax cost of funded debt", "%", {C: lambda c: f"={r('d_rate_at', 'C')}"}, FMT_PCT)
    s.row("u_spread", "Unlevered IRR less after-tax cost of debt", "pp",
          {C: lambda c: f"={r('u_irr', C)}-{r('u_dcost', C)}"}, FMT_PCT,
          note="Leverage raises the equity IRR only to the extent the business earns more than the debt costs")
    return s


# ============================================================================= Sensitivities
EXITS = [12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0]
PREMS = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35]
LEVS = [2.50, 3.00, 3.50, 3.75, 4.00, 4.50, 5.00]
DELTAS = [-0.03, -0.02, -0.01, 0.0, 0.01, 0.02, 0.03]
DRIVERS = {"scen_ovr": 5, "metric_ovr": 6, "prem_ovr": 7, "exit_ovr": 8, "lev_ovr": 9, "m_delta": 10, "g_delta": 11}
DRV_LAST = 11      # last driver row (Checks counts D5:D11)
HURDLE_ROW = 12
TABLES = [
    dict(id="t1", corner=19, title="Sponsor IRR: offer premium (rows) x exit multiple (columns)",
         top_label="Exit multiple (x CY2031E EBITDA)", left_label="Offer premium to 30-Oct-2026 close",
         top=EXITS, left=PREMS, row_input="exit_ovr", col_input="prem_ovr", out="r_irr",
         f_top=FMT_X, f_left=FMT_PCT, f_out=FMT_PCT, highlight=True),
    dict(id="t2", corner=30, title="Sponsor IRR: total leverage at close (rows) x exit multiple (columns)",
         top_label="Exit multiple (x CY2031E EBITDA)", left_label="Total funded debt (x CY2026E EBITDA)",
         top=EXITS, left=LEVS, row_input="exit_ovr", col_input="lev_ovr", out="r_irr",
         f_top=FMT_X, f_left=FMT_X2, f_out=FMT_PCT, highlight=True),
    dict(id="t3", corner=41, title="Sponsor IRR: EBITDA margin change (rows) x revenue growth change (columns), "
                                   "applied to every year CY2027E-CY2031E",
         top_label="Change in annual revenue growth (pp)", left_label="Change in EBITDA margin (pp)",
         top=DELTAS, left=DELTAS, row_input="g_delta", col_input="m_delta", out="r_irr",
         f_top='+0.0%;-0.0%;0.0%', f_left='+0.0%;-0.0%;0.0%', f_out=FMT_PCT, highlight=True),
    dict(id="t4", corner=52, title="Sponsor MOIC: offer premium (rows) x exit multiple (columns)",
         top_label="Exit multiple (x CY2031E EBITDA)", left_label="Offer premium to 30-Oct-2026 close",
         top=EXITS, left=PREMS, row_input="exit_ovr", col_input="prem_ovr", out="r_moic",
         f_top=FMT_X, f_left=FMT_PCT, f_out=FMT_X2, highlight=False),
]
T5 = dict(title_row=61, label_row=62, formula_row=63, first=64,
          cols=["D", "E", "F", "G", "H", "I", "J", "K", "L", "M"],
          labels=["Sponsor IRR", "MOIC", "CY2031E EBITDA (Rs crore)", "EBITDA CAGR CY2026E-31E", "Exit EV (Rs crore)",
                  "Exit equity (Rs crore)", "Net debt / EBITDA at exit", "Lowest EBITDA / cash interest",
                  "Covenant tests", "Core model checks"],
          fmts=[FMT_PCT, FMT_X2, FMT_CR, FMT_PCT, FMT_CR, FMT_CR, FMT_X2, FMT_X2, FMT_GEN, FMT_GEN])


def plan_sensitivities() -> None:
    for k, row in DRIVERS.items():
        POS[k] = ("Sensitivities", row)
    POS["sens_hurdle"] = ("Sensitivities", HURDLE_ROW)
    for i in range(3):
        POS[f"t5_{i + 1}"] = ("Sensitivities", T5["first"] + i)


def write_sensitivities(wb: Workbook) -> dict:
    ws = wb["Sensitivities"]
    CTX["sheet"] = "Sensitivities"
    ws["A1"] = "Sensitivity analysis (Excel data tables, live)"
    ws["A1"].font = F_TITLE
    ws["A2"] = ("Each grid is an Excel What-If data table ({=TABLE()}) that re-runs the whole model for every cell. "
                "Green cells reach the IRR hurdle. If the grids look stale, press F9 (Formulas > Calculation Options "
                "must be Automatic, not 'Automatic except for data tables').")
    ws["A2"].font = F_NOTE
    for col in range(1, 6):
        ws.cell(4, col).fill = FILL_SEC
    ws["A4"] = "Data-table driver cells: leave these EMPTY. The data tables below write trial values into them."
    ws["A4"].font = F_SEC
    labels = {"scen_ovr": "Scenario override (1-3) used by the scenario table",
              "metric_ovr": "Output selector (1-10) used by the scenario table",
              "prem_ovr": "Offer premium override", "exit_ovr": "Exit multiple override (x)",
              "lev_ovr": "Total leverage override (x CY2026E EBITDA)",
              "m_delta": "EBITDA margin change, every forecast year (pp)",
              "g_delta": "Revenue growth change, every forecast year (pp)"}
    for k, row in DRIVERS.items():
        ws[f"A{row}"] = labels[k]
        ws[f"A{row}"].font = F_TXT
        c = ws[f"D{row}"]
        c.border = B_BOX
        c.fill = FILL_ASSUMP
        c.font = F_IN
        ws[f"E{row}"] = "keep empty"
        ws[f"E{row}"].font = F_NOTE
    h = HURDLE_ROW
    ws[f"A{h}"] = "IRR hurdle (from Assumptions)"
    style_value(ws[f"D{h}"], f"={r('hurdle', 'C', True)}", "calc", FMT_PCT)
    ws[f"A{h + 1}"] = "Selected case: sponsor IRR"
    style_value(ws[f"D{h + 1}"], f"={r('r_irr', 'C', True)}", "calc", FMT_PCT)
    ws[f"A{h + 2}"] = "Selected case: exit multiple used (x)"
    style_value(ws[f"D{h + 2}"], f"={r('x_mult', 'C', True)}", "calc", FMT_X)
    ws[f"A{h + 3}"] = "Selected case: entry multiple, EV / CY2026E EBITDA (x)"
    style_value(ws[f"D{h + 3}"], f"={r('m_26', 'C', True)}", "calc", FMT_X)
    hurdle_abs = f"$D${h}"
    specs = []
    for t in TABLES:
        cr = t["corner"]
        ws[f"A{cr - 2}"] = t["title"]
        ws[f"A{cr - 2}"].font = F_HDR
        ws[f"D{cr - 1}"] = t["top_label"] + "  ->"
        ws[f"D{cr - 1}"].font = F_NOTE
        ws[f"A{cr + 1}"] = t["left_label"]
        ws[f"A{cr + 1}"].font = F_NOTE
        style_value(ws[f"C{cr}"], f"={r(t['out'], 'C', True)}", "calc", t["f_out"])
        ws[f"C{cr}"].fill = FILL_HDR
        for j, v in enumerate(t["top"]):
            c = ws.cell(cr, 4 + j)
            style_value(c, v, "input", t["f_top"])
            c.fill = FILL_HDR
            c.font = Font(name="Calibri", size=10, bold=True, color=BLUE)
        for i, v in enumerate(t["left"]):
            c = ws.cell(cr + 1 + i, 3)
            style_value(c, v, "input", t["f_left"])
            c.fill = FILL_HDR
            c.font = Font(name="Calibri", size=10, bold=True, color=BLUE)
            for j in range(len(t["top"])):
                cc = ws.cell(cr + 1 + i, 4 + j)
                cc.number_format = t["f_out"]
                cc.border = B_BOX
                cc.alignment = Alignment(horizontal="center")
        last_col = chr(ord("D") + len(t["top"]) - 1)
        last_row = cr + len(t["left"])
        rng = f"C{cr}:{last_col}{last_row}"
        body = f"D{cr + 1}:{last_col}{last_row}"
        if t["highlight"]:
            ws.conditional_formatting.add(body, CellIsRule(operator="greaterThanOrEqual", formula=[hurdle_abs],
                                                           fill=FILL_GOOD, font=Font(color="006100", bold=True)))
        specs.append(dict(id=t["id"], range=rng, body=body, row_input=f"D{DRIVERS[t['row_input']]}",
                          col_input=f"D{DRIVERS[t['col_input']]}", top=t["top"], left=t["left"], out=t["out"],
                          title=t["title"]))
    # scenario comparison: two-variable data table (output selector across, scenario down). Excel only accepts
    # data-table input cells on the table's own sheet, so the scenario and the output are both driven from D5 / D6.
    ws[f"A{T5['title_row']}"] = ("Scenario comparison (live data table: scenario 1-3 down the side, output number "
                                 "1-10 across the top)")
    ws[f"A{T5['title_row']}"].font = F_HDR
    outs = [
        lambda: f"={r('r_irr', 'C', True)}",
        lambda: f"={r('r_moic', 'C', True)}",
        lambda: f"={r('o_ebitda', 'H', True)}",
        lambda: f"=({r('o_ebitda', 'H', True)}/{r('o_ebitda', 'C', True)})^(1/5)-1",
        lambda: f"={r('x_ev', 'C', True)}",
        lambda: f"={r('x_eq', 'C', True)}",
        lambda: f"={r('d_lev_net', 'H', True)}",
        lambda: f"=MIN({rg('d_icr', 'D', 'H', True)})",
        lambda: f"={r('d_cov_all', 'C', True)}",
        lambda: f"={r('chk_core', 'E', True)}",
    ]
    sel = f"IF(ISNUMBER({r('metric_ovr', 'D', True)}),{r('metric_ovr', 'D', True)},1)"
    corner = f"=CHOOSE({sel}," + ",".join(fn()[1:] for fn in outs) + ")"
    cc0 = ws[f"C{T5['formula_row']}"]
    style_value(cc0, corner, "calc", FMT_GEN)
    cc0.fill = FILL_HDR
    for j, (col, lab, fmt) in enumerate(zip(T5["cols"], T5["labels"], T5["fmts"])):
        c = ws[f"{col}{T5['label_row']}"]
        c.value = lab
        c.font = F_HDR
        c.fill = FILL_HDR
        c.alignment = Alignment(wrap_text=True, horizontal="center", vertical="center")
        f = ws[f"{col}{T5['formula_row']}"]
        style_value(f, j + 1, "input", FMT_GEN)
        f.fill = FILL_HDR
        f.alignment = Alignment(horizontal="center")
        for i in range(3):
            cc = ws[f"{col}{T5['first'] + i}"]
            cc.number_format = fmt
            cc.border = B_BOX
            cc.alignment = Alignment(horizontal="center")
    ws.row_dimensions[T5["label_row"]].height = 42
    ws[f"A{T5['formula_row']}"] = "Output number (the corner cell picks one output with CHOOSE)"
    ws[f"A{T5['formula_row']}"].font = F_NOTE
    for i, name in enumerate(["Base", "Upside", "Downside"]):
        rr = T5["first"] + i
        ws[f"B{rr}"] = name
        ws[f"B{rr}"].font = F_HDR
        style_value(ws[f"C{rr}"], i + 1, "input", FMT_GEN)
    ws.conditional_formatting.add(f"D{T5['first']}:D{T5['first'] + 2}",
                                  CellIsRule(operator="greaterThanOrEqual", formula=[hurdle_abs], fill=FILL_GOOD,
                                             font=Font(color="006100", bold=True)))
    specs.append(dict(id="t5", range=f"C{T5['formula_row']}:M{T5['first'] + 2}", body=f"D{T5['first']}:M{T5['first'] + 2}",
                      row_input=f"D{DRIVERS['metric_ovr']}", col_input=f"D{DRIVERS['scen_ovr']}", top=T5["labels"],
                      left=[1, 2, 3], out="scenario", title="Scenario comparison"))
    for col, w in {"A": 52, "B": 10, "C": 10, "D": 11, "E": 11, "F": 12, "G": 11, "H": 12, "I": 12, "J": 12,
                   "K": 12, "L": 11, "M": 11}.items():
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A5"
    ws.sheet_view.zoomScale = 90
    return {"tables": specs, "drivers": {k: f"D{v}" for k, v in DRIVERS.items()}}


# ============================================================================= Checks
def check_list() -> tuple[list, list]:
    core = [
        ("Sources of funds equal uses of funds", lambda: f"=ABS({r('su_diff', 'C')})", 0.01, "le"),
        ("No negative balance in any debt tranche, any year",
         lambda: f"=MIN({rg('tla_close', 'C', 'H')},{rg('tlb_close', 'C', 'H')},{rg('mz_close', 'C', 'H')},"
                 f"{rg('rcf_close', 'C', 'H')})", -0.01, "ge"),
        ("Cash never falls below the minimum cash balance",
         lambda: f"=MIN({rg('d_close_cash', 'D', 'H')})-{r('min_cash', 'C')}", -0.01, "ge"),
        ("Revolver never exceeds its commitment",
         lambda: f"=MAX({rg('rcf_close', 'C', 'H')})-{r('rcf_commit', 'C')}", 0.01, "le"),
        ("Levered FCF: indirect method equals direct method, every year",
         lambda: f"=SUMPRODUCT(ABS({rg('o_lfcf_diff', 'D', 'H')}))", 0.01, "le"),
        ("Cash roll-forward: cash at close + FCF - repayments = cash at exit",
         lambda: f"=ABS({r('d_close_cash', 'H')}-({r('d_close_cash', 'C')}+SUM({rg('d_lfcf', 'D', 'H')})"
                 f"+SUM({rg('d_m_tla', 'D', 'H')})+SUM({rg('d_m_tlb', 'D', 'H')})+SUM({rg('d_rcf_draw', 'D', 'H')})"
                 f"+SUM({rg('d_rcf_rep', 'D', 'H')})+SUM({rg('d_s_tlb', 'D', 'H')})+SUM({rg('d_s_tla', 'D', 'H')})))",
         0.01, "le"),
        ("Senior debt roll-forward ties to scheduled repayments and sweeps",
         lambda: f"=ABS({r('tla_close', 'H')}+{r('tlb_close', 'H')}-({r('tla_close', 'C')}+{r('tlb_close', 'C')}"
                 f"+SUM({rg('tla_m', 'D', 'H')})+SUM({rg('tla_s', 'D', 'H')})+SUM({rg('tlb_m', 'D', 'H')})"
                 f"+SUM({rg('tlb_s', 'D', 'H')})))", 0.01, "le"),
        ("Holdco notes at exit = amount at close + PIK accrued",
         lambda: f"=ABS({r('mz_close', 'H')}-{r('mz_close', 'C')}-SUM({rg('mz_pik', 'D', 'H')}))", 0.01, "le"),
        ("Financing fees fully amortised by exit", lambda: f"=ABS({r('ff_close', 'H')})", 0.01, "le"),
        ("NPV of sponsor cash flows at the IRR is about zero", lambda: f"=ABS({r('r_npv', 'C')})", 0.01, "le"),
        ("XIRR equals the closed-form IRR (two cash flows)",
         lambda: f"=ABS({r('r_irr', 'C')}-{r('r_irr_cf', 'C')})", 0.0001, "le"),
        ("Returns attribution reconciles to the sponsor's gain", lambda: f"=ABS({r('a_diff', 'C')})", 0.01, "le"),
        ("Cash after close equals the minimum cash (excess cash used at close)",
         lambda: f"=ABS({r('cash_post', 'C')}-{r('min_cash', 'C')})", 0.01, "le"),
        ("Historical PBT recomputed from line items equals reported PBT",
         lambda: f"=SUMPRODUCT(ABS({rg('h_pbt_calc', 'C', 'I')}-{rg('h_pbt_rep', 'C', 'I')}))", 0.05, "le"),
        ("Historical PAT recomputed equals reported PAT",
         lambda: f"=SUMPRODUCT(ABS({rg('h_pat_calc', 'C', 'I')}-{rg('h_pat_rep', 'C', 'I')}))", 0.05, "le"),
        ("Revenue within Rs 1 crore of Screener sales (Screener rounds to whole crore)",
         lambda: f"=MAX(MAX({rg('h_scr_sales_d', 'C', 'G')},{r('h_scr_sales_d', 'J')}),"
                 f"-MIN({rg('h_scr_sales_d', 'C', 'G')},{r('h_scr_sales_d', 'J')}))", 1.0, "le"),
        ("EBITDA within Rs 1.5 crore of Screener operating profit",
         lambda: f"=MAX(MAX({rg('h_scr_op_d', 'C', 'G')},{r('h_scr_op_d', 'J')}),"
                 f"-MIN({rg('h_scr_op_d', 'C', 'G')},{r('h_scr_op_d', 'J')}))", 1.5, "le"),
        ("Exit equity value is positive", lambda: f"={r('x_eq', 'C')}", 0.0, "gt"),
    ]
    state = [
        (f"Sensitivity driver cells D5:D{DRV_LAST} on Sensitivities are empty",
         lambda: f"=COUNTA(Sensitivities!$D$5:$D${DRV_LAST})", 0, "eq"),
        ("Scenario selector is 1, 2 or 3", lambda: f"={r('scen_in', 'C')}", "1, 2 or 3", "in123"),
        ("Scenario used equals the scenario selected", lambda: f"=ABS({r('scen', 'C')}-{r('scen_in', 'C')})", 0, "le"),
    ]
    return core, state


def plan_checks() -> dict:
    core, state = check_list()
    POS["chk_overall"] = ("Checks", 4)
    POS["chk_core"] = ("Checks", 5)
    POS["chk_state"] = ("Checks", 6)
    first_core = 9
    last_core = first_core + len(core) - 1
    sec_row = last_core + 2
    first_state = sec_row + 1
    last_state = first_state + len(state) - 1
    info_row = last_state + 2
    return dict(core=core, state=state, first_core=first_core, last_core=last_core, sec_row=sec_row,
                first_state=first_state, last_state=last_state, info_row=info_row)


def write_checks(wb: Workbook, P: dict) -> None:
    ws = wb["Checks"]
    CTX["sheet"] = "Checks"
    ws["A1"] = "Model checks (every row must say PASS)"
    ws["A1"].font = F_TITLE
    ws["A2"] = ("Core checks test the arithmetic of the model. Input-state checks confirm the sensitivity driver cells "
                "are empty and the scenario switch is valid. Covenant tests are reported separately (information).")
    ws["A2"].font = F_NOTE
    for rr, lab, f in [(4, "Overall status", f'=IF(AND(E5="PASS",E6="PASS"),"ALL PASS","FAIL")'),
                       (5, "Core model checks", f'=IF(COUNTIF(E{P["first_core"]}:E{P["last_core"]},"FAIL")=0,"PASS","FAIL")'),
                       (6, "Input-state checks",
                        f'=IF(COUNTIF(E{P["first_state"]}:E{P["last_state"]},"FAIL")=0,"PASS","FAIL")')]:
        ws[f"B{rr}"] = lab
        ws[f"B{rr}"].font = F_HDR
        style_value(ws[f"E{rr}"], f, "calc", FMT_GEN)
        ws[f"E{rr}"].font = Font(name="Calibri", size=11, bold=True)
        ws[f"E{rr}"].fill = FILL_KEY
    for col, txt in zip("ABCDE", ["#", "Check", "Value", "Tolerance / rule", "Result"]):
        c = ws[f"{col}8"]
        c.value = txt
        c.font = F_HDR
        c.fill = FILL_HDR
        c.border = B_BOTTOM

    def put(rr: int, n: int, desc: str, fn: Callable[[], str], tol: Any, rule: str) -> None:
        ws[f"A{rr}"] = n
        ws[f"B{rr}"] = desc
        style_value(ws[f"C{rr}"], fn(), "calc", '#,##0.0000')
        style_value(ws[f"D{rr}"], tol, "input", '#,##0.0000' if not isinstance(tol, str) else FMT_GEN)
        if rule == "le":
            res = f'=IF(C{rr}<=D{rr},"PASS","FAIL")'
        elif rule == "ge":
            res = f'=IF(C{rr}>=D{rr},"PASS","FAIL")'
        elif rule == "gt":
            res = f'=IF(C{rr}>D{rr},"PASS","FAIL")'
        elif rule == "eq":
            res = f'=IF(C{rr}=D{rr},"PASS","FAIL")'
        else:
            res = f'=IF(OR(C{rr}=1,C{rr}=2,C{rr}=3),"PASS","FAIL")'
        style_value(ws[f"E{rr}"], res, "calc", FMT_GEN)
        ws[f"E{rr}"].font = Font(name="Calibri", size=10, bold=True)

    n = 1
    for i, (desc, fn, tol, rule) in enumerate(P["core"]):
        put(P["first_core"] + i, n, desc, fn, tol, rule)
        n += 1
    ws[f"B{P['sec_row']}"] = "Input-state checks"
    ws[f"B{P['sec_row']}"].font = F_HDR
    for i, (desc, fn, tol, rule) in enumerate(P["state"]):
        put(P["first_state"] + i, n, desc, fn, tol, rule)
        n += 1
    ir = P["info_row"]
    ws[f"B{ir}"] = "Information only: covenant tests in the selected scenario (Debt_Schedule)"
    ws[f"B{ir}"].font = F_NOTE
    style_value(ws[f"E{ir}"], f"={r('d_cov_all', 'C')}", "calc", FMT_GEN)
    for col, w in {"A": 5, "B": 72, "C": 14, "D": 16, "E": 12}.items():
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A9"
    green = PatternFill("solid", fgColor="C6EFCE")
    red = PatternFill("solid", fgColor="FFC7CE")
    rng = f"E4:E{ir}"
    ws.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=['"FAIL"'], fill=red))
    ws.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=['"PASS"'], fill=green))
    ws.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=['"ALL PASS"'], fill=green))
    ws.sheet_view.zoomScale = 90


# ============================================================================= Real deal context
def build_real_deal(D: dict) -> Sheet:
    deal = D["deal"]
    mkt = D["mkt"]
    bp = deal["bp_stonepeak"]
    fin = deal["global_financing"]
    oo = deal["open_offer"]
    s = Sheet("Real_Deal_Context", note_col="D", widths={"A": 66, "B": 12, "C": 14, "D": 120}, freeze="A5")
    s.title("Real-world context: the 2025-26 bp / Stonepeak deal and the Castrol India open offer")
    s.text("US$ bn or Rs crore as stated. Facts are inputs (blue) with their source; comparisons are formulas.")
    s.blank()
    s.header({"A": "Item", "B": "Unit", "C": "Value", "D": "Source / note"})
    C = "C"
    s.section("bp sells 65% of Castrol (global lubricants) to Stonepeak, announced 24-Dec-2025")
    s.row("rd_ev", "Enterprise value of Castrol (100%)", "US$ bn", {C: bp["ev_usd_bn"]}, '0.00', "input",
          "bp press release 24-Dec-2025: " + bp["url"])
    s.row("rd_mult", "Implied EV / LTM EBITDA", "x", {C: bp["ev_ltm_ebitda_x"]}, FMT_X, "input", "Same release")
    s.row("rd_ebitda", "Implied LTM EBITDA of Castrol", "US$ bn", {C: lambda c: f"={r('rd_ev', C)}/{r('rd_mult', C)}"},
          '0.00')
    s.row("rd_eq", "Equity value after JV minorities and debt-like items", "US$ bn", {C: bp["equity_value_usd_bn"]},
          '0.00', "input", "Same release: after JV minority interests of US$1.8bn and debt-like items of about US$0.3bn")
    s.row("rd_minor", "JV minority interests (mainly the 49% public stake in Castrol India)", "US$ bn",
          {C: bp["jv_minority_interests_usd_bn"]}, '0.00', "input",
          "Same release; notes to editors list India (49% minority interest) first")
    s.row("rd_stake", "Stake sold to Stonepeak", "%", {C: bp["stake_sold"]}, FMT_PCT, "input", "Same release")
    s.row("rd_proc", "Expected net proceeds to bp (incl. ~US$0.8bn dividend pre-payment)", "US$ bn",
          {C: bp["net_proceeds_to_bp_usd_bn"]}, '0.00', "input", "Same release")
    s.row("rd_cpp", "CPP Investments contribution", "US$ bn", {C: deal["cpp_investments"]["investment_usd_bn"]}, '0.00',
          "input", "CPP Investments release 24-Dec-2025: " + deal["cpp_investments"]["url"])
    s.row("rd_holdco", "Holdco debt raised (US$1.0bn notes + US$2.75bn term loans)", "US$ bn",
          {C: fin["holdco_debt_usd_bn"]}, '0.00', "input", "Latham & Watkins, Jul-2026: " + fin["url"])
    s.row("rd_holdco_x", "Holdco debt / implied LTM EBITDA", "x", {C: lambda c: f"={r('rd_holdco', C)}/{r('rd_ebitda', C)}"},
          FMT_X)
    s.row("rd_rcf", "Operating-level revolving credit facility", "US$ bn", {C: fin["opco_rcf_usd_bn"]}, '0.00', "input",
          "Same note")
    s.row("rd_rcf_in", "  of which earmarked for the Castrol India mandatory tender offer", "US$ bn",
          {C: fin["rcf_for_india_tender_offer_usd_bn"]}, '0.00', "input", "Same note")
    s.row("rd_fx_deal", "USD/INR at signing (23-Dec-2025 close)", "Rs per US$", {C: mkt["usd_inr_23dec2025"]["value"]},
          '0.0000', "input", "Yahoo Finance INR=X (source_data/yahoo_finance/USDINR_daily.csv)")
    s.row("rd_fx_now", "USD/INR at the 30-Oct-2026 close", "Rs per US$", {C: mkt["usd_inr_30oct2026"]["value"]},
          '0.0000', "input", "Yahoo Finance INR=X")
    s.row("rd_ev_inr", "Castrol global EV in rupees at signing", "Rs crore",
          {C: lambda c: f"={r('rd_ev', C)}*{r('rd_fx_deal', C)}*100"}, FMT_CR)
    s.blank()
    s.section("Mandatory open offer for Castrol India (SEBI SAST Regulations 3(1), 4 and 5(1))")
    s.row("rd_oo", "Initial offer price", "Rs/share", {C: lambda c: f"={r('oo_price', 'C')}"}, FMT_RS,
          note="Public announcement 24-Dec-2025 (manager: UBS Securities India): " + oo["url"])
    s.row("rd_oo_sh", "Offer shares (26% of fully diluted capital)", "shares", {C: oo["offer_shares"]}, FMT_INT, "input",
          "Same announcement")
    s.row("rd_oo_pct", "Offer shares / fully diluted shares", "%",
          {C: lambda c: f"={r('rd_oo_sh', C)}/{r('shares', 'C')}"}, FMT_PCT)
    s.row("rd_oo_size", "Offer size at full acceptance", "Rs crore",
          {C: lambda c: f"={r('rd_oo', C)}*{r('rd_oo_sh', C)}/10^7"}, FMT_CR2, note="Announcement states Rs 4,990.16 crore")
    s.row("rd_oo_usd", "Offer size in US$ at the 30-Oct-2026 rate", "US$ bn",
          {C: lambda c: f"={r('rd_oo_size', C)}/{r('rd_fx_now', C)}/100"}, '0.00',
          note="Compare with the US$0.3bn revolver tranche earmarked for the tender offer")
    s.row("rd_prom", "Shares held by Castrol Ltd (UK), the promoter", "shares", {C: oo["promoter_shares"]}, FMT_INT,
          "input", "Same announcement (51.00%)")
    s.row("rd_prom_pct", "Promoter holding", "%", {C: lambda c: f"={r('rd_prom', C)}/{r('shares', 'C')}"}, FMT_PCT)
    s.row("rd_max", "Holding controlled by the acquirer if the offer is fully accepted", "%",
          {C: lambda c: f"=({r('rd_prom', C)}+{r('rd_oo_sh', C)})/{r('shares', 'C')}"}, FMT_PCT,
          note="Below the 90% needed to delist under SEBI Delisting Regulation 21(a)")
    s.row("rd_spa", "Share purchase agreement date (start of the price enhancement)", "date",
          {C: dt.datetime(2025, 12, 23)}, FMT_DATE, "input", "Public announcement")
    s.row("rd_enh_rate", "Price enhancement for indirect acquisitions", "% a year", {C: 0.10}, FMT_PCT, "input",
          "SEBI SAST Regulation 8(12): 10% a year from the primary agreement to the detailed public statement")
    s.row("rd_dps", "Assumed detailed public statement date (illustrative)", "date", {C: dt.datetime(2026, 12, 31)},
          FMT_DATE, "assump", "Not known at 30-Oct-2026: due within 5 working days of completing the global deal")
    s.row("rd_enh", "Illustrative enhanced offer price at that date (simple interest)", "Rs/share",
          {C: lambda c: f"={r('rd_oo', C)}*(1+{r('rd_enh_rate', C)}*({r('rd_dps', C)}-{r('rd_spa', C)})/365)"}, FMT_RS)
    s.blank()
    s.section("How the model's hypothetical take-private compares")
    s.row("rd_mcap", "Castrol India market capitalisation at the 30-Oct-2026 close", "Rs crore",
          {C: lambda c: f"={r('px', 'C')}*{r('shares_cr', 'C')}"}, FMT_CR)
    s.row("rd_mcap_usd", "Castrol India market capitalisation", "US$ bn",
          {C: lambda c: f"={r('rd_mcap', C)}/{r('rd_fx_now', C)}/100"}, '0.00')
    s.row("rd_ebitda_in", "Castrol India CY2025 EBITDA in US$ (signing-date rate)", "US$ bn",
          {C: lambda c: f"={r('h_ebitda', 'G')}/{r('rd_fx_deal', C)}/100"}, '0.000')
    s.row("rd_ebitda_sh", "Castrol India EBITDA as a share of Castrol's global LTM EBITDA (approx.)", "%",
          {C: lambda c: f"={r('rd_ebitda_in', C)}/{r('rd_ebitda', C)}"}, FMT_PCT,
          note="Different periods (CY2025 vs bp's LTM) and FX; order of magnitude only")
    s.row("rd_ev_oo", "Castrol India EV at the open-offer price (31-Dec-2025 balance sheet)", "Rs crore",
          {C: lambda c: f"={r('rd_oo', C)}*{r('shares_cr', 'C')}+{r('h_borrow', 'G')}+{r('h_lease', 'G')}"
                        f"-{r('h_cash_tot', 'G')}-{r('h_invest', 'G')}"}, FMT_CR)
    s.row("rd_m_oo", "EV / CY2025 EBITDA at the open-offer price", "x",
          {C: lambda c: f"={r('rd_ev_oo', C)}/{r('h_ebitda', 'G')}"}, FMT_X, key_out=True)
    s.row("rd_m_mkt", "Market EV / LTM Sep-2026 EBITDA at the 30-Oct-2026 close (no premium)", "x",
          {C: lambda c: f"={r('mkt_m', 'C')}"}, FMT_X, key_out=True)
    s.row("rd_m_26", "Model entry EV / CY2026E EBITDA", "x", {C: lambda c: f"={r('m_26', 'C')}"}, FMT_X, key_out=True)
    s.row("rd_m_ltm", "Model entry EV / LTM Sep-2026 EBITDA", "x", {C: lambda c: f"={r('m_ltm', 'C')}"}, FMT_X,
          key_out=True)
    s.row("rd_m_glob", "bp / Stonepeak global deal EV / LTM EBITDA", "x", {C: lambda c: f"={r('rd_mult', C)}"}, FMT_X,
          key_out=True)
    s.row("rd_vs_glob", "Model LTM entry multiple vs the global deal multiple", "%",
          {C: lambda c: f"={r('rd_m_ltm', C)}/{r('rd_m_glob', C)}-1"}, FMT_PCT)
    s.row("rd_vs_oo", "Model offer price vs the Rs 194.04 open-offer price", "%",
          {C: lambda c: f"={r('offer', 'C')}/{r('rd_oo', C)}-1"}, FMT_PCT)
    s.row("rd_vs_enh", "Model offer price vs the illustrative enhanced offer price", "%",
          {C: lambda c: f"={r('offer', 'C')}/{r('rd_enh', C)}-1"}, FMT_PCT)
    s.blank()
    s.section("Status at 30-Oct-2026 (text)")
    st = [
        "The global deal had not completed. bp's 3Q 2026 results (30-Oct-2026) described the Castrol closing as "
        "'imminent' and still expected about US$6bn of proceeds in 2026 (Alliance News via AJ Bell, 30-Oct-2026).",
        "On Castrol India's Q3 CY2026 call (26-Oct-2026) management said licensing and regulatory work for the "
        "Stonepeak transaction was still under way.",
        "The detailed public statement is due within 5 working days of completing the underlying deal, so the open offer "
        "had not opened and there was no acceptance result at 30-Oct-2026.",
        "Even a fully accepted offer leaves the acquirer at about 77%, below the 90% delisting threshold; a full "
        "take-private (this model) would need a separate delisting offer.",
    ]
    for t in st:
        s.text(t, style="txt")
    s.blank()
    s.section("Sources (all retrieved 31-Oct-2026 to 1-Nov-2026; copies in source_data/)")
    for t in [
        "bp press release, 24-Dec-2025: " + bp["url"],
        "CPP Investments release, 24-Dec-2025: " + deal["cpp_investments"]["url"],
        "Latham & Watkins financing note, Jul-2026: " + fin["url"],
        "Open-offer public announcement, 24-Dec-2025: " + oo["url"],
        "Castrol India stock-exchange copy of the announcement: " + mkt["open_offer"]["url"],
        "bp 3Q 2026 results coverage, 30-Oct-2026: https://www.ajbell.co.uk/news/articles/"
        "bp-hits-debt-target-year-ahead-schedule-profit-beats-forecast",
        "Castrol India Q3 CY2026 call transcript, 26-Oct-2026: https://www.castrol.com/content/dam/castrol/"
        "country-sites-new/en_in/india/home/documents/investors/clse-intimation-analyst-call-26-oct-2026-transcriptsigned.pdf",
        "SEBI SAST Regulations (consolidated Aug-2026): " + deal["regulation"]["sebi_sast"]["url"],
        "SEBI Delisting Regulations (consolidated Aug-2026): " + deal["regulation"]["sebi_delisting"]["url"],
    ]:
        s.text(t, style="note")
    return s


# ============================================================================= Cover
def build_cover(D: dict) -> Sheet:
    s = Sheet("Cover", note_col="E", widths={"A": 58, "B": 12, "C": 13, "D": 12, "E": 13, "F": 13, "G": 13,
                                              "H": 13, "I": 13, "J": 13}, freeze=None)
    s.title("Castrol India Ltd (NSE: CASTROLIND): leveraged buyout model")
    s.text("Hypothetical take-private of 100% of Castrol India by a financial sponsor. Entry 31-Dec-2026, exit "
           "31-Dec-2031. Rs crore unless stated. Market data to the 30-Oct-2026 close; built 1-Nov-2026.", style="txt")
    s.text("Purpose: test what a sponsor would earn buying Castrol India at a premium to the market, using sources and "
           "uses, a tranche-by-tranche debt schedule with a cash sweep, and XIRR / MOIC returns.", style="txt")
    s.blank()
    C = "C"
    s.section("Key outputs (selected scenario)", last_col="J")
    s.row("cv_scen", "Scenario selected (change on Assumptions, cell C6)", "", {C: lambda c: f"={r('scen_name', 'C')}"},
          FMT_GEN, key_out=True)
    rows = [
        ("Offer price per share", "Rs/share", "offer", "C", FMT_RS),
        ("Premium to the 30-Oct-2026 close (Rs 188.00)", "%", "su_prem_close", "C", FMT_PCT),
        ("Equity purchase price (100%)", "Rs crore", "su_eq", "C", FMT_CR),
        ("Entry enterprise value", "Rs crore", "ev", "C", FMT_CR),
        ("Entry EV / CY2026E EBITDA", "x", "m_26", "C", FMT_X),
        ("Entry EV / LTM Sep-2026 EBITDA", "x", "m_ltm", "C", FMT_X),
        ("Total funded debt at close", "Rs crore", "debt_amt", "C", FMT_CR),
        ("Total funded debt / CY2026E EBITDA", "x", "debt_x", "C", FMT_X2),
        ("CY2026E EBITDA / pro-forma cash interest", "x", "pf_icr", "C", FMT_X2),
        ("Sponsor equity cheque", "Rs crore", "s_eq", "C", FMT_CR),
        ("Sponsor equity / total capitalisation", "%", "eq_pct", "C", FMT_PCT),
        ("CY2031E EBITDA", "Rs crore", "o_ebitda", "H", FMT_CR),
        ("Exit multiple (EV / CY2031E EBITDA)", "x", "x_mult", "C", FMT_X),
        ("Exit enterprise value", "Rs crore", "x_ev", "C", FMT_CR),
        ("Exit equity value (100%)", "Rs crore", "x_eq", "C", FMT_CR),
        ("Sponsor exit proceeds (after management incentive pool)", "Rs crore", "r_proc", "C", FMT_CR),
        ("Sponsor IRR", "%", "r_irr", "C", FMT_PCT),
        ("Sponsor MOIC", "x", "r_moic", "C", FMT_X2),
        ("Net debt / EBITDA at exit", "x", "d_lev_net", "H", FMT_X2),
    ]
    for i, (lab, unit, key, col, fmt) in enumerate(rows):
        s.row(f"cv_{i}", lab, unit, {C: (lambda c, k=key, cc=col: f"={r(k, cc)}")}, fmt,
              key_out=key in ("r_irr", "r_moic", "ev", "m_26"))
    s.blank()
    s.section("Checks", last_col="J")
    s.row("cv_chk", "Model checks (Checks sheet; must say ALL PASS)", "", {C: lambda c: f"={r('chk_overall', 'E')}"},
          FMT_GEN, key_out=True)
    s.row("cv_cov", "Covenant tests in the selected scenario (Debt_Schedule)", "",
          {C: lambda c: f"={r('d_cov_all', 'C')}"}, FMT_GEN)
    s.blank()
    s.section("Scenario comparison (live data table on Sensitivities)", last_col="J")
    s.header({"A": "Scenario", "B": "", "C": "IRR", "D": "MOIC", "E": "CY2031E EBITDA", "F": "Exit equity",
              "G": "Net debt / EBITDA at exit", "H": "Lowest interest cover", "I": "Covenants", "J": "Model checks"})
    src_cols = {"C": "D", "D": "E", "E": "F", "F": "I", "G": "J", "H": "K", "I": "L", "J": "M"}
    fmts = {"C": FMT_PCT, "D": FMT_X2, "E": FMT_CR, "F": FMT_CR, "G": FMT_X2, "H": FMT_X2, "I": FMT_GEN,
            "J": FMT_GEN}
    for i, name in enumerate(["Base", "Upside", "Downside"]):
        cols = {}
        for dst, srcc in src_cols.items():
            cols[dst] = (lambda c, k=f"t5_{i + 1}", sc=srcc: f"={r(k, sc)}")
        s.add("row", key=f"cv_s{i}", label=name, unit="", cols=cols, fmt=FMT_PCT, kind="calc", note="",
              total=False, key_out=False)
        s.items[-1]["fmts"] = fmts
    s.blank()
    s.section("How to use", last_col="J")
    for t in [
        "1. Pick the case on Assumptions!C6 (1 = Base, 2 = Upside, 3 = Downside). Every sheet updates.",
        "2. Blue cells are inputs; yellow-filled blue cells are judgement assumptions with the reason in column I.",
        "3. Black cells are formulas and green cells link to another sheet. Do not type over them.",
        "4. Sensitivities holds live Excel data tables. Keep its driver cells D5:D11 empty; press F9 if grids look stale.",
        "5. Checks must read ALL PASS. Covenant tests are information and can breach in a downside.",
        "6. Rebuild from source: python build/run_all.py (needs Python and Excel on Windows).",
    ]:
        s.text(t, style="txt")
    s.blank()
    s.section("Sheet guide", last_col="J")
    for t in [
        "Historical: CY2021-CY2025, 9M CY2025/26, LTM and H1 CY2026 from filings, with margins, NWC days and cash flow.",
        "Assumptions: scenario selector, offer price, fees, financing terms, CY2026E bridge and scenario drivers.",
        "Sources_Uses: cash at close, entry EV and multiples, debt sizing, sources and uses, pro-forma credit stats.",
        "Operating_Model: CY2026E-CY2031E income statement, working capital, unlevered and levered free cash flow.",
        "Debt_Schedule: cash waterfall, TLA / TLB / holdco PIK notes / revolver, credit statistics, covenant tests.",
        "Returns: exit value, sponsor cash flows by date, XIRR, MOIC, returns attribution, unlevered IRR.",
        "Sensitivities: IRR and MOIC data tables and the live scenario comparison.",
        "Checks: model-integrity checks (PASS / FAIL). Real_Deal_Context: bp / Stonepeak deal and the Rs 194.04 offer.",
    ]:
        s.text(t, style="txt")
    s.blank()
    s.section("Colour code", last_col="J")
    s.text("Blue font = input. Black font = formula. Green font = link to another sheet. Yellow fill = judgement "
           "assumption. Green-filled cells on Sensitivities = IRR at or above the hurdle.", style="txt")
    s.blank()
    s.section("Disclaimer", last_col="J")
    s.text("Educational project, not investment advice. The take-private is hypothetical; Castrol India is subject to a "
           "real mandatory open offer by Stonepeak entities at Rs 194.04 a share (public announcement 24-Dec-2025).",
           style="txt")
    s.text("Figures from company filings, Screener.in, StockAnalysis.com and Yahoo Finance; forecasts are the author's "
           "assumptions. See README.md and source_data/README.md for sources.", style="txt")
    return s


# ============================================================================= charts
def add_charts(wb: Workbook) -> None:
    ws = wb["Debt_Schedule"]
    ch = BarChart()
    ch.type = "col"
    ch.grouping = "stacked"
    ch.overlap = 100
    ch.title = "Debt outstanding by tranche (Rs crore)"
    ch.y_axis.title = "Rs crore"
    hdr_row = 4
    for key, name in [("tla_close", "Term loan A"), ("tlb_close", "Term loan B"), ("mz_close", "Holdco PIK notes"),
                      ("rcf_close", "Revolver")]:
        row = POS[key][1]
        ch.series.append(Series(Reference(ws, min_col=3, max_col=8, min_row=row, max_row=row), title=name))
    ch.set_categories(Reference(ws, min_col=3, max_col=8, min_row=hdr_row, max_row=hdr_row))
    ch.height, ch.width = 8.5, 16
    ws.add_chart(ch, "K5")
    wr = wb["Returns"]
    ch2 = BarChart()
    ch2.type = "col"
    ch2.title = "Returns attribution (Rs crore)"
    a0, a1 = POS["a_ebitda"][1], POS["a_mip"][1]
    ch2.series.append(Series(Reference(wr, min_col=3, max_col=3, min_row=a0, max_row=a1), title="Rs crore"))
    ch2.set_categories(Reference(wr, min_col=1, max_col=1, min_row=a0, max_row=a1))
    ch2.legend = None
    ch2.height, ch2.width = 8.5, 16
    wr.add_chart(ch2, "K5")


# ============================================================================= main
def main() -> None:
    D = load_inputs()
    builders = [
        ("Cover", build_cover), ("Historical", build_historical), ("Assumptions", build_assumptions),
        ("Sources_Uses", build_sources_uses), ("Operating_Model", build_operating), ("Debt_Schedule", build_debt),
        ("Returns", build_returns), ("Real_Deal_Context", build_real_deal),
    ]
    sheets = {name: fn(D) for name, fn in builders}
    # pass 1: assign rows
    for sh in sheets.values():
        assign_rows(sh)
    plan_sensitivities()
    P = plan_checks()
    # pass 2: write
    wb = Workbook()
    wb.remove(wb.active)
    order = ["Cover", "Historical", "Assumptions", "Sources_Uses", "Operating_Model", "Debt_Schedule", "Returns",
             "Sensitivities", "Checks", "Real_Deal_Context"]
    for name in order:
        wb.create_sheet(name)
    for name in order:
        if name in sheets:
            write_sheet(wb, sheets[name])
    # per-cell formats for the cover scenario table
    wc = wb["Cover"]
    for it in sheets["Cover"].items:
        if it.get("fmts"):
            for col, fmt in it["fmts"].items():
                wc[f"{col}{it['row']}"].number_format = fmt
    wc.sheet_view.showGridLines = False
    sens = write_sensitivities(wb)
    write_checks(wb, P)
    add_charts(wb)
    wa = wb["Assumptions"]
    dv = DataValidation(type="list", formula1='"1,2,3"', allow_blank=False, showDropDown=False)
    dv.error = "Enter 1 (Base), 2 (Upside) or 3 (Downside)"
    wa.add_data_validation(dv)
    dv.add(f"C{POS['scen_in'][1]}")
    wb.properties.title = "Castrol India LBO model"
    wb.properties.creator = "Finance portfolio project 7"
    wb.save(OUT_XLSX)
    layout = {"pos": {k: list(v) for k, v in POS.items()}, "sens": sens,
              "checks": {"first_core": P["first_core"], "last_core": P["last_core"],
                         "first_state": P["first_state"], "last_state": P["last_state"]},
              "scen_cell": f"C{POS['scen_in'][1]}"}
    LAYOUT_JSON.write_text(json.dumps(layout, indent=1), encoding="utf-8")
    n_formulas = sum(1 for ws in wb.worksheets for row in ws.iter_rows() for c in row
                     if isinstance(c.value, str) and c.value.startswith("="))
    print(f"saved {OUT_XLSX.name}: {len(wb.sheetnames)} sheets, {n_formulas} formulas, {len(POS)} keys")
    print("scenario cell:", layout["scen_cell"])
    print("EXIT_OK")


if __name__ == "__main__":
    main()
