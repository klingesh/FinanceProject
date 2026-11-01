"""Excel copies of the downloaded Screener and stockanalysis.com tables, plus the source_data/README.md index.

- source_data/screener/<Name>_Screener_Consolidated.xlsx (and _Standalone where fetched): one sheet per Screener
  section plus a Schedules sheet with the line-item breakdowns.
- source_data/stockanalysis/<Name>_<Statement>_StockAnalysis.xlsx: one workbook per page type, tables stacked.
- Row 1 of every sheet: "Source: <site> | <URL> | downloaded <date> | units". The raw HTML/CSV/JSON stay as they are.
- source_data/README.md: index of every file (by pattern). The script stops if a file is not covered.

Offline: reads only files already in source_data/. Run: python build/export_source_xlsx.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "source_data"
DOWNLOADED = "01-Nov-2026"
NAMES = {"ASIANPAINT": "AsianPaints", "BERGEPAINT": "BergerPaints", "KANSAINER": "KansaiNerolac",
         "JSWDULUX": "JSWDulux", "INDIGOPNTS": "IndigoPaints"}
STANDALONE_TOO = ["INDIGOPNTS", "JSWDULUX"]
SCREENER_SECTIONS = [("quarters", "Quarters"), ("profit-loss", "Profit_Loss"), ("balance-sheet", "Balance_Sheet"),
                     ("cash-flow", "Cash_Flow"), ("ratios", "Ratios"), ("shareholding", "Shareholding")]
SA_PAGES = {  # key -> URL path (same as build/fetch_sources.py)
    "statistics": "statistics/", "income_annual": "financials/", "income_quarterly": "financials/?p=quarterly",
    "balance_annual": "financials/balance-sheet/", "balance_quarterly": "financials/balance-sheet/?p=quarterly",
    "cashflow_annual": "financials/cash-flow-statement/", "ratios_annual": "financials/ratios/",
    "forecast": "forecast/",
}
SA_BOOKS = [  # (file suffix, [(sheet name, page key)])
    ("Income_Statement", [("Annual", "income_annual"), ("Quarterly", "income_quarterly")]),
    ("Balance_Sheet", [("Annual", "balance_annual"), ("Quarterly", "balance_quarterly")]),
    ("Cash_Flow_Statement", [("Annual", "cashflow_annual")]),
    ("Ratios", [("Annual", "ratios_annual")]),
    ("Statistics_Valuation", [("Statistics", "statistics")]),
    ("Forecast_Analyst_Projections", [("Forecast", "forecast")]),
]
HDR_FILL = PatternFill("solid", fgColor="1F4E78")
SEC_FILL = PatternFill("solid", fgColor="DDEBF7")
NUM = re.compile(r"^-?\d[\d,]*(\.\d+)?$")


def parse(v):
    """Return (value, number_format). Plain numbers become floats, 'x%' becomes a fraction; other text stays."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None, None
    if isinstance(v, (int, float)):
        return float(v), "#,##0.00"
    s = str(v).strip()
    if s == "" or s.lower() == "nan":
        return None, None
    if NUM.match(s):
        return float(s.replace(",", "")), "#,##0.00"
    if s.endswith("%") and NUM.match(s[:-1].strip()):
        return float(s[:-1].replace(",", "")) / 100, "0.00%"
    return s, None


def source_line(ws, text: str) -> None:
    ws["A1"] = text
    ws["A1"].font = Font(italic=True, size=9, color="404040")


