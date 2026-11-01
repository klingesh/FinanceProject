"""Save the original source files behind every external number into source_data/.

Run from the project folder (internet needed; the analysis itself does not use this folder):
    python src/fetch_source_data.py            # skip files that already exist
    python src/fetch_source_data.py --force    # download everything again

What it does
1. yahoo_finance/: untouched copies of the yfinance downloads in data/raw/ and data/metadata.json,
   plus one Excel workbook with a sheet per ticker (row 1 = source line, table from row 2).
2. company_filings/, nse/, news_and_macro/: downloads each document with a browser User-Agent.
   For every file it checks that the phrase or number quoted in this project appears in the
   saved text. If a site blocks the download, or the phrase is missing, it writes a .md note
   with the link and the fact used instead.
3. download_log.csv: file, URL, HTTP status, bytes, SHA-256, phrase and whether it was found.
"""
from __future__ import annotations

import csv
import hashlib
import html
import re
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import DATA_DIR, PROJECT_DIR, RAW_DIR  # noqa: E402

SRC_DIR = PROJECT_DIR / "source_data"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")


@dataclass(frozen=True)
class Doc:
    """One source document: where to save it, candidate URLs and the phrase that must appear."""

    folder: str
    name: str            # file name without extension
    urls: tuple[str, ...]
    phrase: str
    fact: str            # the fact used in the project (kept in the .md note if the download fails)
    used_for: str
    kind: str = "html"   # "html", "pdf" or "csv"


