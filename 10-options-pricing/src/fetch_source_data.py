"""Save the original files behind every external number into source_data/ (internet needed).

The analysis never reads source_data/: `src/run_all.py` and the notebook use data/raw/ only.

What this script does
1. Copies the six NSE option-chain JSON snapshots and the two Yahoo Finance CSVs from data/raw/
   (downloaded on 31-Oct-2026) and checks that each copy is identical (SHA-256).
2. Writes two Excel files with a source line in row 1: the cleaned 23-Nov-2026 option chain and
   the Yahoo NIFTY 50 / India VIX daily history.
3. Downloads the exchange pages and circulars, the RBI page and the news pages with a browser
   User-Agent. A file that is already on disk is kept and not downloaded again.
4. Checks that the number or phrase used in the project appears in each saved file and writes
   source_data/download_log.csv.

News pages are copyrighted. They are kept on the author's PC and left out of GitHub by .gitignore.

Usage (from the project folder):  python src/fetch_source_data.py
"""
from __future__ import annotations

import hashlib
import html
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
SRC = ROOT / "source_data"
UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
CHAIN_URL = "https://www.nseindia.com/api/option-chain-v3?type=Indices&symbol=NIFTY&expiry={expiry}"

#: Files copied from data/raw/: (file name, target folder, source URL, phrase that must appear)
RAW_COPIES = [
    *[(f"nse_nifty_chain_{e}.json", "nse", CHAIN_URL.format(expiry=e), "23053.1")
      for e in ("03-Nov-2026", "09-Nov-2026", "17-Nov-2026", "23-Nov-2026", "01-Dec-2026", "29-Dec-2026")],
    ("IDX_NSEI.csv", "yahoo_finance", "https://finance.yahoo.com/quote/%5ENSEI/history/", "2026-10-30"),
    ("IDX_INDIAVIX.csv", "yahoo_finance", "https://finance.yahoo.com/quote/%5EINDIAVIX/history/", "2026-10-30"),
]

#: Web downloads: (folder/file, URL, phrase that must appear, local_only)
DOWNLOADS = [
    ("nse/NSE_NIFTY50_FO_contract_specifications.html", "https://www.nseindia.com/products-services/equity-derivatives-nifty50",
     "European", False),
    ("nse/NSE_circular_FAOP70616_index_lot_size_revision_Oct2025.pdf", "https://nsearchives.nseindia.com/content/circulars/FAOP70616.pdf",
     "65", False),
    ("nse/NSE_circular_FAOP74467_derivatives_close_1540_CAS_2026.pdf",
     ("https://nsearchives.nseindia.com/content/circulars/FAOP74467.pdf",  # HTTP 404 on 1-Nov-2026
      "https://www.mnclgroup.com/storage/nse-circular-ref-no-nse-faop74467.pdf"),  # the same circular, hosted by a broker
     "15:40", False),
    ("nse/NSE_FAQ_closing_auction_session_and_derivatives_changes_2026.pdf",
     "https://s3.ap-south-1.amazonaws.com/jmfswebsite/uploads/media/2026/7/31/media_1785476519030.pdf",  # NSE FAQ, copy hosted by JM Financial
     "3:40 PM", False),
    ("news_and_macro/ET_NSE_extends_FO_trading_to_340pm_May2026.html", "https://economictimes.indiatimes.com/articleshow/131404896.cms",
     "3:40", True),
    ("nse/NSE_circular_FAOP68747_expiry_day_Tuesday.pdf", "https://nsearchives.nseindia.com/content/circulars/FAOP68747.pdf",
     "Tuesday", False),
    ("nse/NIFTY50_factsheet_30Oct2026.pdf", "https://www.niftyindices.com/Factsheet/ind_nifty50.pdf", "1.42", False),
    ("news_and_macro/RBI_homepage_current_rates_TBill_cutoff_30Oct2026.html", "https://www.rbi.org.in/", "5.9337", False),
    ("news_and_macro/ET_91day_TBill_cutoff_5.93pct_28Oct2026.html",
     "https://economictimes.indiatimes.com/markets/bonds/rbi-accepts-20-bps-higher-treasury-bill-cutoff-yields-than-last-auction/articleshow/135284706.cms",
     "5.93", True),
    ("news_and_macro/CapitalMarket_Nifty_Nov2026_futures_close_30Oct2026.html",
     "https://www.capitalmarket.com/markets/news/live-news/nifty-november-futures-trade-at-a-premium/1742066", "23,101.40", True),
    ("news_and_macro/ET_NSE_clarifies_CAS_closing_auction_Aug2026.html",
     "https://economictimes.indiatimes.com/markets/stocks/news/niftys-value-doesnt-change-suddenly-at-330-pm-nse-clarifies-amid-cas-confusion/articleshow/132850802.cms",
     "3:35", True),
    ("news_and_macro/Upstox_market_holidays_November2026.html",
     "https://upstox.com/news/market-news/latest-updates/stock-market-holidays-in-november-2026-nse-bse-to-remain-closed-on-these-days-check-muhurat-trading-schedule/article-202726/",
     "24", True),
    ("news_and_macro/5paisa_index_options_cash_settled.html",
     "https://www.5paisa.com/stock-market-guide/derivatives-trading-basics/options-assignment-and-physical-settlement-in-india-what-retail-traders-must-know",
     "cash-settled", True),
]