def write_table(ws, row: int, df: pd.DataFrame, title: str | None = None) -> int:
    """Write a header + rows block starting at `row`; return the next free row (one blank row after)."""
    if title:
        for col in range(1, len(df.columns) + 1):
            ws.cell(row=row, column=col).fill = SEC_FILL
        ws.cell(row=row, column=1, value=title).font = Font(bold=True, color="1F4E78")
        row += 1
    for j, col in enumerate(df.columns, start=1):
        c = ws.cell(row=row, column=j, value=str(col))
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = HDR_FILL
        c.alignment = Alignment(wrap_text=True, vertical="center")
    row += 1
    for rec in df.itertuples(index=False):
        for j, v in enumerate(rec, start=1):
            val, fmt = parse(v) if j > 1 else (None if pd.isna(v) else str(v), None)
            c = ws.cell(row=row, column=j, value=val)
            if fmt:
                c.number_format = fmt
        row += 1
    return row + 1


def finish(ws, ncols: int, first_width: float = 46) -> None:
    ws.column_dimensions["A"].width = first_width
    for j in range(2, ncols + 1):
        ws.column_dimensions[ws.cell(row=2, column=j).column_letter].width = 15
    ws.freeze_panes = "B3"


# ----------------------------------------------------------------------------------------------
def schedules_df(path: Path) -> tuple[pd.DataFrame, str]:
    j = json.loads(path.read_text(encoding="utf-8"))
    data = j.get("data") or {}
    periods: list[str] = []
    for item in data.values():
        if isinstance(item, dict):
            for p in item:
                if p not in periods:
                    periods.append(p)
    rows = [[name] + [vals.get(p, "") if isinstance(vals, dict) else "" for p in periods]
            for name, vals in data.items()]
    return pd.DataFrame(rows, columns=["Line item"] + periods), j.get("url", "")


def screener_book(sym: str, basis: str) -> Path:
    wb = Workbook()
    wb.remove(wb.active)
    url = f"https://www.screener.in/company/{sym}/" + ("consolidated/" if basis == "consolidated" else "")
    prefix = f"{sym}_" if basis == "consolidated" else f"{sym}_standalone_"
    for sec, sheet in SCREENER_SECTIONS:
        f = SRC / "screener" / f"{prefix}{sec}.csv"
        if not f.exists():
            continue
        df = pd.read_csv(f, dtype=str)
        units = ("% of shares" if sec == "shareholding" else
                 "days and % as shown" if sec == "ratios" else "Rs crore")
        ws = wb.create_sheet(sheet)
        source_line(ws, f"Source: Screener.in ({basis}) | {url}#{sec} | downloaded {DOWNLOADED} | {units}")
        write_table(ws, 2, df.rename(columns={"item": "Line item"}))
        finish(ws, len(df.columns))
    scheds = sorted((SRC / "screener" / "schedules").glob(f"{sym}_{basis}_*.json"))
    if scheds:
        ws = wb.create_sheet("Schedules")
        source_line(ws, f"Source: Screener.in schedules API ({basis}; URL above each block) | downloaded "
                        f"{DOWNLOADED} | Rs crore unless the line says %")
        row, ncols = 3, 1
        for p in scheds:
            df, surl = schedules_df(p)
            if df.empty:
                continue
            section, parent = p.stem.split("_", 2)[2].split("_", 1)
            row = write_table(ws, row, df, title=f"{section} | {parent.replace('_', ' ')} | {surl}")
            ncols = max(ncols, len(df.columns))
        finish(ws, ncols, 44)
        ws.freeze_panes = "B2"
    out = SRC / "screener" / f"{NAMES[sym]}_Screener_{basis.capitalize()}.xlsx"
    wb.save(out)
    return out


def natural_tables(sym: str, key: str) -> list[Path]:
    files = list((SRC / "stockanalysis" / "raw").glob(f"{sym}_{key}_table*.csv"))
    return sorted(files, key=lambda p: int(re.search(r"table(\d+)\.csv$", p.name).group(1)))


