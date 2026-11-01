"""Download daily prices for the 10-stock universe, NIFTY 50 and a NIFTY total-return proxy.

This is the only step that needs internet access. Everything downstream runs offline
from the files written here.

Run from the project folder:
    python src/fetch_data.py

Writes
    data/raw/<TICKER>.csv       raw yfinance bars per ticker ("^" replaced by "IDX_"):
                                Open, High, Low, Close, Adj Close, Volume, Dividends, Stock Splits
    data/prices_adjclose.csv    tidy table, dates x tickers, Adj Close as downloaded (uncorrected)
    data/metadata.json          download timestamp, tickers, source, parameters, row counts
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import (ALL_TICKERS, BENCHMARK_TICKER, DATA_DIR, DOWNLOAD_END,  # noqa: E402
                        DOWNLOAD_START, NAMES, LABELS, RAW_DIR)


def raw_file_name(ticker: str) -> str:
    """File name used for a ticker's raw CSV (Windows-safe)."""
    return ticker.replace("^", "IDX_") + ".csv"


def download_ticker(ticker: str, start: str, end: str, retries: int = 3) -> pd.DataFrame:
    """Download daily bars for one ticker with yfinance (auto_adjust=False, actions=True).

    Parameters
    ----------
    ticker : Yahoo Finance symbol, e.g. "RELIANCE.NS" or "^NSEI".
    start, end : ISO dates; ``end`` is exclusive.
    retries : number of attempts before giving up.

    Returns
    -------
    DataFrame indexed by trading date with OHLC, Adj Close, Volume, Dividends, Stock Splits.
    """
    import yfinance as yf

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            df = yf.download(ticker, start=start, end=end, auto_adjust=False, actions=True,
                             progress=False, threads=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if df.empty:
                raise ValueError(f"empty frame for {ticker}")
            df.index = pd.to_datetime(df.index).tz_localize(None)
            df.index.name = "Date"
            return df
        except Exception as exc:  # noqa: BLE001 - network errors vary by version
            last_error = exc
            time.sleep(2 * attempt)
    raise RuntimeError(f"download failed for {ticker}: {last_error}")


def main() -> None:
    """Download every ticker, write raw CSVs, the tidy Adj Close table and metadata."""
    import yfinance as yf

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    adj: dict[str, pd.Series] = {}
    summary: dict[str, dict] = {}
    for ticker in ALL_TICKERS:
        df = download_ticker(ticker, DOWNLOAD_START, DOWNLOAD_END)
        df.to_csv(RAW_DIR / raw_file_name(ticker))
        adj[ticker] = df["Adj Close"]
        summary[ticker] = {
            "label": LABELS[ticker],
            "rows": int(len(df)),
            "first_date": str(df.index.min().date()),
            "last_date": str(df.index.max().date()),
            "last_close": round(float(df["Close"].iloc[-1]), 2),
            "missing_adj_close": int(df["Adj Close"].isna().sum()),
            "dividend_events": int((df.get("Dividends", pd.Series(dtype=float)) > 0).sum()),
            "split_events": int((df.get("Stock Splits", pd.Series(dtype=float)) > 0).sum()),
        }
        print(f"{ticker:15s} rows={len(df):5d} {summary[ticker]['first_date']} -> "
              f"{summary[ticker]['last_date']} last close={summary[ticker]['last_close']:,.2f}")

    prices = pd.DataFrame(adj).sort_index()
    prices.index.name = "Date"
    prices.to_csv(DATA_DIR / "prices_adjclose.csv")

    now_utc = datetime.now(timezone.utc)
    meta = {
        "source": "Yahoo Finance, downloaded with the yfinance Python package",
        "yfinance_version": yf.__version__,
        "download_timestamp_utc": now_utc.isoformat(timespec="seconds"),
        "download_timestamp_ist": (now_utc + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M:%S IST"),
        "parameters": {"start": DOWNLOAD_START, "end_exclusive": DOWNLOAD_END, "interval": "1d",
                       "auto_adjust": False, "actions": True},
        "tickers": {t: {"label": LABELS[t], "name": NAMES[LABELS[t]]} for t in ALL_TICKERS},
        "benchmark": BENCHMARK_TICKER,
        "files": {"raw": "data/raw/<TICKER>.csv ('^' replaced by 'IDX_')",
                  "tidy_adj_close": "data/prices_adjclose.csv (uncorrected, union of trading dates)"},
        "notes": ["Adj Close is adjusted by Yahoo for splits, bonuses and cash dividends, "
                  "but not for demergers (corrected in src/data_cleaning.py).",
                  "^NSEI is the NIFTY 50 price index; it excludes dividends."],
        "summary": summary,
    }
    (DATA_DIR / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"saved {len(ALL_TICKERS)} raw files, prices_adjclose.csv {prices.shape}, metadata.json")


if __name__ == "__main__":
    main()
