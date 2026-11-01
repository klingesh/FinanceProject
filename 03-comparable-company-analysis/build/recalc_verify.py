"""Recalculate AsianPaints_Comps_and_DCF.xlsx in Excel (COM), then verify the cached values with openpyxl.

Steps:
1. Open the workbook in a private Excel instance (DispatchEx, invisible), CalculateFull, save, close, quit.
   The football-field chart is also exported to PNG (optional path argument) so it can be inspected.
2. Re-open with openpyxl data_only=True: no error values anywhere, every check = PASS, key outputs sensible.
3. Write the verification log to build/verify_log.txt.

Usage: python build/recalc_verify.py [chart_png_path]
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
XLSX = ROOT / "AsianPaints_Comps_and_DCF.xlsx"
LOG = ROOT / "build" / "verify_log.txt"
ERRORS = ("#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A", "#NUM!", "#NULL!", "#SPILL!", "#CALC!")


def recalc_in_excel(path: Path, chart_png: Path | None) -> list[str]:
    import pythoncom
    import win32com.client

    notes = []
    pythoncom.CoInitialize()
    excel = win32com.client.DispatchEx("Excel.Application")
    wb = None
    try:
        excel.Visible = False
        excel.DisplayAlerts = False
        wb = excel.Workbooks.Open(str(path), UpdateLinks=0)
        excel.CalculateFull()
        time.sleep(1)
        notes.append(f"Excel {excel.Version}: CalculateFull done")
        ws = wb.Worksheets("Football_Field")
        n = ws.ChartObjects().Count
        notes.append(f"Football_Field chart objects: {n}")
        if chart_png is not None and n:
            co = ws.ChartObjects(1)
            co.Chart.Export(str(chart_png))
            notes.append(f"chart exported to {chart_png}")
        wb.Save()
        notes.append("saved")
    finally:
        if wb is not None:
            wb.Close(SaveChanges=False)
        excel.Quit()
        del excel
        pythoncom.CoUninitialize()
    return notes


def verify(path: Path) -> tuple[list[str], bool]:
    out: list[str] = []
    ok = True
    wb = load_workbook(path, data_only=True)
    wbf = load_workbook(path, data_only=False)
    n_formula = n_cells = 0
    errors = []
    empty_formula = []
    for ws in wb.worksheets:
        wsf = wbf[ws.title]
        for row in ws.iter_rows():
            for c in row:
                if c.value is None and wsf[c.coordinate].value is None:
                    continue
                n_cells += 1
                fv = wsf[c.coordinate].value
                if isinstance(fv, str) and fv.startswith("="):
                    n_formula += 1
                    if c.value is None:
                        empty_formula.append(f"{ws.title}!{c.coordinate}")
                if isinstance(c.value, str) and c.value.strip() in ERRORS:
                    errors.append(f"{ws.title}!{c.coordinate}={c.value}")
    out.append(f"cells with content: {n_cells}; formulas: {n_formula}")
    out.append(f"error values: {len(errors)} {errors[:20]}")
    out.append(f"formulas with no cached value: {len(empty_formula)} {empty_formula[:20]}")
    if errors or empty_formula:
        ok = False
    k = wb["Checks"]
    out.append("--- Checks")
    for r in range(5, k.max_row + 1):
        label, res, det = k[f"B{r}"].value, k[f"C{r}"].value, k[f"D{r}"].value
        if label is None:
            continue
        out.append(f"{k[f'A{r}'].value or '':>3} {res!s:>6}  {label}  [{det}]")
        if res == "FAIL":
            ok = False
    c = wb["Comps"]
    d = wb["DCF"]
    w = wb["WACC"]
    f = wb["Football_Field"]
    s = wb["Sensitivity"]
    out.append("--- Comps (EV Rs cr, EV/EBITDA, P/E, EV/Sales, EV/EBITDA FY27E, P/E FY27E, margin)")
    for r in range(5, 10):
        out.append(f"{c[f'A{r}'].value:<15} TTM {c[f'B{r}'].value}  mcap {c[f'E{r}'].value:>10,.0f}  EV {c[f'I{r}'].value:>10,.0f}"
                   f"  {c[f'R{r}'].value:5.1f}x {c[f'S{r}'].value:5.1f}x {c[f'T{r}'].value:5.2f}x"
                   f"  {c[f'V{r}'].value:5.1f}x {c[f'W{r}'].value:5.1f}x  {c[f'N{r}'].value:6.1%}")
    for r in range(12, 18):
        out.append(f"{c[f'A{r}'].value:<45} EV/EBITDA {c[f'R{r}'].value:.3f}  P/E {c[f'S{r}'].value:.3f}"
                   f"  EV/Sales {c[f'T{r}'].value:.3f}  EV/EBITDA27 {c[f'V{r}'].value:.3f}  P/E27 {c[f'W{r}'].value:.3f}")
    out.append("--- Implied values (Rs/share): min, 25th, median, 75th, max, median vs price")
    for r in range(21, 26):
        vals = [c[f"{x}{r}"].value for x in "CDEFG"]
        out.append(f"{c[f'A{r}'].value:<45} " + "  ".join(f"{v:,.0f}" for v in vals) + f"  {c[f'H{r}'].value:+.1%}")
    out.append("--- Drop-one (median EV/EBITDA, P/E, EV/Sales -> implied Rs)")
    for r in range(30, 38):
        vals = [c[f"{x}{r}"].value for x in "BCDEFG"]
        out.append(f"{c[f'A{r}'].value:<40} " + "  ".join(f"{v:,.2f}" for v in vals))
    out.append("--- DCF")
    for r in [5, 6, 7, 8, 10, 11, 14, 17, 19, 20, 21, 22, 24, 25, 26, 27, 35, 40, 41]:
        vals = []
        for x in "BCDEFGHI":
            v = d[f"{x}{r}"].value
            vals.append("" if v is None else (f"{v:,.4f}" if abs(v) < 5 else f"{v:,.0f}"))
        out.append(f"{d[f'A{r}'].value:<45} " + " | ".join(vals))
    for r in list(range(48, 68)) + list(range(70, 84)):
        out.append(f"{d[f'A{r}'].value:<75} {d[f'B{r}'].value}")
    out.append("--- WACC")
    for r in range(5, 30):
        if w[f"A{r}"].value:
            out.append(f"{w[f'A{r}'].value:<75} {w[f'B{r}'].value}")
    out.append("--- Sensitivity grid")
    for r in range(6, 12):
        out.append("  ".join(str(round(s[f"{x}{r}"].value, 4)) if isinstance(s[f"{x}{r}"].value, float)
                             else str(s[f"{x}{r}"].value) for x in "BCDEFG"))
    out.append("--- Football field")
    for r in range(5, 12):
        out.append(f"{f[f'A{r}'].value:<45} {f[f'B{r}'].value}  {f[f'C{r}'].value}  {f[f'D{r}'].value}  {f[f'F{r}'].value}")
    for r in range(14, 27):
        out.append(f"{f[f'A{r}'].value} -> {f[f'B{r}'].value} {f[f'C{r}'].value or ''}")
    cover = wb["Cover"]
    out.append("--- Cover")
    for r in range(11, 33):
        if cover[f"A{r}"].value:
            out.append(f"{cover[f'A{r}'].value}: {cover[f'B{r}'].value}  {cover[f'C{r}'].value or ''}")
    return out, ok


def main() -> None:
    chart_png = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    notes = recalc_in_excel(XLSX, chart_png)
    lines, ok = verify(XLSX)
    text = "\n".join(notes + lines + [f"VERIFICATION {'PASSED' if ok else 'FAILED'}"])
    LOG.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
