"""Data hygiene for the daily price panel.

Steps (all logged, see ``clean_prices``):
1. Load the raw yfinance files (Adj Close, Close, Volume, Stock Splits).
2. Report missing values per series.
3. Treat stock rows with zero volume as missing: no trade means Yahoo carried the
   previous price forward, so the "return" for that day is not a real observation.
4. Align the 10 stocks and NIFTY 50 on common trading days (inner join).
5. Demergers: replace whatever adjustment Yahoo applied with the exchange's price-discovery
   factor and multiply every price before the ex-date by the residual factor.
6. Scan one-day returns below -8% and match each against a reviewed list of news events or
   corporate actions (with sources). Unreviewed drops make the hygiene check fail.
7. Bonus issues / splits: confirm Yahoo's split adjustment leaves no artificial jump.

Run ``python src/data_cleaning.py`` to print the full before/after report.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import (ANALYSIS_END, ANALYSIS_START, BENCHMARK, BENCHMARK_TICKER,  # noqa: E402
                        LABELS, LARGE_DROP_THRESHOLD, RAW_DIR, STOCK_LABELS, STOCKS,
                        TR_PROXY, TR_PROXY_TICKER)


# ----------------------------------------------------------------------------- reference data
@dataclass(frozen=True)
class Demerger:
    """A demerger (spin-off) with the exchange's special pre-open price discovery."""

    label: str                 # parent, short label
    ex_date: str               # ex-date = record date (T+1 settlement), special pre-open session
    child: str                 # demerged company
    ratio: str                 # entitlement
    parent_shares_per_child: int
    prev_close: float          # parent's exchange close on the cum-date, Rs (before later bonuses)
    discovered_price: float    # parent price discovered in the special pre-open session, Rs
    sources: tuple[str, ...]


DEMERGERS: tuple[Demerger, ...] = (
    Demerger(
        label="RELIANCE", ex_date="2023-07-20", child="Jio Financial Services (JFSL)",
        ratio="1 JFSL share for every 1 RIL share", parent_shares_per_child=1,
        prev_close=2841.85, discovered_price=2580.00,
        sources=(
            "Reuters via Yahoo Finance, 20-Jul-2023: RIL closed at Rs 2,841.85 on 19-Jul, price at end of "
            "special session Rs 2,580, JFSL value Rs 261.85 - "
            "https://sg.finance.yahoo.com/news/reliance-starts-special-trading-session-034517252.html",
            "Indian Express, 20-Jul-2023: demerger ratio 1:1 - "
            "https://indianexpress.com/article/business/companies/jio-financial-services-ltd-to-demerge-from-ril-today-8849165/",
        ),
    ),
    Demerger(
        label="ITC", ex_date="2025-01-06", child="ITC Hotels",
        ratio="1 ITC Hotels share for every 10 ITC shares", parent_shares_per_child=10,
        prev_close=481.60, discovered_price=455.60,
        sources=(
            "Times Now, 6-Jan-2025: ITC closed at Rs 481.60 on 3-Jan; NSE special session price Rs 455.60 "
            "(adjusted by Rs 26); ratio 1 for 10 - https://www.timesnownews.com/business-economy/markets/"
            "itc-hotels-share-price-special-trading-session-ends-itc-share-price-adjusts-by-rs-26-on-nse-article-116981147",
            "CNBC-TV18, 6-Jan-2025: market assigned ITC a price of Rs 455.60 - "
            "https://www.cnbctv18.com/market/itc-shares-now-trade-ex-hotels-check-stock-price-post-demerger-19534891.htm",
        ),
    ),
)


@dataclass(frozen=True)
class ReviewedMove:
    """A large one-day move that was checked against news and corporate actions."""

    label: str
    date: str
    cause: str
    corporate_action: bool
    source: str


