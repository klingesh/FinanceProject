"""Offline data preparation: raw snapshots -> clean price panel, quality reports, returns.

`fetch_data.py` saves the raw Yahoo Finance and NSE bhavcopy files once. Everything in this
module works offline from `data/raw/`, so the clean dataset can be rebuilt at any time.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from . import config as cfg


# ------------------------------------------------------------------ raw file access
def raw_path(ticker: str):
    """Path of the raw Yahoo Finance CSV for `ticker` (e.g. data/raw/yahoo_NIFTYBEES.NS.csv)."""
    safe = ticker.replace("^", "IDX_").replace("=", "_")
    return cfg.RAW / f"yahoo_{safe}.csv"


def nse_symbol(ticker: str) -> str:
    """NSE trading symbol for a Yahoo ticker (drops the .NS suffix)."""
    return ticker.replace(".NS", "")


def read_yahoo(ticker: str) -> pd.DataFrame:
    """Read one raw Yahoo Finance download (daily OHLC, Adj Close, Volume, actions)."""
    df = pd.read_csv(raw_path(ticker), index_col=0, parse_dates=True)
    df.index = pd.DatetimeIndex(df.index).normalize()
    df.index.name = "Date"
    return df.sort_index()


def read_nse_closes() -> pd.DataFrame:
    """Official NSE closing prices for selected dates (from saved bhavcopy extracts)."""
    if not cfg.NSE_FILE.exists():
        return pd.DataFrame(columns=["date", "symbol", "close", "prev_close", "volume"])
    df = pd.read_csv(cfg.NSE_FILE, parse_dates=["date"])
    return df


def load_raw(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """Read raw files for all `tickers` that were downloaded."""
    return {t: read_yahoo(t) for t in tickers if raw_path(t).exists()}


def read_nse_requests() -> pd.DataFrame:
    """Log of NSE bhavcopy requests (date, purpose, HTTP status) written by fetch_data.py."""
    path = cfg.RAW / "nse_requests_log.csv"
    if not path.exists():
        return pd.DataFrame(columns=["date", "purpose", "status", "url"])
    return pd.read_csv(path, parse_dates=["date"], dtype={"status": str})


# ------------------------------------------------------------------ calendar and cleaning
def trading_calendar(raw: dict[str, pd.DataFrame],
                     nse_requests: pd.DataFrame | None = None) -> tuple[pd.DatetimeIndex, list[dict]]:
    """NSE trading days in the download period.

    * A day is a trading day if the NIFTY 50 index has a close on Yahoo.
    * ETF rows on other days are kept only if at least one portfolio ETF traded; rows with zero
      volume in every ETF and no index close are exchange-holiday placeholders and are dropped.
    * Sessions that Yahoo misses entirely are added when an NSE bhavcopy exists for that date
      (calendar check in fetch_data.py).
    """
    index_days = raw[cfg.CALENDAR_TICKER]["Close"].dropna().index
    etf_days = pd.DatetimeIndex([])
    for t in cfg.TICKERS:
        etf_days = etf_days.union(raw[t]["Close"].dropna().index)
    notes, keep = [], []
    for d in etf_days.difference(index_days):
        vols = [raw[t]["Volume"].get(d, np.nan) for t in cfg.TICKERS]
        if all((pd.isna(v) or v == 0) for v in vols):
            notes.append({"date": d.date().isoformat(), "ticker": "all six ETFs", "action": "row dropped",
                          "reason": "no NIFTY 50 close and zero volume in every ETF: exchange-holiday "
                                    "placeholder row on Yahoo (no NSE bhavcopy exists for the date)"})
        else:
            keep.append(d)
    calendar = index_days.union(pd.DatetimeIndex(keep))
    if nse_requests is not None and len(nse_requests):
        hit = nse_requests[(nse_requests["purpose"] == "calendar_check") & (nse_requests["status"] == "200")]
        extra = pd.DatetimeIndex(hit["date"]).difference(calendar)
        for d in extra:
            notes.append({"date": d.date().isoformat(), "ticker": "all six ETFs", "action": "session added",
                          "reason": "NSE held a session (bhavcopy exists) that Yahoo omits; closes taken "
                                    "from the NSE bhavcopy"})
        calendar = calendar.union(extra)
    return calendar, notes


def clean_portfolio_prices(raw: dict[str, pd.DataFrame], nse: pd.DataFrame,
                           calendar: pd.DatetimeIndex) -> tuple[pd.DataFrame, list[dict]]:
    """Adjusted closes for the six portfolio ETFs on the NSE calendar, with documented fixes.

    Fixes, both based on the official NSE bhavcopy close for the same day:
    * a trading day missing on Yahoo is inserted with the NSE close;
    * a Yahoo close that differs from the NSE close by more than 0.01% is replaced with the
      NSE close (most such rows are zero-volume bad prints on Yahoo).
    Adj Close equals Close for these ETFs (they distribute nothing), so the NSE close can be
    used directly; this is asserted below.
    """
    fixes: list[dict] = []
    out = {}
    for t in cfg.TICKERS:
        df = raw[t]
        ratio = (df["Adj Close"] / df["Close"]).dropna()
        if not np.allclose(ratio.to_numpy(), 1.0, atol=1e-6):
            raise ValueError(f"{t}: Adj Close differs from Close; patching logic must be revisited")
        first = df["Close"].dropna().index.min()
        adj = df["Adj Close"].reindex(calendar)
        vol = df["Volume"].reindex(calendar)
        sym = nse_symbol(t)
        nse_t = nse[nse["symbol"] == sym].set_index("date")
        for d in calendar[calendar >= first]:
            nse_close = nse_t["close"].get(d, np.nan)
            if pd.isna(adj[d]):
                if pd.notna(nse_close):
                    adj[d] = nse_close
                    fixes.append({"date": d.date().isoformat(), "ticker": t, "action": "row inserted",
                                  "reason": f"trading day missing on Yahoo; NSE bhavcopy close {nse_close:.2f} "
                                            f"(volume {int(nse_t['volume'].get(d, 0)):,})"})
            elif pd.notna(nse_close) and abs(adj[d] / nse_close - 1) > 1e-4:
                tag = "bad print with zero volume" if vol[d] == 0 else f"close (volume {int(vol[d]):,})"
                fixes.append({"date": d.date().isoformat(), "ticker": t, "action": "close replaced",
                              "reason": f"Yahoo {tag} {adj[d]:.2f}; NSE bhavcopy close {nse_close:.2f} "
                                        f"(volume {int(nse_t['volume'].get(d, 0)):,}), "
                                        f"difference {100 * (adj[d] / nse_close - 1):+.2f}%"})
                adj[d] = nse_close
        missing = adj[adj.index >= first].isna()
        if missing.any():
            for d in adj[adj.index >= first][missing].index:
                fixes.append({"date": d.date().isoformat(), "ticker": t, "action": "previous close carried",
                              "reason": "no Yahoo row and no NSE trade in this ETF that session"})
            adj = adj.ffill()
        out[t] = adj
    prices = pd.DataFrame(out)
    prices.index.name = "Date"
    return prices, fixes


# ------------------------------------------------------------------ quality metrics
def window_base_date(calendar: pd.DatetimeIndex) -> pd.Timestamp:
    """Last trading day before the analysis window starts (its close is the first base price)."""
    return calendar[calendar < pd.Timestamp(cfg.WINDOW_START)][-1]


def series_quality(df: pd.DataFrame, calendar: pd.DatetimeIndex, threshold: float) -> dict:
    """Coverage and quality statistics of one raw Yahoo series over the analysis window.

    Stale day = a trading day whose close equals the previous close (zero return).
    Gap = an NSE trading day with no Yahoo row.
    """
    base = window_base_date(calendar)
    end = pd.Timestamp(cfg.WINDOW_END)
    close = df["Close"].dropna()
    first = close.index.min()
    span_start = max(first, base)
    cal_span = calendar[(calendar >= span_start) & (calendar <= end)]
    c = close[(close.index >= span_start) & (close.index <= end)]
    c = c[c.index.isin(calendar)]  # ignore holiday placeholder rows
    gaps = cal_span.difference(c.index)
    r = (c / c.shift(1) - 1).dropna()
    vol = df["Volume"].reindex(c.index)
    traded_value_lakh = (c * vol / 1e5).median()
    acov = np.cov(r.to_numpy()[1:], r.to_numpy()[:-1])[0, 1]
    big = r[r.abs() > threshold]
    return {
        "first_yahoo_date": first.date().isoformat(),
        "years_in_window": round((end - span_start).days / 365.25, 2),
        "trading_days": len(cal_span),
        "gap_days": len(gaps),
        "gap_dates": ";".join(d.date().isoformat() for d in gaps[:30]),
        "stale_days": int((r == 0).sum()),
        "stale_pct": round(100 * float((r == 0).mean()), 2),
        "zero_volume_days": int((vol.iloc[1:] == 0).sum()),
        "zero_volume_pct": round(100 * float((vol.iloc[1:] == 0).mean()), 2),
        "median_traded_value_lakh": round(float(traded_value_lakh), 1),
        "ann_vol_pct": round(100 * float(r.std() * np.sqrt(cfg.TRADING_DAYS_PER_YEAR)), 2),
        "lag1_autocorr": round(float(r.autocorr(1)), 3),
        "roll_spread_pct": round(100 * 2 * np.sqrt(-acov), 3) if acov < 0 else 0.0,
        "max_abs_return_pct": round(100 * float(r.abs().max()), 2),
        "moves_above_threshold": len(big),
        "splits_recorded": int((df.get("Stock Splits", pd.Series(dtype=float)) > 0).sum()),
        "dividends_recorded": int((df.get("Dividends", pd.Series(dtype=float)) > 0).sum()),
    }


def bond_screen(raw: dict[str, pd.DataFrame], calendar: pd.DatetimeIndex,
                names: dict[str, str] | None = None) -> pd.DataFrame:
    """Quality table for the government-bond ETF candidates and the selection rule.

    Rule: holds government securities, at least 4.9 years of Yahoo history in the window,
    at most 5 gap days and at most 5% stale days; among those, pick the lowest stale share.
    """
    rows = []
    for t, (holds, requested) in cfg.BOND_CANDIDATES.items():
        base = {"ticker": t, "name": (names or {}).get(t, ""), "holds": holds,
                "requested": requested}
        if t not in raw:
            rows.append({**base, "first_yahoo_date": "no data on Yahoo"})
            continue
        q = series_quality(raw[t], calendar, threshold=0.03)
        rows.append({**base, **q})
    tab = pd.DataFrame(rows)
    gsec = tab["holds"].str.startswith("G-Secs")
    ok = (gsec & (tab["years_in_window"] >= 4.9) & (tab["gap_days"] <= 5) & (tab["stale_pct"] <= 5.0))
    tab["eligible"] = ok.fillna(False)
    tab["selected"] = False
    if tab["eligible"].any():
        pick = tab[tab["eligible"]].sort_values(["stale_pct", "gap_days"]).index[0]
        tab.loc[pick, "selected"] = True
    return tab


def jump_screen(raw: dict[str, pd.DataFrame], prices: pd.DataFrame, nse: pd.DataFrame,
                calendar: pd.DatetimeIndex) -> pd.DataFrame:
    """Large one-day moves in the raw Yahoo data of the portfolio ETFs and how each was resolved.

    Thresholds: |return| > 8% for equity ETFs, > 3% for the gold and bond ETFs. A move is
    'genuine' if the Yahoo close and previous close both match the official NSE bhavcopy.
    """
    rows = []
    base = window_base_date(calendar)
    for t in cfg.TICKERS:
        thr = cfg.JUMP_THRESHOLD[t]
        c_raw = raw[t]["Close"].dropna()
        c_raw = c_raw[c_raw.index.isin(calendar)]
        r_raw = (c_raw / c_raw.shift(1) - 1).dropna()
        r_raw = r_raw[r_raw.index > base]
        c_cln = prices[t].dropna()
        r_cln = (c_cln / c_cln.shift(1) - 1).dropna()
        flagged = r_raw[r_raw.abs() > thr].index.union(r_cln[(r_cln.abs() > thr) & (r_cln.index > base)].index)
        nse_t = nse[nse["symbol"] == nse_symbol(t)].set_index("date")
        for d in flagged:
            raw_ret = r_raw.get(d, np.nan)
            cln_ret = r_cln.get(d, np.nan)
            y_close = c_cln.get(d, np.nan)
            y_prev = c_cln.shift(1).get(d, np.nan)
            n_close = nse_t["close"].get(d, np.nan)
            n_prev = nse_t["prev_close"].get(d, np.nan)
            if pd.isna(cln_ret) or abs(cln_ret) <= thr:
                status = "artefact: within threshold after the data fix (bad print or missing session)"
            elif pd.notna(n_close) and abs(y_close / n_close - 1) <= 1e-4 and abs(y_prev / n_prev - 1) <= 1e-4:
                status = "genuine: close and previous close match NSE bhavcopy"
            elif pd.notna(n_close):
                status = "check: differs from NSE bhavcopy"
            else:
                status = "unverified: no NSE file for this date"
            rows.append({"date": d.date().isoformat(), "ticker": t, "threshold_pct": 100 * thr,
                         "raw_return_pct": round(100 * raw_ret, 2) if pd.notna(raw_ret) else np.nan,
                         "clean_return_pct": round(100 * cln_ret, 2) if pd.notna(cln_ret) else np.nan,
                         "clean_close": y_close, "nse_close": n_close, "nse_prev_close": n_prev,
                         "status": status})
    return pd.DataFrame(rows)


def nse_crosscheck(raw: dict[str, pd.DataFrame], prices: pd.DataFrame, nse: pd.DataFrame) -> pd.DataFrame:
    """Compare raw Yahoo closes and the cleaned closes with every official NSE close fetched.

    `prev_match` checks the cleaned close of the previous session against the NSE previous close,
    which confirms that no session is missing between the two dates.
    """
    rows = []
    prev = prices.shift(1)
    for _, x in nse.iterrows():
        t = f"{x['symbol']}.NS"
        d = pd.Timestamp(x["date"])
        y = raw[t]["Close"].get(d, np.nan) if t in raw else np.nan
        c = prices[t].get(d, np.nan)
        cp = prev[t].get(d, np.nan)
        rows.append({"date": d.date().isoformat(), "ticker": t, "purpose": x.get("purpose", ""),
                     "nse_close": x["close"], "nse_prev_close": x["prev_close"], "yahoo_close": y,
                     "clean_close": c, "clean_prev_close": cp,
                     "yahoo_match": bool(pd.notna(y) and abs(y / x["close"] - 1) <= 1e-4),
                     "clean_match": bool(pd.notna(c) and abs(c / x["close"] - 1) <= 1e-4),
                     "prev_match": bool(pd.notna(cp) and abs(cp / x["prev_close"] - 1) <= 1e-4)})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ build everything
def build_dataset(download_log: dict | None = None) -> dict:
    """Rebuild data/prices_adjclose.csv, data/metadata.json and the data-quality CSVs offline."""
    cfg.OUTPUTS.mkdir(parents=True, exist_ok=True)
    tickers = list(dict.fromkeys(cfg.TICKERS + list(cfg.BOND_CANDIDATES) + [cfg.CALENDAR_TICKER]))
    raw = load_raw(tickers)
    nse = read_nse_closes()
    calendar, cal_notes = trading_calendar(raw, read_nse_requests())
    # quality metrics use Yahoo's own NIFTY 50 calendar, so sessions that Yahoo misses for every
    # ticker (added from NSE above) do not count as gaps of one particular ETF
    yahoo_calendar, _ = trading_calendar(raw)
    prices, fixes = clean_portfolio_prices(raw, nse, calendar)
    prices = prices[prices.index <= pd.Timestamp(cfg.WINDOW_END)]
    prices.round(4).to_csv(cfg.PRICES_FILE)
    cross = nse_crosscheck(raw, prices, nse)
    cross.to_csv(cfg.OUTPUTS / "nse_crosscheck.csv", index=False)
    cross_summary = (cross.groupby("purpose")[["yahoo_match", "clean_match", "prev_match"]]
                     .agg(["sum", "count"]) if len(cross) else pd.DataFrame())

    log_file = cfg.RAW / "download_log.json"
    if download_log is None and log_file.exists():
        download_log = json.loads(log_file.read_text(encoding="utf-8"))
    names = (download_log or {}).get("names", {})

    screen = bond_screen(raw, yahoo_calendar, names)
    screen.to_csv(cfg.OUTPUTS / "bond_etf_screen.csv", index=False)
    quality = pd.DataFrame([{"ticker": t, "label": cfg.HOLDINGS[t][0],
                             **series_quality(raw[t], yahoo_calendar, cfg.JUMP_THRESHOLD[t])}
                            for t in cfg.TICKERS])
    quality.to_csv(cfg.OUTPUTS / "data_quality.csv", index=False)
    jumps = jump_screen(raw, prices, nse, calendar)
    jumps.to_csv(cfg.OUTPUTS / "jump_screen.csv", index=False)
    fixes_df = pd.DataFrame(cal_notes + fixes)
    fixes_df.to_csv(cfg.OUTPUTS / "data_fixes.csv", index=False)

    meta = {
        "project": "1-day and 10-day VaR / ES of a Rs 1 crore multi-asset ETF portfolio",
        "portfolio_value_inr": cfg.PORTFOLIO_VALUE,
        "valuation_date": cfg.VALUATION_DATE,
        "analysis_window": [cfg.WINDOW_START, cfg.WINDOW_END],
        "holdings": {t: {"label": v[0], "fund": v[1], "asset_class": v[2], "weight": v[3]}
                     for t, v in cfg.HOLDINGS.items()},
        "price_field": "Adj Close (equals Close: the six ETFs paid no distributions in the period)",
        "sources": {
            "yahoo_finance": "yfinance.download(start=%s, end=%s exclusive, auto_adjust=False, actions=True)"
                             % (cfg.YF_START, cfg.YF_END_EXCLUSIVE),
            "nse_bhavcopy": "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_<YYYYMMDD>_F_0000.csv.zip "
                            "(official NSE closing prices, used to verify and patch Yahoo rows)",
        },
        "calendar": {"trading_days_incl_base_date": int(len(calendar[(calendar >= window_base_date(calendar)) &
                                                                     (calendar <= pd.Timestamp(cfg.WINDOW_END))])),
                     "rule": "NIFTY 50 (^NSEI) close dates on Yahoo, minus ETF-only holiday placeholder rows, "
                             "plus sessions for which an NSE bhavcopy exists but Yahoo has no row"},
        "data_fixes": cal_notes + fixes,
        "nse_crosscheck": {p: {"yahoo_match": int(cross_summary.loc[p, ("yahoo_match", "sum")]),
                               "clean_match": int(cross_summary.loc[p, ("clean_match", "sum")]),
                               "prev_match": int(cross_summary.loc[p, ("prev_match", "sum")]),
                               "rows": int(cross_summary.loc[p, ("yahoo_match", "count")])}
                           for p in cross_summary.index} if len(cross_summary) else {},
        "bond_selection": screen.loc[screen["selected"], "ticker"].tolist(),
        "download_log": download_log,
    }
    cfg.METADATA_FILE.write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    return {"prices": prices, "screen": screen, "quality": quality, "jumps": jumps, "fixes": fixes_df,
            "calendar": calendar, "crosscheck": cross}


# ------------------------------------------------------------------ returns and portfolio
def load_prices() -> pd.DataFrame:
    """Clean adjusted closes of the six ETFs (columns = Yahoo tickers)."""
    prices = pd.read_csv(cfg.PRICES_FILE, index_col=0, parse_dates=True)
    return prices[cfg.TICKERS]


def simple_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Daily simple returns r_t = P_t / P_{t-1} - 1."""
    return (prices / prices.shift(1) - 1).dropna(how="all")


