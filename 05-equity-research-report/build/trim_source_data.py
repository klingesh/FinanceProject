"""Shrink source_data/ below GitHub-friendly limits (whole folder < 40 MB, no file > 20 MB) without losing a cited page.

Run after build/fetch_*.py (each step is skipped when it is already done, so re-running is safe):
1. Q2 FY27: NSE's "results" and "press release" downloads of 29-Oct-2026 are byte-identical. One copy is kept, image-
   compressed, as AsianPaints_Q2FY27_Results_and_Press_Release_29Oct2026.pdf (the name the data files cite).
2. Large PDFs that are cited in full are image-compressed in place (110 dpi, JPEG quality 60). The text layer, page
   count and page order do not change, so every page reference in data/ stays valid (checked page by page).
3. Large documents where only a few pages are used are saved as page extracts (EXTRACTS; the original page numbers
   are listed in source_data/README.md and the full document stays at its link).
4. Files that no number in this project uses (UNUSED) move to the archive folder outside the repository; their links
   stay in source_data/README.md.
Originals are moved to the archive folder, never deleted. Prints the folder size and the largest files at the end.

Run:  python build/trim_source_data.py [--archive-dir <folder outside the repo>] [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
SD = ROOT / "source_data"
CF = SD / "company_filings"
ARCHIVE_DEFAULT = ROOT.parents[2] / "_scratch" / "p05" / "big_files"   # same folder build/fetch_nse_filings.py uses
DPI, QUALITY = 110, 60
LIMIT_TOTAL_MB, LIMIT_FILE_MB = 40.0, 20.0

Q2_SOURCES = ["AsianPaints_Q2FY27_Financial_Results_29Oct2026.pdf", "AsianPaints_Q2FY27_Press_Release_29Oct2026.pdf"]
Q2_TARGET = "AsianPaints_Q2FY27_Results_and_Press_Release_29Oct2026.pdf"
COMPRESS = ["AsianPaints_Q4FY26_Results_and_Press_Release_29May2026.pdf",
            "AsianPaints_Q4FY26_Earnings_Call_Transcript_29May2026.pdf",
            "peers/BergerPaints_Q4FY26_Financial_Results_12May2026.pdf",
            "peers/JSWDulux_Q4FY26_Financial_Results_13May2026.pdf"]
# (extract written to company_filings/, original file name, pages kept in the original's 1-based numbering)
EXTRACTS = [
    ("AsianPaints_Annual_Report_FY2025-26_extract.pdf", "AsianPaints_Integrated_Annual_Report_FY2025-26.pdf",
     [1, 5, 10, 18, 30, 44, 165]),
    ("peers/KansaiNerolac_Q4FY26_Results_extract.pdf", "KansaiNerolac_Q4FY26_Results_and_Press_Release_06May2026.pdf",
     [1, 2, 14, 15, 16, 17, 18, 19]),
    ("peers/KansaiNerolac_Q4FY25_Results_extract.pdf", "KansaiNerolac_Q4FY25_Results_May2025.pdf", [1, 14, 15, 16]),
    ("peers/IndigoPaints_Q4FY26_Financial_Results_extract.pdf", "IndigoPaints_Q4FY26_Financial_Results_22May2026.pdf",
     [1, 13, 14, 15, 16]),
]
# Downloaded but not used for any number in this project (links in source_data/README.md)
UNUSED = ["company_filings/AsianPaints_Q1FY27_Investor_Presentation_29Jul2026.pdf",
          "company_filings/AsianPaints_Q1FY27_Press_Release_29Jul2026.pdf",
          "company_filings/AsianPaints_Q4FY26_Investor_Presentation_29May2026.pdf",
          "company_filings/AsianPaints_BRSR_FY2025-26.pdf",
          "company_filings/peers/IndigoPaints_Q2FY27_Investor_Presentation_30Oct2026.pdf",
          "company_filings/peers/JSWDulux_Q4FY26_Investor_Presentation_13May2026.pdf"]
# Raw web pages behind no number (their tables are still in the .xlsx exports and data/): StockAnalysis pages other
# than the income statement and balance sheet (plus Asian Paints' forecast and dividend pages), and Screener
# standalone pages except Indigo Paints (standalone for FY2021-FY2023).
SA_KEEP = {f"{s}_{p}.html" for s in ["ASIANPAINT", "BERGEPAINT", "KANSAINER", "JSWDULUX", "INDIGOPNTS"]
           for p in ["income", "balance"]} | {"ASIANPAINT_forecast.html", "ASIANPAINT_dividend.html"}
SCR_KEEP_STANDALONE = {"INDIGOPNTS_standalone.html"}


def page_text(page: pymupdf.Page) -> str:
    """Words on the page outside form widgets. Digital-signature stamps are widgets: page extracts do not carry them
    (and any re-saved PDF no longer validates the signature), so they are left out on both sides of the check."""
    boxes = [w.rect for w in page.widgets()]
    words = [w for w in page.get_text("words")
             if not any(b.contains(pymupdf.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2)) for b in boxes)]
    return " ".join(w[4] for w in words)


def page_texts(doc: pymupdf.Document) -> list[str]:
    return [page_text(p) for p in doc]


def compressed_copy(src: Path, dst: Path, pages: list[int] | None = None) -> str:
    """Write an image-compressed copy (optionally of selected pages) and check that the text of each page is kept."""
    doc = pymupdf.open(src)
    if pages:
        new = pymupdf.open()
        for p in pages:
            new.insert_pdf(doc, from_page=p - 1, to_page=p - 1)
        before = [page_text(doc[p - 1]) for p in pages]
        doc = new
    else:
        before = page_texts(doc)
    try:
        doc.rewrite_images(dpi_threshold=DPI + 10, dpi_target=DPI, quality=QUALITY)
    except Exception as e:  # noqa: BLE001 - keep the uncompressed pages if MuPDF cannot rewrite an image
        print(f"  note: image rewrite skipped for {src.name}: {e!r}")
    tmp = dst.with_suffix(".tmp.pdf")
    doc.save(tmp, garbage=4, deflate=True, deflate_images=True, deflate_fonts=True)
    after = page_texts(pymupdf.open(tmp))
    if after != before:
        tmp.unlink()
        raise RuntimeError(f"text changed while compressing {src.name}")
    tmp.replace(dst)
    return f"{src.stat().st_size / 1e6:.2f} MB -> {dst.stat().st_size / 1e6:.2f} MB ({len(after)} pages, text identical)"


def archive(path: Path, archive_dir: Path, dry: bool) -> str:
    target = archive_dir / path.relative_to(SD)
    if dry:
        return f"would move {path.relative_to(SD)} -> {target}"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    shutil.move(str(path), str(target))
    return f"moved {path.relative_to(SD)} -> {target}"


def find_original(name: str, archive_dir: Path) -> Path | None:
    for cand in [CF / name, CF / "peers" / name, archive_dir / name, archive_dir / "company_filings" / name,
                 archive_dir / "company_filings" / "peers" / name]:
        if cand.exists():
            return cand
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive-dir", default=str(ARCHIVE_DEFAULT), help="folder outside the repository for originals")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    arc, dry = Path(args.archive_dir), args.dry_run
    log: list[str] = []

    # 1. Q2 FY27 duplicate pair -> one compressed copy
    srcs = [CF / n for n in Q2_SOURCES if (CF / n).exists()]
    if srcs and not (CF / Q2_TARGET).exists():
        digests = {hashlib.sha256(p.read_bytes()).hexdigest() for p in srcs}
        log.append(f"Q2 FY27 downloads: {len(srcs)} files, {'identical' if len(digests) == 1 else 'DIFFERENT'}")
        if len(digests) != 1:
            raise SystemExit("Q2 FY27 results and press release differ: keep both and review by hand")
        if not dry:
            log.append(f"  {Q2_TARGET}: " + compressed_copy(srcs[0], CF / Q2_TARGET))
    for p in srcs:
        if (CF / Q2_TARGET).exists() or dry:
            log.append("  " + archive(p, arc, dry))

    # 2. compress in place (original archived first)
    for rel in COMPRESS:
        p = CF / rel
        orig = arc / "company_filings" / rel
        if not p.exists():
            log.append(f"missing {rel}")
            continue
        if orig.exists():
            log.append(f"already compressed: {rel} ({p.stat().st_size / 1e6:.2f} MB)")
            continue
        if dry:
            log.append(f"would compress {rel} ({p.stat().st_size / 1e6:.2f} MB)")
            continue
        orig.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, orig)
        res = compressed_copy(orig, p)
        if p.stat().st_size > 0.9 * orig.stat().st_size:      # less than 10% saved: keep the untouched original
            shutil.copy2(orig, p)
            res += "; saving under 10%, original kept"
        log.append(f"compressed {rel}: {res}")

    # 3. page extracts
    for out_rel, orig_name, pages in EXTRACTS:
        out = CF / out_rel
        if out.exists():
            log.append(f"extract exists: {out_rel} ({out.stat().st_size / 1e6:.2f} MB)")
            continue
        src = find_original(orig_name, arc)
        if src is None:
            log.append(f"MISSING original for {out_rel}: {orig_name} (download it with build/fetch_nse_filings.py)")
            continue
        if dry:
            log.append(f"would extract pages {pages} of {src.name} -> {out_rel}")
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        log.append(f"extract {out_rel} (pages {pages} of {src.name}): " + compressed_copy(src, out, pages))
        if src.is_relative_to(SD):
            log.append("  " + archive(src, arc, dry))

    # 4. unused files and raw pages -> archive
    unused = [SD / r for r in UNUSED]
    unused += [p for p in (SD / "stockanalysis" / "raw").glob("*.html") if p.name not in SA_KEEP]
    unused += [p for p in (SD / "screener" / "raw").glob("*_standalone.html") if p.name not in SCR_KEEP_STANDALONE]
    for p in unused:
        if p.exists():
            log.append(archive(p, arc, dry))

    files = [p for p in SD.rglob("*") if p.is_file()]
    total = sum(p.stat().st_size for p in files) / 1e6
    biggest = sorted(files, key=lambda q: -q.stat().st_size)[:8]
    log.append(f"source_data/: {len(files)} files, {total:.1f} MB (limit {LIMIT_TOTAL_MB:.0f} MB); largest file "
               f"{biggest[0].stat().st_size / 1e6:.1f} MB (limit {LIMIT_FILE_MB:.0f} MB)")
    log += [f"  {q.stat().st_size / 1e6:6.2f} MB  {q.relative_to(SD)}" for q in biggest]
    ok = total < LIMIT_TOTAL_MB and biggest[0].stat().st_size / 1e6 < LIMIT_FILE_MB
    log.append("SIZE CHECK " + ("PASS" if ok else "FAIL"))
    (ROOT / "build" / "_trim_log.txt").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    main()