REVIEWED_LARGE_MOVES: tuple[ReviewedMove, ...] = (
    ReviewedMove("INFY", "2023-04-17", "Q4 FY23 results below estimates and weak FY24 guidance (4-7%)", False,
                 "The Hindu, 17-Apr-2023 - https://www.thehindu.com/business/infosys-shares-fall-over-9-mcap-"
                 "declines-by-59349-crore-post-earnings-announcement/article66747825.ece"),
    ReviewedMove("INFY", "2023-07-21", "FY24 revenue growth guidance cut to 1-3.5%", False,
                 "Reuters via Yahoo Finance, 21-Jul-2023 - "
                 "https://finance.yahoo.com/news/indias-infosys-shares-slide-cutting-035551775.html"),
    ReviewedMove("HDFCBANK", "2024-01-17", "Q3 FY24 results disappointed (margins, deposit growth)", False,
                 "Economic Times, 19-Mar-2026 - https://economictimes.indiatimes.com/markets/stocks/news/"
                 "hdfc-banks-covid-plunge-to-earnings-disappointment-5-biggest-single-day-stock-crashes-since-2020/"
                 "articleshow/129674611.cms"),
    ReviewedMove("LT", "2024-06-04", "General election results day; NIFTY fell 5.93%", False,
                 "The Hindu, 4-Jun-2024 - https://www.thehindu.com/business/markets/sensex-plunges-57-as-bjp-"
                 "fails-to-win-majority-on-its-own/article68251438.ece"),
    ReviewedMove("ITC", "2026-01-01", "New excise duty on cigarettes notified on 31-Dec-2025", False,
                 "Reuters via Yahoo Finance, 1-Jan-2026 - "
                 "https://sg.finance.yahoo.com/news/indian-tobacco-stocks-tank-government-063100025.html"),
)

# Large up-moves (> +8%) inside the window, listed for completeness (not corporate actions).
REVIEWED_LARGE_GAINS: tuple[ReviewedMove, ...] = (
    ReviewedMove("HDFCBANK", "2022-04-04", "Merger with HDFC Ltd announced", False,
                 "CNBC-TV18, 4-Apr-2022 - https://www.cnbctv18.com/market/stocks/hdfc-hdfc-bank-merger-mortgage-"
                 "lender-overtakes-icici-bank-to-become-5th-largest-co-by-market-value-13038642.htm"),
    ReviewedMove("MARUTI", "2025-08-18", "Proposed GST cut on small cars (28% to 18%)", False,
                 "CNBC-TV18, 18-Aug-2025 - https://www.cnbctv18.com/market/maruti-suzuki-india-share-price-gains-"
                 "most-in-five-years-gst-rate-cut-product-mix-impact-demand-returns-19655101.htm"),
)

BONUS_SOURCES: dict[tuple[str, str], str] = {
    ("RELIANCE", "2024-10-28"): "1:1 bonus, record date 28-Oct-2024 - Business Today, 16-Oct-2024 - "
                                "https://www.businesstoday.in/markets/stocks/story/ril-bonus-shares-reliance-fixes-"
                                "monday-october-28-as-record-date-for-issue-450406-2024-10-16",
    ("HDFCBANK", "2025-08-26"): "1:1 bonus, ex-date 26-Aug-2025 (record date 27-Aug-2025) - Livemint, 26-Aug-2025 - "
                                "https://livemint.com/market/stock-market-news/hdfc-bank-bonus-issue-reward-or-a-trap-"
                                "explained-with-the-share-outlook-income-tax-rule-11755912368086.html",
}

KNOWN_NON_TRADING_DAYS: dict[str, str] = {
    "2026-01-15": "Exchange holiday for Maharashtra municipal elections - Livemint, 15-Jan-2026 - "
                  "https://www.livemint.com/market/stock-market-news/stock-market-holiday-bse-nse-to-remain-shut-"
                  "for-maharashtra-municipal-elections-commodity-trading-to-begin-at-5-pm-11768439343202.html",
}


# ----------------------------------------------------------------------------- result container
@dataclass
class CleanResult:
    """Output of :func:`clean_prices`."""

    prices: pd.DataFrame                 # aligned, demerger-corrected Adj Close (10 stocks + NIFTY50)
    prices_as_downloaded: pd.DataFrame   # aligned Adj Close before the demerger correction
    tr_proxy: pd.Series                  # NIFTYBEES Adj Close on the same dates (reference only)
    missing: pd.DataFrame
    stale: pd.DataFrame
    dropped_dates: pd.DataFrame
    demergers: pd.DataFrame
    large_moves: pd.DataFrame
    large_gains: pd.DataFrame
    splits: pd.DataFrame
    checks: dict[str, bool] = field(default_factory=dict)
    log: list[str] = field(default_factory=list)


