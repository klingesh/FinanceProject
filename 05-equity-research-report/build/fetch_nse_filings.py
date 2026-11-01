"""Download company filings and shareholding data from NSE (www.nseindia.com public APIs).

Step 1 lists corporate announcements for each company in chosen windows and saves the JSON to source_data/nse/.
Step 2 downloads the PDFs listed in FILES (results, press releases, investor presentations, transcripts)
into source_data/company_filings/. Files larger than MAX_MB are not saved; their link is recorded instead.

Run:  python build/fetch_nse_filings.py [list|download|all]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
NSE_DIR = ROOT / "source_data" / "nse"
FIL_DIR = ROOT / "source_data" / "company_filings"
NSE_DIR.mkdir(parents=True, exist_ok=True)
FIL_DIR.mkdir(parents=True, exist_ok=True)
MAX_MB = 19.0

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
}
WINDOWS = {
    "ASIANPAINT": [("20-10-2026", "01-11-2026"), ("20-07-2026", "10-08-2026"), ("20-05-2026", "15-06-2026")],
    "BERGEPAINT": [("15-04-2026", "15-06-2026"), ("15-07-2026", "31-08-2026"), ("15-10-2026", "01-11-2026")],
    "KANSAINER": [("15-04-2026", "15-06-2026"), ("15-07-2026", "31-08-2026"), ("15-10-2026", "01-11-2026")],
    "JSWDULUX": [("15-04-2026", "15-06-2026"), ("15-07-2026", "31-08-2026"), ("15-10-2026", "01-11-2026")],
    "INDIGOPNTS": [("15-04-2026", "15-06-2026"), ("15-07-2026", "31-08-2026"), ("15-10-2026", "01-11-2026")],
}


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    s.get("https://www.nseindia.com/companies-listing/corporate-filings-announcements", timeout=30)
    return s


def list_announcements(s: requests.Session) -> None:
    lines = []
    for sym, wins in WINDOWS.items():
        rows = []
        for a, b in wins:
            url = (f"https://www.nseindia.com/api/corporate-announcements?index=equities&symbol={sym}"
                   f"&from_date={a}&to_date={b}")
            r = s.get(url, timeout=40)
            try:
                js = r.json()
            except ValueError:
                lines.append(f"{sym} {a}-{b}: status {r.status_code}, not JSON")
                continue
            rows.extend(js if isinstance(js, list) else [])
            time.sleep(1.2)
        (NSE_DIR / f"{sym}_announcements_2026.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
        for t in rows:
            lines.append(f"{sym} | {t.get('an_dt')} | {t.get('desc')} | {str(t.get('attchmntText'))[:110]} | "
                         f"{t.get('attchmntFile')} | size={t.get('fileSize')}")
    for sym in ["ASIANPAINT"]:
        for api in ["annual-reports", "corporate-share-holdings-master"]:
            r = s.get(f"https://www.nseindia.com/api/{api}?index=equities&symbol={sym}", timeout=40)
            (NSE_DIR / f"{sym}_{api}.json").write_text(r.text, encoding="utf-8")
            time.sleep(1.2)
    (ROOT / "build" / "_nse_listing.txt").write_text("\n".join(lines), encoding="utf-8")
    print("listed", len(lines))


# (local file name, URL) - chosen from the listing; see source_data/README.md for what each file is.
FILES = [
    ("AsianPaints_Q2FY27_Financial_Results_29Oct2026.pdf",
     "https://nsearchives.nseindia.com/corporate/ASIANPAINT_29102026140213_OutcomeofBM29102026signed.pdf"),
    ("AsianPaints_Q2FY27_Press_Release_29Oct2026.pdf",
     "https://nsearchives.nseindia.com/corporate/ASIANPAINT_29102026141409_OutcomeofBM29102026signed.pdf"),
    ("AsianPaints_Q2FY27_Investor_Presentation_29Oct2026.pdf",
     "https://nsearchives.nseindia.com/corporate/ASIANPAINT_29102026164544_SEIntimation_Investor_Presentation_Q2FY26-27pdfsigned.pdf"),
    ("AsianPaints_Q2FY27_Call_Recording_Link_29Oct2026.pdf",
     "https://nsearchives.nseindia.com/corporate/ASIANPAINT_29102026211830_SE_intimation__Audio_Recording_Q2FY26-27signed.pdf"),
    ("AsianPaints_Q1FY27_Press_Release_29Jul2026.pdf",
     "https://nsearchives.nseindia.com/corporate/ASIANPAINT_29072026140548_SEintimationJune26.pdf"),
    ("AsianPaints_Q1FY27_Investor_Presentation_29Jul2026.pdf",
     "https://nsearchives.nseindia.com/corporate/ASIANPAINT_29072026165710_Intimation_Investor_Presentation_Q1FY26-27finsigned.pdf"),
    ("AsianPaints_Q4FY26_Results_and_Press_Release_29May2026.pdf",
     "https://nsearchives.nseindia.com/corporate/ASIANPAINT_29052026140521_SEIntimationoutcomeFY26.pdf"),
    ("AsianPaints_Q4FY26_Investor_Presentation_29May2026.pdf",
     "https://nsearchives.nseindia.com/corporate/ASIANPAINT_29052026165558_SEintimationInvestorPresentation_Q4FY26finalfinal.pdf"),
    ("AsianPaints_Q4FY26_Earnings_Call_Transcript_29May2026.pdf",
     "https://nsearchives.nseindia.com/corporate/ASIANPAINT_03062026154629_Reg30_Transcript_Q4FY26.pdf"),
    ("AsianPaints_BRSR_FY2025-26.pdf",
     "https://nsearchives.nseindia.com/corporate/ASIANPAINT_12062026163131_SEIntimationBRSR202526signed.pdf"),
    ("AsianPaints_Integrated_Annual_Report_FY2025-26.pdf",
     "https://nsearchives.nseindia.com/annual_reports/AR_29385_ASIANPAINT_2025_2026_A_26278926_12062026160918.pdf"),
]


PEER_FILES = [
    ("peers/BergerPaints_Q4FY26_Financial_Results_12May2026.pdf",
     "https://nsearchives.nseindia.com/corporate/PAINTBERGE_12052026152354_ResultsFinal.pdf"),
    ("peers/KansaiNerolac_Q4FY26_Results_and_Press_Release_06May2026.pdf",
     "https://nsearchives.nseindia.com/corporate/KANSAINER_06052026164550_Outcome_BM_6that_may_2026signed.pdf"),
    ("peers/JSWDulux_Q4FY26_Financial_Results_13May2026.pdf",
     "https://nsearchives.nseindia.com/corporate/AKZOINDIA_13052026221122_JSWDuluxOutcomeofBoardMeeting13May26.pdf"),
    ("peers/JSWDulux_Q4FY26_Investor_Presentation_13May2026.pdf",
     "https://nsearchives.nseindia.com/corporate/AKZOINDIA_13052026230002_JSWDuluxInvestorCall14May26Presentation.pdf"),
    ("peers/IndigoPaints_Q4FY26_Financial_Results_22May2026.pdf",
     "https://nsearchives.nseindia.com/corporate/INDIGOPNTS_22052026201253_BM_Outcome_M26.pdf"),
    ("peers/IndigoPaints_Q2FY27_Investor_Presentation_30Oct2026.pdf",
     "https://nsearchives.nseindia.com/corporate/INDIGOPNTS_30102026184320_Indigo_Intimation_Presentation_of_Transcript_call-Signed.pdf"),
]


def download(s: requests.Session, files: list[tuple[str, str]], max_mb: float, log_name: str) -> None:
    """Save each PDF untouched. Files above max_mb go to _scratch/p05/big_files (outside the repo);
    build/trim_source_data.py then keeps only the pages the report uses, and the link is recorded."""
    log = []
    big = ROOT.parent.parent.parent / "_scratch" / "p05" / "big_files"
    big.mkdir(parents=True, exist_ok=True)
    for name, url in files:
        try:
            r = s.get(url, timeout=120)
        except requests.RequestException as e:
            log.append(f"FAIL {name}: {e!r}")
            continue
        mb = len(r.content) / 1e6
        ok = r.status_code == 200 and r.content[:4] == b"%PDF"
        if not ok:
            log.append(f"FAIL {name}: status {r.status_code}, head {r.content[:20]!r}")
            continue
        target = (big / Path(name).name) if mb > max_mb else (FIL_DIR / name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(r.content)
        log.append(f"{'BIG ' if mb > max_mb else 'OK  '} {name}: {mb:.2f} MB -> {target}")
        time.sleep(1.5)
    (ROOT / "build" / log_name).write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    ses = session()
    if mode in ("list", "all"):
        list_announcements(ses)
    if mode in ("download", "all"):
        download(ses, FILES, MAX_MB, "_nse_download_log.txt")
    if mode in ("peers", "all"):
        download(ses, PEER_FILES, 7.0, "_nse_download_peers_log.txt")
