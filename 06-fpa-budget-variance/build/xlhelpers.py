"""Formatting and writing helpers for the openpyxl build script."""
from __future__ import annotations

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

BLUE, BLACK, GREEN, GREY, WHITE = "0000FF", "000000", "008000", "595959", "FFFFFF"
YELLOW = PatternFill("solid", fgColor="FFF2CC")
SEC_FILL = PatternFill("solid", fgColor="1F3864")
HDR_FILL = PatternFill("solid", fgColor="D9E1F2")
TOT_FILL = PatternFill("solid", fgColor="F2F2F2")
PASS_FILL = PatternFill("solid", fgColor="C6EFCE")
FAIL_FILL = PatternFill("solid", fgColor="FFC7CE")

FMT_CR = '#,##0.0;(#,##0.0);"-"'
FMT_CR2 = '#,##0.00;(#,##0.00);"-"'
FMT_T = '#,##0;(#,##0);"-"'
FMT_T1 = '#,##0.0;(#,##0.0);"-"'
FMT_RS = '#,##0.00'
FMT_PCT = '0.0%'
FMT_PCT2 = '0.00%'
FMT_PP = '+0.0%;-0.0%;0.0%'
FMT_DATE = 'mmm-yy'
FMT_DAY = 'dd-mmm-yyyy'
FMT_INT = '0'
FMT_HC = '#,##0'
FMT_SCI = '0.0E+00'

THIN = Side(style="thin", color="BFBFBF")
TOP_BORDER = Border(top=Side(style="thin", color="000000"))

KIND_COLOR = {"input": BLUE, "calc": BLACK, "link": GREEN, "text": BLACK, "note": GREY}


def col(n: int) -> str:
    """1-based column number to letter."""
    return get_column_letter(n)


def put(ws, ref, value, kind="calc", fmt=None, bold=False, yellow=False, italic=False,
        size=None, fill=None, align=None, wrap=False, color=None):
    """Write a value or formula with the house style."""
    c = ws[ref]
    c.value = value
    c.font = Font(color=color or KIND_COLOR[kind], bold=bold, italic=italic, size=size or 10)
    if fmt:
        c.number_format = fmt
    if yellow:
        c.fill = YELLOW
    elif fill is not None:
        c.fill = fill
    if align or wrap:
        c.alignment = Alignment(horizontal=align, vertical="top" if wrap else None, wrap_text=wrap)
    return c


def title(ws, text, sub=None, note=None):
    put(ws, "A1", text, "text", bold=True, size=14)
    if sub:
        put(ws, "A2", sub, "note", italic=True)
    if note:
        put(ws, "A3", note, "note", italic=True)


def section(ws, row, text, first_col=1, last_col=18):
    for c in range(first_col, last_col + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill = SEC_FILL
    cell = ws.cell(row=row, column=first_col)
    cell.value = text
    cell.font = Font(color=WHITE, bold=True, size=10)


def header_row(ws, row, labels: dict, fill=HDR_FILL):
    """labels: {col_letter: value}. Dates get mmm-yy format."""
    for letter, v in labels.items():
        c = ws[f"{letter}{row}"]
        c.value = v
        c.fill = fill
        c.font = Font(bold=True, size=10, color=BLACK)
        c.alignment = Alignment(horizontal="center", wrap_text=True)


def widths(ws, mapping: dict):
    for letter, w in mapping.items():
        ws.column_dimensions[letter].width = w


def bold_row(ws, row, first_col, last_col, fill=TOT_FILL, border=True):
    for c in range(first_col, last_col + 1):
        cell = ws.cell(row=row, column=c)
        cell.font = Font(color=cell.font.color.rgb if cell.font and cell.font.color and cell.font.color.rgb else BLACK,
                         bold=True, size=10)
        if fill is not None:
            cell.fill = fill
        if border:
            cell.border = TOP_BORDER
