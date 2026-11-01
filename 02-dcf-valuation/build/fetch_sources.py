"""Save the web sources behind Project 2 into source_data/ (needs internet; the model itself does not).

What it saves (1-Nov-2026 run):
  stockanalysis/raw/*.html        the five StockAnalysis.com pages the model's inputs came from, as they are today
  company_filings/                TCS investor-relations page; checks that the author's TCS PDFs are the files
                                  published at the tcs.com links (SHA-256 comparison)
  yahoo_finance/                  TCS.NS daily prices, Sep-Oct 2026
  news_and_macro/*.html           macro and news pages cited by the model (copyrighted: kept local, see .gitignore)
  download_log.csv                one row per download: URL, HTTP status, bytes, SHA-256, phrase check

The author's own downloads of 23-Oct-2026 (stockanalysis/exports/*.xlsx and company_filings/*.pdf) are the
files the workbook was built from. This script does not change them.

Usage:  python build/fetch_sources.py [--force]
"""
from __future__ import annotations

import csv
import hashlib
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests

ROOT = Path(__file__).resolve().parents[1]
SD = ROOT / "source_data"
CACHE = ROOT / "build" / "_cache"
FORCE = "--force" in sys.argv
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/130.0 Safari/537.36",
      "Accept-Language": "en-IN,en;q=0.9"}

PAGES = [
    # (relative path, URL, phrase that must appear, local_only)
    ("stockanalysis/raw/TCS_income_statement_annual.html",
     "https://stockanalysis.com/quote/nse/TCS/financials/", "2,670,210", False),
    ("stockanalysis/raw/TCS_balance_sheet_annual.html",
     "https://stockanalysis.com/quote/nse/TCS/financials/balance-sheet/", "Lease", False),
    ("stockanalysis/raw/TCS_cash_flow_statement_annual.html",
     "https://stockanalysis.com/quote/nse/TCS/financials/cash-flow-statement/", "-42,240", False),
    ("stockanalysis/raw/TCS_statistics.html",
     "https://stockanalysis.com/quote/nse/TCS/statistics/", "Beta", False),
    ("stockanalysis/raw/TCS_forecast.html",
     "https://stockanalysis.com/quote/nse/TCS/forecast/", "Price Target", False),
    ("company_filings/TCS_IR_financial_statements_page.html",
     "https://www.tcs.com/investor-relations/financial-statements", "Fact Sheet", False),
    # macro inputs and news (copyrighted third-party pages: saved locally, not published)
    ("news_and_macro/TradingEconomics_India_10Y_yield_news_28Sep2026.html",
     "https://tradingeconomics.com/india/government-bond-yield/news/587153", "India", True),
    ("news_and_macro/Damodaran_country_risk_premiums_Jan2026.html",
     "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ctryprem.html", "India", True),
    ("news_and_macro/BVWire_Damodaran_2026_data_update.html",
     "https://bvresources.com/articles/bvwire/damodaran-posts-his-first-data-update-for-2026", "Damodaran", True),
    ("news_and_macro/FreePressJournal_TCS_Q2FY27_8Oct2026.html",
     "https://www.freepressjournal.in/business/tcs-net-profit-up-025-to-13884-crore-in-q2-fy27-revenue-rises-to-73188-crore",
     "TCS", True),
    ("news_and_macro/BusinessToday_TCS_Q2FY27_8Oct2026.html",
     "https://www.businesstoday.in/markets/stocks/story/tcs-q2-fy27-results-net-profit-rises-15-to-rs-13934-crore-declares-rs-12-dividend-560435-2026-10-08",
     "TCS", True),
    ("news_and_macro/FreePressJournal_TCS_Q1FY27_9Jul2026.html",
     "https://www.freepressjournal.in/business/tcs-reports-14-revenue-growth-in-q1-fy27-net-profit-rises-47-to-13420-crore-despite-legal-settlement-charge",
     "TCS", True),
    ("news_and_macro/AngelOne_TCS_Q2FY27_H1_total.html",
     "https://www.angelone.in/news/stocks/tcs-share-price-in-focus-after-q2-fy27-earnings-results-total-income-up-11-8-yoy",
     "TCS", True),
    ("news_and_macro/Upstox_TCS_Q2FY27_TCV_8Oct2026.html",
     "https://upstox.com/news/market-news/earnings/tcs-q2-results-net-profit-rises-15-to-13-884-crore-revenue-jumps-11-yo-y-tcv-rises-to-9-6-billion/article-201534/",
     "TCS", True),
]

# The author's TCS PDFs and the tcs.com links given in the PDF report's source table
USER_PDFS = [
    ("company_filings/TCS_Q2FY27_Fact_Sheet_8Oct2026.pdf",
     "https://www.tcs.com/content/dam/tcs/investor-relations/financial-statements/2026-27/q2/Presentations/Q2%202026-27%20Fact%20Sheet.pdf"),
    ("company_filings/TCS_Q1FY27_Press_Release_INR_9Jul2026.pdf",
     "https://www.tcs.com/content/dam/tcs/investor-relations/financial-statements/2026-27/q1/IND%20AS/Press%20Release%20-%20INR.pdf"),
]

