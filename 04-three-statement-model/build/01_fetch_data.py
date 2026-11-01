"""Fetch UltraTech Cement (NSE: ULTRACEMCO) consolidated financials and market data (network step).

Raw downloads (audit trail) go to source_data/, parsed tables to data/raw/:
  source_data/screener/raw/ULTRACEMCO_consolidated.html        raw Screener page
  source_data/screener/raw/ULTRACEMCO_schedule_<sec>_<parent>.json   schedules API (line-item breakdowns)
  source_data/stockanalysis/raw/<page>.html                    raw stockanalysis.com pages (S&P Global data)
  source_data/yahoo_finance/ULTRACEMCO_NS_daily.csv            daily prices (yfinance, auto_adjust=False)
  source_data/yahoo_finance/quote_30Oct2026.json               close on 30-Oct-2026
  data/raw/screener/ULTRACEMCO_<section>.csv                   quarters, profit-loss, balance-sheet, cash-flow, ratios (Rs crore)
  data/raw/screener/screener_summary.json                      top ratios, company id, fetch time
  data/raw/stockanalysis/<page>_table<i>.csv                   every table on each page (INR millions)

Run:  python build/01_fetch_data.py
"""
from __future__ import annotations

import io
import json
import re
import shutil
import time
import traceback
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests
from bs4 import BeautifulSoup

SYMBOL = "ULTRACEMCO"
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "source_data"
SCR_RAW = SRC / "screener" / "raw"
SA_RAW = SRC / "stockanalysis" / "raw"
YF = SRC / "yahoo_finance"
SCR = ROOT / "data" / "raw" / "screener"
SA = ROOT / "data" / "raw" / "stockanalysis"
for d in (SCR_RAW, SA_RAW, YF, SCR, SA):
    d.mkdir(parents=True, exist_ok=True)

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130 Safari/537.36"
    )
}
SECTIONS = ["quarters", "profit-loss", "balance-sheet", "cash-flow", "ratios"]
SCHEDULES = {
    "profit-loss": ["Sales", "Expenses", "Material Cost %", "Other Income", "Net Profit"],
    "quarters": ["Sales", "Expenses", "Other Income", "Net Profit"],
    "balance-sheet": ["Borrowings", "Other Liabilities", "Fixed Assets", "Other Assets", "Investments", "Trade receivables"],
    "cash-flow": [
        "Cash from Operating Activity",
        "Cash from Investing Activity",
        "Cash from Financing Activity",
    ],
}
SA_BASE = f"https://stockanalysis.com/quote/nse/{SYMBOL}/"
SA_PAGES = {
    # 'financials/' is an overview page (summary rows + segment revenue);
    # the full income statement sits under 'financials/income-statement/'.
    "overview_annual": "financials/",
    "income_annual": "financials/income-statement/",
    "income_quarterly": "financials/income-statement/?p=quarterly",
    "balance_annual": "financials/balance-sheet/",
    "balance_quarterly": "financials/balance-sheet/?p=quarterly",
    "cashflow_annual": "financials/cash-flow-statement/",
    # quarterly cash flow is empty for Indian filers (cash flow is reported half-yearly)
    "ratios_annual": "financials/ratios/",
    "statistics": "statistics/",
    "forecast": "forecast/",
}
VALUATION_DATE = "2026-10-30"


