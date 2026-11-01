"""Company filings and the pages behind news / macro facts -> source_data/ (network step, run once).

PDFs: the full files are large (up to 28 MB, scanned pages), so only the pages the model uses are written to
source_data/company_filings/ as page extracts (page numbers are listed in source_data/README.md). Full PDFs are
read from a local cache: the folder in the environment variable P04_PDF_CACHE if set, else build/_cache/
(git-ignored). A PDF missing from the cache is downloaded from ultratechcement.com once.

Pages: news and macro pages are saved as cleaned HTML (scripts and styles removed) in
source_data/news_and_macro/. If a site blocks the download, a short .md note with the URL and the fact is written.

Run:  python build/02_fetch_filings.py        (first run: 1-Nov-2026)
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib.parse import quote

import pymupdf as fitz
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path(os.environ.get("P04_PDF_CACHE", ROOT / "build" / "_cache"))
FIL = ROOT / "source_data" / "company_filings"
NEWS = ROOT / "source_data" / "news_and_macro"
for d in (CACHE, FIL, NEWS):
    d.mkdir(parents=True, exist_ok=True)

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130 Safari/537.36"
    ),
    "Accept": "text/html,application/pdf,*/*",
}
HOST = "https://www.ultratechcement.com"
DAM = "/content/dam/ultratechcementwebsite/pdf/financials/"

# cache name -> (path on ultratechcement.com, pages to keep (1-indexed PDF pages) or None = whole file, output name)
PDFS: dict[str, tuple[str, list[int] | None, str]] = {
    "q2fy27-investor-presentation": (
        DAM + "investor-update/q2fy27-investor-presentation.pdf", [2, 9, 12, 13, 19, 20, 22, 30, 31, 32, 33],
        "UltraTech_Q2FY27_Investor_Presentation_19Oct2026_extract.pdf"),
    "q2fy27-results": (
        DAM + "financial-results/fy27/q2/q2fy27-results.pdf", [6, 7, 8],
        "UltraTech_Q2FY27_Consolidated_Results_19Oct2026_extract.pdf"),
    "q2fy27-earnings-call-transcript": (
        DAM + "earnings-call/q2fy27-earnings-call-transcript.pdf", None,
        "UltraTech_Q2FY27_Earnings_Call_Transcript_19Oct2026.pdf"),
    "q1fy27-results-presentation": (
        DAM + "investor-update/results-presentation-q1fy27.pdf", [8, 10, 13, 27, 28, 29],
        "UltraTech_Q1FY27_Results_Presentation_extract.pdf"),
    "q4fy26-investor-presentation": (
        DAM + "investor-update/q4fy26-investor-presentation.pdf", [10, 14, 15, 20, 21, 22, 32, 33, 34, 35, 36, 37],
        "UltraTech_Q4FY26_Investor_Presentation_27Apr2026_extract.pdf"),
    "q4fy26-results": (
        DAM + "financial-results/fy26/q4/q4fy26-results.pdf", [8, 9, 10, 12],
        "UltraTech_FY26_Audited_Consolidated_Results_extract.pdf"),
    "q4fy26-earnings-call-transcript": (
        DAM + "earnings-call/ultratech-cement-limited-earnings-call-transcript-q4fy26.pdf", None,
        "UltraTech_Q4FY26_Earnings_Call_Transcript_27Apr2026.pdf"),
    "annual-report-fy26": (
        DAM + "annual-reports/integrated-and-sustainability-report-2025-26-single-page.pdf",
        [20, 46, 47, 195, 199, 464, 465, 468, 469, 498, 506, 509, 510, 511, 512, 530, 531, 532, 533],
        "UltraTech_Integrated_Report_FY2025-26_extract.pdf"),
    "q4fy25-results-presentation": (
        DAM + "investor-update/UltraTech-Result-Presentation-Q4-FY25.pdf", [10, 13, 14, 37, 38, 39, 41],
        "UltraTech_Q4FY25_Results_Presentation_extract.pdf"),
    "q4fy24-results-presentation": (
        DAM + "investor-update/Result-Presentation-Q4-FY24 (2).pdf", [7, 9, 17, 36, 37, 39],
        "UltraTech_Q4FY24_Results_Presentation_extract.pdf"),
    "q4fy24-results": (
        DAM + "financial-results/fy24/q4/Q4FY24Results.pdf", None, "UltraTech_FY24_Audited_Results.pdf"),
    "q4fy23-results-presentation": (
        DAM + "investor-update/ultratech-result-presentation-q4-fy-23.pdf", [7, 8, 19, 35, 36, 38],
        "UltraTech_Q4FY23_Results_Presentation_extract.pdf"),
    "q4fy23-results": (
        DAM + "financial-results/fy23/q4/utcl-results-q4-fy-23-clean.pdf", None, "UltraTech_FY23_Audited_Results.pdf"),
    "q4fy22-investor-presentation": (
        DAM + "investor-update/utcl-investor-presentation-q4-fy-22.pdf", [7, 16],
        "UltraTech_Q4FY22_Investor_Presentation_extract.pdf"),
}

# file stem -> (url, short note with the fact used; written to a .md file if the site blocks the download)
PAGES: dict[str, tuple[str, str]] = {
    "ET_TBill_auction_28Oct2026": (
        "https://economictimes.indiatimes.com/markets/bonds/rbi-accepts-20-bps-higher-treasury-bill-cutoff-yields-than-last-auction/articleshow/135284706.cms",
        "RBI T-bill auction of 28-Oct-2026: 91-day cut-off yield 5.93%, 182-day 6.54%, 364-day 6.69%."),
    "TheHindu_RBI_repo_hike_7Oct2026": (
        "https://www.thehindu.com/business/Economy/rbi-hikes-repo-rate-by-25-basis-points-to-55/article71554369.ece",
        "RBI raised the repo rate by 25 bp to 5.50% on 7-Oct-2026."),
    "Mint_RBI_repo_hike_7Oct2026": (
        "https://www.livemint.com/market/stock-market-news/rbi-mpc-meeting-october-2026-repo-rate-hiked-by-25-bps-to-5-50-growth-inflation-forecast-other-key-takeaways-11791344804917.html",
        "Second source: repo rate hiked by 25 bp to 5.50% on 7-Oct-2026."),
    "TradingEconomics_India_10Y_yield": (
        "https://tradingeconomics.com/india/government-bond-yield",
        "India 10-year G-sec yield 7.40% on 30-Oct-2026."),
    "ETBFSI_Reuters_India_bonds_30Oct2026": (
        "https://bfsi.economictimes.indiatimes.com/articles/india-bonds-buckle-for-fourth-straight-month-on-oils-climb/135363689",
        "Benchmark 6.94% 2036 bond yield 7.4139% on 30-Oct-2026 (Reuters)."),
    "IncomeTaxIndia_domestic_company_rates": (
        "https://www.incometaxindia.gov.in/domestic-company",
        "Section 115BAA: 22% base rate, 10% surcharge irrespective of income, 4% cess -> 25.17%."),
    "ClearTax_section_115BAA": (
        "https://cleartax.in/s/section-115-baa-tax-rate-domestic-companies",
        "Second source: 22% + 10% surcharge + 4% cess = 25.17% effective rate under s.115BAA."),
    "TheHindu_StarCement_stake_27Dec2024": (
        "https://www.thehindu.com/business/Industry/ultratech-to-acquire-minority-stake-in-star-cement-from-promoters-in-851-crore-deal/article69032907.ece",
        "UltraTech to buy a minority 8.69% stake in Star Cement Ltd from promoters for up to Rs 851 crore (27-Dec-2024)."),
    "Moneycontrol_StarCement_stake_27Dec2024": (
        "https://www.moneycontrol.com/news/business/markets/ultratech-cement-acquires-8-7-stake-in-star-cement-for-rs-851-crore-12898638.html",
        "Second source: 8.69% of Star Cement for Rs 851 crore, up to 3.7 crore shares at up to Rs 235 each."),
}


def get_pdf(name: str, path: str, log: list[str]) -> Path | None:
    """Return the cached PDF, downloading it once if it is missing."""
    p = CACHE / f"{name}.pdf"
    if p.exists() and p.stat().st_size > 1000:
        return p
    url = HOST + quote(path)
    r = requests.get(url, headers=UA, timeout=180)
    if r.status_code != 200 or r.content[:5] != b"%PDF-":
        log.append(f"PDF {name}: download failed status={r.status_code} {url}")
        return None
    p.write_bytes(r.content)
    time.sleep(1.0)
    return p


def extract(src: Path, pages: list[int] | None, out: Path) -> int:
    """Write the selected 1-indexed pages of src to out (whole file if pages is None); return page count."""
    doc = fitz.open(src)
    if pages is None:
        out.write_bytes(src.read_bytes())
        return doc.page_count
    new = fitz.open()
    for pg in pages:
        new.insert_pdf(doc, from_page=pg - 1, to_page=pg - 1)
    new.set_metadata({"title": f"Extract of {src.name}, PDF pages {pages}", "producer": "PyMuPDF page extract"})
    new.save(out, garbage=4, deflate=True)
    return len(pages)


def clean_html(text: str, url: str) -> str:
    """Drop scripts, styles and media so saved pages stay small; keep the readable text and a source-url tag."""
    soup = BeautifulSoup(text, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "link", "img", "picture", "video"]):
        tag.decompose()
    meta = soup.new_tag("meta")
    meta.attrs["name"] = "source-url"
    meta.attrs["content"] = url
    if soup.head:
        soup.head.insert(0, meta)
    return str(soup)


def main() -> None:
    log: list[str] = [f"run {time.strftime('%Y-%m-%d %H:%M')} cache={CACHE}"]
    manifest: dict = {"pdfs": {}, "pages": {}}
    for name, (path, pages, outname) in PDFS.items():
        url = HOST + quote(path)
        try:
            src = get_pdf(name, path, log)
            if src is None:
                manifest["pdfs"][name] = {"url": url, "status": "failed"}
                continue
            n = extract(src, pages, FIL / outname)
            size = (FIL / outname).stat().st_size
            total_pages = fitz.open(src).page_count
            log.append(f"PDF {name}: {outname} pages={pages or 'all'} ({n} of {total_pages}) size={size/1e6:.2f} MB")
            manifest["pdfs"][name] = {"url": url, "file": outname, "pages": pages or "all",
                                      "pdf_pages_total": total_pages, "size_mb": round(size / 1e6, 2)}
        except Exception as exc:  # noqa: BLE001
            log.append(f"PDF {name}: ERROR {exc}")
    for stem, (url, note) in PAGES.items():
        try:
            r = requests.get(url, headers=UA, timeout=60)
            if r.status_code != 200 or len(r.text) < 2000:
                raise RuntimeError(f"status {r.status_code}, {len(r.text)} chars")
            html = clean_html(r.text, url)
            (NEWS / f"{stem}.html").write_text(html, encoding="utf-8")
            log.append(f"PAGE {stem}: saved {len(html)/1e3:.0f} KB (raw {len(r.text)/1e3:.0f} KB)")
            manifest["pages"][stem] = {"url": url, "status": "saved", "file": f"{stem}.html", "fact": note}
        except Exception as exc:  # noqa: BLE001
            md = (f"# {stem}\n\nURL: {url}\n\nThe site blocked or failed the download on "
                  f"{time.strftime('%d-%b-%Y')} ({exc}).\n\nFact used: {note}\n")
            (NEWS / f"{stem}.md").write_text(md, encoding="utf-8")
            log.append(f"PAGE {stem}: blocked -> wrote .md ({exc})")
            manifest["pages"][stem] = {"url": url, "status": f"blocked: {exc}", "file": f"{stem}.md", "fact": note}
        time.sleep(1.0)
    (ROOT / "data" / "raw").mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "raw" / "filings_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (ROOT / "data" / "raw" / "fetch_filings.log").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    main()
