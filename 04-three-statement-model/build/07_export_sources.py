"""Export the Screener and StockAnalysis tables as .xlsx files in source_data/ (offline step).

Reads the tables saved by build/01_fetch_data.py:
  data/raw/screener/ULTRACEMCO_<section>.csv, data/raw/screener/screener_summary.json
  source_data/screener/raw/ULTRACEMCO_schedule_<section>_<parent>.json   (Screener schedules API)
  data/raw/stockanalysis/<page>_table<i>.csv                             (stockanalysis.com, S&P Global data)
Writes:
  source_data/screener/UltraTech_Screener_Consolidated.xlsx               one sheet per Screener section + schedules
  source_data/stockanalysis/UltraTech_<Statement>_StockAnalysis.xlsx      one file per page group
  data/raw/export_sources.log

Every sheet: row 1 = "Source: <site> | <URL> | downloaded 01-Nov-2026 | units", row 2 = what the sheet holds,
row 3 = table header. Values are copied as shown on the page: plain numbers become Excel numbers; percentages and
abbreviated amounts (B = INR billion, T = INR trillion) stay as text. Two clean-ups, both noted on the sheet: the
rupee sign that the page decoder garbled ("â¹") is restored, and on the StockAnalysis overview page the tooltip
text that the parser appended to row labels ("Revenue Revenue Growth") is removed.

Run:  python build/07_export_sources.py
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
SCR_CSV = RAW / "screener"
SA_CSV = RAW / "stockanalysis"
SCR_JSON = ROOT / "source_data" / "screener" / "raw"
OUT_SCR = ROOT / "source_data" / "screener"
OUT_SA = ROOT / "source_data" / "stockanalysis"
SYMBOL = "ULTRACEMCO"
COMPANY = "UltraTech Cement Ltd (NSE: ULTRACEMCO)"
DOWNLOADED = "01-Nov-2026"
SCR_URL = f"https://www.screener.in/company/{SYMBOL}/consolidated/"
SA_BASE = f"https://stockanalysis.com/quote/nse/{SYMBOL}/"
SA_SITE = "StockAnalysis.com (S&P Global Market Intelligence data)"
HEAD_FILL = PatternFill("solid", fgColor="D9E1F2")
NUM_RE = re.compile(r"^-?\d[\d,]*(\.\d+)?$")
SA_UNITS = "INR millions unless stated (per-share values in INR, margins and growth in %)"


def fix_text(s: str) -> str:
    """Undo the latin-1 mis-decoding of the rupee sign on stockanalysis.com pages ('â\\x82¹' -> '₹')."""
    if "\u00e2" not in s and "\u00c3" not in s:
        return s
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s.replace("\u00e2\u0082\u00b9", "\u20b9").replace("\u00e2\u00b9", "\u20b9")


def to_cell(v: object) -> object:
    """Plain numbers -> int/float; blanks -> None; everything else -> text as shown."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if isinstance(v, (int, float)):
        return int(v) if float(v).is_integer() else float(v)
    s = fix_text(str(v)).strip()
    if NUM_RE.match(s):
        f = float(s.replace(",", ""))
        return int(f) if f.is_integer() and "." not in s else f
    return s


def clean_overview_label(s: str) -> str:
    """'Revenue Revenue Growth' -> 'Revenue'; 'Earnings Per Share EPS Growth' -> 'Earnings Per Share'."""
    for i, ch in enumerate(s):
        if ch == " " and s[i + 1:] == s[:i] + " Growth":
            return s[:i]
    m = re.match(r"^(.+) (EPS|CapEx|Net Cash) Growth$", s)
    return m.group(1) if m else s


Block = tuple[str | None, pd.DataFrame]