# ----------------------------------------------------------------------------- loading
def raw_path(ticker: str, raw_dir: Path = RAW_DIR) -> Path:
    """Path of the raw CSV written by ``fetch_data.py`` for a ticker."""
    return raw_dir / (ticker.replace("^", "IDX_") + ".csv")


def load_raw(tickers: list[str] | None = None, raw_dir: Path = RAW_DIR) -> dict[str, pd.DataFrame]:
    """Read the raw per-ticker CSVs into a dict keyed by short label."""
    tickers = tickers or list(STOCKS) + [BENCHMARK_TICKER, TR_PROXY_TICKER]
    out = {}
    for t in tickers:
        df = pd.read_csv(raw_path(t, raw_dir), index_col=0, parse_dates=True).sort_index()
        df.index = pd.DatetimeIndex(df.index).as_unit("ns")
        out[LABELS[t]] = df
    return out


def panel(raw: dict[str, pd.DataFrame], column: str, labels: list[str]) -> pd.DataFrame:
    """Combine one column (e.g. 'Adj Close') of several raw frames into a dates x labels table."""
    return pd.DataFrame({lab: raw[lab][column] for lab in labels}).sort_index()


# ----------------------------------------------------------------------------- hygiene steps
def missing_value_report(adj: pd.DataFrame) -> pd.DataFrame:
    """Rows, missing count and the dates that are missing for each series (union of dates)."""
    rows = []
    for c in adj.columns:
        miss = adj.index[adj[c].isna()]
        rows.append({"series": c, "rows": int(adj[c].notna().sum()), "missing": len(miss),
                     "missing_dates": ", ".join(d.strftime("%Y-%m-%d") for d in miss)})
    return pd.DataFrame(rows).set_index("series")


def stale_rows(volume: pd.DataFrame, labels: list[str]) -> pd.DataFrame:
    """Stock rows with zero traded volume (price carried forward by the data vendor)."""
    z = volume[labels].fillna(-1).eq(0)
    rows = [{"date": d, "series": c} for d in z.index for c in labels if z.at[d, c]]
    if not rows:
        return pd.DataFrame(columns=["date", "n_series", "series"])
    df = pd.DataFrame(rows)
    return (df.groupby("date")["series"].agg(lambda s: ", ".join(s)).to_frame()
            .assign(n_series=df.groupby("date").size()).reset_index()[["date", "n_series", "series"]])