def to_number(x: object) -> float | None:
    """Convert a Screener cell ('1,234', '12%', '') to float or None."""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    s = str(x).replace(",", "").replace("%", "").strip()
    if s in ("", "-", "--"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_section(soup: BeautifulSoup, sec_id: str) -> pd.DataFrame | None:
    """Parse one Screener data table into a tidy DataFrame (first column = item)."""
    sec = soup.find("section", id=sec_id)
    if sec is None:
        return None
    table = sec.find("table", class_=re.compile("data-table"))
    if table is None:
        return None
    df = pd.read_html(io.StringIO(str(table)))[0]
    df = df.rename(columns={df.columns[0]: "item"})
    df["item"] = (
        df["item"].astype(str).str.replace(r"\s*\+\s*$", "", regex=True).str.replace("\xa0", " ").str.strip()
    )
    df = df[df["item"].str.lower() != "raw pdf"]
    for c in df.columns[1:]:
        df[c] = df[c].map(to_number)
    return df


def parse_top_ratios(soup: BeautifulSoup) -> dict:
    """Return the 'top ratios' box (market cap, price, P/E ...)."""
    res: dict = {}
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


def fetch_screener(log: list[str]) -> None:
    """Consolidated Screener page, tables, and schedules API breakdowns."""
    url = f"https://www.screener.in/company/{SYMBOL}/consolidated/"
    r = requests.get(url, headers=UA, timeout=40)
    r.raise_for_status()
    (SCR_RAW / f"{SYMBOL}_consolidated.html").write_text(r.text, encoding="utf-8")
    soup = BeautifulSoup(r.text, "lxml")
    info: dict = {"url": url, "fetched_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())}
    h1 = soup.find("h1")
    info["name"] = h1.get_text(strip=True) if h1 else SYMBOL
    info["top_ratios"] = parse_top_ratios(soup)
    for sec in SECTIONS:
        df = parse_section(soup, sec)
        if df is None:
            info[f"{sec}_shape"] = None
            continue
        df.to_csv(SCR / f"{SYMBOL}_{sec}.csv", index=False)
        info[f"{sec}_shape"] = list(df.shape)
        info[f"{sec}_columns"] = [str(c) for c in df.columns]
    m = re.search(r'data-company-id="(\d+)"', r.text)
    cid = m.group(1) if m else None
    info["company_id"] = cid
    log.append(f"screener page ok, company_id={cid}")
    # Consolidated schedules: '&consolidated=true' (tested 1-Nov-2026: '', '=' and '=true' all return data
    # for ULTRACEMCO; '=true' is used so the consolidated numbers are explicit).
    sched_log = {}
    if cid:
        for section, parents in SCHEDULES.items():
            for parent in parents:
                api = (
                    f"https://www.screener.in/api/company/{cid}/schedules/"
                    f"?parent={quote(parent)}&section={section}&consolidated=true"
                )
                try:
                    rr = requests.get(api, headers=UA, timeout=40)
                    ok = rr.status_code == 200
                    data = rr.json() if ok else None
                except Exception as exc:  # noqa: BLE001
                    ok, data = False, {"error": str(exc)}
                safe = parent.replace(" ", "_").replace("%", "pct")
                fname = f"{SYMBOL}_schedule_{section}_{safe}.json"
                (SCR_RAW / fname).write_text(json.dumps({"url": api, "data": data}, indent=2), encoding="utf-8")
                sched_log[f"{section}|{parent}"] = {
                    "ok": ok,
                    "keys": list(data.keys()) if isinstance(data, dict) else None,
                }
                time.sleep(1.0)
    info["schedules"] = sched_log
    (SCR / "screener_summary.json").write_text(json.dumps({SYMBOL: info}, indent=2), encoding="utf-8")
    for k, v in sched_log.items():
        log.append(f"schedule {k}: {v}")


def fetch_stockanalysis(log: list[str]) -> None:
    """Save every table (parsed CSV) and the raw html of each stockanalysis.com page."""
    for old in list(SA.glob("*_table*.csv")) + list(SA_RAW.glob("*.html")):
        old.unlink()  # clear stale snapshots so table numbering always matches the current pages
    for name, page in SA_PAGES.items():
        url = SA_BASE + page
        try:
            r = requests.get(url, headers=UA, timeout=40)
            log.append(f"stockanalysis {name}: status={r.status_code} len={len(r.text)} url={url}")
            if r.status_code != 200:
                continue
            (SA_RAW / f"{name}.html").write_text(r.text, encoding="utf-8")
            try:
                tables = pd.read_html(io.StringIO(r.text))
            except ValueError:
                tables = []
            for i, t in enumerate(tables):
                if isinstance(t.columns, pd.MultiIndex):
                    t.columns = [" | ".join(str(x) for x in c if "Unnamed" not in str(x)) for c in t.columns]
                t.to_csv(SA / f"{name}_table{i}.csv", index=False)
                log.append(f"  table{i} shape={t.shape}")
            time.sleep(1.5)
        except Exception:  # noqa: BLE001
            log.append(f"stockanalysis {name}: FAILED {traceback.format_exc()}")


def fetch_yahoo(log: list[str]) -> None:
    """Daily prices for ULTRACEMCO.NS; record the 30-Oct-2026 close."""
    import yfinance as yf

    df = yf.download(f"{SYMBOL}.NS", start="2021-01-01", end="2026-10-31",
                     auto_adjust=False, progress=False, actions=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.to_csv(YF / f"{SYMBOL}_NS_daily.csv")
    sub = df.loc[:VALUATION_DATE]
    last = sub.iloc[-1]
    win = df.loc[pd.Timestamp(VALUATION_DATE) - pd.Timedelta(days=365):VALUATION_DATE]
    info = {
        "ticker": f"{SYMBOL}.NS",
        "source": "Yahoo Finance via yfinance (auto_adjust=False)",
        "url": f"https://finance.yahoo.com/quote/{SYMBOL}.NS/history/",
        "fetched_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        "close_date": str(sub.index[-1].date()),
        "close": round(float(last["Close"]), 2),
        "adj_close": round(float(last["Adj Close"]), 2),
        "high_52w": round(float(win["High"].max()), 2),
        "low_52w": round(float(win["Low"].min()), 2),
        "dividends": {str(k.date()): float(v) for k, v in df["Dividends"][df["Dividends"] > 0].items()},
    }
    (YF / "quote_30Oct2026.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    log.append("yahoo: " + json.dumps(info))


def main() -> None:
    log: list[str] = []
    for fn in (fetch_screener, fetch_stockanalysis, fetch_yahoo):
        try:
            fn(log)
        except Exception:  # noqa: BLE001
            log.append(f"{fn.__name__} FAILED {traceback.format_exc()}")
    # remove the layout of an earlier run (raw html used to live under data/raw/)
    for stale in [ROOT / "data" / "raw" / "yahoo_finance"]:
        if stale.exists():
            shutil.rmtree(stale)
    for stale in list(SCR.glob("*.html")) + list(SCR.glob("*_schedule_*.json")) + list(SA.glob("*.html")):
        stale.unlink()
    (ROOT / "data" / "raw" / "fetch_data.log").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    main()