log_rows: list[dict] = []


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def get(url: str, timeout: int = 90):
    for attempt in range(1, 4):
        try:
            return requests.get(url, headers=UA, timeout=timeout)
        except requests.RequestException as e:
            print(f"  attempt {attempt} failed for {url}: {type(e).__name__}: {e}")
            time.sleep(3 * attempt)
    return None


def log(rel, url, status, data, phrase, found, local_only, note=""):
    log_rows.append({
        "file": rel, "url": url, "http_status": status, "bytes": len(data) if data else 0,
        "sha256": sha(data) if data else "", "phrase_checked": phrase, "phrase_found": found,
        "local_only": local_only, "downloaded": time.strftime("%Y-%m-%d"), "note": note,
    })


def fetch_pages():
    for rel, url, phrase, local_only in PAGES:
        path = SD / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not FORCE:
            data = path.read_bytes()
            log(rel, url, "cached", data, phrase, phrase.encode() in data, local_only)
            continue
        r = get(url)
        if r is None or r.status_code != 200 or len(r.content) < 2000:
            log(rel, url, getattr(r, "status_code", "error"), None, phrase, False, local_only,
                "blocked or empty; link kept in source_data/README.md")
            continue
        path.write_bytes(r.content)
        log(rel, url, r.status_code, r.content, phrase, phrase.encode() in r.content, local_only)
        time.sleep(2)


def verify_user_pdfs():
    """Download each tcs.com link and compare it with the author's copy (same SHA-256 = same file)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    for rel, url in USER_PDFS:
        mine = (SD / rel).read_bytes()
        r = get(url, timeout=120)
        if r is None or r.status_code != 200 or not r.content.startswith(b"%PDF"):
            log(rel, url, getattr(r, "status_code", "error"), mine, "same SHA-256 as the link", False, False,
                "could not download the link to compare")
            continue
        same = sha(r.content) == sha(mine)
        (CACHE / Path(rel).name).write_bytes(r.content)
        log(rel, url, r.status_code, mine, "same SHA-256 as the link", same, False,
            "identical to the file at the link" if same else
            f"differs from the link ({len(r.content)} bytes there vs {len(mine)} here)")


def find_transcript_link():
    """Look for the Q1 FY2027 call transcript on the saved IR page and compare it with the author's copy."""
    rel = "company_filings/TCS_Q1FY27_Earnings_Call_Transcript_9Jul2026.pdf"
    page = SD / "company_filings" / "TCS_IR_financial_statements_page.html"
    if not page.exists():
        return
    html = page.read_text(encoding="utf-8", errors="replace")
    links = sorted(set(re.findall(r'href="([^"]+\.pdf)"', html, flags=re.I)))
    (CACHE / "tcs_ir_pdf_links.txt").write_text("\n".join(links), encoding="utf-8")
    cands = [l for l in links if "2026-27" in l and "q1" in l.lower() and "transcript" in l.lower()]
    mine = (SD / rel).read_bytes()
    for c in cands:
        url = urljoin("https://www.tcs.com/", c)
        r = get(url, timeout=120)
        if r is not None and r.status_code == 200 and r.content.startswith(b"%PDF"):
            same = sha(r.content) == sha(mine)
            log(rel, url, r.status_code, mine, "same SHA-256 as the link", same, False,
                "identical to the file at the link" if same else "differs from the file at the link")
            return
    log(rel, "", "not found", mine, "transcript link on the IR page", False, False,
        f"{len(cands)} candidate links on the saved IR page; see build/_cache/tcs_ir_pdf_links.txt")


def fetch_prices():
    import yfinance as yf
    rel = "yahoo_finance/TCS_NS_daily_2026-09-01_to_2026-10-30.csv"
    path = SD / rel
    if path.exists() and not FORCE:
        log(rel, "yfinance TCS.NS", "cached", path.read_bytes(), "2026-10-19", b"2026-10-19" in path.read_bytes(), False)
        return
    df = yf.download("TCS.NS", start="2026-09-01", end="2026-10-31", auto_adjust=False, progress=False)
    if df is None or df.empty:
        log(rel, "yfinance TCS.NS", "empty", None, "2026-10-19", False, False)
        return
    if hasattr(df.columns, "levels"):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df.index.name = "Date"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.round(4).to_csv(path)
    data = path.read_bytes()
    log(rel, "https://finance.yahoo.com/quote/TCS.NS/history (via yfinance)", 200, data, "2026-10-19",
        b"2026-10-19" in data, False)


if __name__ == "__main__":
    fetch_pages()
    verify_user_pdfs()
    find_transcript_link()
    fetch_prices()
    with open(SD / "download_log.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(log_rows[0].keys()))
        w.writeheader()
        w.writerows(log_rows)
    bad = [r for r in log_rows if not r["phrase_found"]]
    print(f"{len(log_rows)} rows logged; {len(bad)} without the expected phrase or failed")
    for r in bad:
        print("  CHECK:", r["file"], r["http_status"], r["note"])