def align_common_days(adj: pd.DataFrame, volume: pd.DataFrame, stock_labels: list[str],
                      bench: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Mask zero-volume stock rows, then keep only dates where every series has a price.

    Returns the aligned panel and a table explaining each dropped date.
    """
    masked = adj[stock_labels + [bench]].copy()
    stale_mask = volume[stock_labels].fillna(-1).eq(0)
    masked[stock_labels] = masked[stock_labels].mask(stale_mask)
    keep = masked.notna().all(axis=1)
    reasons = []
    for d in masked.index[~keep]:
        stale = [c for c in stock_labels if stale_mask.at[d, c]]
        missing = [c for c in stock_labels + [bench] if pd.isna(adj.at[d, c])]
        why = []
        if missing:
            why.append("no price for " + ", ".join(missing))
        if stale:
            why.append(f"zero volume (stale price) for {len(stale)} stocks")
        note = KNOWN_NON_TRADING_DAYS.get(d.strftime("%Y-%m-%d"), "")
        reasons.append({"date": d, "reason": "; ".join(why), "note": note})
    return masked.loc[keep], pd.DataFrame(reasons)


def demerger_corrections(adj: pd.DataFrame, close: pd.DataFrame, splits: pd.DataFrame,
                         demergers: tuple[Demerger, ...] = DEMERGERS) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply the exchange price-discovery factor to every price before each demerger.

    Target factor  f* = discovered price / previous close (both from the exchange).
    Yahoo factor   f_y = Yahoo Close on the cum-date x later split ratios / exchange close
                   (1.0 would mean Yahoo did not adjust at all).
    Applied factor f* / f_y multiplies Adj Close on all dates up to the cum-date, so the
    ex-date return equals P_ex / (f* x P_cum) - 1: the holder's return if the spun-off
    shares were valued at the discovered price and reinvested in the parent.
    """
    out = adj.copy()
    rows = []
    for d in demergers:
        ex = pd.Timestamp(d.ex_date)
        if ex not in out.index:
            raise ValueError(f"ex-date {d.ex_date} for {d.label} is not a trading day in the panel")
        cum = out.index[out.index.get_loc(ex) - 1]
        later = splits.loc[splits.index > cum, d.label]
        later_factor = float(later[later > 0].prod()) if (later > 0).any() else 1.0
        f_target = d.discovered_price / d.prev_close
        f_yahoo = float(close.at[cum, d.label]) * later_factor / d.prev_close
        f_apply = f_target / f_yahoo
        ret_traded = float(close.at[ex, d.label]) * later_factor / d.prev_close - 1
        ret_before = float(adj.at[ex, d.label] / adj.at[cum, d.label] - 1)
        out.loc[out.index <= cum, d.label] = out.loc[out.index <= cum, d.label] * f_apply
        ret_after = float(out.at[ex, d.label] / out.at[cum, d.label] - 1)
        rows.append({
            "ticker": d.label, "ex_date": ex.date(), "cum_date": cum.date(), "spun_off": d.child, "ratio": d.ratio,
            "prev_close_rs": d.prev_close, "discovered_price_rs": d.discovered_price,
            "child_value_per_child_share_exchange_rs": round((d.prev_close - d.discovered_price)
                                                             * d.parent_shares_per_child, 2),
            "child_value_per_child_share_yahoo_rs": round((1 - f_yahoo) * d.prev_close
                                                          * d.parent_shares_per_child, 2),
            "factor_exchange": f_target, "factor_yahoo_embedded": f_yahoo, "factor_applied": f_apply,
            "ex_date_return_traded_price": ret_traded, "ex_date_return_as_downloaded": ret_before,
            "ex_date_return_corrected": ret_after,
            "sources": " | ".join(d.sources),
        })
    return out, pd.DataFrame(rows)


def scan_large_moves(prices: pd.DataFrame, bench: str, threshold: float = LARGE_DROP_THRESHOLD,
                     start: pd.Timestamp = ANALYSIS_START, end: pd.Timestamp = ANALYSIS_END,
                     reviewed: tuple[ReviewedMove, ...] = REVIEWED_LARGE_MOVES,
                     dividends: pd.DataFrame | None = None, splits: pd.DataFrame | None = None,
                     upside: bool = False) -> pd.DataFrame:
    """List one-day returns beyond ``threshold`` inside the window and attach the review.

    With ``upside=True`` the scan looks for returns above ``-threshold`` instead.
    """
    rets = prices / prices.shift(1) - 1
    rets = rets.loc[(rets.index >= start) & (rets.index <= end)]
    lookup = {(m.label, m.date): m for m in reviewed}
    rows = []
    for c in [col for col in rets.columns if col != bench]:
        hit = rets[c] > -threshold if upside else rets[c] < threshold
        for d in rets.index[hit]:
            m = lookup.get((c, d.strftime("%Y-%m-%d")))
            ca = []
            if dividends is not None and dividends.at[d, c] > 0:
                ca.append(f"dividend Rs {dividends.at[d, c]:.2f}")
            if splits is not None and splits.at[d, c] > 0:
                ca.append(f"split {splits.at[d, c]:g}:1")
            rows.append({"date": d.date(), "ticker": c, "return": float(rets.at[d, c]),
                         "nifty_return": float(rets.at[d, bench]),
                         "yahoo_corporate_action_that_day": "; ".join(ca) or "none",
                         "status": ("reviewed: corporate action" if m and m.corporate_action
                                    else "reviewed: genuine price move" if m else "UNREVIEWED"),
                         "cause": m.cause if m else "", "source": m.source if m else ""})
    cols = ["date", "ticker", "return", "nifty_return", "yahoo_corporate_action_that_day", "status",
            "cause", "source"]
    return pd.DataFrame(rows, columns=cols).sort_values("date").reset_index(drop=True)


def split_check(prices: pd.DataFrame, close: pd.DataFrame, splits: pd.DataFrame,
                threshold: float = abs(LARGE_DROP_THRESHOLD)) -> pd.DataFrame:
    """For every split/bonus Yahoo reports, compare the unadjusted and adjusted ex-date returns."""
    rows = []
    for c in prices.columns:
        if c not in splits:
            continue
        for d in splits.index[splits[c] > 0]:
            if d not in prices.index:
                continue
            i = prices.index.get_loc(d)
            ratio = float(splits.at[d, c])
            r_adj = float(prices[c].iloc[i] / prices[c].iloc[i - 1] - 1)
            window = (prices[c].iloc[i - 1:i + 2] / prices[c].shift(1).iloc[i - 1:i + 2] - 1).abs().max()
            r_unadj = float(close[c].iloc[i] / (close[c].iloc[i - 1] * ratio) - 1)
            rows.append({"ticker": c, "ex_date": d.date(), "ratio": f"{ratio:g}:1 (1:{ratio - 1:g} bonus)",
                         "return_if_unadjusted": r_unadj, "adj_close_return": r_adj,
                         "max_abs_return_t-1_to_t+1": float(window),
                         "no_artificial_jump": bool(window < threshold),
                         "source": BONUS_SOURCES.get((c, d.strftime("%Y-%m-%d")), "")})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------- pipeline
def clean_prices(raw_dir: Path = RAW_DIR, verbose: bool = False) -> CleanResult:
    """Run every hygiene step and return the cleaned panel plus the audit tables."""
    labels_all = STOCK_LABELS + [BENCHMARK, TR_PROXY]
    raw = load_raw(raw_dir=raw_dir)
    adj = panel(raw, "Adj Close", labels_all)
    close = panel(raw, "Close", labels_all)
    vol = panel(raw, "Volume", labels_all)
    splits = panel(raw, "Stock Splits", labels_all).fillna(0.0)
    divs = panel(raw, "Dividends", labels_all).fillna(0.0)

    missing = missing_value_report(adj)
    stale = stale_rows(vol, STOCK_LABELS)
    aligned, dropped = align_common_days(adj, vol, STOCK_LABELS, BENCHMARK)
    corrected, dem = demerger_corrections(aligned, close.loc[aligned.index], splits)
    drops = scan_large_moves(corrected, BENCHMARK, dividends=divs.loc[corrected.index],
                             splits=splits.loc[corrected.index])
    gains = scan_large_moves(corrected, BENCHMARK, reviewed=REVIEWED_LARGE_GAINS,
                             dividends=divs.loc[corrected.index], splits=splits.loc[corrected.index],
                             upside=True)
    spl = split_check(corrected, close.loc[corrected.index], splits.loc[corrected.index])
    tr_proxy = adj[TR_PROXY].reindex(corrected.index).ffill()

    rets = corrected / corrected.shift(1) - 1
    window = rets.loc[ANALYSIS_START:ANALYSIS_END]
    checks = {
        "no missing values after alignment": bool(corrected.notna().all().all()),
        "no zero-volume stock rows left": bool(not vol.loc[corrected.index, STOCK_LABELS].eq(0).any().any()),
        "demerger ex-date returns within +/-8% after correction":
            bool((dem["ex_date_return_corrected"].abs() < abs(LARGE_DROP_THRESHOLD)).all()),
        "every drop below -8% reviewed": bool((~drops["status"].eq("UNREVIEWED")).all()),
        "no artificial jump at bonus/split dates": bool(spl["no_artificial_jump"].all()) if len(spl) else True,
        "window covers 1-Nov-2021 to 30-Oct-2026":
            bool(window.index[0] <= ANALYSIS_START + pd.Timedelta(days=3) and window.index[-1] == ANALYSIS_END),
    }
    res = CleanResult(prices=corrected, prices_as_downloaded=aligned, tr_proxy=tr_proxy, missing=missing,
                      stale=stale, dropped_dates=dropped, demergers=dem, large_moves=drops, large_gains=gains,
                      splits=spl, checks=checks)
    res.log = hygiene_report_lines(res)
    if verbose:
        print("\n".join(res.log))
    return res


def hygiene_report_lines(res: CleanResult) -> list[str]:
    """Human-readable summary of every hygiene step (used by run_all.py and the notebook)."""
    pct = lambda x: f"{x * 100:+.2f}%"  # noqa: E731
    lines = ["DATA HYGIENE REPORT", "=" * 19, "", "1) Missing values in the raw union of dates:"]
    for s, r in res.missing.iterrows():
        lines.append(f"   {s:11s} rows={r['rows']:5d} missing={r['missing']:2d} {r['missing_dates']}")
    lines += ["", "2) Zero-volume stock rows (stale prices, treated as missing):"]
    for _, r in res.stale.iterrows():
        lines.append(f"   {pd.Timestamp(r['date']).date()} {r['n_series']:2d} stocks: {r['series']}")
    lines += ["", "3) Dates dropped when aligning on common trading days:"]
    for _, r in res.dropped_dates.iterrows():
        lines.append(f"   {pd.Timestamp(r['date']).date()}: {r['reason']}" + (f" [{r['note'][:60]}...]" if r['note'] else ""))
    p = res.prices
    lines.append(f"   aligned panel: {len(p)} trading days, {p.index[0].date()} to {p.index[-1].date()}, "
                 f"{p.shape[1]} series")
    lines += ["", "4) Demerger corrections (before/after):"]
    for _, r in res.demergers.iterrows():
        lines += [f"   {r['ticker']} ex-date {r['ex_date']} ({r['spun_off']}, {r['ratio']})",
                  f"     exchange: prev close Rs {r['prev_close_rs']:,.2f}, discovered Rs {r['discovered_price_rs']:,.2f}"
                  f" -> factor {r['factor_exchange']:.5f}; spun-off share worth Rs "
                  f"{r['child_value_per_child_share_exchange_rs']:,.2f}",
                  f"     Yahoo already embeds factor {r['factor_yahoo_embedded']:.5f} (spun-off share worth Rs "
                  f"{r['child_value_per_child_share_yahoo_rs']:,.2f}); residual factor applied {r['factor_applied']:.5f}",
                  f"     ex-date return: traded price {pct(r['ex_date_return_traded_price'])}, "
                  f"Yahoo Adj Close as downloaded {pct(r['ex_date_return_as_downloaded'])}, "
                  f"corrected {pct(r['ex_date_return_corrected'])}"]
    lines += ["", "5) One-day returns below -8% (after correction):"]
    for _, r in res.large_moves.iterrows():
        lines.append(f"   {r['date']} {r['ticker']:9s} {pct(r['return'])} (NIFTY {pct(r['nifty_return'])}); "
                     f"Yahoo action: {r['yahoo_corporate_action_that_day']}; {r['status']}: {r['cause']}")
    lines += ["   One-day returns above +8% (for completeness):"]
    for _, r in res.large_gains.iterrows():
        lines.append(f"   {r['date']} {r['ticker']:9s} {pct(r['return'])} (NIFTY {pct(r['nifty_return'])}); "
                     f"{r['status']}: {r['cause']}")
    lines += ["", "6) Bonus issues reported by Yahoo as splits:"]
    for _, r in res.splits.iterrows():
        lines.append(f"   {r['ticker']} {r['ex_date']} {r['ratio']}: return if unadjusted {pct(r['return_if_unadjusted'])}, "
                     f"Adj Close return {pct(r['adj_close_return'])}, max |return| t-1..t+1 "
                     f"{r['max_abs_return_t-1_to_t+1'] * 100:.2f}% -> "
                     f"{'no artificial jump' if r['no_artificial_jump'] else 'JUMP'}")
    lines += ["", "7) Hygiene checks:"]
    lines += [f"   [{'PASS' if ok else 'FAIL'}] {name}" for name, ok in res.checks.items()]
    return lines


if __name__ == "__main__":
    clean_prices(verbose=True)
