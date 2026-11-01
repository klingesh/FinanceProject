"""Export the three native Excel charts on the workbook's Charts sheet as PNG files (Windows + Excel only).

The workbook is opened read-only in a private Excel instance and closed without saving.
Output: figures/excel_chart_<n>_<name>.png

Usage:  python build/export_excel_charts.py
"""
from __future__ import annotations

import re
import time

import win32com.client as win32

from common import FIGURES, WORKBOOK

FIGURES.mkdir(exist_ok=True)
NAMES = {1: "margin_trends", 2: "dupont_fy2026", 3: "roce_and_debt_to_equity_fy2026"}

xl = win32.DispatchEx("Excel.Application")
xl.Visible = False
xl.DisplayAlerts = False
wb = None
try:
    wb = xl.Workbooks.Open(str(WORKBOOK), UpdateLinks=0, ReadOnly=True)
    ws = wb.Worksheets("Charts")
    n = ws.ChartObjects().Count
    for i in range(1, n + 1):
        co = ws.ChartObjects(i)
        title = co.Chart.ChartTitle.Text if co.Chart.HasTitle else co.Name
        # export at 2x the on-screen size so the PNG stays sharp on GitHub
        co.Width, co.Height = co.Width * 2, co.Height * 2
        co.Chart.ChartArea.Format.TextFrame2.TextRange.Font.Size = 20
        out = FIGURES / f"excel_chart_{i}_{NAMES.get(i, re.sub(r'[^a-z0-9]+', '_', title.lower())[:40])}.png"
        for attempt in range(1, 6):  # an invisible Excel sometimes writes an empty file; retry after a redraw
            co.Chart.Refresh()
            time.sleep(0.5 * attempt)
            co.Chart.Export(str(out), "PNG")
            if out.exists() and out.stat().st_size > 1000:
                break
            try:
                co.Activate()
            except Exception:
                pass
        size = out.stat().st_size if out.exists() else 0
        print(f"chart {i}: {title!r} -> {out.name} ({co.Width:.0f} x {co.Height:.0f} pt, {size} bytes, "
              f"attempt {attempt})")
        if size < 1000:
            raise RuntimeError(f"export of chart {i} produced an empty file")
finally:
    if wb is not None:
        wb.Close(SaveChanges=False)
    xl.Quit()
