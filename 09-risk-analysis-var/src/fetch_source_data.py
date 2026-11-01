"""Save the original source files behind every external number into source_data/.

Run from the project folder (internet needed; the analysis itself never reads source_data/):
    python src/fetch_source_data.py            # skip files that already exist
    python src/fetch_source_data.py --force    # download everything again

What it does
1. yahoo_finance/: untouched copies of the yfinance downloads in data/raw/ and the download log,
   USD/INR (INR=X, same yfinance parameters), and one Excel workbook with a sheet per ticker
   (row 1 = source line, table from row 2).
2. nse/: copies of the bhavcopy extract and request log from data/raw/, an Excel copy of the
   extract, and the original zipped bhavcopy files for seven key dates.
3. company_filings/, regulators/, news_and_macro/: each document is downloaded with a browser
   User-Agent and the phrase or number quoted in this project is checked in the saved text. If a
   site blocks the download, or the phrase is missing, a .md note with the link and the fact used
   is written instead.
4. download_log.csv: file, URL, HTTP status, bytes, SHA-256, phrase and whether it was found.
News articles are saved for the author's PC only; .gitignore keeps them out of the public repository.
"""
from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import re
import shutil
import sys
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import config as cfg  # noqa: E402

SRC_DIR = ROOT / "source_data"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/130.0 Safari/537.36")
NIPPON = "https://mf.nipponindiaim.com/FundsAndPerformance/ProductNotes/"
SBI_FS = "https://www.sbimf.com/campaign/efactsheet/efactsheet-{m}-2026/passive-fund-factsheet/fixed-income/nifty-10-yr-benchmark-g-sec-etf.html"
# Original NSE bhavcopy files kept as evidence (the extract in data/raw/ covers 76 dates)
BHAVCOPY_DATES = {
    "2026-10-30": "valuation date: closes of all six ETFs",
    "2026-03-23": "worst portfolio day in the window",
    "2026-02-01": "Sunday Union Budget session that Yahoo omits",
    "2025-10-24": "session missing on Yahoo for five ETFs; MON100 bad print (Yahoo 217.32 vs NSE 241.80)",
    "2025-03-18": "zero-volume Yahoo rows with wrong prices for all six ETFs",
    "2024-06-04": "election-results day: NIFTYBEES close 250.48 (-2.97%) while NIFTY 50 fell 5.93%",
    "2023-11-12": "Sunday Diwali Muhurat session that Yahoo omits (older bhavcopy format)",
}


@dataclass(frozen=True)
class Doc:
    """One source document: where to save it, candidate URLs and the phrase that must appear."""

    folder: str
    name: str            # file name without extension
    urls: tuple[str, ...]
    phrase: str
    fact: str            # the fact used in the project (kept in the .md note if the download fails)
    used_for: str
    kind: str = "html"   # "html" or "pdf"
    local_only: bool = False


