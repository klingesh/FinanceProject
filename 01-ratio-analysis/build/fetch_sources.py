"""Save the web sources behind Project 1 into source_data/ (needs internet; the analysis does not).

What it saves (1-Nov-2026 run):
  screener/raw/<SYMBOL>_consolidated.html   Screener.in company pages for the four companies
  screener/<SYMBOL>_<section>.csv           tables parsed from those pages (Rs crore)
  company_filings/                          Bajaj Auto press release (KTM, 21-May-2025) and page extracts of the
                                            FY2025 and FY2026 annual reports (the notes behind the one-off gains)
  news_and_macro/*.html                     news articles cited in notes/ (copyrighted: kept local, see .gitignore)
  download_log.csv                          one row per download: URL, HTTP status, bytes, SHA-256, phrase check

The author's own Screener Excel exports of 15-Oct-2026 (screener/exports/) were downloaded by hand and are the
files the workbook was built from. This script does not touch them.

Usage:  python build/fetch_sources.py [--force]
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sys
import time
from pathlib import Path

import fitz  # PyMuPDF
import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
SD = ROOT / "source_data"
CACHE = ROOT / "build" / "_cache"  # full annual-report PDFs (too large for GitHub; ignored)
FORCE = "--force" in sys.argv
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/130.0 Safari/537.36",
      "Accept-Language": "en-IN,en;q=0.9"}

# Screener symbol, company, FY2026 revenue as Screener prints it (phrase check)
COMPANIES = [
    ("HEROMOTOCO", "Hero MotoCorp", "47,411"),
    ("BAJAJ-AUTO", "Bajaj Auto", "62,905"),
    ("TVSMOTOR", "TVS Motor", "56,070"),
    ("EICHERMOT", "Eicher Motors", "23,408"),
]
SECTIONS = ["profit-loss", "balance-sheet", "cash-flow", "ratios"]

PAGES = [
    # (relative path, URL, phrase that must appear, local_only)
    ("company_filings/BajajAuto_press_release_KTM_control_21May2025.html",
     "https://www.bajajauto.com/corporate/media-centre/press-releases/bajaj-auto-makes-decisive-move-to-take-charge-of-rebuilding-ktm",
     "KTM", False),
    ("news_and_macro/ET_Bajaj_KTM_EUR566m_loan_18May2025.html",
     "https://economictimes.indiatimes.com/industry/auto/auto-news/ktm-co-owner-bajaj-auto-signs-566m-loan-before-funding-deadline/articleshow/121245454.cms",
     "KTM", True),
    ("news_and_macro/AckoDrive_Bajaj_KTM_loan_23May2025.html",
     "https://ackodrive.com/news/bajaj-auto-raises-5-399-crore-loan-for-ktm-buyout/",
     "KTM", True),
    ("news_and_macro/Livemint_KTM_operating_profit_28Aug2026.html",
     "https://www.livemint.com/news/ktm-bajaj-auto-bajaj-mobility-ktm-insolvency-motorcycle-sales-premium-motorcycles-11787886342479.html",
     "KTM", True),
]

# Annual reports: only the pages that contain these phrases are kept (plus the next page of each hit)
ANNUAL_REPORTS = [
    ("BajajAuto_Annual_Report_FY2025-26_extract.pdf",
     "https://www.bajajauto.com/-/media/images/bajajauto/media-kit/press-release/new-annual-reports/fy2025-26/bajaj-auto-annual-report-2025-26.pdf",
     ["953.10", "645.71", "Business combinations and acquisition of non-controlling interests", "15,338.94",
      "21,980.59", "1,785.90"]),
    ("BajajAuto_Annual_Report_FY2024-25_extract.pdf",
     "https://investors.bajajauto.com/ar25/wp-content/uploads/2025/07/BAL_Annual_Report_2025.pdf",
     ["915.48", "211.26"]),
]

log_rows: list[dict] = []


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def get(url: str, timeout: int = 90) -> requests.Response | None:
    for attempt in range(1, 4):
        try:
            r = requests.get(url, headers=UA, timeout=timeout)
            return r
        except requests.RequestException as e:
            print(f"  attempt {attempt} failed: {type(e).__name__}: {e}")
            time.sleep(3 * attempt)
    return None


OLD_LOG = {}
if (SD / "download_log.csv").exists():
    with open(SD / "download_log.csv", encoding="utf-8") as f:
        OLD_LOG = {r["file"]: r for r in csv.DictReader(f)}


def log(rel, url, status, data: bytes | None, phrase, found, local_only, note=""):
    digest = sha(data) if data else ""
    old = OLD_LOG.get(rel)
    downloaded = time.strftime("%Y-%m-%d")
    if status == "cached" and old and old["sha256"] == digest:  # unchanged file: keep the original download record
        status, downloaded = old["http_status"], old["downloaded"]
    log_rows.append({
        "file": rel, "url": url, "http_status": status, "bytes": len(data) if data else 0,
        "sha256": digest, "phrase_checked": phrase, "phrase_found": found,
        "local_only": local_only, "downloaded": downloaded, "note": note,
    })


def to_number(x):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    s = str(x).replace(",", "").replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse_section(soup: BeautifulSoup, sec_id: str) -> pd.DataFrame | None:
    sec = soup.find("section", id=sec_id)
    table = sec.find("table", class_=re.compile("data-table")) if sec else None
    if table is None:
        return None
    df = pd.read_html(io.StringIO(str(table)))[0]
    df = df.rename(columns={df.columns[0]: "item"})
    df["item"] = (df["item"].astype(str).str.replace(r"\s*\+\s*$", "", regex=True)
                  .str.replace("\xa0", " ").str.strip())
    df = df[df["item"].str.lower() != "raw pdf"]
    for c in df.columns[1:]:
        df[c] = df[c].map(to_number)
    return df


def fetch_screener():
    raw = SD / "screener" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    summary = {}
    for sym, name, phrase in COMPANIES:
        rel = f"screener/raw/{sym}_consolidated.html"
        url = f"https://www.screener.in/company/{sym}/consolidated/"
        path = SD / rel
        if path.exists() and not FORCE:
            data = path.read_bytes()
            html = data.decode("utf-8", errors="replace")
            status = "cached"
        else:
            r = get(url)
            if r is None or r.status_code != 200:
                log(rel, url, getattr(r, "status_code", "error"), None, phrase, False, False)
                continue
            html, data, status = r.text, r.content, r.status_code
            path.write_bytes(data)  # the bytes as served, so the SHA-256 in download_log.csv matches the file
            time.sleep(2)
        log(rel, url, status, data, phrase, phrase in html, False)
        soup = BeautifulSoup(html, "lxml")
        info = {"company": name, "url": url}
        for sec in SECTIONS:
            df = parse_section(soup, sec)
            if df is None:
                continue
            out = SD / "screener" / f"{sym}_{sec}.csv"
            df.to_csv(out, index=False)
            info[sec] = list(df.shape)
        m = re.search(r'data-company-id="(\d+)"', html)
        info["company_id"] = m.group(1) if m else None
        summary[sym] = info
    (SD / "screener" / "screener_pages_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


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


def fetch_annual_reports():
    CACHE.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, url, phrases in ANNUAL_REPORTS:
        rel = f"company_filings/{name}"
        out = SD / rel
        full = CACHE / url.rsplit("/", 1)[-1]
        status = 200
        if full.exists() and not FORCE:
            old = OLD_LOG.get(rel)
            status = old["http_status"] if old else "cached"
        else:
            r = get(url, timeout=300)
            if r is None or r.status_code != 200 or not r.content.startswith(b"%PDF"):
                log(rel, url, getattr(r, "status_code", "error"), None, ";".join(phrases), False, False,
                    "download failed; link kept in source_data/README.md")
                continue
            full.write_bytes(r.content)
        doc = fitz.open(full)
        hits = []
        for i, page in enumerate(doc):
            text = page.get_text()
            if any(p in text for p in phrases):
                hits.append(i)
        keep = sorted({j for i in hits for j in (i, i + 1) if j < doc.page_count})
        if len(keep) > 24:  # keep the extract small: first hits only
            keep = keep[:24]
        ext = fitz.open()
        for i in keep:
            ext.insert_pdf(doc, from_page=i, to_page=i)
        ext.save(out, garbage=4, deflate=True)
        data = out.read_bytes()
        ext_text = "".join(p.get_text() for p in fitz.open(out))
        found = all(p in ext_text for p in phrases if p[0].isdigit())
        log(rel, url, status, data, ";".join(phrases), found, False,
            f"extract of {len(keep)} of {doc.page_count} pages (1-based): {[k + 1 for k in keep]}; "
            f"full PDF {full.stat().st_size / 1e6:.1f} MB")
        manifest[name] = {"url": url, "pages_total": doc.page_count, "pages_kept_1based": [k + 1 for k in keep],
                          "phrases": phrases}
    (SD / "company_filings" / "annual_report_extracts.json").write_text(json.dumps(manifest, indent=2),
                                                                        encoding="utf-8")


if __name__ == "__main__":
    fetch_screener()
    fetch_pages()
    fetch_annual_reports()
    with open(SD / "download_log.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(log_rows[0].keys()))
        w.writeheader()
        w.writerows(log_rows)
    bad = [r for r in log_rows if not r["phrase_found"]]
    print(f"{len(log_rows)} downloads logged; {len(bad)} without the expected phrase or failed")
    for r in bad:
        print("  CHECK:", r["file"], r["http_status"], r["note"])
