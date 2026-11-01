"""Fetch Castrol India market data and S&P Global statements (stockanalysis.com) for the LBO model.

Saves to source_data/ :
  yahoo_finance/CASTROLIND_NS_daily.csv     daily OHLC, Adj Close, dividends (yfinance, auto_adjust=False)
  yahoo_finance/quote_30Oct2026.json        close on 30-Oct-2026 and 52-week range
  yahoo_finance/USDINR_daily.csv            INR=X closes (to translate the bp/Stonepeak US$ figures)
  yahoo_finance/deal_dates_fx_prices.json   FX and share prices around the 23/24-Dec-2025 announcement
  stockanalysis/<page>_table<i>.csv         every table on each page (INR millions unless stated)
  stockanalysis/<page>.html                 raw page (audit trail)
  stockanalysis/fetch_market_data.log       run log

The snapshot in source_data/ was downloaded on 31-Oct-2026. Re-running overwrites it.

Run:  python build/fetch_market_data.py
"""
from __future__ import annotations

import io
import json
import time
import traceback
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
YF_DIR = ROOT / "source_data" / "yahoo_finance"
SA_DIR = ROOT / "source_data" / "stockanalysis"
YF_DIR.mkdir(parents=True, exist_ok=True)
SA_DIR.mkdir(parents=True, exist_ok=True)
UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130 Safari/537.36"
    )
}
SA_BASE = "https://stockanalysis.com/quote/nse/CASTROLIND/"
SA_PAGES = {
    "income_annual": "financials/",
    "income_quarterly": "financials/?p=quarterly",
    "balance_annual": "financials/balance-sheet/",
    "balance_quarterly": "financials/balance-sheet/?p=quarterly",
    "cashflow_annual": "financials/cash-flow-statement/",
    "ratios_annual": "financials/ratios/",
    "statistics": "statistics/",
    "forecast": "forecast/",
}
VALUATION_DATE = "2026-10-30"


def fetch_yfinance(log: list[str]) -> None:
    """Daily prices for CASTROLIND.NS; record the 30-Oct-2026 close and 52-week range."""
    df = yf.download("CASTROLIND.NS", start="2021-01-01", end="2026-10-31",
                     auto_adjust=False, progress=False, actions=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.to_csv(YF_DIR / "CASTROLIND_NS_daily.csv")
    last = df.loc[:VALUATION_DATE].iloc[-1]
    last_date = df.loc[:VALUATION_DATE].index[-1]
    win = df.loc[pd.Timestamp(VALUATION_DATE) - pd.Timedelta(days=365):VALUATION_DATE]
    info = {
        "ticker": "CASTROLIND.NS",
        "source": "Yahoo Finance via yfinance (auto_adjust=False)",
        "fetched_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        "close_date": str(last_date.date()),
        "close": round(float(last["Close"]), 2),
        "adj_close": round(float(last["Adj Close"]), 2),
        "high_52w": round(float(win["High"].max()), 2),
        "low_52w": round(float(win["Low"].min()), 2),
        "avg_close_60d": round(float(df.loc[:VALUATION_DATE]["Close"].tail(60).mean()), 2),
        "vwap_60d_proxy": round(float((df.loc[:VALUATION_DATE]["Close"] * df.loc[:VALUATION_DATE]["Volume"]).tail(60).sum()
                                      / df.loc[:VALUATION_DATE]["Volume"].tail(60).sum()), 2),
        "dividends_last_24m": {str(k.date()): float(v) for k, v in df["Dividends"][df["Dividends"] > 0].tail(8).items()},
    }
    (YF_DIR / "quote_30Oct2026.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    log.append("yfinance: " + json.dumps(info))
    log.append(df.tail(8).to_string())


def fetch_fx(log: list[str]) -> None:
    """USD/INR (Yahoo INR=X) closes used to translate the BP/Stonepeak US$ figures."""
    fx = yf.download("INR=X", start="2025-12-01", end="2026-10-31", auto_adjust=False, progress=False)
    if isinstance(fx.columns, pd.MultiIndex):
        fx.columns = fx.columns.get_level_values(0)
    fx.to_csv(YF_DIR / "USDINR_daily.csv")
    px = pd.read_csv(YF_DIR / "CASTROLIND_NS_daily.csv", index_col=0, parse_dates=True)
    out = {
        "source": "Yahoo Finance via yfinance: INR=X and CASTROLIND.NS closes",
        "usdinr_close_2025-12-23": round(float(fx.loc[:"2025-12-23"]["Close"].iloc[-1]), 4),
        "usdinr_close_2026-10-30": round(float(fx.loc[:"2026-10-30"]["Close"].iloc[-1]), 4),
        "castrolind_close_2025-12-23": round(float(px.loc[:"2025-12-23"]["Close"].iloc[-1]), 2),
        "castrolind_close_2025-12-24": round(float(px.loc[:"2025-12-24"]["Close"].iloc[-1]), 2),
        "castrolind_close_2025-12-26": round(float(px.loc[:"2025-12-26"]["Close"].iloc[-1]), 2),
        "castrolind_closes_2025-12-19_to_2025-12-31": {
            str(k.date()): round(float(v), 2) for k, v in px.loc["2025-12-19":"2025-12-31"]["Close"].items()
        },
    }
    (YF_DIR / "deal_dates_fx_prices.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    log.append("fx/prices: " + json.dumps(out))


def fetch_stockanalysis(log: list[str]) -> None:
    """Save the first table (and raw html) of each stockanalysis.com page."""
    for name, page in SA_PAGES.items():
        url = SA_BASE + page
        try:
            r = requests.get(url, headers=UA, timeout=40)
            log.append(f"stockanalysis {name}: status={r.status_code} len={len(r.text)} url={url}")
            if r.status_code != 200:
                continue
            (SA_DIR / f"{name}.html").write_text(r.text, encoding="utf-8")
            tables = pd.read_html(io.StringIO(r.text))
            for i, t in enumerate(tables):
                if isinstance(t.columns, pd.MultiIndex):
                    t.columns = [" | ".join(str(x) for x in c if "Unnamed" not in str(x)) for c in t.columns]
                t.to_csv(SA_DIR / f"{name}_table{i}.csv", index=False)
                log.append(f"  table{i} shape={t.shape} cols={[str(c) for c in t.columns][:10]}")
            time.sleep(1.5)
        except Exception:  # noqa: BLE001
            log.append(f"stockanalysis {name}: FAILED {traceback.format_exc()}")


def main() -> None:
    log: list[str] = []
    try:
        fetch_yfinance(log)
    except Exception:  # noqa: BLE001
        log.append("yfinance FAILED " + traceback.format_exc())
    try:
        fetch_fx(log)
    except Exception:  # noqa: BLE001
        log.append("fx FAILED " + traceback.format_exc())
    fetch_stockanalysis(log)
    (SA_DIR / "fetch_market_data.log").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    main()