def write_sheet(wb: Workbook, name: str, source: str, note: str, blocks: list[Block]) -> int:
    """Write row 1 = source line, row 2 = note, then the tables. Returns the number of data rows written."""
    ws = wb.create_sheet(name)
    ws["A1"] = source
    ws["A1"].font = Font(bold=True)
    ws["A2"] = note
    ws["A2"].font = Font(italic=True, color="404040")
    r, prev_cols, n_rows = 3, None, 0
    widths: dict[int, int] = {}
    for title, df in blocks:
        cols = [str(c) for c in df.columns]
        if title is not None or cols != prev_cols:
            if prev_cols is not None:
                r += 1  # blank row between blocks
            if title is not None:
                ws.cell(r, 1, title).font = Font(bold=True, italic=True)
                r += 1
            for j, c in enumerate(cols, start=1):
                cell = ws.cell(r, j, fix_text(c))
                cell.font = Font(bold=True)
                cell.fill = HEAD_FILL
                cell.alignment = Alignment(wrap_text=True, vertical="top")
                widths[j] = max(widths.get(j, 0), min(len(c), 24))
            r += 1
            prev_cols = cols
        if df.empty:
            ws.cell(r, 1, "(no rows returned by the source)").font = Font(italic=True)
            r += 1
        for row in df.itertuples(index=False):
            for j, v in enumerate(row, start=1):
                val = to_cell(v)
                cell = ws.cell(r, j, val)
                if isinstance(val, float):
                    cell.number_format = "#,##0.00"
                elif isinstance(val, int):
                    cell.number_format = "#,##0"
                widths[j] = max(widths.get(j, 0), len(str(val)) if val is not None else 0)
            r += 1
            n_rows += 1
    for j, w in widths.items():
        ws.column_dimensions[get_column_letter(j)].width = min(70 if j == 1 else 26, max(10, w + 2))
    ws.freeze_panes = "B4"
    return n_rows


def schedule_frame(path: Path) -> tuple[str, pd.DataFrame]:
    """Screener schedules JSON {line: {period: value}} -> (API url, table with periods as columns)."""
    d = json.loads(path.read_text(encoding="utf-8"))
    data = d.get("data") or {}
    periods: list[str] = []
    for vals in data.values():
        for p in vals:
            if p != "isExpandable" and p not in periods:
                periods.append(p)
    rows = [[line] + [vals.get(p) for p in periods] for line, vals in data.items()]
    return d.get("url", ""), pd.DataFrame(rows, columns=["Line item"] + periods)


def screener_workbook(log: list[str]) -> Path:
    wb = Workbook()
    wb.remove(wb.active)
    summ = json.loads((SCR_CSV / "screener_summary.json").read_text(encoding="utf-8"))[SYMBOL]
    src = f"Source: Screener.in | {SCR_URL} | downloaded {DOWNLOADED} | units: Rs crore unless stated"
    top = [["Company", summ.get("name", ""), None], ["Screener company id", summ.get("company_id"), None],
           ["Page fetched (UTC)", summ.get("fetched_utc"), None]]
    for k, v in summ.get("top_ratios", {}).items():
        nums = v.get("numbers") or []
        top.append([k, v.get("text"), nums[0] if len(nums) == 1 else ", ".join(f"{n:g}" for n in nums)])
    n = write_sheet(wb, "Summary", src.replace("Rs crore unless stated", "Rs crore (market cap), Rs (price, "
                                               "book value), % (yield, ROCE, ROE)"),
                    f"{COMPANY}, consolidated. Top-ratios box of the company page (prices as of the 30-Oct-2026 "
                    "close). Raw page: source_data/screener/raw/ULTRACEMCO_consolidated.html.",
                    [(None, pd.DataFrame(top, columns=["Metric", "As shown", "Value"]))])
    log.append(f"  Summary: {n} rows")
    sections = [("Quarters", "quarters", "Quarterly results (Rs crore; OPM % and Tax % in %; EPS in Rs)"),
                ("Profit_Loss", "profit-loss", "Annual profit and loss, fiscal years ending March (Rs crore; "
                                               "OPM %, Tax % and Dividend Payout % in %; EPS in Rs; TTM = 12 months "
                                               "to Sep-2026)"),
                ("Balance_Sheet", "balance-sheet", "Balance sheet at each 31 March, plus 30-Sep-2026 (Rs crore)"),
                ("Cash_Flow", "cash-flow", "Cash flow statement, fiscal years ending March (Rs crore)"),
                ("Ratios", "ratios", "Efficiency ratios (days) and ROCE (%)")]
    for sheet, sec, what in sections:
        df = pd.read_csv(SCR_CSV / f"{SYMBOL}_{sec}.csv").rename(columns={"item": "Line item"})
        n = write_sheet(wb, sheet, src, f"{COMPANY}, consolidated. {what}. Parsed from the '{sec}' section of "
                                        "the saved page (source_data/screener/raw/ULTRACEMCO_consolidated.html).",
                        [(None, df)])
        log.append(f"  {sheet}: {n} rows")
    for sheet, sec in [("Sched_Profit_Loss", "profit-loss"), ("Sched_Quarters", "quarters"),
                       ("Sched_Balance_Sheet", "balance-sheet"), ("Sched_Cash_Flow", "cash-flow")]:
        blocks: list[Block] = []
        for p in sorted(SCR_JSON.glob(f"{SYMBOL}_schedule_{sec}_*.json")):
            url, df = schedule_frame(p)
            parent = p.stem.split(f"_schedule_{sec}_", 1)[1].replace("_", " ")
            blocks.append((f"Breakdown of '{parent}' | {url}", df))
        n = write_sheet(wb, sheet, "Source: Screener.in schedules API | https://www.screener.in/api/company/3525/"
                                   f"schedules/?parent=<line>&section={sec}&consolidated=true | downloaded "
                                   f"{DOWNLOADED} | units: Rs crore; % rows in %",
                        f"{COMPANY}, consolidated. Line-item breakdowns behind the '{sec}' table (the '+' rows on "
                        "the page), one block per parent line with its exact URL. Raw JSON: "
                        "source_data/screener/raw/.", blocks)
        log.append(f"  {sheet}: {len(blocks)} blocks, {n} rows")
    out = OUT_SCR / "UltraTech_Screener_Consolidated.xlsx"
    wb.save(out)
    return out


