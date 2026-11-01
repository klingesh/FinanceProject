"""Download the raw data for the VaR project (run once; needs internet, takes about 5 minutes).

Usage:
    python src/fetch_data.py

Saves:
    data/raw/yahoo_<ticker>.csv            raw Yahoo Finance downloads: the six portfolio ETFs,
                                           the bond-ETF candidates and ^NSEI (trading calendar)
    data/raw/nse_bhavcopy_etf_closes.csv   official NSE closes of the six ETFs taken from daily
                                           bhavcopy files (calendar check, verification, random sample)
    data/raw/nse_requests_log.csv          every NSE file requested and its HTTP status
    data/raw/download_log.json             what was downloaded and when
    data/prices_adjclose.csv, data/metadata.json and outputs/ data-quality tables
                                           (built offline by data_prep.build_dataset)

NSE checks
----------
1. Calendar check: for every calendar date in the window that is not a Yahoo trading day
   (weekends and holidays) the NSE bhavcopy is requested. A file exists only if the exchange
   held a session (e.g. the Sunday Union Budget session of 1-Feb-2026), so a 200 response
   reveals a session that Yahoo is missing; 404 confirms a holiday.
2. Verification: dates where a portfolio ETF has no Yahoo row, a zero-volume row or a large move,
   plus the valuation date and 3-5 June 2024 (EXTRA_VERIFY_DATES).
3. Random sample: 25 Yahoo trading days (seed 42) to measure how often Yahoo matches NSE closes.
"""
from __future__ import annotations

import io
import json
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import config as cfg  # noqa: E402
from src import data_prep as dp  # noqa: E402

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/130 Safari/537.36")
UDIFF_FROM = pd.Timestamp("2024-01-01")  # NSE serves the UDiFF bhavcopy format from early 2024
# Extra dates checked against NSE: on 4-Jun-2024 (general election results) NIFTYBEES fell 2.97% while
# the NIFTY 50 fell 5.93%, so the closes of 3, 4 and 5 June 2024 are confirmed from the bhavcopy.
EXTRA_VERIFY_DATES = ("2024-06-03", "2024-06-04", "2024-06-05")


def download_yahoo(ticker: str) -> pd.DataFrame | None:
    """Daily history from Yahoo Finance with unadjusted Close, Adj Close and corporate actions."""
    df = yf.download(ticker, start=cfg.YF_START, end=cfg.YF_END_EXCLUSIVE, auto_adjust=False,
                     progress=False, actions=True)
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    df.index = idx.normalize()
    df.index.name = "Date"
    return df


def yahoo_name(ticker: str) -> str:
    """Fund name reported by Yahoo Finance (empty string if unavailable)."""
    try:
        info = yf.Ticker(ticker).info
        return info.get("longName") or info.get("shortName") or ""
    except Exception:  # noqa: BLE001 - the name is cosmetic
        return ""


def nse_session() -> requests.Session:
    """HTTP session with browser headers; NSE archives reject requests without them."""
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9",
                      "Referer": "https://www.nseindia.com/all-reports"})
    try:
        s.get("https://www.nseindia.com/all-reports", timeout=20)
    except requests.RequestException:
        pass
    return s


def bhavcopy_urls(day: pd.Timestamp) -> list[str]:
    """Candidate archive URLs for the capital-market bhavcopy of `day` (preferred format first)."""
    ymd = day.strftime("%Y%m%d")
    mon = day.strftime("%b").upper()
    udiff = f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{ymd}_F_0000.csv.zip"
    legacy = (f"https://nsearchives.nseindia.com/content/historical/EQUITIES/{day.year}/{mon}/"
              f"cm{day.strftime('%d')}{mon}{day.year}bhav.csv.zip")
    return [udiff, legacy] if day >= UDIFF_FROM else [legacy, udiff]


def parse_bhavcopy(content: bytes, symbols: list[str]) -> pd.DataFrame:
    """Rows of `symbols` (series EQ) from a zipped bhavcopy in either NSE format."""
    z = zipfile.ZipFile(io.BytesIO(content))
    bc = pd.read_csv(io.BytesIO(z.read(z.namelist()[0])))
    bc.columns = [c.strip() for c in bc.columns]
    if "TckrSymb" in bc.columns:
        sub = bc[bc["TckrSymb"].isin(symbols)]
        out = pd.DataFrame({"symbol": sub["TckrSymb"], "series": sub["SctySrs"], "close": sub["ClsPric"],
                            "prev_close": sub["PrvsClsgPric"], "volume": sub["TtlTradgVol"],
                            "traded_value_inr": sub["TtlTrfVal"]})
    else:
        sub = bc[bc["SYMBOL"].isin(symbols)]
        out = pd.DataFrame({"symbol": sub["SYMBOL"], "series": sub["SERIES"], "close": sub["CLOSE"],
                            "prev_close": sub["PREVCLOSE"], "volume": sub["TOTTRDQTY"],
                            "traded_value_inr": sub["TOTTRDVAL"]})
    return out[out["series"].astype(str).str.strip() == "EQ"]


