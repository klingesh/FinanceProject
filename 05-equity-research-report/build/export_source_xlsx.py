"""Excel copies of the downloaded Screener.in and StockAnalysis.com tables, so they open cleanly in Excel.

Writes source_data/screener/<Company>_Screener_Consolidated.xlsx and _Standalone.xlsx (one sheet per Screener
section plus the top-of-page summary and the line-item schedules) and source_data/stockanalysis/
<Company>_<Statement>_StockAnalysis.xlsx (one sheet per table on the page). Each sheet: row 1 = "Source: <site> |
<URL> | downloaded <date> | <units>", row 2 = what the table is, row 4 = column headers, then the table as downloaded.
Plain numbers are stored as numbers; text such as "12.53%", "416.72B" or "Upgrade" is kept exactly as shown.

Input: the tables parsed by build/fetch_screener.py and build/fetch_stockanalysis.py (data/screener/,
data/stockanalysis/), which are the raw pages' tables unchanged.

Run:  python build/export_source_xlsx.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SD = ROOT / "source_data"
CO = {"ASIANPAINT": "AsianPaints", "BERGEPAINT": "BergerPaints", "KANSAINER": "KansaiNerolac", "JSWDULUX": "JSWDulux",
      "INDIGOPNTS": "IndigoPaints"}
SA_PAGES = {"income": ("Income_Statement", "Income statement (annual)"),
            "balance": ("Balance_Sheet", "Balance sheet (annual)"),
            "cashflow": ("Cash_Flow_Statement", "Cash flow statement (annual)"),
            "ratios": ("Ratios", "Financial ratios"),
            "statistics": ("Statistics_Valuation", "Statistics and valuation"),
            "forecast": ("Forecast_Analyst_Projections", "Analyst forecasts, ratings and price targets"),
            "dividend": ("Dividends", "Dividend history")}
SA_UNITS = {"income": "INR millions", "balance": "INR millions", "cashflow": "INR millions",
            "ratios": "ratios as shown", "statistics": "as shown (INR, %, x)",
            "forecast": "as shown (B = INR billions; per-share values in INR)", "dividend": "INR per share"}
SCR_SECTIONS = [("quarters", "Quarters", "Quarterly results"), ("profit-loss", "Profit_Loss", "Profit and loss (annual)"),
                ("balance-sheet", "Balance_Sheet", "Balance sheet (annual)"),
                ("cash-flow", "Cash_Flow", "Cash flows (annual)"), ("ratios", "Ratios", "Ratios (annual)"),
                ("shareholding_quarterly", "Shareholding_Quarterly", "Shareholding pattern by quarter (%)"),
                ("shareholding_yearly", "Shareholding_Yearly", "Shareholding pattern by year (%)"),
                ("schedules", "Schedules", "Line-item schedules (long format: section, parent, item, period, value)")]
BOLD, GREY = Font(bold=True), Font(italic=True, color="666666")
HEAD = PatternFill("solid", fgColor="DCE6F1")
NUM = re.compile(r"-?\d+(?:\.\d+)?")


def value(x):
    """Number if the cell is a plain number (commas allowed), else the text as shown, None if empty."""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    if isinstance(x, (int, float)):
        return x
    s = str(x).strip()
    t = s.replace(",", "")
    return float(t) if NUM.fullmatch(t) else s


def add_sheet(wb: Workbook, title: str, source: str, desc: str, df: pd.DataFrame) -> None:
    ws = wb.create_sheet(title[:31])
    ws["A1"], ws["A2"] = source, desc
    ws["A1"].font, ws["A2"].font = BOLD, GREY
    for j, c in enumerate(df.columns, start=1):
        cell = ws.cell(row=4, column=j, value=str(c))
        cell.font, cell.fill = BOLD, HEAD
    for i, row in enumerate(df.itertuples(index=False), start=5):
        for j, v in enumerate(row, start=1):
            ws.cell(row=i, column=j, value=value(v))
    ws.column_dimensions["A"].width = 44
    for j in range(2, len(df.columns) + 1):
        ws.column_dimensions[ws.cell(row=4, column=j).column_letter].width = 16
    ws.freeze_panes = "B5"


def save(wb: Workbook, path: Path) -> None:
    del wb["Sheet"]
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def screener(summary: dict) -> list[str]:
    out = []
    for sym, co in CO.items():
        for scope in ["consolidated", "standalone"]:
            info = summary.get(f"{sym}_{scope}", {})
            url = info.get("url", f"https://www.screener.in/company/{sym}/" + ("consolidated/" if scope == "consolidated"
                                                                                else ""))
            when = info.get("fetched", "2026-11-01")
            wb = Workbook()
            top = pd.DataFrame([{"item": k, "as shown": v.get("text"), "number(s)": ", ".join(f"{x:g}" for x in v.get(
                "numbers", []))} for k, v in info.get("top_ratios", {}).items()])
            add_sheet(wb, "Summary", f"Source: Screener.in | {url} | downloaded {when} | Rs crore, Rs per share, %",
                      f"{info.get('name', co)} ({scope}): figures at the top of the company page; Screener company id "
                      f"{info.get('company_id')}", top)
            for sec, title, desc in SCR_SECTIONS:
                f = DATA / "screener" / f"{sym}_{scope}_{sec}.csv"
                if not f.exists():
                    continue
                src = (f"Source: Screener.in schedules API | https://www.screener.in/api/company/{info.get('company_id')}"
                       f"/schedules/?parent=<parent>&section=<section>" + ("&consolidated=true" if scope ==
                                                                          "consolidated" else "")
                       if sec == "schedules" else f"Source: Screener.in | {url}")
                add_sheet(wb, title, f"{src} | downloaded {when} | Rs crore (rows ending in % are percent)",
                          f"{info.get('name', co)} ({scope}): {desc}", pd.read_csv(f))
            path = SD / "screener" / f"{co}_Screener_{scope.title()}.xlsx"
            save(wb, path)
            out.append(f"{path.relative_to(SD)}: {len(wb.sheetnames)} sheets")
    return out


def stockanalysis(meta: dict) -> list[str]:
    out = []
    for sym, co in CO.items():
        for page, (name, desc) in SA_PAGES.items():
            info = meta.get(f"{sym}_{page}", {})
            files = sorted((DATA / "stockanalysis").glob(f"{sym}_{page}_t*.csv"),
                           key=lambda p: int(p.stem.rsplit("_t", 1)[1]))
            if not files:
                continue
            wb = Workbook()
            for f in files:
                k = int(f.stem.rsplit("_t", 1)[1]) + 1
                add_sheet(wb, f"Table {k}", f"Source: StockAnalysis.com (S&P Global Market Intelligence data) | "
                          f"{info.get('url')} | downloaded {info.get('fetched')} | {SA_UNITS[page]}",
                          f"{co}: {desc}, table {k} of {len(files)} on the page", pd.read_csv(f))
            path = SD / "stockanalysis" / f"{co}_{name}_StockAnalysis.xlsx"
            save(wb, path)
            out.append(f"{path.relative_to(SD)}: {len(files)} tables")
    return out


def main() -> None:
    summary = json.loads((DATA / "screener" / "screener_summary.json").read_text(encoding="utf-8"))
    meta = json.loads((DATA / "stockanalysis" / "stockanalysis_meta.json").read_text(encoding="utf-8"))
    log = screener(summary) + stockanalysis(meta)
    (ROOT / "build" / "_export_log.txt").write_text("\n".join(log), encoding="utf-8")
    print(f"{len(log)} workbooks written")


if __name__ == "__main__":
    main()