DOCS: tuple[Doc, ...] = (
    # ------------------------------------------------------------------ fund-house documents (published)
    Doc("company_filings", "Nippon_India_ETF_Nifty_50_BeES_product_note",
        (NIPPON + "NipponIndia-ETF-Nifty-50-BeES-Apr-2026.pdf", NIPPON + "NipponIndia-ETF-Nifty-BeES.pdf"),
        "Nifty 50", "Nippon India ETF Nifty 50 BeES is an open-ended index ETF investing in the NIFTY 50 stocks.",
        "What NIFTYBEES holds (30% of the portfolio)", "pdf"),
    Doc("company_filings", "Nippon_India_ETF_Nifty_Next_50_Junior_BeES_product_note",
        (NIPPON + "NipponIndia-ETF-Nifty-Next-50-Junior-BeES-May-2026.pdf",
         NIPPON + "NipponIndia-ETF-Nifty-Next-50-Junior-BeES-January-2026.pdf", NIPPON + "NipponIndia-ETF-Junior-BeES.PDF"),
        "Next 50", "Nippon India ETF Nifty Next 50 Junior BeES invests in the NIFTY Next 50 stocks.",
        "What JUNIORBEES holds (10%)", "pdf"),
    Doc("company_filings", "Nippon_India_ETF_Nifty_Bank_BeES_product_note",
        (NIPPON + "NipponIndia-ETF-Nifty-Bank-BeES-Aug-2026.pdf", NIPPON + "NipponIndia-ETF-Bank-BeES.pdf"),
        "Bank", "Nippon India ETF Nifty Bank BeES invests in the NIFTY Bank index stocks.",
        "What BANKBEES holds (10%)", "pdf"),
    Doc("company_filings", "Nippon_India_ETF_Gold_BeES_product_note",
        (NIPPON + "NipponIndia-ETF-Gold-BeES-August-2025.pdf", NIPPON + "NipponIndia-ETF-Gold-BeES.pdf"),
        "physical gold", "Nippon India ETF Gold BeES invests in physical gold; benchmark: domestic price of gold.",
        "What GOLDBEES holds (15%)", "pdf"),
    Doc("company_filings", "Motilal_Oswal_Nasdaq_100_ETF_SID_May2026",
        ("https://www.motilaloswalmf.com/content/dam/motilal-mf/downloads/mf/sid/2026/may/SID_Motilal%20Oswal%20Nasdaq%20100%20ETF.pdf",),
        "nasdaq", "Motilal Oswal Nasdaq 100 ETF tracks the Nasdaq-100 index; its rupee NAV moves with USD/INR.",
        "What MON100 holds (10%) and why it carries currency risk", "pdf"),
    Doc("company_filings", "SBI_Nifty_10yr_Benchmark_GSec_ETF_factsheet",
        tuple(SBI_FS.format(m=m) for m in ("oct", "sep", "aug", "jul")),
        "Benchmark G-Sec", "SBI Nifty 10 yr Benchmark G-Sec ETF tracks the NIFTY 10 yr Benchmark G-Sec index.",
        "What SETF10GILT holds (25%); modified duration for the bond-shock scenario"),
    # ------------------------------------------------------------------ regulators (published)
    Doc("regulators", "BIS_BCBS22_backtesting_framework_Jan1996",
        ("https://www.bis.org/publ/bcbs22.pdf",), "yellow zone",
        "Basel traffic light for 99% VaR over 250 days: green 0-4 exceptions, yellow 5-9, red 10 or more.",
        "Basel traffic-light zones in the backtest", "pdf"),
    Doc("regulators", "BIS_BCBS22_publication_page",
        ("https://www.bis.org/publ/bcbs22.htm",), "backtesting",
        "BIS page of the 1996 backtesting framework: compares actual trading results with model risk measures.",
        "Basel traffic light (publication page; the PDF is linked from it)"),
    Doc("news_and_macro", "RBI_homepage_current_rates_TBill",
        ("https://www.rbi.org.in/",), "5.9337",
        "RBI Current Rates panel: 91-day T-bill cut-off yield 5.9337% (auction of 28-Oct-2026).",
        "Risk-free rate used to judge the zero-mean assumption"),
    # ------------------------------------------------------------------ news (local only: copyrighted)
    Doc("news_and_macro", "ET_91day_TBill_cutoff_5.93pct_28Oct2026",
        ("https://economictimes.indiatimes.com/markets/bonds/rbi-accepts-20-bps-higher-treasury-bill-cutoff-yields-than-last-auction/articleshow/135284706.cms",),
        "5.93", "91-day T-bill cut-off yield 5.93% at the RBI auction of 28-Oct-2026.",
        "Risk-free rate (second source)", local_only=True),
    Doc("news_and_macro", "Livemint_market_crash_US_Iran_war_23Mar2026",
        ("https://livemint.com/market/stock-market-news/stock-market-live-gold-silver-rate-today-23-march-2026-nifty-sensex-crude-oil-us-iran-war-11774231309874.html",),
        "22,512", "23-Mar-2026: NIFTY 50 fell 602 points (2.6%) to 22,512.65; gold and silver fell about 10%.",
        "Stress test: worst day (23-Mar-2026)", local_only=True),
    Doc("news_and_macro", "FinancialExpress_Nifty_8month_low_23Mar2026",
        ("https://financialexpress.com/market/why-did-markets-fall-today-nifty-closes-at-8-month-lows-sensex-slides-1800-points-5-key-reasons-explained-4181369/",),
        "105", "23-Mar-2026: crude oil above $105 and West Asia tensions; NIFTY 50 at an 8-month low.",
        "Stress test: worst day (23-Mar-2026)", local_only=True),
    Doc("news_and_macro", "Livemint_HDFC_Bank_shock_West_Asia_19Mar2026",
        ("https://www.livemint.com/market/stock-market-news/stock-market-rout-deepens-as-hdfc-bank-shock-meets-west-asia-turmoil-11773900435554.html",),
        "23,002", "19-Mar-2026: NIFTY 50 fell 3.3% to 23,002.15, its worst day since the 5.9% fall of 4-Jun-2024.",
        "Stress test: 19-Mar-2026", local_only=True),
    Doc("news_and_macro", "CNBCTV18_Nifty_biggest_fall_in_21_months_19Mar2026",
        ("https://www.cnbctv18.com/market/stock-market-crash-nifty-50-sell-off-key-triggers-market-cap-erosion-oil-hdfc-bank-it-stocks-52-week-low-shares-ws-e-19871727.htm",),
        "Atanu Chakraborty", "19-Mar-2026: biggest one-day NIFTY fall in 21 months; HDFC Bank's part-time chairman "
        "Atanu Chakraborty had resigned.", "Stress test: 19-Mar-2026", local_only=True),
    Doc("news_and_macro", "TimesofIndia_tariff_selloff_7Apr2025",
        ("https://timesofindia.indiatimes.com/business/international-business/global-stock-markets-tumble-amid-tariff-war-japan-china-and-india-hit-hard-10-things-to-know/articleshow/120051763.cms",),
        "22,161", "7-Apr-2025: NIFTY 50 fell 743 points (3.24%) to 22,161.60 amid the tariff war.",
        "Stress test: 7-Apr-2025", local_only=True),
    Doc("news_and_macro", "TheHindu_Russia_Ukraine_crash_24Feb2022",
        ("https://www.thehindu.com/business/markets/russia-ukraine-crisis-sensex-nifty-tank-over-47-in-line-with-global-meltdown/article65080368.ece",),
        "16,247.95", "24-Feb-2022: NIFTY 50 fell 815.30 points (4.78%) to 16,247.95 as Russia invaded Ukraine.",
        "Stress test: 24-Feb-2022", local_only=True),
    Doc("news_and_macro", "TimesofIndia_Russia_Ukraine_crash_24Feb2022",
        ("https://timesofindia.indiatimes.com/business/markets/sensex/russia-ukraine-crisis-spooks-markets-sensex-crashes-2702-points-nifty-ends-below-16300/articleshow/89799030.cms",),
        "4.78", "24-Feb-2022: NIFTY 50 fell 4.78% to 16,248.", "Stress test: 24-Feb-2022 (second source)",
        local_only=True),
    Doc("news_and_macro", "TheHindu_Budget_day_STT_1Feb2026",
        ("https://www.thehindu.com/business/markets/stock-markets-sensex-nifty-budget-day-february-1-2026/article70576763.ece",),
        "24,825.45", "1-Feb-2026 (Sunday special session): NIFTY 50 fell 1.96% to 24,825.45 after the Budget raised "
        "STT on derivatives.", "Stress test and calendar check: 1-Feb-2026", local_only=True),
    Doc("news_and_macro", "ET_Budget_day_crash_STT_1Feb2026",
        ("https://economictimes.com/markets/stocks/news/rs-10-lakh-crore-wiped-out-sensex-down-1900-points-nifty-below-24600-why-did-the-stock-market-crash-after-budget-key-factors/articleshow/127836069.cms",),
        "securities transaction tax", "1-Feb-2026: markets fell in the Sunday special session after the STT hike on "
        "futures and options.", "Stress test: 1-Feb-2026 (second source)", local_only=True),
    Doc("news_and_macro", "ET_gold_silver_ETF_crash_30Jan2026",
        ("https://economictimes.com/markets/stocks/news/explained-why-gold-silver-etfs-crashed-up-to-14-and-should-you-buy-the-dip/articleshow/127791282.cms",),
        "Nippon India Gold ETF", "30-Jan-2026: Nippon India Gold ETF fell about 11% in the precious-metals crash.",
        "Jump screen: GOLDBEES -10.5% on 30-Jan-2026 is genuine", local_only=True),
    Doc("news_and_macro", "TheHindu_election_results_crash_4Jun2024",
        ("https://www.thehindu.com/business/markets/sensex-plunges-57-as-bjp-fails-to-win-majority-on-its-own/article68251438.ece",),
        "21,884", "4-Jun-2024: NIFTY 50 fell 5.93% to 21,884.50 on general election results day.",
        "ETF price vs index check (NIFTYBEES -2.97%)", local_only=True),
    Doc("news_and_macro", "Livemint_market_holiday_15Jan2026",
        ("https://www.livemint.com/market/stock-market-news/stock-market-holiday-bse-nse-to-remain-shut-for-maharashtra-municipal-elections-commodity-trading-to-begin-at-5-pm-11768439343202.html",),
        "Maharashtra", "15-Jan-2026: BSE and NSE closed for the Maharashtra municipal elections.",
        "Calendar check: Yahoo placeholder row dropped", local_only=True),
)


