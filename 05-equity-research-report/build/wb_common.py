"""Shared styles, inputs and helpers for build_ratio_workbook.py (openpyxl).

Column layout used on Raw_Data and Ratios (so a year sits in the same column letter on both sheets):
  A code | B line item / ratio | C unit | D..I = FY2021..FY2026 | J = 5-year average (Ratios) or source (Raw_Data)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ratio_engine as RE  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUTFILE = ROOT / "AsianPaints_Ratio_Analysis.xlsx"
INPUTS = pd.read_csv(ROOT / "data" / "ratio_inputs.csv")
COMPANY_CHECKS = pd.read_csv(ROOT / "data" / "company_reported_checks.csv")
EXCEPTIONAL = pd.read_csv(ROOT / "data" / "exceptional_items_company_reported.csv")
META_SCR = json.loads((ROOT / "data" / "screener" / "screener_summary.json").read_text(encoding="utf-8"))

SYMS = RE.COMPANIES
NAMES = RE.NAMES
FYS = RE.ALL_FY                                                     # FY2021..FY2026
RFYS = RE.FY                                                        # FY2022..FY2026 (ratio years)
YCOL = {fy: get_column_letter(4 + i) for i, fy in enumerate(FYS)}   # D..I
AVG_COL = "J"

F_IN = Font(name="Calibri", size=10, color="0000FF")
F_CALC = Font(name="Calibri", size=10, color="000000")
F_CALC_B = Font(name="Calibri", size=10, color="000000", bold=True)
F_LINK = Font(name="Calibri", size=10, color="008000")
F_LINK_B = Font(name="Calibri", size=10, color="008000", bold=True)
F_BOLD = Font(name="Calibri", size=10, bold=True)
F_TXT = Font(name="Calibri", size=10)
F_TITLE = Font(name="Calibri", size=14, bold=True, color="1F3864")
F_SUB = Font(name="Calibri", size=11, bold=True, color="1F3864")
F_HDR = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
F_NOTE = Font(name="Calibri", size=9, italic=True, color="595959")
FILL_HDR = PatternFill("solid", fgColor="1F3864")
FILL_BLOCK = PatternFill("solid", fgColor="D9E1F2")
FILL_SEC = PatternFill("solid", fgColor="EDEDED")
FILL_YEL = PatternFill("solid", fgColor="FFF2CC")
FILL_AP = PatternFill("solid", fgColor="E2EFDA")
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(bottom=THIN)
WRAP = Alignment(wrap_text=True, vertical="top")
CENTER = Alignment(horizontal="center", vertical="center")
FMT = {"pct": "0.0%", "x": '0.00"x"', "x1": '0.0"x"', "days": "0", "cr": "#,##0", "cr1": "#,##0.0",
       "cr2": "#,##0.00", "rank": "0", "score": "0.00"}
RATIO_FMT = {c: f for c, _l, _g, f, _b in RE.RATIOS}
RATIO_LABEL = {c: lab for c, lab, _g, _f, _b in RE.RATIOS}
RATIO_UNIT = {"pct": "%", "x": "x", "x1": "x", "days": "days"}


def val(sym: str, code: str, fy: str):
    row = INPUTS[(INPUTS.company == sym) & (INPUTS.code == code)]
    if row.empty:
        return None
    v = row.iloc[0][fy]
    return None if pd.isna(v) else float(v)


def meta(sym: str, code: str, field: str) -> str:
    row = INPUTS[(INPUTS.company == sym) & (INPUTS.code == code)]
    if row.empty:
        return ""
    v = row.iloc[0][field]
    return "" if pd.isna(v) else str(v)


def label(sym: str, code: str) -> str:
    return meta(sym, code, "item")


def style_header(ws, row: int, labels: list[str], start_col: int = 1, height: float | None = 28) -> None:
    for i, lab in enumerate(labels):
        c = ws.cell(row, start_col + i, lab)
        c.font, c.fill = F_HDR, FILL_HDR
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    if height:
        ws.row_dimensions[row].height = height


def block_title(ws, row: int, text: str, ncols: int = 11) -> None:
    for col in range(1, ncols + 1):
        ws.cell(row, col).fill = FILL_BLOCK
    ws.cell(row, 1, text).font = F_SUB


def section_row(ws, row: int, text: str, ncols: int = 11) -> None:
    for col in range(1, ncols + 1):
        ws.cell(row, col).fill = FILL_SEC
    ws.cell(row, 2, text).font = F_BOLD


def set_widths(ws, widths: dict[str, float]) -> None:
    for k, w in widths.items():
        ws.column_dimensions[k].width = w


def note(ws, row: int, col: int, text: str) -> None:
    c = ws.cell(row, col, text)
    c.font = F_NOTE
    c.alignment = Alignment(wrap_text=False, vertical="top")


def para(ws, row: int, col: int, text: str, ncols_merge: int = 0, height: float | None = None,
         font: Font = F_TXT) -> None:
    """Write a wrapped paragraph, optionally merged across ncols_merge columns."""
    c = ws.cell(row, col, text)
    c.font = font
    c.alignment = WRAP
    if ncols_merge:
        ws.merge_cells(start_row=row, start_column=col, end_row=row, end_column=col + ncols_merge - 1)
    if height:
        ws.row_dimensions[row].height = height