def fetch_bhavcopy(session: requests.Session, day: pd.Timestamp, symbols: list[str],
                   try_both: bool = True) -> tuple[pd.DataFrame | None, str, str]:
    """Official NSE closes of `symbols` on `day`.

    Returns (rows or None, status, url). Status '404' means no file, i.e. no session that day.
    Other failures are retried twice and reported as 'error ...'.
    """
    urls = bhavcopy_urls(day) if try_both else bhavcopy_urls(day)[:1]
    status, used = "", ""
    for url in urls:
        for attempt in range(3):
            try:
                r = session.get(url, timeout=30)
            except requests.RequestException as exc:
                status, used = f"error {exc.__class__.__name__}", url
                time.sleep(2 * (attempt + 1))
                continue
            if r.status_code == 200 and r.content[:2] == b"PK":
                rows = parse_bhavcopy(r.content, symbols)
                rows.insert(0, "date", day.date().isoformat())
                rows["source"] = url
                return rows, "200", url
            if r.status_code == 404:
                status, used = "404", url
                break
            status, used = f"error {r.status_code}", url
            time.sleep(2 * (attempt + 1))
    return None, status, used


def dates_to_verify(raw: dict[str, pd.DataFrame], calendar: pd.DatetimeIndex) -> list[pd.Timestamp]:
    """Dates where Yahoo data of a portfolio ETF needs an official cross-check."""
    base = dp.window_base_date(calendar)
    index_days = raw[cfg.CALENDAR_TICKER]["Close"].dropna().index
    days: set[pd.Timestamp] = {pd.Timestamp(cfg.VALUATION_DATE)} | {pd.Timestamp(d) for d in EXTRA_VERIFY_DATES}
    for t in cfg.TICKERS:
        df = raw[t]
        c = df["Close"].dropna()
        days |= set(index_days[index_days >= c.index.min()].difference(c.index))  # missing rows
        days |= set(df.index[df["Volume"] == 0])  # zero-volume rows
        r = c / c.shift(1) - 1
        days |= set(r.index[r.abs() > cfg.JUMP_THRESHOLD[t]])  # large moves
    return sorted(d for d in days if base <= d <= pd.Timestamp(cfg.WINDOW_END))


def main() -> None:
    cfg.RAW.mkdir(parents=True, exist_ok=True)
    tickers = list(dict.fromkeys(cfg.TICKERS + list(cfg.BOND_CANDIDATES) + [cfg.CALENDAR_TICKER]))
    log: dict = {"downloaded_at": datetime.now().isoformat(timespec="seconds"),
                 "yfinance_version": yf.__version__, "tickers": {}, "names": {}}
    raw: dict[str, pd.DataFrame] = {}
    for t in tickers:
        df = download_yahoo(t)
        if df is None:
            log["tickers"][t] = "no data returned by Yahoo Finance"
            print(f"{t}: no data", flush=True)
            continue
        df.to_csv(dp.raw_path(t))
        raw[t] = df
        log["tickers"][t] = {"rows": len(df), "first": df.index.min().date().isoformat(),
                             "last": df.index.max().date().isoformat(),
                             "last_close": round(float(df["Close"].dropna().iloc[-1]), 4)}
        print(f"{t}: {log['tickers'][t]}", flush=True)
    for t in tickers:
        if t in raw and t != cfg.CALENDAR_TICKER:
            log["names"][t] = yahoo_name(t)

    yahoo_calendar, _ = dp.trading_calendar(raw)
    base = dp.window_base_date(yahoo_calendar)
    end = pd.Timestamp(cfg.WINDOW_END)
    symbols = [dp.nse_symbol(t) for t in cfg.TICKERS]
    session = nse_session()
    frames, requests_log = [], []

    def run(day: pd.Timestamp, purpose: str, try_both: bool) -> None:
        rows, status, url = fetch_bhavcopy(session, day, symbols, try_both=try_both)
        requests_log.append({"date": day.date().isoformat(), "purpose": purpose, "status": status, "url": url})
        if rows is not None:
            rows["purpose"] = purpose
            frames.append(rows)
        time.sleep(0.25)

    # 1. calendar check: every non-trading date (per Yahoo) inside the window
    all_days = pd.date_range(base, end, freq="D")
    for i, day in enumerate(all_days.difference(yahoo_calendar)):
        run(day, "calendar_check", try_both=False)
        if i % 50 == 0:
            print(f"calendar check {i}: {day.date()}", flush=True)
    found = [r["date"] for r in requests_log if r["purpose"] == "calendar_check" and r["status"] == "200"]
    print("sessions missing on Yahoo:", found, flush=True)

    # 2. verification dates and 3. random sample of Yahoo trading days
    for day in dates_to_verify(raw, yahoo_calendar):
        run(day, "verification", try_both=True)
    window_days = yahoo_calendar[(yahoo_calendar > base) & (yahoo_calendar <= end)]
    rng = np.random.default_rng(cfg.SEED)
    for day in sorted(rng.choice(window_days, size=25, replace=False)):
        run(pd.Timestamp(day), "random_sample", try_both=True)

    nse = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["date", "symbol", "series", "close", "prev_close", "volume", "traded_value_inr", "source",
                 "purpose"])
    nse = nse.drop_duplicates(subset=["date", "symbol"], keep="first")
    nse.to_csv(cfg.NSE_FILE, index=False)
    pd.DataFrame(requests_log).to_csv(cfg.RAW / "nse_requests_log.csv", index=False)
    log["nse_requests"] = {"total": len(requests_log),
                           "status_counts": pd.Series([r["status"] for r in requests_log]).value_counts().to_dict(),
                           "sessions_missing_on_yahoo": found}
    (cfg.RAW / "download_log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")

    built = dp.build_dataset(log)
    print("prices:", built["prices"].shape, built["prices"].index.min().date(), built["prices"].index.max().date())
    print(built["fixes"].to_string())
    print(built["screen"][["ticker", "years_in_window", "gap_days", "stale_pct", "eligible", "selected"]].to_string())


if __name__ == "__main__":
    main()
