"""Load and clean the NSE NIFTY option-chain snapshots and the Yahoo index histories.

NSE JSON layout (https://www.nseindia.com/api/option-chain-v3?type=Indices&symbol=NIFTY&expiry=<date>):
records.timestamp, records.underlyingValue and records.data[], one entry per strike with a CE
(call) and PE (put) object holding lastPrice, buyPrice1/sellPrice1 (best bid/ask),
buyQuantity1/sellQuantity1, openInterest, totalTradedVolume, impliedVolatility (%) and
underlyingValue. Strikes with no listed contract carry an all-zero object with identifier=None.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

__all__ = [
    "VALUATION_DATE",
    "load_chain_json",
    "load_option_chains",
    "apply_quote_filters",
    "filter_summary",
    "load_index_history",
]

#: Valuation date of the snapshot (30-Oct-2026 close). Expiry is at the same clock time, so
#: T = calendar days / 365 exactly.
VALUATION_DATE = pd.Timestamp("2026-10-30")


def load_chain_json(path: str | Path) -> pd.DataFrame:
    """Read one NSE option-chain JSON file into a tidy frame (one row per strike and option type)."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    rec = raw["records"]
    rows = []
    for item in rec["data"]:
        for side, opt in (("CE", "C"), ("PE", "P")):
            o = item.get(side)
            if not o or o.get("identifier") is None:
                continue  # no contract listed at this strike
            rows.append(
                {
                    "expiry": pd.to_datetime(item["expiryDates"], format="%d-%b-%Y"),
                    "strike": float(item["strikePrice"]),
                    "option_type": opt,
                    "bid": float(o.get("buyPrice1") or 0.0),
                    "ask": float(o.get("sellPrice1") or 0.0),
                    "bid_qty": float(o.get("buyQuantity1") or 0.0),
                    "ask_qty": float(o.get("sellQuantity1") or 0.0),
                    "last": float(o.get("lastPrice") or 0.0),
                    "open_interest": float(o.get("openInterest") or 0.0),
                    "volume": float(o.get("totalTradedVolume") or 0.0),
                    "iv_nse_pct": float(o.get("impliedVolatility") or 0.0),
                    "underlying_value": float(o.get("underlyingValue") or 0.0),
                    "identifier": o.get("identifier"),
                }
            )
    df = pd.DataFrame(rows)
    df["snapshot_time"] = pd.to_datetime(rec["timestamp"], format="%d-%b-%Y %H:%M:%S")
    df["chain_underlying"] = float(rec["underlyingValue"])
    return df


def load_option_chains(raw_dir: str | Path, valuation_date: pd.Timestamp = VALUATION_DATE) -> pd.DataFrame:
    """Load every nse_nifty_chain_*.json file in raw_dir and add derived columns.

    Added columns: days (calendar days to expiry), T (= days / 365), mid (only when both quotes
    are positive), spread, rel_spread (spread / mid), moneyness (strike / chain underlying).
    """
    files = sorted(Path(raw_dir).glob("nse_nifty_chain_*.json"))
    if not files:
        raise FileNotFoundError(f"no NSE chain files in {raw_dir}")
    df = pd.concat([load_chain_json(f) for f in files], ignore_index=True)
    df["days"] = (df["expiry"] - valuation_date).dt.days
    df["T"] = df["days"] / 365.0
    both = (df["bid"] > 0) & (df["ask"] > 0)
    df["mid"] = np.where(both, 0.5 * (df["bid"] + df["ask"]), np.nan)
    df["spread"] = np.where(both, df["ask"] - df["bid"], np.nan)
    df["rel_spread"] = df["spread"] / df["mid"]
    df["moneyness"] = df["strike"] / df["chain_underlying"]
    df = df.sort_values(["expiry", "strike", "option_type"]).reset_index(drop=True)
    return df


def apply_quote_filters(
    df: pd.DataFrame,
    spot: float,
    moneyness_band: float = 0.10,
    max_rel_spread: float = 0.25,
) -> pd.DataFrame:
    """Flag the quotes used for pricing.

    A quote is usable when all of these hold:
      f_oi      open interest > 0
      f_quotes  best bid > 0, best ask > 0 and ask >= bid
      f_spread  (ask - bid) / mid <= max_rel_spread
      f_band    |strike / spot - 1| <= moneyness_band
    """
    out = df.copy()
    out["f_oi"] = out["open_interest"] > 0
    out["f_quotes"] = (out["bid"] > 0) & (out["ask"] > 0) & (out["ask"] >= out["bid"])
    out["f_spread"] = out["f_quotes"] & (out["rel_spread"] <= max_rel_spread)
    out["f_band"] = (out["strike"] / spot - 1.0).abs() <= moneyness_band
    out["usable"] = out["f_oi"] & out["f_quotes"] & out["f_spread"] & out["f_band"]
    return out


def filter_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Count contracts surviving each filter step, by expiry (cumulative, in the order applied)."""
    rows = []
    for exp, g in df.groupby("expiry"):
        step1 = g["f_band"]
        step2 = step1 & g["f_oi"]
        step3 = step2 & g["f_quotes"]
        step4 = step3 & g["f_spread"]
        rows.append(
            {
                "expiry": exp.date(),
                "days": int(g["days"].iloc[0]),
                "listed": len(g),
                "within_10pct": int(step1.sum()),
                "and_oi_gt_0": int(step2.sum()),
                "and_two_sided_quote": int(step3.sum()),
                "and_spread_le_25pct": int(step4.sum()),
                "usable_calls": int((step4 & (g["option_type"] == "C")).sum()),
                "usable_puts": int((step4 & (g["option_type"] == "P")).sum()),
            }
        )
    return pd.DataFrame(rows)


def load_index_history(path: str | Path) -> pd.Series:
    """Daily close series from a Yahoo Finance CSV (Date, Close, ...), indexed by date."""
    df = pd.read_csv(path, parse_dates=["Date"])
    s = df.set_index("Date")["Close"].astype(float).sort_index()
    s = s[~s.index.duplicated(keep="last")]
    return s.dropna()
