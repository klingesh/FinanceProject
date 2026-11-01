"""Stress tests: worst historical days and hypothetical shocks applied to today's positions."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as cfg

# What happened on the worst portfolio days (news links in README.md and source_data/README.md)
EVENTS: dict[str, str] = {
    "2026-03-23": "US-Iran war: crude oil above $105 and no clarity on the Strait of Hormuz; NIFTY 50 -2.6% "
                  "to 22,512.65 and gold and silver fell about 10% (Livemint, Financial Express)",
    "2026-03-19": "Crude-oil spike, hawkish US Fed and an HDFC Bank sell-off after its part-time chairman "
                  "resigned; NIFTY 50 -3.26% to 23,002.15, its worst day since 4-Jun-2024 (Livemint, CNBC-TV18)",
    "2025-04-07": "Global sell-off after the US reciprocal tariffs; NIFTY 50 -3.24% to 22,161.60 "
                  "(Times of India)",
    "2022-02-24": "Russia invaded Ukraine; NIFTY 50 -4.78% to 16,247.95 while gold rose (The Hindu, Times of India)",
    "2026-02-01": "Sunday Union Budget session: higher STT on futures and options (NIFTY 50 -1.96% to 24,825.45) "
                  "and gold ETFs fell further after the 30-Jan precious-metals crash (The Hindu, Economic Times)",
}


def worst_days(port_ret: pd.Series, asset_returns: pd.DataFrame, value: float, k: int = 5) -> pd.DataFrame:
    """The k worst portfolio days: date, portfolio return and P&L, and each ETF's return that day."""
    idx = port_ret.nsmallest(k).index
    out = asset_returns.loc[idx].mul(100).round(2)
    out.columns = [cfg.HOLDINGS[c][0] + "_ret_pct" for c in out.columns]
    out.insert(0, "portfolio_ret_pct", (100 * port_ret.loc[idx]).round(3))
    out.insert(1, "pnl_inr", (value * port_ret.loc[idx]).round(0))
    out.index = out.index.date
    out.index.name = "date"
    return out


def hypothetical_shocks() -> dict[str, dict[str, float]]:
    """Instantaneous shocks (simple returns) by scenario and ticker.

    The Nasdaq leg: MON100 is a rupee price of a US-dollar index fund, so its rupee return is
    (1 + Nasdaq return)(1 + USD/INR return) - 1. An INR appreciation of 3% is modelled as USD/INR
    falling 3%, giving (0.85)(0.97) - 1 = -17.55%.
    """
    mon100 = (1 + cfg.NASDAQ_SHOCK) * (1 - cfg.INR_APPRECIATION) - 1
    eq = {"NIFTYBEES.NS": -0.10, "JUNIORBEES.NS": -0.10, "BANKBEES.NS": -0.10}
    nas = {"MON100.NS": mon100}
    gold = {"GOLDBEES.NS": 0.05}
    bond = {"SETF10GILT.NS": -0.02}
    return {
        "Indian equity -10%": eq,
        "Nasdaq-100 -15% and INR +3%": nas,
        "Gold +5%": gold,
        "Bonds -2% (yield spike)": bond,
        "Combined (all four)": {**eq, **nas, **gold, **bond},
    }


def hypothetical_stress(w: np.ndarray, value: float, var99: float) -> pd.DataFrame:
    """Rupee P&L per ETF and in total for each hypothetical scenario.

    `var99` is a 1-day 99% VaR in rupees, used to express each loss as a multiple of VaR.
    """
    positions = pd.Series(w * value, index=cfg.TICKERS)
    rows = []
    for name, shocks in hypothetical_shocks().items():
        s = pd.Series(shocks).reindex(cfg.TICKERS).fillna(0.0)
        pnl = positions * s
        row = {"scenario": name}
        for t in cfg.TICKERS:
            row[f"{cfg.HOLDINGS[t][0]}_shock_pct"] = round(100 * s[t], 2)
        for t in cfg.TICKERS:
            row[f"{cfg.HOLDINGS[t][0]}_pnl_inr"] = round(pnl[t], 0)
        row["total_pnl_inr"] = round(pnl.sum(), 0)
        row["total_pnl_pct"] = round(100 * pnl.sum() / value, 3)
        row["multiple_of_1d_var99"] = round(-pnl.sum() / var99, 2)
        rows.append(row)
    return pd.DataFrame(rows)
