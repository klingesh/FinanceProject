"""Download the raw source files used by this project into source_data/ (the only online step).

Everything after this step (prepare_data.py, build_model.py, ...) runs offline from the saved files.
Re-running this script pulls whatever the websites show on the day you run it, so numbers can change;
the snapshot used for the published model was downloaded on 1-Nov-2026 (prices = 30-Oct-2026 close).

Usage:
    python build/fetch_sources.py screener schedules stockanalysis yahoo filings macro
    (pass any subset of the section names; no argument = all sections)
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "source_data"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/130 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"}

# NSE symbol -> display name. Screener and stockanalysis.com use the same NSE symbols.
COMPANIES = {
    "ASIANPAINT": "Asian Paints",
    "BERGEPAINT": "Berger Paints India",
    "KANSAINER": "Kansai Nerolac Paints",
    "JSWDULUX": "JSW Dulux (formerly Akzo Nobel India)",
    "INDIGOPNTS": "Indigo Paints",
}
SCREENER_SECTIONS = ["quarters", "profit-loss", "balance-sheet", "cash-flow", "ratios", "shareholding"]
# Screener pages also fetched in standalone form (to compare with consolidated)
SCREENER_STANDALONE_TOO = ["INDIGOPNTS", "JSWDULUX"]
SCHEDULE_PARENTS = [
    ("Borrowings", "balance-sheet"),
    ("Other Liabilities", "balance-sheet"),
    ("Investments", "balance-sheet"),
    ("Other Assets", "balance-sheet"),
    ("Fixed Assets", "balance-sheet"),
    ("Expenses", "profit-loss"),
    ("Other Income", "profit-loss"),
    ("Sales", "quarters"),
    ("Expenses", "quarters"),
    ("Other Income", "quarters"),
    ("Net Profit", "quarters"),
    ("Cash from Operating Activity", "cash-flow"),
    ("Cash from Investing Activity", "cash-flow"),
    ("Cash from Financing Activity", "cash-flow"),
]
SA_PAGES = {
    "statistics": "statistics/",
    "income_annual": "financials/",
    "income_quarterly": "financials/?p=quarterly",
    "balance_annual": "financials/balance-sheet/",
    "balance_quarterly": "financials/balance-sheet/?p=quarterly",
    "cashflow_annual": "financials/cash-flow-statement/",
    "ratios_annual": "financials/ratios/",
    "forecast": "forecast/",
}
YAHOO = {"ASIANPAINT.NS": "Asian Paints", "BERGEPAINT.NS": "Berger Paints", "KANSAINER.NS": "Kansai Nerolac",
         "JSWDULUX.NS": "JSW Dulux", "INDIGOPNTS.NS": "Indigo Paints", "^NSEI": "NIFTY 50"}
YAHOO_START, YAHOO_END = "2021-01-01", "2026-10-31"  # end is exclusive -> last row 30-Oct-2026


def get(url: str, **kw) -> requests.Response:
    """GET with a browser User-Agent and one retry."""
    for attempt in range(2):
        try:
            r = requests.get(url, headers={**UA, **kw.pop("headers", {})}, timeout=60, **kw)
            return r
        except requests.RequestException:
            if attempt:
                raise
            time.sleep(3)
    raise RuntimeError("unreachable")


def to_number(x):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    s = str(x).replace(",", "").replace("%", "").strip()
    if s in ("", "-", "--"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ----------------------------------------------------------------------------------------------
# Screener.in (same parsing as d:/Financeprojects/_scratch/fetch_screener.py, plus standalone)
# ----------------------------------------------------------------------------------------------
def parse_screener_section(soup: BeautifulSoup, sec_id: str) -> pd.DataFrame | None:
    sec = soup.find("section", id=sec_id)
    if sec is None:
        return None
    table = sec.find("table", class_=re.compile("data-table"))
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


def parse_top_ratios(soup: BeautifulSoup) -> dict:
    res = {}
    ul = soup.find("ul", id="top-ratios")
    if ul is None:
        return res
    for li in ul.find_all("li"):
        name = li.find("span", class_="name")
        val = li.find("span", class_=re.compile("value"))
        if not name or not val:
            continue
        key = " ".join(name.get_text(" ", strip=True).split())
        txt = " ".join(val.get_text(" ", strip=True).split())
        nums = [to_number(n) for n in re.findall(r"[-\d,]+\.?\d*", txt)]
        res[key] = {"text": txt, "numbers": [n for n in nums if n is not None]}
    return res


def fetch_screener() -> None:
    out = SRC / "screener"
    raw = out / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    summary = {}
    jobs = [(s, "consolidated") for s in COMPANIES] + [(s, "standalone") for s in SCREENER_STANDALONE_TOO]
    for sym, basis in jobs:
        url = f"https://www.screener.in/company/{sym}/" + ("consolidated/" if basis == "consolidated" else "")
        r = get(url)
        r.raise_for_status()
        tag = f"{sym}_{basis}"
        (raw / f"{tag}.html").write_text(r.text, encoding="utf-8")
        soup = BeautifulSoup(r.text, "lxml")
        info = {"url": url, "basis": basis, "fetched_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())}
        h1 = soup.find("h1")
        info["name"] = h1.get_text(strip=True) if h1 else sym
        info["top_ratios"] = parse_top_ratios(soup)
        for sec in SCREENER_SECTIONS:
            df = parse_screener_section(soup, sec)
            if df is None:
                info[f"{sec}_shape"] = None
                continue
            name = f"{sym}_{sec}.csv" if basis == "consolidated" else f"{sym}_standalone_{sec}.csv"
            df.to_csv(out / name, index=False)
            info[f"{sec}_shape"] = list(df.shape)
            info[f"{sec}_columns"] = [str(c) for c in df.columns]
        m = re.search(r'data-company-id="(\d+)"', r.text)
        info["company_id"] = m.group(1) if m else None
        summary[tag] = info
        print("screener", tag, info.get("profit-loss_shape"))
        time.sleep(1.5)
    (out / "screener_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


def fetch_schedules() -> None:
    """Line-item breakdowns (borrowings incl. leases, investments, cash...) from Screener's schedules API.

    Files already saved with HTTP 200 are kept; rate-limited calls (HTTP 429) are retried with a pause.
    """
    out = SRC / "screener" / "schedules"
    out.mkdir(parents=True, exist_ok=True)
    summary = json.loads((SRC / "screener" / "screener_summary.json").read_text(encoding="utf-8"))
    log = []
    for tag, info in summary.items():
        cid = info.get("company_id")
        basis = info.get("basis", "consolidated")
        sym = tag.split("_")[0]
        if not cid:
            continue
        flag = "&consolidated=true" if basis == "consolidated" else ""
        for parent, section in SCHEDULE_PARENTS:
            fname = f"{sym}_{basis}_{section}_{parent.replace(' ', '_')}.json"
            path = out / fname
            if path.exists() and json.loads(path.read_text(encoding="utf-8")).get("status") == 200:
                log.append(f"{fname}: kept (already downloaded)")
                continue
            url = (f"https://www.screener.in/api/company/{cid}/schedules/?parent={requests.utils.quote(parent)}"
                   f"&section={section}{flag}")
            for attempt in range(4):
                r = get(url)
                if r.status_code != 429:
                    break
                time.sleep(15 * (attempt + 1))
            try:
                data = r.json()
            except ValueError:
                data = {"_error": r.text[:300]}
            path.write_text(json.dumps({"url": url, "status": r.status_code, "data": data}, indent=2),
                            encoding="utf-8")
            log.append(f"{fname}: status={r.status_code} keys={list(data)[:8] if isinstance(data, dict) else data}")
            time.sleep(2.5)
    (out / "_schedules_log.txt").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


# ----------------------------------------------------------------------------------------------
# stockanalysis.com (S&P Global Market Intelligence data)
# ----------------------------------------------------------------------------------------------
def fetch_stockanalysis() -> None:
    out = SRC / "stockanalysis"
    raw = out / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    log = []
    for sym in COMPANIES:
        for key, page in SA_PAGES.items():
            url = f"https://stockanalysis.com/quote/nse/{sym}/{page}"
            r = get(url)
            log.append(f"{sym} {key} {url} -> {r.status_code} len={len(r.text)}")
            if r.status_code != 200:
                continue
            (raw / f"{sym}_{key}.html").write_text(r.text, encoding="utf-8")
            try:
                tables = pd.read_html(io.StringIO(r.text))
            except ValueError:
                tables = []
            for i, t in enumerate(tables):
                if isinstance(t.columns, pd.MultiIndex):
                    t.columns = [" | ".join(str(x) for x in col if not str(x).startswith("Unnamed")).strip()
                                 for col in t.columns]
                t.to_csv(raw / f"{sym}_{key}_table{i}.csv", index=False)
            log.append(f"   tables={len(tables)}")
            time.sleep(1.2)
    (out / "_fetch_log.txt").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


# ----------------------------------------------------------------------------------------------
# Yahoo Finance daily prices (yfinance)
# ----------------------------------------------------------------------------------------------
def fetch_yahoo() -> None:
    import yfinance as yf

    out = SRC / "yahoo_finance"
    out.mkdir(parents=True, exist_ok=True)
    log = []
    for t, name in YAHOO.items():
        df = yf.download(t, start=YAHOO_START, end=YAHOO_END, auto_adjust=False, progress=False, actions=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        fname = t.replace("^", "IDX_") + "_daily.csv"
        df.to_csv(out / fname)
        log.append(f"{t} ({name}): rows={len(df)} first={df.index.min().date()} last={df.index.max().date()} "
                   f"last_close={df['Close'].iloc[-1]:.2f} splits={int((df.get('Stock Splits', 0) > 0).sum())} "
                   f"divs={int((df.get('Dividends', 0) > 0).sum())}")
    (out / "_fetch_log.txt").write_text(
        f"Downloaded with yfinance {yf.__version__} on {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}; "
        f"start={YAHOO_START}, end(exclusive)={YAHOO_END}, auto_adjust=False\n" + "\n".join(log), encoding="utf-8")
    print("\n".join(log))


# ----------------------------------------------------------------------------------------------
# Company filings (PDF) and macro / news pages (HTML)
# ----------------------------------------------------------------------------------------------
NSE_ARCHIVE = "https://nsearchives.nseindia.com/corporate/"
FILINGS = {
    # Asian Paints board-meeting outcome: audited standalone + unaudited consolidated results for Q2/H1 FY27,
    # balance sheet at 30-Sep-2026, cash flow statement, and the press release (pages 17-20). Filed 29-Oct-2026.
    "AsianPaints_Q2FY27_Results_and_Press_Release_29Oct2026.pdf":
        NSE_ARCHIVE + "ASIANPAINT_29102026140213_OutcomeofBM29102026signed.pdf",
    "AsianPaints_Q2FY27_Investor_Presentation_29Oct2026.pdf":
        NSE_ARCHIVE + "ASIANPAINT_29102026164544_SEIntimation_Investor_Presentation_Q2FY26-27pdfsigned.pdf",
    # Indigo Paints results for Q2 FY27 (filed 30-Oct-2026 at 17:41 IST, after the market close)
    "IndigoPaints_Q2FY27_Results_30Oct2026.pdf":
        NSE_ARCHIVE + "INDIGOPNTS_30102026174023_Regulation_30_Outcome_of_Board_Meeting_-_FR-Signed.pdf",
    # Peer filings that show their Q2 FY27 results were still to come on 30-Oct-2026
    "BergerPaints_Q2FY27_Analyst_Call_Intimation_30Oct2026.pdf":
        NSE_ARCHIVE + "PAINTBERGE_30102026124130_concallinvite2710Letter.pdf",
    "KansaiNerolac_Q2FY27_Analyst_Call_Intimation_26Oct2026.pdf":
        NSE_ARCHIVE + "KANSAINER_26102026153719_SEintimation_Q2FY27_Invite_signed.pdf",
    "JSWDulux_Q2FY27_Investor_Call_Intimation_29Oct2026.pdf":
        NSE_ARCHIVE + "AKZOINDIA_29102026172646_JSWDuluxInvestorCall4thNov26Intimation.pdf",
}
MACRO_PAGES = {
    # 10-year G-sec yield (risk-free rate), two independent sources plus the news report
    "Investing_India_10Y_bond_historical_data.html":
        "https://in.investing.com/rates-bonds/india-10-year-bond-yield-historical-data",
    "TradingEconomics_India_10Y_bond_yield.html": "https://tradingeconomics.com/india/government-bond-yield",
    "ETBFSI_Reuters_India_bonds_October_2026.html":
        "https://bfsi.economictimes.indiatimes.com/articles/india-bonds-buckle-for-fourth-straight-month-on-oils-climb/135363689",
    "FinancialExpress_Gsec_yields_October_2026.html":
        "https://www.financialexpress.com/market/g-sec-yields-spike-30-bps-in-oct-global-cues-rate-hike-fears-weigh-4371647/",
    # Equity risk premium
    "Damodaran_country_risk_premium_Jan2026.html":
        "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ctryprem.html",
    # Asian Paints Q2 FY27 news coverage and management commentary
    "ET_AsianPaints_Q2FY27_results_29Oct2026.html":
        "https://economictimes.indiatimes.com/markets/stocks/earnings/asian-paints-q2-results-net-profit-rises-7-yoy-to-rs-1068-crore-firm-announces-rs-5-75/share-dividend/articleshow/135297927.cms",
    "BusinessStandard_AsianPaints_Q2FY27_29Oct2026.html":
        "https://www.business-standard.com/amp/companies/quarterly-results/asian-paints-q2fy27-result-profit-rises-7-5-to-1-068-cr-sales-grow-17-126102900944_1.html",
    "ET_AsianPaints_brokerages_cut_targets_30Oct2026.html":
        "https://economictimes.indiatimes.com/markets/stocks/news/asian-paints-shares-in-focus-as-jefferies-goldman-sachs-other-brokerages-cut-target-prices-after-q2-results-buy-sell-or-hold/articleshow/135342271.cms",
    "Investing_AsianPaints_Q2FY27_presentation_summary.html":
        "https://au.investing.com/news/stock-market-news/asian-paints-q2-fy27-slides-169-sales-growth-margin-pressure-93CH-4726180",
    # Peers: JSW Dulux rename, 1:10 split, Akzo Nobel India sale; Indigo Q2 timing
    "ET_AkzoNobel_India_renamed_JSW_Dulux_Mar2026.html":
        "https://manufacturing.economictimes.indiatimes.com/news/chemicals/akzo-nobel-india-gets-regulatory-nod-to-change-name-to-jsw-dulux/129502125",
    "Livemint_JSW_Dulux_1for10_split_record_date.html":
        "https://www.livemint.com/market/stock-market-news/jsw-dulux-announced-record-date-for-1-10-stock-split-what-investors-should-know-11790079151086.html",
    "PCImag_AkzoNobel_completes_India_sale_Dec2025.html": "https://www.pcimag.com/articles/114243-akzo-completes-strategic-sale",
    "ETLegal_JSW_Paints_unlisted_completes_AkzoNobel_India.html":
        "https://legal.economictimes.indiatimes.com/news/corporate-business/jsw-paints-completes-acquisition-of-majority-stake-in-akzonobel-india/125909724",
    "BusinessWorld_Grasim_Birla_Opus_FY26.html":
        "https://www.businessworld.in/article/grasim-industries-targets-rs-2-lakh-cr-revenue-in-fy27-birla-620427",
    "Daijiworld_Indigo_Paints_Q2FY27_30Oct2026.html": "https://daijiworld.com/news/newsDisplay?newsID=1333925",
}


def nse_session() -> requests.Session:
    """NSE archive and API calls need the cookies set by a normal page visit."""
    s = requests.Session()
    s.headers.update({**UA, "Accept": "application/json, text/plain, application/pdf, */*",
                      "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements"})
    try:
        s.get("https://www.nseindia.com/companies-listing/corporate-filings-announcements", timeout=30)
    except requests.RequestException:
        pass
    return s


def save_url(url: str, path: Path, session: requests.Session | None = None) -> str:
    getter = session.get if session else (lambda u, **k: get(u, headers={"Accept": "application/pdf,text/html,*/*"}))
    try:
        r = getter(url, timeout=90) if session else getter(url)
    except requests.RequestException as exc:
        return f"FAILED {exc!r} for {url}"
    if r.status_code == 200 and len(r.content) > 1000:
        path.write_bytes(r.content)
        return f"OK {r.status_code} {len(r.content):,} bytes -> {path.name}"
    return f"FAILED {r.status_code} len={len(r.content)} for {url}"


def fetch_filings() -> None:
    out = SRC / "company_filings"
    out.mkdir(parents=True, exist_ok=True)
    s = nse_session()
    log = [f"{name}: {save_url(url, out / name, s)}" for name, url in FILINGS.items()]
    (out / "_fetch_log.txt").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


def fetch_nse() -> None:
    """Corporate announcements 20-31 Oct 2026 (used to date each company's Q2 FY27 results)."""
    out = SRC / "nse"
    out.mkdir(parents=True, exist_ok=True)
    s = nse_session()
    log = []
    for sym in COMPANIES:
        url = (f"https://www.nseindia.com/api/corporate-announcements?index=equities&symbol={sym}"
               f"&from_date=20-10-2026&to_date=31-10-2026")
        r = s.get(url, timeout=40)
        try:
            data = r.json()
        except ValueError:
            data = {"_error": r.text[:300]}
        (out / f"{sym}_announcements_20Oct-31Oct2026.json").write_text(
            json.dumps({"url": url, "status": r.status_code, "data": data}, indent=1), encoding="utf-8")
        n = len(data) if isinstance(data, list) else 0
        log.append(f"{sym}: status={r.status_code} announcements={n}")
        time.sleep(1.5)
    (out / "_fetch_log.txt").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


def fetch_macro() -> None:
    out = SRC / "news_and_macro"
    out.mkdir(parents=True, exist_ok=True)
    log = []
    for name, url in MACRO_PAGES.items():
        log.append(f"{name}: {save_url(url, out / name)}")
        time.sleep(1.0)
    (out / "_fetch_log.txt").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


SECTIONS = {"screener": fetch_screener, "schedules": fetch_schedules, "stockanalysis": fetch_stockanalysis,
            "yahoo": fetch_yahoo, "filings": fetch_filings, "nse": fetch_nse, "macro": fetch_macro}

if __name__ == "__main__":
    chosen = sys.argv[1:] or list(SECTIONS)
    for s in chosen:
        print(f"=== {s}")
        SECTIONS[s]()
    print("FETCH DONE")
