"""Export the raw Screener.in and StockAnalysis.com downloads in source_data/ to .xlsx files that open cleanly in Excel.

Each sheet has the source line in row 1 ("Source: <site> | <URL> | downloaded <date> | units"), a blank row 2 and the
table from row 3. The raw HTML / CSV / JSON files stay next to the exports (audit trail). Offline; re-run any time:

    python build/export_source_tables.py

Outputs
  source_data/screener/Castrol_India_Screener_Standalone.xlsx      one sheet per Screener section + schedules
  source_data/stockanalysis/Castrol_India_<page>_StockAnalysis.xlsx one workbook per page, one sheet per table
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[1]
SD = ROOT / "source_data"
SCR_DIR, SA_DIR = SD / "screener", SD / "stockanalysis"
SCR_URL = "https://www.screener.in/company/CASTROLIND/"
SCR_DATE = "31-Oct-2026 (18:03 UTC; prices as of the 30-Oct-2026 close)"
SA_DATE = "31-Oct-2026 (18:24 UTC)"
SA_BASE = "https://stockanalysis.com/quote/nse/CASTROLIND/"
SA_PAGES = [  # (raw file prefix, workbook name, URL suffix, units)
    ("income_annual", "Income_Statement_Annual", "financials/", "INR millions (per-share data in INR)"),
    ("income_quarterly", "Income_Statement_Quarterly", "financials/?p=quarterly", "INR millions (per-share data in INR)"),
    ("balance_annual", "Balance_Sheet_Annual", "financials/balance-sheet/", "INR millions"),
    ("balance_quarterly", "Balance_Sheet_Quarterly", "financials/balance-sheet/?p=quarterly", "INR millions"),
    ("cashflow_annual", "Cash_Flow_Statement_Annual", "financials/cash-flow-statement/", "INR millions"),
    ("ratios_annual", "Ratios_Annual", "financials/ratios/", "ratios as shown; market values in INR millions"),
    ("statistics", "Statistics", "statistics/", "as shown on the page"),
    ("forecast", "Forecast", "forecast/", "INR per share for price targets; analyst counts"),
]
BOLD = Font(bold=True)
NOTE = Font(italic=True, color="555555")


def write_df(wb: Workbook, title: str, df: pd.DataFrame, source_line: str) -> None:
    ws = wb.create_sheet(title[:31])
    ws["A1"] = source_line
    ws["A1"].font = NOTE
    for j, col in enumerate(df.columns, start=1):
        ws.cell(3, j, str(col)).font = BOLD
    for i, row in enumerate(df.itertuples(index=False), start=4):
        for j, v in enumerate(row, start=1):
            if isinstance(v, float) and pd.isna(v):
                v = None
            elif isinstance(v, (dict, list)):
                v = json.dumps(v)
            ws.cell(i, j, v)
    ws.column_dimensions["A"].width = 44
    for j in range(2, len(df.columns) + 1):
        ws.column_dimensions[get_column_letter(j)].width = 18
    ws.freeze_panes = "B4"


def screener() -> Path:
    wb = Workbook()
    wb.remove(wb.active)
    for sec in ["profit-loss", "quarters", "balance-sheet", "cash-flow", "ratios"]:
        df = pd.read_csv(SCR_DIR / f"CASTROLIND_{sec}.csv")
        units = "Rs crore (percentages and per-share values as labelled)"
        write_df(wb, sec, df, f"Source: Screener.in (standalone) | {SCR_URL}#{sec} | downloaded {SCR_DATE} | {units}")
    rows = []
    for p in sorted(SCR_DIR.glob("CASTROLIND_schedule_*.json")):
        js = json.loads(p.read_text(encoding="utf-8"))
        for item, vals in (js.get("data") or {}).items():
            if not isinstance(vals, dict):
                continue
            rec = {"schedule (API url)": js["url"], "line item": item}
            rec.update({k: v for k, v in vals.items()
                        if k != "isExpandable" and isinstance(v, (str, int, float))})  # drop styling metadata
            rows.append(rec)
    sched = pd.DataFrame(rows)
    write_df(wb, "schedules", sched, "Source: Screener.in schedules API (standalone) | "
             "https://www.screener.in/api/company/589/schedules/?parent=<parent>&section=<section> | downloaded "
             f"{SCR_DATE} | Rs crore or % as shown")
    out = SCR_DIR / "Castrol_India_Screener_Standalone.xlsx"
    wb.save(out)
    return out


def stockanalysis() -> list[Path]:
    outs = []
    for prefix, name, suffix, units in SA_PAGES:
        files = sorted(SA_DIR.glob(f"{prefix}_table*.csv"), key=lambda p: int(p.stem.split("table")[1]))
        if not files:
            continue
        wb = Workbook()
        wb.remove(wb.active)
        for f in files:
            df = pd.read_csv(f)
            write_df(wb, f.stem.split("_")[-1], df,
                     f"Source: StockAnalysis.com (S&P Global data) | {SA_BASE}{suffix} | downloaded {SA_DATE} | {units}")
        out = SA_DIR / f"Castrol_India_{name}_StockAnalysis.xlsx"
        wb.save(out)
        outs.append(out)
    return outs


def main() -> None:
    outs = [screener()] + stockanalysis()
    for o in outs:
        print(f"saved {o.relative_to(ROOT)} ({o.stat().st_size / 1e3:.0f} KB)")
    print("EXIT_OK")


if __name__ == "__main__":
    main()