DOCS: tuple[Doc, ...] = (
    # ------------------------------------------------------------------ demerger evidence: company filings
    Doc("company_filings", "RIL_intimation_apportionment_of_cost_JFSL_2023",
        ("https://www.ril.com/sites/default/files/2023-08/SEIntimation_ApportionmentofCost_0.pdf",),
        "4.68", "RIL: cost of acquisition of pre-demerger RIL shares split 95.32% to RIL and 4.68% to Jio Financial "
        "Services (tax rule, based on book values).", "Reliance demerger documentation (tax split, not used in returns)", "pdf"),
    Doc("company_filings", "ITC_letter_demerger_effective_date_17Dec2024",
        ("https://www.itcportal.com/content/dam/itc-corporate/stock-exchange-/Demerger%20of%20the%20Hotels%20Business%20-%20Appointed%20Date%20and%20Effective%20Date%2017%20Dec%202024.pdf",
         "https://stage.itcportal.com/content/dam/itc-corporate/stock-exchange-/Demerger%20of%20the%20Hotels%20Business%20-%20Appointed%20Date%20and%20Effective%20Date%2017%20Dec%202024.pdf"),
        "January, 2025", "ITC: NCLT order received 16-Dec-2024; demerger of the Hotels Business effective 1-Jan-2025.",
        "ITC demerger timeline", "pdf"),
    Doc("company_filings", "ITC_letter_record_date_18Dec2024",
        ("https://itcportal.com/content/dam/itc-corporate/pdfs/2024/lodr-18dec24.pdf",
         "https://www.itcportal.com/content/dam/itc-corporate/stock-exchange-/Demerger%20of%20the%20Hotels%20Business%20-%20Record%20Date%2018%20Dec%202024.pdf"),
        "6th January, 2025 as the Record Date", "ITC and ITC Hotels fixed Monday 6-Jan-2025 as the record date for "
        "allotting ITC Hotels shares under the scheme of arrangement.", "ITC demerger record date and ex-date (6-Jan-2025)",
        "pdf"),
    Doc("company_filings", "ITC_letter_ITC_Hotels_allotment_11Jan2025",
        ("https://www.itcportal.com/content/dam/itc-corporate/stock-exchange-/2025/lodr-11jan25.pdf",
         "https://dev.itcportal.com/content/dam/itc-corporate/stock-exchange-/2025/lodr-11jan25.pdf"),
        "6th January, 2025", "ITC Hotels allotted 125,11,71,040 shares to ITC shareholders on the record date "
        "6-Jan-2025 (1 for 10).", "ITC demerger ratio and record date", "pdf"),
    Doc("company_filings", "ITC_intimation_apportionment_of_cost_ITC_Hotels_27Jan2025",
        ("https://www.itcportal.com/content/dam/itc-corporate/stock-exchange-/2025/lodr-27jan25.pdf",
         "https://stockinsights-ai.s3.amazonaws.com/in/announcements/8c1118a5-bfb7-49ba-9f57-1f922561d440.pdf"),
        "86.49", "ITC: cost of acquisition split 86.49% to ITC and 13.51% to ITC Hotels (tax rule).",
        "ITC demerger documentation (tax split, not used in returns)", "pdf"),
    # ------------------------------------------------------------------ demerger evidence: exchange and index provider
    Doc("nse", "NSE_circular_CMTR57524_RIL_special_pre-open_session_12Jul2023",
        ("https://nsearchives.nseindia.com/content/circulars/CMTR57524.pdf",
         "https://archives.nseindia.com/content/circulars/CMTR57524.pdf"),
        "Reliance", "NSE circular NSE/CMTR/57524 (12-Jul-2023): special pre-open session for RELIANCE on 20-Jul-2023 "
        "for the demerger of its financial services business.", "Reliance ex-date and price-discovery method", "pdf"),
    Doc("nse", "NSE_Indices_press_release_RIL_demerger_index_treatment_Jul2023",
        ("https://www.niftyindices.com/Press_Release/ind_prs17072023.pdf",
         "https://www.sharekhan.com/MediaGalary/Newsletter/SK-Nse-Press-release-RIL-Demerger-180723.pdf"),
        "spun off entity", "NSE Indices: spun-off entity (Jio Financial Services) included in NIFTY 50 and other "
        "indices from 20-Jul-2023 (close of 19-Jul-2023).", "Why the exchange price-discovery factor is used", "pdf"),
    Doc("nse", "NSE_circular_FO_adjustment_ITC_scheme_of_arrangement_Jan2025",
        ("https://nsearchives.nseindia.com/content/circulars/FAOP65975.pdf",
         "https://www.steelcitynettrade.com/Circulars/Scheme%20of%20Arrangement-%20Adjustment%20of%20Futures%20and%20Options%20contracts%20of%20ITC%20Limited%20ITC.pdf"),
        "06-JAN-2025", "NSE: ITC ex-date and effective date 06-Jan-2025; F&O trading starts at 10:00 after the special "
        "pre-open call auction session (SPOS).", "ITC ex-date and price-discovery method", "pdf"),
    Doc("nse", "MSEI_circular_16558_ITC_special_pre-open_session_Jan2025",
        ("https://www.msei.in/SX-Content/Circulars/2025/January/Circular-16558.pdf",),
        "ITC", "Exchange circular: ITC special pre-open call auction 9:00-10:00 on 6-Jan-2025; base price = discovered price.",
        "ITC price-discovery session", "pdf"),
    Doc("nse", "NSE_circular_index_constituent_spun_off_entity_constant_price",
        ("https://nsearchives.nseindia.com/content/circulars/FAOP58203.pdf",
         "https://www.steelcitynettrade.com/Circulars/Short%20notice%20period%20in%20case%20of%20change%20in%20constituent%20stock%20in%20an%20underlying%20derivative%20index.pdf"),
        "spun off", "NSE: per index methodology the spun-off entity stays in the index at a constant price derived in "
        "the special pre-open session until it lists.", "Why the exchange price-discovery factor is used", "pdf"),
    Doc("nse", "NSE_circular_0160_2025_listing_of_ITC_Hotels_27Jan2025",
        ("https://www.steelcitynettrade.com/Circulars/Listing%20of%20Equity%20Shares%20of%20ITC%20Hotels%20Limited%20pursuant%20to%20the%20Scheme%20of%20Arrangement.pdf",),
        "ITC Hotels", "NSE circular 0160/2025: ITC Hotels admitted to dealings from 29-Jan-2025.",
        "ITC demerger timeline (listing of the spun-off company)", "pdf"),
    Doc("nse", "NIFTY50_factsheet",
        ("https://www.niftyindices.com/Factsheet/ind_nifty50.pdf", "https://niftyindices.com/Factsheet/ind_nifty50.pdf"),
        "Nifty 50", "NIFTY 50 factsheet: methodology (free-float market cap), constituents, sector weights.",
        "Benchmark description", "pdf"),
    Doc("nse", "NIFTY50_constituents_list",
        ("https://www.niftyindices.com/IndexConstituent/ind_nifty50list.csv",),
        "SUNPHARMA", "NIFTY 50 constituent list (company, industry, symbol, ISIN): all ten project stocks are members.",
        "Universe check (all ten stocks are NIFTY 50 members)", "csv"),
    # ------------------------------------------------------------------ risk-free rate
    Doc("news_and_macro", "ET_91day_TBill_cutoff_5.93pct_28Oct2026",
        ("https://economictimes.indiatimes.com/markets/bonds/rbi-accepts-20-bps-higher-treasury-bill-cutoff-yields-than-last-auction/articleshow/135284706.cms",),
        "5.93", "91-day T-bill cut-off yield 5.93% at the RBI auction of 28-Oct-2026.", "Risk-free rate (5.93%)"),
    # The link to RBI press release 2026-2027/1399 (full auction result) redirects to the RBI home page, so the
    # saved copy is the home page of 1-Nov-2026. Its "Current Rates" panel shows the cut-off at the last auction.
    Doc("news_and_macro", "RBI_homepage_current_rates_TBill_cutoff_30Oct2026",
        ("https://www.rbi.org.in/", "https://website.rbi.org.in/documents/d/rbi/pr1399202627"),
        "5.9337%", "RBI home page, Current Rates: 91-day T-bill 5.9337% (cut-off at the last auction, "
        "28-Oct-2026); 182-day 6.5493%; 364-day 6.6900%.", "Risk-free rate (official second source)"),
    # ------------------------------------------------------------------ demerger prices
    Doc("news_and_macro", "Reuters_Yahoo_RIL_special_session_price_20Jul2023",
        ("https://sg.finance.yahoo.com/news/reliance-starts-special-trading-session-034517252.html",),
        "2,580", "RIL closed at Rs 2,841.85 on 19-Jul-2023; price at the end of the special session Rs 2,580.",
        "Reliance demerger factor 0.90786"),
    Doc("news_and_macro", "IndianExpress_JFSL_demerger_ratio_20Jul2023",
        ("https://indianexpress.com/article/business/companies/jio-financial-services-ltd-to-demerge-from-ril-today-8849165/",),
        "1:1", "Demerger ratio 1 JFSL share for every 1 RIL share.", "Reliance demerger ratio"),
    Doc("news_and_macro", "Livemint_RIL_JFSL_cost_of_acquisition_20Jul2023",
        ("https://www.livemint.com/companies/news/reliancejfsl-demerger-cost-of-acquisition-of-ril-jio-financial-services-shares-declared-details-here-11689820049646.html",),
        "4.68", "Cost of acquisition split 95.32% RIL / 4.68% JFSL.", "Reliance demerger documentation"),
    Doc("news_and_macro", "TimesNow_ITC_special_session_price_6Jan2025",
        ("https://www.timesnownews.com/business-economy/markets/itc-hotels-share-price-special-trading-session-ends-itc-share-price-adjusts-by-rs-26-on-nse-article-116981147",),
        "455.60", "ITC adjusted by Rs 26 to Rs 455.60 on NSE in the special session of 6-Jan-2025; ratio 1 for 10.",
        "ITC demerger factor 0.94601"),
    Doc("news_and_macro", "CNBCTV18_ITC_ex_hotels_price_6Jan2025",
        ("https://www.cnbctv18.com/market/itc-shares-now-trade-ex-hotels-check-stock-price-post-demerger-19534891.htm",),
        "455.6", "Market assigned ITC a price of Rs 455.60 after the special session.", "ITC demerger factor (second source)"),
    Doc("news_and_macro", "Livemint_ITC_Hotels_cost_of_acquisition_27Jan2025",
        ("https://www.livemint.com/market/stock-market-news/itc-revises-cost-of-acquisition-of-itc-hotels-shares-details-here-11738040274139.html",),
        "86.49", "Cost of acquisition split 86.49% ITC / 13.51% ITC Hotels; discovered price Rs 260 on NSE.",
        "ITC demerger documentation"),
    # ------------------------------------------------------------------ large one-day moves
    Doc("news_and_macro", "TheHindu_Infosys_fall_17Apr2023",
        ("https://www.thehindu.com/business/infosys-shares-fall-over-9-mcap-declines-by-59349-crore-post-earnings-announcement/article66747825.ece",),
        "Infosys", "Infosys fell over 9% on 17-Apr-2023 after Q4 FY23 results.", "Large-move review"),
    Doc("news_and_macro", "Reuters_Yahoo_Infosys_guidance_cut_21Jul2023",
        ("https://finance.yahoo.com/news/indias-infosys-shares-slide-cutting-035551775.html",),
        "Infosys", "Infosys slid after cutting its FY24 revenue guidance to 1-3.5%.", "Large-move review"),
    Doc("news_and_macro", "ET_HDFC_Bank_biggest_single_day_falls_19Mar2026",
        ("https://economictimes.indiatimes.com/markets/stocks/news/hdfc-banks-covid-plunge-to-earnings-disappointment-5-biggest-single-day-stock-crashes-since-2020/articleshow/129674611.cms",),
        "HDFC Bank", "HDFC Bank's 17-Jan-2024 fall after Q3 FY24 results.", "Large-move review"),
    Doc("news_and_macro", "TheHindu_election_results_crash_4Jun2024",
        ("https://www.thehindu.com/business/markets/sensex-plunges-57-as-bjp-fails-to-win-majority-on-its-own/article68251438.ece",),
        "Sensex", "Market fell on general election results day, 4-Jun-2024.", "Large-move review (L&T)"),
    Doc("news_and_macro", "Reuters_Yahoo_tobacco_stocks_excise_duty_1Jan2026",
        ("https://sg.finance.yahoo.com/news/indian-tobacco-stocks-tank-government-063100025.html",),
        "ITC", "Tobacco stocks fell after a new excise duty on cigarettes was notified on 31-Dec-2025.",
        "Large-move review (ITC)"),
    Doc("news_and_macro", "CNBCTV18_HDFC_merger_announced_4Apr2022",
        ("https://www.cnbctv18.com/market/stocks/hdfc-hdfc-bank-merger-mortgage-lender-overtakes-icici-bank-to-become-5th-largest-co-by-market-value-13038642.htm",),
        "HDFC", "HDFC Bank jumped on 4-Apr-2022 when the merger with HDFC Ltd was announced.", "Large-move review"),
    Doc("news_and_macro", "CNBCTV18_Maruti_GST_cut_18Aug2025",
        ("https://www.cnbctv18.com/market/maruti-suzuki-india-share-price-gains-most-in-five-years-gst-rate-cut-product-mix-impact-demand-returns-19655101.htm",),
        "Maruti", "Maruti gained most in five years on the proposed GST cut on small cars.", "Large-move review"),
    # ------------------------------------------------------------------ bonus issues, holiday, index weights
    Doc("news_and_macro", "BusinessToday_RIL_bonus_record_date_28Oct2024",
        ("https://www.businesstoday.in/markets/stocks/story/ril-bonus-shares-reliance-fixes-monday-october-28-as-record-date-for-issue-450406-2024-10-16",),
        "October 28", "RIL 1:1 bonus, record date 28-Oct-2024.", "Bonus-issue check"),
    Doc("news_and_macro", "Livemint_HDFC_Bank_bonus_26Aug2025",
        ("https://www.livemint.com/market/stock-market-news/hdfc-bank-bonus-issue-reward-or-a-trap-explained-with-the-share-outlook-income-tax-rule-11755912368086.html",),
        "bonus", "HDFC Bank 1:1 bonus, ex-date 26-Aug-2025 (record date 27-Aug-2025).", "Bonus-issue check"),
    Doc("news_and_macro", "Livemint_market_holiday_15Jan2026",
        ("https://www.livemint.com/market/stock-market-news/stock-market-holiday-bse-nse-to-remain-shut-for-maharashtra-municipal-elections-commodity-trading-to-begin-at-5-pm-11768439343202.html",),
        "Maharashtra", "BSE and NSE shut on 15-Jan-2026 for the Maharashtra municipal elections.",
        "Calendar alignment (dropped date)"),
    Doc("news_and_macro", "TimesNow_NIFTY50_weights_ICICI_vs_Reliance_Jun2026",
        ("https://www.timesnownews.com/business-economy/markets/how-icici-bank-surpassed-reliance-industries-to-become-nifty-50s-second-highest-weighted-stock-despite-a-smaller-market-cap-explained-article-154530028",),
        "ICICI", "HDFC Bank, ICICI Bank and Reliance are among the largest NIFTY 50 weights.", "Beta discussion"),
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
    """Plain text of a saved PDF (PyMuPDF) or HTML page (tags kept, entities decoded, spaces collapsed)."""
    if path.suffix.lower() == ".pdf":
        import pymupdf  # PyMuPDF

        with pymupdf.open(path) as doc:
            raw = " ".join(page.get_text() for page in doc)
    else:
        raw = html.unescape(path.read_bytes().decode("utf-8", errors="replace"))
    return re.sub(r"\s+", " ", raw)


def download(url: str, target: Path, kind: str) -> tuple[int, str]:
    """GET ``url`` with a browser User-Agent and save it to ``target``. Returns (HTTP status, error text)."""
    import requests

    headers = {"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9",
               "Accept": "application/pdf,text/html,application/xhtml+xml,*/*;q=0.8"}
    if "nseindia.com" in url:
        headers["Referer"] = "https://www.nseindia.com/"
    elif "niftyindices.com" in url:
        headers["Referer"] = "https://www.niftyindices.com/"
    try:
        r = requests.get(url, headers=headers, timeout=40, allow_redirects=True)
    except Exception as exc:  # noqa: BLE001
        return 0, f"{type(exc).__name__}: {exc}"[:200]
    if r.status_code != 200:
        return r.status_code, f"HTTP {r.status_code}"
    body = r.content
    if kind == "pdf" and not body.startswith(b"%PDF"):
        return r.status_code, "response is not a PDF"
    if kind == "html" and len(body) < 2000:
        return r.status_code, "response too small to be the article"
    if kind == "csv" and (body.lstrip()[:1] == b"<" or b"," not in body[:300]):
        return r.status_code, "response is not a CSV"
    target.write_bytes(body)
    return r.status_code, ""


def note_md(doc: Doc, path: Path, status: str, today: str) -> None:
    """Write a short note for a source that could not be saved."""
    lines = [f"# {doc.name}", "", f"- Links tried: " + "; ".join(doc.urls), f"- Date tried: {today}",
             f"- Result: {status}", f"- Fact used in this project: {doc.fact}", f"- Used for: {doc.used_for}"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ============================================================================ steps
def copy_yahoo(today: str) -> list[dict]:
    """Copy the raw yfinance files and build the Excel export. Returns log rows."""
    import json

    import pandas as pd

    out = SRC_DIR / "yahoo_finance"
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    meta = json.loads((DATA_DIR / "metadata.json").read_text(encoding="utf-8"))
    for f in sorted(RAW_DIR.glob("*.csv")) + [DATA_DIR / "metadata.json"]:
        dst = out / f.name
        shutil.copy2(f, dst)
        rows.append({"file": dst.relative_to(SRC_DIR).as_posix(), "url": "copy of data/" + f.relative_to(DATA_DIR).as_posix(),
                     "status": "copied", "bytes": dst.stat().st_size, "sha256": sha256(dst), "phrase": "",
                     "phrase_found": "", "saved_on": meta["download_timestamp_ist"][:10]})
    xlsx = out / "Yahoo_Finance_daily_prices_NSE_2021-10-01_to_2026-10-30.xlsx"
    stamp = meta["download_timestamp_ist"]
    with pd.ExcelWriter(xlsx, engine="xlsxwriter", datetime_format="dd-mmm-yyyy", date_format="dd-mmm-yyyy") as xw:
        index = []
        for f in sorted(RAW_DIR.glob("*.csv")):
            ticker = f.stem.replace("IDX_", "^")
            info = meta["tickers"].get(ticker, {})
            df = pd.read_csv(f, index_col=0, parse_dates=True)
            sheet = ticker.replace("^", "").replace(".NS", "")[:31]
            unit = "index points" if ticker.startswith("^") else "INR per share"
            line = (f"Source: Yahoo Finance via yfinance {meta['yfinance_version']} | "
                    f"https://finance.yahoo.com/quote/{ticker}/history/ | downloaded {stamp} | "
                    f"prices in {unit}, Volume in shares, Dividends in INR per share; auto_adjust=False")
            df.to_excel(xw, sheet_name=sheet, startrow=1)
            ws = xw.sheets[sheet]
            ws.write(0, 0, line)
            ws.set_column(0, 0, 12, xw.book.add_format({"num_format": "dd-mmm-yyyy"}))
            ws.set_column(1, len(df.columns), 13, xw.book.add_format({"num_format": "#,##0.00"}))
            ws.freeze_panes(2, 1)
            index.append({"sheet": sheet, "ticker": ticker, "name": info.get("name", ""), "rows": len(df),
                          "first date": df.index.min().date(), "last date": df.index.max().date()})
        idx = pd.DataFrame(index)
        idx.to_excel(xw, sheet_name="Index", startrow=1, index=False)
        ws = xw.sheets["Index"]
        ws.write(0, 0, f"Source: Yahoo Finance via yfinance {meta['yfinance_version']} | https://finance.yahoo.com | "
                       f"downloaded {stamp} | one sheet per ticker, copied unchanged from data/raw/")
        ws.set_column(0, 5, 16)
        xw.book.worksheets_objs.sort(key=lambda s: s.name != "Index")
    rows.append({"file": xlsx.relative_to(SRC_DIR).as_posix(), "url": "built from data/raw/*.csv", "status": "built",
                 "bytes": xlsx.stat().st_size, "sha256": sha256(xlsx), "phrase": "", "phrase_found": "",
                 "saved_on": today})
    return rows


def fetch_docs(force: bool, today: str) -> list[dict]:
    """Download every document in DOCS (skipping existing files unless ``force``). Returns log rows."""
    rows = []
    for doc in DOCS:
        folder = SRC_DIR / doc.folder
        folder.mkdir(parents=True, exist_ok=True)
        ext = {"pdf": ".pdf", "csv": ".csv"}.get(doc.kind, ".html")
        target = folder / (doc.name + ext)
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
            used_url = next((r["url"] for r in read_log() if r["file"].endswith(target.name)), doc.urls[0])
        if target.exists():
            note.unlink(missing_ok=True)
            found = doc.phrase.lower() in text_of(target).lower()
            rows.append({"file": target.relative_to(SRC_DIR).as_posix(), "url": used_url, "status": status,
                         "bytes": target.stat().st_size, "sha256": sha256(target), "phrase": doc.phrase,
                         "phrase_found": found, "saved_on": today})
        else:
            note_md(doc, note, err or "download failed", today)
            rows.append({"file": note.relative_to(SRC_DIR).as_posix(), "url": doc.urls[0], "status": f"note only ({err})",
                         "bytes": note.stat().st_size, "sha256": sha256(note), "phrase": doc.phrase,
                         "phrase_found": "", "saved_on": today})
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
    rows = copy_yahoo(today) + fetch_docs(force, today)
    with (SRC_DIR / "download_log.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    total = sum(p.stat().st_size for p in SRC_DIR.rglob("*") if p.is_file())
    print(f"{len(rows)} entries; source_data/ total {total / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
