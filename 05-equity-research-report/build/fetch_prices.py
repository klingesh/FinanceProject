"""Download daily prices from Yahoo Finance (yfinance) for Asian Paints, the four peers and NIFTY 50.

Saves untouched yfinance output to source_data/yahoo_finance/<ticker>.csv and a tidy file
data/prices/prices_daily.csv (Close and Adj Close), plus data/prices/price_summary.json with the
30-Oct-2026 close, 52-week high/low and 1/3/5-year returns.

Run:  python build/fetch_prices.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "source_data" / "yahoo_finance"
TIDY = ROOT / "data" / "prices"
RAW.mkdir(parents=True, exist_ok=True)
TIDY.mkdir(parents=True, exist_ok=True)

TICKERS = {"ASIANPAINT.NS": "Asian Paints", "BERGEPAINT.NS": "Berger Paints", "KANSAINER.NS": "Kansai Nerolac",
           "JSWDULUX.NS": "JSW Dulux", "INDIGOPNTS.NS": "Indigo Paints", "^NSEI": "NIFTY 50"}
FALLBACK = {"JSWDULUX.NS": "AKZOINDIA.NS"}
START, END = "2021-10-01", "2026-10-31"   # END is exclusive in yfinance -> last bar 30-Oct-2026
ASOF = pd.Timestamp("2026-10-30")


def get(tk: str) -> pd.DataFrame:
    df = yf.download(tk, start=START, end=END, auto_adjust=False, progress=False, actions=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def main() -> None:
    frames, summary = {}, {}
    for tk, name in TICKERS.items():
        df = get(tk)
        used = tk
        if (df is None or df.empty) and tk in FALLBACK:
            used = FALLBACK[tk]
            df = get(used)
        if df is None or df.empty:
            summary[name] = {"ticker": tk, "error": "no data"}
            continue
        df.to_csv(RAW / f"{used.replace('^', 'IDX_')}.csv")
        df = df[df.index <= ASOF]
        frames[name] = df
        close = df["Close"].dropna()
        last = close.index[-1]
        win = df[df.index > last - pd.Timedelta(days=365)]
        # big one-day moves (corporate actions check, as the conventions require)
        r = close.pct_change()
        flags = [(d.strftime("%Y-%m-%d"), round(v * 100, 1)) for d, v in r.items() if abs(v) > 0.08]

        def ret(years: int) -> float | None:
            base_date = last - pd.DateOffset(years=years)
            base = close[close.index <= base_date]
            return None if base.empty else float(close.iloc[-1] / base.iloc[-1] - 1)

        adj = df["Adj Close"].dropna()

        def tret(years: int) -> float | None:
            base = adj[adj.index <= last - pd.DateOffset(years=years)]
            return None if base.empty else float(adj.iloc[-1] / base.iloc[-1] - 1)

        summary[name] = {
            "ticker": used, "last_date": last.strftime("%Y-%m-%d"), "close": round(float(close.iloc[-1]), 2),
            "high_52w": round(float(win["High"].max()), 2), "low_52w": round(float(win["Low"].min()), 2),
            "ret_1y": ret(1), "ret_3y": ret(3), "ret_5y": ret(5),
            "tr_1y": tret(1), "tr_3y": tret(3), "tr_5y": tret(5),
            "first_date": close.index[0].strftime("%Y-%m-%d"), "moves_over_8pct": flags,
        }
    tidy = []
    for name, df in frames.items():
        t = df[["Close", "Adj Close"]].copy()
        t["name"] = name
        tidy.append(t.reset_index())
    pd.concat(tidy).to_csv(TIDY / "prices_daily.csv", index=False)
    (TIDY / "price_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