def stockanalysis_book(sym: str, suffix: str, sheets: list[tuple[str, str]]) -> Path:
    wb = Workbook()
    wb.remove(wb.active)
    for sheet, key in sheets:
        url = f"https://stockanalysis.com/quote/nse/{sym}/{SA_PAGES[key]}"
        units = ("INR billions where values end in B; % as shown" if key == "forecast" else
                 "as shown on the page (INR, %, x)" if key == "statistics" else "INR millions; % as shown")
        ws = wb.create_sheet(sheet)
        source_line(ws, f"Source: stockanalysis.com (S&P Global Market Intelligence data) | {url} | downloaded "
                        f"{DOWNLOADED} | {units}")
        row, ncols = 2, 1
        for i, f in enumerate(natural_tables(sym, key)):
            df = pd.read_csv(f, dtype=str)
            row = write_table(ws, row, df, title=None if i == 0 else f"Table {i + 1} on the page")
            ncols = max(ncols, len(df.columns))
        finish(ws, ncols)
    out = SRC / "stockanalysis" / f"{NAMES[sym]}_{suffix}_StockAnalysis.xlsx"
    wb.save(out)
    return out


# ----------------------------------------------------------------------------------------------
# source_data/README.md (pattern-based index; every file must match one row)
# ----------------------------------------------------------------------------------------------
NSE = "https://nsearchives.nseindia.com/corporate/"
INDEX = [  # (regex on the path relative to source_data, file shown, contents, source, used for)
    (r"company_filings/AsianPaints_Q2FY27_Results_and_Press_Release_29Oct2026\.pdf",
     "company_filings/AsianPaints_Q2FY27_Results_and_Press_Release_29Oct2026.pdf",
     "Board-meeting outcome, 29-Oct-2026: Q2 and H1 FY27 standalone and consolidated results, 30-Sep-2026 balance "
     "sheet, cash-flow statement, press release",
     f"NSE filing: {NSE}ASIANPAINT_29102026140213_OutcomeofBM29102026signed.pdf",
     "H1 FY27 actuals, balance sheet for the EV bridge and DCF, Q2 margin and volume growth (data/asian_paints_q2fy27_filing.csv)"),
    (r"company_filings/AsianPaints_Q2FY27_Investor_Presentation_29Oct2026\.pdf",
     "company_filings/AsianPaints_Q2FY27_Investor_Presentation_29Oct2026.pdf",
     "Q2 FY27 investor presentation", f"NSE filing: {NSE}ASIANPAINT_29102026164544_SEIntimation_Investor_"
     "Presentation_Q2FY26-27pdfsigned.pdf", "Price increases (~12%), gross margin, outlook, VAE/VAM capex"),
    (r"company_filings/IndigoPaints_Q2FY27_Results_30Oct2026\.pdf",
     "company_filings/IndigoPaints_Q2FY27_Results_30Oct2026.pdf",
     "Indigo Paints Q2 FY27 results, filed 30-Oct-2026 17:41 IST",
     f"NSE filing: {NSE}INDIGOPNTS_30102026174023_Regulation_30_Outcome_of_Board_Meeting_-_FR-Signed.pdf",
     "TTM to Sep-2026; Apple Chemie minority liability (p.6); timing flag"),
    (r"company_filings/BergerPaints_Q2FY27_Analyst_Call_Intimation_30Oct2026\.pdf",
     "company_filings/BergerPaints_Q2FY27_Analyst_Call_Intimation_30Oct2026.pdf",
     "Berger Paints analyst-call notice (Q2 FY27 results after 30-Oct-2026)",
     f"NSE filing: {NSE}PAINTBERGE_30102026124130_concallinvite2710Letter.pdf", "TTM timing (Jun-2026)"),
    (r"company_filings/KansaiNerolac_Q2FY27_Analyst_Call_Intimation_26Oct2026\.pdf",
     "company_filings/KansaiNerolac_Q2FY27_Analyst_Call_Intimation_26Oct2026.pdf",
     "Kansai Nerolac analyst-call notice (Q2 FY27 results after 30-Oct-2026)",
     f"NSE filing: {NSE}KANSAINER_26102026153719_SEintimation_Q2FY27_Invite_signed.pdf", "TTM timing (Jun-2026)"),
    (r"company_filings/JSWDulux_Q2FY27_Investor_Call_Intimation_29Oct2026\.pdf",
     "company_filings/JSWDulux_Q2FY27_Investor_Call_Intimation_29Oct2026.pdf",
     "JSW Dulux investor-call notice for 4-Nov-2026",
     f"NSE filing: {NSE}AKZOINDIA_29102026172646_JSWDuluxInvestorCall4thNov26Intimation.pdf", "TTM timing (Jun-2026)"),
    (r"news_and_macro/ETBFSI_Reuters_India_bonds_October_2026\.html",
     "news_and_macro/ETBFSI_Reuters_India_bonds_October_2026.html",
     "Reuters report: 6.94% 2036 benchmark bond at 7.4139% on 30-Oct-2026",
     "https://bfsi.economictimes.indiatimes.com/articles/india-bonds-buckle-for-fourth-straight-month-on-oils-climb/135363689",
     "Risk-free rate 7.41%"),
    (r"news_and_macro/TradingEconomics_India_10Y_bond_yield\.html",
     "news_and_macro/TradingEconomics_India_10Y_bond_yield.html", "India 10-year yield 7.40% on 30-Oct-2026",
     "https://tradingeconomics.com/india/government-bond-yield", "Second source for the risk-free rate"),
    (r"news_and_macro/FinancialExpress_Gsec_yields_October_2026\.html",
     "news_and_macro/FinancialExpress_Gsec_yields_October_2026.html", "G-sec yields in October 2026 (29-Oct close ~7.44%)",
     "https://www.financialexpress.com/market/g-sec-yields-spike-30-bps-in-oct-global-cues-rate-hike-fears-weigh-4371647/",
     "Explains the 7.44% figure in the shared macro table"),
    (r"news_and_macro/Damodaran_country_risk_premium_Jan2026\.html",
     "news_and_macro/Damodaran_country_risk_premium_Jan2026.html",
     "Country default spreads and risk premiums, Jan-2026 (India: spread 1.87%, CRP 2.85%, total ERP 7.08%)",
     "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ctryprem.html", "Memo cost of equity on the WACC sheet"),
    (r"news_and_macro/ET_AsianPaints_Q2FY27_results_29Oct2026\.html",
     "news_and_macro/ET_AsianPaints_Q2FY27_results_29Oct2026.html", "Economic Times report on Q2 FY27 results",
     "https://economictimes.indiatimes.com/markets/stocks/earnings/asian-paints-q2-results-net-profit-rises-7-yoy-to-"
     "rs-1068-crore-firm-announces-rs-5-75/share-dividend/articleshow/135297927.cms", "Cross-check of revenue and PAT"),
    (r"news_and_macro/BusinessStandard_AsianPaints_Q2FY27_29Oct2026\.html",
     "news_and_macro/BusinessStandard_AsianPaints_Q2FY27_29Oct2026.html", "Business Standard report on Q2 FY27 results",
     "https://www.business-standard.com/amp/companies/quarterly-results/asian-paints-q2fy27-result-profit-rises-7-5-"
     "to-1-068-cr-sales-grow-17-126102900944_1.html", "Cross-check of revenue and PAT"),
    (r"news_and_macro/ET_AsianPaints_brokerages_cut_targets_30Oct2026\.html",
     "news_and_macro/ET_AsianPaints_brokerages_cut_targets_30Oct2026.html", "Brokerage target changes after Q2 FY27",
     "https://economictimes.indiatimes.com/markets/stocks/news/asian-paints-shares-in-focus-as-jefferies-goldman-"
     "sachs-other-brokerages-cut-target-prices-after-q2-results-buy-sell-or-hold/articleshow/135342271.cms",
     "Context for the analyst-target bar"),
    (r"news_and_macro/ET_AkzoNobel_India_renamed_JSW_Dulux_Mar2026\.html",
     "news_and_macro/ET_AkzoNobel_India_renamed_JSW_Dulux_Mar2026.html", "Akzo Nobel India renamed JSW Dulux (11-Mar-2026)",
     "https://manufacturing.economictimes.indiatimes.com/news/chemicals/akzo-nobel-india-gets-regulatory-nod-to-"
     "change-name-to-jsw-dulux/129502125", "Peer identity and ticker"),
    (r"news_and_macro/Livemint_JSW_Dulux_1for10_split_record_date\.html",
     "news_and_macro/Livemint_JSW_Dulux_1for10_split_record_date.html", "JSW Dulux 1:10 split, record date 22-Oct-2026",
     "https://www.livemint.com/market/stock-market-news/jsw-dulux-announced-record-date-for-1-10-stock-split-what-"
     "investors-should-know-11790079151086.html", "Split adjustment of consensus EPS"),
    (r"news_and_macro/ETLegal_JSW_Paints_unlisted_completes_AkzoNobel_India\.html",
     "news_and_macro/ETLegal_JSW_Paints_unlisted_completes_AkzoNobel_India.html",
     "JSW Paints completes 60.76% purchase of Akzo Nobel India (11-Dec-2025)",
     "https://legal.economictimes.indiatimes.com/news/corporate-business/jsw-paints-completes-acquisition-of-"
     "majority-stake-in-akzonobel-india/125909724", "Exclusion of JSW Paints (unlisted parent)"),
    (r"news_and_macro/BusinessWorld_Grasim_Birla_Opus_FY26\.html",
     "news_and_macro/BusinessWorld_Grasim_Birla_Opus_FY26.html", "Grasim FY26: Birla Opus about 10% decorative revenue share",
     "https://www.businessworld.in/article/grasim-industries-targets-rs-2-lakh-cr-revenue-in-fy27-birla-620427",
     "Exclusion of Birla Opus; competition context"),
    (r"news_and_macro/Daijiworld_Indigo_Paints_Q2FY27_30Oct2026\.html",
     "news_and_macro/Daijiworld_Indigo_Paints_Q2FY27_30Oct2026.html", "News report on Indigo Paints Q2 FY27",
     "https://daijiworld.com/news/newsDisplay?newsID=1333925", "Cross-check of Indigo results timing"),
    (r"nse/[A-Z]+_announcements_20Oct-31Oct2026\.json", "nse/<SYMBOL>_announcements_20Oct-31Oct2026.json (5 files)",
     "NSE corporate announcements, 20-31 Oct 2026, with filing timestamps",
     "https://www.nseindia.com/api/corporate-announcements?index=equities&symbol=<SYMBOL>&from_date=20-10-2026&to_date=31-10-2026",
     "Which quarter each TTM ends in; Indigo's after-close filing"),
    (r"screener/[A-Z]+_(quarters|profit-loss|balance-sheet|cash-flow|ratios|shareholding)\.csv",
     "screener/<SYMBOL>_<section>.csv (5 companies x 6 sections)", "Consolidated tables: quarters, P&L, balance sheet, "
     "cash flow, ratios, shareholding (Rs crore)", "https://www.screener.in/company/<SYMBOL>/consolidated/",
     "TTM revenue, EBITDA, PAT; balance-sheet items; FY2023-FY2026 history; ROCE, ROE"),
    (r"screener/[A-Z]+_standalone_(quarters|profit-loss|balance-sheet|cash-flow|ratios|shareholding)\.csv",
     "screener/<SYMBOL>_standalone_<section>.csv (INDIGOPNTS, JSWDULUX)", "Standalone tables (Rs crore)",
     "https://www.screener.in/company/<SYMBOL>/", "Consolidated vs standalone comparison"),
    (r"screener/raw/[A-Z]+_(consolidated|standalone)\.html", "screener/raw/<SYMBOL>_<basis>.html",
     "Saved Screener page HTML", "https://www.screener.in/company/<SYMBOL>/consolidated/ (or without consolidated/)",
     "Raw copy behind the CSVs and screener_summary.json"),
    (r"screener/schedules/[A-Z]+_(consolidated|standalone)_[a-z-]+_[A-Za-z_]+\.json",
     "screener/schedules/<SYMBOL>_<basis>_<section>_<parent>.json",
     "Line-item breakdowns (borrowings and leases, investments, other assets/liabilities, expenses, other income, "
     "cash-flow items); the URL is inside each file",
     "https://www.screener.in/api/company/<company_id>/schedules/?parent=<parent>&section=<section>&consolidated=",
     "Debt incl. leases, liquid investments, lease principal repaid, exceptional items"),
    (r"screener/schedules/_schedules_log\.txt", "screener/schedules/_schedules_log.txt", "Download log", "", ""),
    (r"screener/screener_summary\.json", "screener/screener_summary.json",
     "Top ratios per company: market cap, price, P/E, 52-week high/low, company id", "Screener pages above",
     "Checks 1-2 (market cap and P/E within 1-2% of Screener)"),
    (r"screener/[A-Za-z]+_Screener_(Consolidated|Standalone)\.xlsx", "screener/<Name>_Screener_<Basis>.xlsx (7 files)",
     "Excel copies of the Screener CSVs and schedules, one sheet per section; row 1 gives source, URL, date, units",
     "Built from the files above by build/export_source_xlsx.py", "Easy reading in Excel"),
    (r"stockanalysis/raw/[A-Z]+_[a-z_]+\.html", "stockanalysis/raw/<SYMBOL>_<page>.html",
     "Saved pages: statistics, income (annual, quarterly), balance sheet (annual, quarterly), cash flow, ratios, forecast",
     "https://stockanalysis.com/quote/nse/<SYMBOL>/<page>/ (statistics/, financials/, financials/balance-sheet/, "
     "financials/cash-flow-statement/, financials/ratios/, forecast/; ?p=quarterly for quarterly)",
     "Consensus EBIT/EPS FY27E-FY28E, price targets, share counts, debt and EV cross-checks"),
    (r"stockanalysis/raw/[A-Z]+_[a-z_]+_table\d+\.csv", "stockanalysis/raw/<SYMBOL>_<page>_table<N>.csv",
     "Tables parsed from each page with pandas.read_html (INR millions unless shown)", "Same pages",
     "Inputs to build/prepare_data.py"),
    (r"stockanalysis/[A-Za-z]+_[A-Za-z_]+_StockAnalysis\.xlsx", "stockanalysis/<Name>_<Statement>_StockAnalysis.xlsx (30 files)",
     "Excel copies: Income_Statement, Balance_Sheet, Cash_Flow_Statement, Ratios, Statistics_Valuation, "
     "Forecast_Analyst_Projections; row 1 gives source, URL, date, units", "Built from the raw tables by "
     "build/export_source_xlsx.py", "Easy reading in Excel"),
    (r"yahoo_finance/[A-Z]+\.NS_daily\.csv", "yahoo_finance/<SYMBOL>.NS_daily.csv (5 files)",
     "Daily open, high, low, close, adjusted close, volume, dividends, splits; 1-Jan-2021 to 30-Oct-2026",
     "https://finance.yahoo.com/quote/<SYMBOL>.NS/history/ via yfinance 1.7.0 (auto_adjust=False)",
     "30-Oct-2026 prices, 52-week ranges, weekly returns for beta"),
    (r"yahoo_finance/IDX_NSEI_daily\.csv", "yahoo_finance/IDX_NSEI_daily.csv", "NIFTY 50 daily data",
     "https://finance.yahoo.com/quote/%5ENSEI/history/ via yfinance", "Market returns for beta"),
    (r"(company_filings|news_and_macro|nse|stockanalysis|yahoo_finance)/_fetch_log\.txt",
     "<folder>/_fetch_log.txt", "Download logs (status codes, sizes, timestamps)", "", "Audit trail"),
    (r"README\.md", "README.md", "This index", "", ""),
]
BLOCKED = [
    ("https://in.investing.com/rates-bonds/india-10-year-bond-yield-historical-data",
     "Investing.com India 10-year yield history; HTTP 403. Trading Economics and Reuters/ETBFSI used instead."),
    ("https://au.investing.com/news/stock-market-news/asian-paints-q2-fy27-slides-169-sales-growth-margin-pressure-93CH-4726180",
     "Investing.com summary of the Q2 FY27 presentation; HTTP 403. The presentation itself is saved."),
    ("https://www.pcimag.com/articles/114243-akzo-completes-strategic-sale",
     "PCI Magazine on Akzo Nobel's India sale; HTTP 403. The ETLegalWorld report is saved instead."),
]