# file name -> list of (sheet, page path, [csv stems], note)
SA_FILES: dict[str, list[tuple[str, str, list[str], str]]] = {
    "UltraTech_Income_Statement_StockAnalysis.xlsx": [
        ("Annual", "financials/income-statement/", ["income_annual_table0", "income_annual_table1"],
         "Annual income statement (FY = year ending 31 March; TTM = 12 months to 30-Sep-2026)"),
        ("Quarterly", "financials/income-statement/?p=quarterly", ["income_quarterly_table0",
                                                                   "income_quarterly_table1"],
         "Quarterly income statement (fiscal quarters: Q2 2027 = Jul-Sep 2026)")],
    "UltraTech_Balance_Sheet_StockAnalysis.xlsx": [
        ("Annual", "financials/balance-sheet/", [f"balance_annual_table{i}" for i in range(4)],
         "Balance sheet at each 31 March; first column = latest balance sheet (30-Sep-2026)"),
        ("Quarterly", "financials/balance-sheet/?p=quarterly", [f"balance_quarterly_table{i}" for i in range(4)],
         "Quarterly balance sheets (Indian companies publish them half-yearly; other quarters may be blank)")],
    "UltraTech_Cash_Flow_Statement_StockAnalysis.xlsx": [
        ("Annual", "financials/cash-flow-statement/", [f"cashflow_annual_table{i}" for i in range(6)],
         "Annual cash flow statement; TTM = 12 months to 30-Sep-2026 (no quarterly page: Indian companies "
         "report cash flow half-yearly)")],
    "UltraTech_Ratios_StockAnalysis.xlsx": [
        ("Annual", "financials/ratios/", [f"ratios_annual_table{i}" for i in range(5)],
         "Valuation, leverage and return ratios by fiscal year; 'Current' column dated 29-Oct-2026 on the page")],
    "UltraTech_Statistics_Valuation_StockAnalysis.xlsx": [
        ("Statistics", "statistics/", [f"statistics_table{i}" for i in range(19)],
         "Key statistics page as shown (amounts abbreviated: B = INR billion, T = INR trillion)")],
    "UltraTech_Forecast_Analyst_Projections_StockAnalysis.xlsx": [
        ("Financial_Forecast", "forecast/", ["forecast_table3"],
         "Consensus financial forecast by fiscal year (B = INR billion, T = INR trillion; EPS in INR; "
         "'Upgrade' = shown only to paying users)"),
        ("Revenue_Range", "forecast/", ["forecast_table4"], "FY2027 revenue estimates: high, average, low "
                                                            "('Pro' = paywalled)"),
        ("Revenue_Growth_Range", "forecast/", ["forecast_table5"], "FY2027 revenue growth estimates"),
        ("EPS_Range", "forecast/", ["forecast_table6"], "FY2027 EPS estimates in INR: high, average, low"),
        ("EPS_Growth_Range", "forecast/", ["forecast_table7"], "FY2027 EPS growth estimates"),
        ("Price_Target", "forecast/", ["forecast_table0"], "12-month analyst price target (INR) vs the last price"),
        ("Ratings", "forecast/", ["forecast_table1"], "Analyst rating counts by month"),
        ("Analyst_Calls", "forecast/", ["forecast_table2"], "Latest analyst actions listed on the page")],
    "UltraTech_Financials_Overview_StockAnalysis.xlsx": [
        ("Annual", "financials/", [f"overview_annual_table{i}" for i in range(7)],
         "Financials overview incl. revenue by segment; row labels cleaned of repeated tooltip text "
         "('Revenue Revenue Growth' -> 'Revenue')"),
        ("Quarterly", "financials/?p=quarterly", [f"overview_quarterly_table{i}" for i in range(6)],
         "Quarterly overview incl. revenue by segment (the segment table uses the page's own quarter labels); "
         "row labels cleaned as on the Annual sheet")],
}