# ============================================================================ helpers
def sha256(path: Path) -> str:
    """SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def text_of(path: Path) -> str:
    """Plain text of a saved PDF (PyMuPDF) or HTML page (entities decoded, spaces collapsed)."""
    if path.suffix.lower() == ".pdf":
        import pymupdf  # PyMuPDF

        with pymupdf.open(path) as doc:
            raw = " ".join(page.get_text() for page in doc)
    else:
        raw = html.unescape(path.read_bytes().decode("utf-8", errors="replace"))
    return re.sub(r"\s+", " ", raw)


def download(url: str, target: Path, kind: str) -> tuple[int, str]:
    """GET `url` with a browser User-Agent and save it to `target`. Returns (HTTP status, error text)."""
    import requests

    headers = {"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9",
               "Accept": "application/pdf,text/html,application/xhtml+xml,*/*;q=0.8"}
    if "bis.org" in url:
        headers["Referer"] = "https://www.bis.org/publ/bcbs22.htm"
    try:
        r = requests.get(url, headers=headers, timeout=60, allow_redirects=True)
    except Exception as exc:  # noqa: BLE001
        return 0, f"{type(exc).__name__}: {exc}"[:200]
    if r.status_code != 200:
        return r.status_code, f"HTTP {r.status_code}"
    body = r.content
    if kind == "pdf" and not body.startswith(b"%PDF"):
        return r.status_code, "response is not a PDF"
    if kind == "html" and len(body) < 2000:
        return r.status_code, "response too small to be the page"
    target.write_bytes(body)
    return r.status_code, ""


def note_md(doc: Doc, path: Path, status: str, today: str) -> None:
    """Write a short note for a source that could not be saved."""
    lines = [f"# {doc.name}", "", "- Links tried: " + "; ".join(doc.urls), f"- Date tried: {today}",
             f"- Result: {status}", f"- Fact used in this project: {doc.fact}", f"- Used for: {doc.used_for}"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def log_row(path: Path, url: str, status: str, phrase: str = "", found: object = "", saved_on: str = "") -> dict:
    return {"file": path.relative_to(SRC_DIR).as_posix(), "url": url, "status": status,
            "bytes": path.stat().st_size, "sha256": sha256(path), "phrase": phrase, "phrase_found": found,
            "saved_on": saved_on}


# ============================================================================ steps
def copy_yahoo(today: str, force: bool) -> list[dict]:
    """Copy the raw yfinance files, add USD/INR, and build the Excel export. Returns log rows."""
    import pandas as pd

    out = SRC_DIR / "yahoo_finance"
    out.mkdir(parents=True, exist_ok=True)
    log = json.loads((cfg.RAW / "download_log.json").read_text(encoding="utf-8"))
    stamp = log["downloaded_at"]
    rows = []
    for f in sorted(cfg.RAW.glob("yahoo_*.csv")) + [cfg.RAW / "download_log.json"]:
        dst = out / f.name
        shutil.copy2(f, dst)
        rows.append(log_row(dst, "copy of data/raw/" + f.name, "copied", saved_on=stamp[:10]))
    fx = out / "yahoo_INR_X.csv"
    if force or not fx.exists():
        import yfinance as yf

        df = yf.download("INR=X", start=cfg.YF_START, end=cfg.YF_END_EXCLUSIVE, auto_adjust=False,
                         progress=False, actions=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.index = pd.DatetimeIndex(df.index).tz_localize(None).normalize()
        df.index.name = "Date"
        df.to_csv(fx)
    usdinr = pd.read_csv(fx, index_col=0, parse_dates=True)["Close"]
    last = float(usdinr.loc[cfg.VALUATION_DATE])
    rows.append(log_row(fx, "yfinance INR=X, same parameters as data/raw", "downloaded", f"{last:.2f}",
                        f"{last:.2f}" == "95.15", stamp[:10]))

    xlsx = out / "Yahoo_Finance_daily_prices_ETFs_2021-10-01_to_2026-10-30.xlsx"
    names = log.get("names", {})
    with pd.ExcelWriter(xlsx, engine="xlsxwriter", datetime_format="dd-mmm-yyyy", date_format="dd-mmm-yyyy") as xw:
        index = []
        for f in sorted(out.glob("yahoo_*.csv")):
            ticker = f.stem.replace("yahoo_", "").replace("IDX_", "^").replace("INR_X", "INR=X")
            df = pd.read_csv(f, index_col=0, parse_dates=True)
            sheet = ticker.replace("^", "").replace(".NS", "").replace("=", "_")[:31]
            unit = ("index points" if ticker.startswith("^") else "INR per US dollar" if ticker == "INR=X"
                    else "INR per ETF unit")
            line = (f"Source: Yahoo Finance via yfinance {log['yfinance_version']} | "
                    f"https://finance.yahoo.com/quote/{ticker}/history/ | downloaded {stamp} | "
                    f"prices in {unit}, Volume in units traded; auto_adjust=False")
            df.to_excel(xw, sheet_name=sheet, startrow=1)
            ws = xw.sheets[sheet]
            ws.write(0, 0, line)
            ws.set_column(0, 0, 12, xw.book.add_format({"num_format": "dd-mmm-yyyy"}))
            ws.set_column(1, len(df.columns), 13, xw.book.add_format({"num_format": "#,##0.0000"}))
            ws.freeze_panes(2, 1)
            index.append({"sheet": sheet, "ticker": ticker, "name": names.get(ticker, ""), "rows": len(df),
                          "first date": df.index.min().date(), "last date": df.index.max().date(),
                          "used for": ("portfolio ETF" if ticker in cfg.TICKERS else
                                       "bond ETF candidate (screen only)" if ticker in cfg.BOND_CANDIDATES else
                                       "NSE trading calendar and index check" if ticker == "^NSEI" else
                                       "USD/INR level for the currency shock")})
        pd.DataFrame(index).to_excel(xw, sheet_name="Index", startrow=1, index=False)
        ws = xw.sheets["Index"]
        ws.write(0, 0, f"Source: Yahoo Finance via yfinance {log['yfinance_version']} | https://finance.yahoo.com | "
                       f"downloaded {stamp} | one sheet per ticker, copied unchanged from the CSV files")
        ws.set_column(0, 6, 18)
        xw.book.worksheets_objs.sort(key=lambda s: s.name != "Index")
    rows.append(log_row(xlsx, "built from the yahoo_*.csv files", "built", saved_on=today))
    return rows


def nse_files(today: str, force: bool) -> list[dict]:
    """Copy the NSE extract and request log, build an Excel copy, save original bhavcopy zips."""
    import pandas as pd

    from src import fetch_data as fd

    out = SRC_DIR / "nse"
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for name in ("nse_bhavcopy_etf_closes.csv", "nse_requests_log.csv"):
        dst = out / name
        shutil.copy2(cfg.RAW / name, dst)
        rows.append(log_row(dst, "copy of data/raw/" + name, "copied", saved_on="2026-10-31 / 2026-11-01"))
    ext = pd.read_csv(cfg.NSE_FILE)
    req = pd.read_csv(cfg.RAW / "nse_requests_log.csv", dtype={"status": str})
    xlsx = out / "NSE_bhavcopy_ETF_closes_extract.xlsx"
    with pd.ExcelWriter(xlsx, engine="xlsxwriter") as xw:
        for sheet, df, line in [
            ("closes", ext, "Source: NSE capital-market bhavcopy | https://nsearchives.nseindia.com/content/cm/"
                            "BhavCopy_NSE_CM_0_0_0_<YYYYMMDD>_F_0000.csv.zip (before 2024: /content/historical/EQUITIES/"
                            "<YYYY>/<MON>/cm<DD><MON><YYYY>bhav.csv.zip) | downloaded 31-Oct-2026 and 1-Nov-2026 | "
                            "close and prev_close in INR per ETF unit, volume in units, traded value in INR; "
                            "rows for the six portfolio ETFs only"),
            ("requests", req, "Every bhavcopy file requested: 404 = no file because the exchange was closed")]:
            df.to_excel(xw, sheet_name=sheet, startrow=1, index=False)
            ws = xw.sheets[sheet]
            ws.write(0, 0, line)
            ws.set_column(0, len(df.columns), 14)
            ws.freeze_panes(2, 0)
    rows.append(log_row(xlsx, "built from the two CSV files", "built", saved_on=today))

    session = None
    for day, why in BHAVCOPY_DATES.items():
        d = pd.Timestamp(day)
        urls = fd.bhavcopy_urls(d)
        existing = [(u, out / u.rsplit("/", 1)[-1]) for u in urls if (out / u.rsplit("/", 1)[-1]).exists()]
        if existing and not force:
            url, target = existing[0]
            z = zipfile.ZipFile(target)
            rows.append(log_row(target, url, "exists", "NIFTYBEES", b"NIFTYBEES" in z.read(z.namelist()[0]), today))
            continue
        if session is None:
            session = fd.nse_session()
        saved = None
        for url in urls:
            try:
                r = session.get(url, timeout=40)
            except Exception:  # noqa: BLE001
                continue
            if r.status_code == 200 and r.content[:2] == b"PK":
                target = out / url.rsplit("/", 1)[-1]
                target.write_bytes(r.content)
                z = zipfile.ZipFile(io.BytesIO(r.content))
                found = b"NIFTYBEES" in z.read(z.namelist()[0])
                saved = log_row(target, url, "200", "NIFTYBEES", found, today)
                break
            time.sleep(1.0)
        if saved is None:
            note = out / f"bhavcopy_{d:%Y%m%d}.md"
            note.write_text(f"# NSE bhavcopy {day}\n\n- Links tried: {'; '.join(urls)}\n"
                            f"- Result: download failed on {today}\n- Why it matters: {why}\n", encoding="utf-8")
            saved = log_row(note, urls[0], "note only", saved_on=today)
        rows.append(saved)
        print(f"{saved['status']:10s} {saved['file']}")
        time.sleep(0.5)
    return rows


def fetch_docs(force: bool, today: str) -> list[dict]:
    """Download every document in DOCS (skipping existing files unless `force`). Returns log rows."""
    previous = {r["file"]: r for r in read_log()}
    rows = []
    for doc in DOCS:
        folder = SRC_DIR / doc.folder
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / (doc.name + (".pdf" if doc.kind == "pdf" else ".html"))
        note = folder / (doc.name + ".md")
        status, used_url, err = "exists", "", ""
        if force or not target.exists():
            status = "failed"
            for url in doc.urls:
                code, err = download(url, target, doc.kind)
                if code == 200 and not err:
                    if doc.phrase.lower() in text_of(target).lower():
                        status, used_url = "200", url
                        break
                    err = f"phrase '{doc.phrase}' not found"
                    target.unlink(missing_ok=True)
                else:
                    target.unlink(missing_ok=True)
                time.sleep(1.0)
        else:
            used_url = previous.get(target.relative_to(SRC_DIR).as_posix(), {}).get("url", doc.urls[0])
        if target.exists():
            note.unlink(missing_ok=True)
            found = doc.phrase.lower() in text_of(target).lower()
            rows.append(log_row(target, used_url, status, doc.phrase, found, today))
        else:
            note_md(doc, note, err or "download failed", today)
            rows.append(log_row(note, doc.urls[0], f"note only ({err})", doc.phrase, "", today))
        rows[-1]["local_only"] = doc.local_only
        print(f"{rows[-1]['status'][:40]:40s} {rows[-1]['file']}")
    return rows


def read_log() -> list[dict]:
    """Previous download log (to keep the URL actually used for files that are not downloaded again)."""
    p = SRC_DIR / "download_log.csv"
    if not p.exists():
        return []
    with p.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> None:
    """Build source_data/ and write download_log.csv."""
    force = "--force" in sys.argv
    today = datetime.now().strftime("%Y-%m-%d")
    SRC_DIR.mkdir(exist_ok=True)
    rows = copy_yahoo(today, force) + nse_files(today, force) + fetch_docs(force, today)
    fields = ["file", "url", "status", "bytes", "sha256", "phrase", "phrase_found", "saved_on", "local_only"]
    with (SRC_DIR / "download_log.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, False if k == "local_only" else "") for k in fields})
    total = sum(p.stat().st_size for p in SRC_DIR.rglob("*") if p.is_file())
    print(f"{len(rows)} entries; source_data/ total {total / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