def write_index() -> list[str]:
    files = sorted(p.relative_to(SRC).as_posix() for p in SRC.rglob("*") if p.is_file())
    files = [f for f in files if f != "README.md"] + ["README.md"]
    uncovered = [f for f in files if not any(re.fullmatch(rx, f) for rx, *_ in INDEX)]
    sizes = {p.relative_to(SRC).as_posix(): p.stat().st_size for p in SRC.rglob("*") if p.is_file()}
    lines = [
        "# source_data: original downloads behind every number",
        "",
        f"Everything here was downloaded on {DOWNLOADED} (prices and filings up to 30-Oct-2026) by "
        "`build/fetch_sources.py`, except the `.xlsx` files, which `build/export_source_xlsx.py` builds from the raw "
        "tables so they open cleanly in Excel. `build/prepare_data.py` turns these files into the tidy inputs in "
        "`data/`. Units: Screener in Rs crore; stockanalysis.com in INR millions (forecast page in INR billions); "
        "prices in Rs.",
        "",
        "Companies (NSE symbol): Asian Paints (ASIANPAINT), Berger Paints (BERGEPAINT), Kansai Nerolac (KANSAINER), "
        "JSW Dulux (JSWDULUX, formerly Akzo Nobel India), Indigo Paints (INDIGOPNTS).",
        "",
        "| File | What it contains | Source (name + full URL) | Date downloaded | Used for |",
        "|---|---|---|---|---|",
    ]
    for rx, shown, what, src, used in INDEX:
        if rx == r"README\.md":
            continue
        n = sum(1 for f in files if re.fullmatch(rx, f))
        lines.append(f"| `{shown}` | {what} | {src} | {DOWNLOADED} | {used} |" + ("" if n else " (missing)"))
    lines += ["", "## Downloads that were blocked", "",
              "| URL | Note |", "|---|---|"]
    lines += [f"| {u} | {n} |" for u, n in BLOCKED]
    total = sum(sizes.values())
    big = max(sizes.items(), key=lambda kv: kv[1])
    lines += ["", f"Folder size: {total / 1e6:.1f} MB in {len(sizes)} files; largest file `{big[0]}` "
                  f"({big[1] / 1e6:.1f} MB).", ""]
    (SRC / "README.md").write_text("\n".join(lines), encoding="utf-8")
    return uncovered


def main() -> None:
    written = []
    for sym in NAMES:
        written.append(screener_book(sym, "consolidated"))
        if sym in STANDALONE_TOO:
            written.append(screener_book(sym, "standalone"))
        for suffix, sheets in SA_BOOKS:
            written.append(stockanalysis_book(sym, suffix, sheets))
    print(f"xlsx written: {len(written)}")
    for p in written:
        print(f"  {p.relative_to(ROOT)}  {p.stat().st_size:,} bytes")
    uncovered = write_index()
    total = sum(p.stat().st_size for p in SRC.rglob("*") if p.is_file())
    print(f"source_data total {total / 1e6:.2f} MB; files not covered by the index: {uncovered}")
    if uncovered:
        raise SystemExit("Index incomplete")
    print("INDEX OK")


if __name__ == "__main__":
    main()