def stockanalysis_workbooks(log: list[str]) -> list[Path]:
    outs = []
    for fname, sheets in SA_FILES.items():
        wb = Workbook()
        wb.remove(wb.active)
        for sheet, page, stems, what in sheets:
            blocks: list[Block] = []
            for stem in stems:
                df = pd.read_csv(SA_CSV / f"{stem}.csv", dtype=str, keep_default_na=False)
                df = df.replace({"": None})
                if stem.startswith("statistics"):
                    df.columns = ["Metric", "Value (as shown)"]
                if stem.startswith("overview"):
                    df.iloc[:, 0] = df.iloc[:, 0].map(lambda s: clean_overview_label(str(s)))
                blocks.append((None, df))
            units = SA_UNITS if not page.startswith(("statistics", "forecast")) else \
                "as shown on the page (B = INR billion, T = INR trillion; per-share values in INR)"
            raw = stems[0].rsplit("_table", 1)[0]
            n = write_sheet(wb, sheet, f"Source: {SA_SITE} | {SA_BASE}{page} | downloaded {DOWNLOADED} | "
                                       f"units: {units}",
                            f"{COMPANY}, consolidated. {what}. Raw page: source_data/stockanalysis/raw/{raw}.html; "
                            f"parsed tables: data/raw/stockanalysis/{raw}_table<N>.csv.", blocks)
            log.append(f"  {fname} / {sheet}: {len(stems)} tables, {n} rows")
        out = OUT_SA / fname
        wb.save(out)
        outs.append(out)
    return outs


def verify(paths: list[Path], log: list[str]) -> bool:
    """Re-open every file: each sheet starts with a source line and holds data; spot-check key values."""
    ok = True
    for p in paths:
        wb = load_workbook(p)
        for ws in wb.worksheets:
            a1 = str(ws["A1"].value or "")
            good = a1.startswith("Source:") and ws.max_row >= 4 and "downloaded 01-Nov-2026" in a1
            ok &= good
            if not good:
                log.append(f"  FAIL {p.name}/{ws.title}: A1={a1[:60]!r}, rows={ws.max_row}")
        wb.close()
    wb = load_workbook(OUT_SCR / "UltraTech_Screener_Consolidated.xlsx")
    pl = wb["Profit_Loss"]
    hdr = [c.value for c in pl[3]]
    sales = next(r for r in pl.iter_rows(min_row=4, values_only=True) if r[0] == "Sales")
    v = sales[hdr.index("Mar 2026")]
    good = v == 88512
    ok &= good
    log.append(f"  {'PASS' if good else 'FAIL'} spot check: Screener FY2026 sales = {v} (filing 88,511.53)")
    wb = load_workbook(OUT_SA / "UltraTech_Forecast_Analyst_Projections_StockAnalysis.xlsx")
    eps = next(r for r in wb["EPS_Range"].iter_rows(min_row=4, values_only=True) if r[0] == "Avg")
    good = abs(float(eps[1]) - 325.76) < 1e-9
    ok &= good
    log.append(f"  {'PASS' if good else 'FAIL'} spot check: consensus FY2027 EPS average = {eps[1]}")
    calls = [r for r in wb["Analyst_Calls"].iter_rows(min_row=4, values_only=True) if r[0]]
    good = all("\u00e2" not in str(x) for r in calls for x in r) and "\u20b9" in str(calls[0][5])
    ok &= good
    log.append(f"  {'PASS' if good else 'FAIL'} rupee sign restored: {calls[0][5]!r}")
    return ok


def main() -> None:
    log = ["export_sources: Screener and StockAnalysis tables -> .xlsx"]
    paths = [screener_workbook(log)] + stockanalysis_workbooks(log)
    ok = verify(paths, log)
    for p in paths:
        log.append(f"wrote {p.relative_to(ROOT)} ({p.stat().st_size / 1e3:.0f} KB)")
    log.append("RESULT: " + ("PASS" if ok else "FAIL"))
    (RAW / "export_sources.log").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))
    print("EXIT_OK" if ok else "EXIT_FAIL")


if __name__ == "__main__":
    main()