def sha256(path: Path) -> str:
    """SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def text_of(path: Path) -> str:
    """Searchable text of a saved file: PDF text via PyMuPDF, otherwise decoded HTML/JSON/CSV with entities unescaped."""
    if path.suffix.lower() == ".pdf":
        try:
            import pymupdf  # PyMuPDF

            with pymupdf.open(path) as doc:
                raw = " ".join(page.get_text() for page in doc)
        except Exception as exc:  # noqa: BLE001 - report, do not stop
            return f"<pdf text extraction failed: {exc}>"
    else:
        raw = html.unescape(path.read_bytes().decode("utf-8", errors="ignore"))
    return re.sub(r"\s+", " ", raw)


def download(url: str, target: Path, session: requests.Session) -> tuple[str, str]:
    """Download url to target unless the file exists. Returns (status, note)."""
    if target.exists():
        return "kept", "already on disk, not downloaded again"
    try:
        if "nseindia.com" in url and "nsearchives" not in url:
            session.get("https://www.nseindia.com/", headers=UA, timeout=30)  # sets the cookies NSE expects
        r = session.get(url, headers=UA, timeout=60)
    except requests.RequestException as exc:
        return "error", type(exc).__name__
    if r.status_code != 200:
        return f"HTTP {r.status_code}", "not saved"
    if target.suffix == ".pdf" and not r.content.startswith(b"%PDF"):
        return "not a PDF", f"content-type {r.headers.get('content-type')}; not saved"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(r.content)
    return "HTTP 200", "downloaded"


def write_sheet(writer: pd.ExcelWriter, df: pd.DataFrame, sheet: str, source_line: str) -> None:
    """Write a table from row 2 with the source line in row 1, frozen header and readable widths."""
    df.to_excel(writer, sheet_name=sheet, index=False, startrow=1)
    ws = writer.sheets[sheet]
    ws["A1"] = source_line
    ws.freeze_panes = "A3"
    for i, col in enumerate(df.columns, start=1):
        width = max(len(str(col)), int(df[col].astype(str).str.len().quantile(0.9)) if len(df) else 0) + 2
        ws.column_dimensions[ws.cell(row=2, column=i).column_letter].width = min(max(width, 8), 34)


def export_chain_xlsx(target: Path) -> str:
    """Excel copy of the cleaned 23-Nov-2026 chain: an NSE-style wide sheet and a tidy sheet with the filter flags."""
    ch = pd.read_csv(ROOT / "data" / "nifty_options_2026-10-30.csv", parse_dates=["expiry", "snapshot_time"])
    g = ch[ch["expiry"] == pd.Timestamp("2026-11-23")].copy()
    src = (f"Source: NSE option chain API | {CHAIN_URL.format(expiry='23-Nov-2026')} | downloaded 31-Oct-2026 "
           "(snapshot 30-Oct-2026 15:40 IST, NIFTY 50 close 23,053.10) | prices in index points (Rs per unit; 1 lot = 65 units); "
           "bid/ask quantities in units; open interest and volume as reported by NSE (contracts); IV = NSE impliedVolatility field, % a year")
    keep = ["open_interest", "volume", "iv_nse_pct", "last", "bid_qty", "bid", "ask", "ask_qty", "usable"]
    calls = g[g["option_type"] == "C"].set_index("strike")[keep]
    puts = g[g["option_type"] == "P"].set_index("strike")[keep[::-1]]
    wide = calls.add_prefix("CE_").join(puts.add_prefix("PE_"), how="outer").reset_index()
    cols = [c for c in wide.columns if c.startswith("CE_")] + ["strike"] + [c for c in wide.columns if c.startswith("PE_")]
    wide = wide[cols]
    tidy = g.drop(columns=["snapshot_time"]).assign(expiry=g["expiry"].dt.strftime("%Y-%m-%d"))
    flags = pd.DataFrame({
        "column": ["f_band", "f_oi", "f_quotes", "f_spread", "usable"],
        "meaning": ["strike within +/-10% of the 23,053.10 close", "open interest > 0", "best bid > 0, best ask > 0 and ask >= bid",
                    "(ask - bid) / mid <= 25%", "all four filters pass; only these quotes are used for implied vols"],
    })
    with pd.ExcelWriter(target, engine="openpyxl") as w:
        write_sheet(w, wide, "Chain 23-Nov-2026 (NSE layout)", src)
        write_sheet(w, tidy, "Chain 23-Nov-2026 (tidy)", src)
        write_sheet(w, flags, "Filter flags", "Quote filters applied in src/options/market_data.py (apply_quote_filters)")
    return f"{len(g)} contracts, {int(g['usable'].sum())} usable"


def export_yahoo_xlsx(target: Path) -> str:
    """Excel copy of the two Yahoo Finance CSVs, one sheet each."""
    with pd.ExcelWriter(target, engine="openpyxl") as w:
        for fname, sheet, sym, unit in (("IDX_NSEI.csv", "NIFTY 50 (^NSEI)", "%5ENSEI", "index points"),
                                       ("IDX_INDIAVIX.csv", "India VIX (^INDIAVIX)", "%5EINDIAVIX", "volatility index, % a year")):
            df = pd.read_csv(RAW / fname)
            line = (f"Source: Yahoo Finance via yfinance (auto_adjust=False) | https://finance.yahoo.com/quote/{sym}/history/ | "
                    f"downloaded 31-Oct-2026 | daily, {df['Date'].iloc[0]} to {df['Date'].iloc[-1]} | {unit}")
            write_sheet(w, df, sheet, line)
    return "2 sheets"


def main() -> int:
    """Build source_data/ and the download log; return 1 if a published file failed its phrase check."""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    log = []
    for fname, folder, url, phrase in RAW_COPIES:
        src, dst = RAW / fname, SRC / folder / fname
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        same = sha256(src) == sha256(dst)
        log.append({"file": f"{folder}/{fname}", "url": url, "status": "copied from data/raw", "bytes": dst.stat().st_size,
                    "sha256": sha256(dst), "phrase": phrase, "phrase_found": phrase in text_of(dst),
                    "local_only": False, "note": "identical to data/raw copy" if same else "MISMATCH with data/raw copy"})
    for target, fn, what in (("nse/NIFTY_option_chain_23-Nov-2026_cleaned.xlsx", export_chain_xlsx, "23,053.10"),
                             ("yahoo_finance/Yahoo_Finance_NIFTY50_IndiaVIX_daily_2021-10-01_to_2026-10-30.xlsx", export_yahoo_xlsx, "Yahoo")):
        path = SRC / target
        note = fn(path)
        log.append({"file": target, "url": "built by src/fetch_source_data.py", "status": "written", "bytes": path.stat().st_size,
                    "sha256": sha256(path), "phrase": what, "phrase_found": True, "local_only": False, "note": note})
    session = requests.Session()
    for target, urls, phrase, local_only in DOWNLOADS:
        path = SRC / target
        tried = []
        for url in (urls,) if isinstance(urls, str) else urls:
            status, note = download(url, path, session)
            tried.append(f"{url} -> {status}")
            if path.exists():
                break
        if len(tried) > 1:
            note = f"{note}; tried: " + " | ".join(tried)
        found = phrase in text_of(path) if path.exists() else False
        log.append({"file": target, "url": url, "status": status, "bytes": path.stat().st_size if path.exists() else 0,
                    "sha256": sha256(path) if path.exists() else "", "phrase": phrase, "phrase_found": found,
                    "local_only": local_only, "note": note})
        time.sleep(1.0)
    df = pd.DataFrame(log)
    df.insert(0, "checked_at", stamp)
    df.to_csv(SRC / "download_log.csv", index=False)
    print(df[["file", "status", "bytes", "phrase", "phrase_found", "note"]].to_string(index=False))
    bad = df[(~df["local_only"]) & (df["bytes"] > 0) & (~df["phrase_found"])]
    return 1 if len(bad) else 0


if __name__ == "__main__":
    sys.exit(main())