def window_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Simple returns inside the analysis window; raises if any value is missing."""
    r = simple_returns(prices)
    r = r[(r.index >= pd.Timestamp(cfg.WINDOW_START)) & (r.index <= pd.Timestamp(cfg.WINDOW_END))]
    if r.isna().any().any():
        raise ValueError("missing returns inside the analysis window")
    return r


def weights() -> np.ndarray:
    """Target weights in the order of config.TICKERS."""
    w = np.array(cfg.WEIGHTS, dtype=float)
    assert abs(w.sum() - 1) < 1e-12
    return w


def portfolio_returns(returns: pd.DataFrame, w: np.ndarray) -> pd.Series:
    """Constant-weight portfolio return: r_p = sum_i w_i r_i (exact for simple returns)."""
    return pd.Series(returns.to_numpy() @ w, index=returns.index, name="portfolio")


def holdings_table(prices: pd.DataFrame, w: np.ndarray, value: float = cfg.PORTFOLIO_VALUE) -> pd.DataFrame:
    """Positions at the valuation-date close: weight, rupee value and approximate units."""
    px = prices.loc[pd.Timestamp(cfg.VALUATION_DATE)]
    rows = []
    for (t, (label, fund, asset, _)), wi in zip(cfg.HOLDINGS.items(), w):
        rows.append({"ticker": t, "label": label, "fund": fund, "asset_class": asset, "weight": wi,
                     "value_inr": wi * value, "price_inr": px[t], "units": wi * value / px[t]})
    return pd.DataFrame(rows)
