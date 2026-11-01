"""Premium-adjusted relative value for Asian Paints (phase 2 of the initiation report).

Lens, fixed before the result was known (report Section 6): Asian Paints' median P/E premium to the median of its four
listed peers over the five years to 30-Oct-2026, applied to the peers' current median P/E on FY2027E consensus EPS and
to Project 3's FY2028E EPS (12-month-forward basis):

    relative value = peer median P/E (FY2027E) x (1 + 5-year median premium) x FY2028E EPS

Daily trailing P/E per company = market cap / trailing PAT to owners excluding one-offs.
- Market cap = Yahoo Finance close x shares outstanding today (Project 3 comps table). Yahoo restates past closes for
  bonus issues and splits, so a past close x today's share count gives the past market cap. Share capital rose 20% at
  Berger and 50% at Kansai Nerolac in FY2024 (bonus issues); JSW Dulux split its shares 1:10 on 22-Oct-2026.
- Trailing PAT = PAT to owners of the last reported fiscal year less one-offs after tax,
  PATOWN - (EXCEP + ONEOFF) x PAT / PBT (the ratio workbook's definition). Fiscal year k counts from 1-June of
  calendar year k, after all five companies have published their March-quarter results.

Run on its own for a quick print:  python build/relative_value.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TARGET = "Asian Paints"
PEERS = ["Berger Paints", "Kansai Nerolac", "JSW Dulux", "Indigo Paints"]
SYMBOL = {"Asian Paints": "ASIANPAINT", "Berger Paints": "BERGEPAINT", "Kansai Nerolac": "KANSAINER",
          "JSW Dulux": "JSWDULUX", "Indigo Paints": "INDIGOPNTS"}
SWITCH_MONTH = 6  # fiscal year k's annual results count from 1-June of calendar year k


def adjusted_pat(inputs: pd.DataFrame) -> pd.DataFrame:
    """PAT to owners excluding one-offs (Rs crore): rows = company name, columns = FY2021..FY2026.

    inputs is data/ratio_inputs.csv (one row per company and code)."""
    fys = [c for c in inputs.columns if c.startswith("FY")]
    out = {}
    for name, grp in inputs.groupby("name"):
        g = grp.set_index("code")[fys].astype(float)
        one_off = g.loc["EXCEP"].fillna(0) + g.loc["ONEOFF"].fillna(0)
        out[name] = g.loc["PATOWN"] - one_off * g.loc["PAT"] / g.loc["PBT"]
    return pd.DataFrame(out).T[fys]


def trailing_fy(dates: pd.DatetimeIndex) -> pd.Series:
    """Label of the last fiscal year whose annual results are public on each date (FYk from 1-June of year k)."""
    yr = dates.year - (dates.month < SWITCH_MONTH).astype(int)
    return pd.Series([f"FY{y}" for y in yr], index=dates)


def pe_history(prices: pd.DataFrame, shares: dict[str, float], adj_pat: pd.DataFrame,
               start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Daily trailing P/E for each company, the peer median P/E and Asian Paints' premium to it.

    prices: long table (Date, Close, name) from data/prices/prices_daily.csv; shares in crore."""
    wide = prices.pivot_table(index="Date", columns="name", values="Close").sort_index()
    wide = wide.loc[(wide.index >= start) & (wide.index <= end), [TARGET] + PEERS].dropna()
    fy = trailing_fy(wide.index)
    hist = pd.DataFrame(index=wide.index)
    hist["trailing_fy"] = fy.values
    for co in [TARGET] + PEERS:
        pat = fy.map(adj_pat.loc[co]).astype(float).values
        hist[f"mcap_{SYMBOL[co]}"] = wide[co] * shares[co]
        hist[f"pe_{SYMBOL[co]}"] = hist[f"mcap_{SYMBOL[co]}"] / pat
    hist["peer_median_pe"] = hist[[f"pe_{SYMBOL[c]}" for c in PEERS]].median(axis=1)
    hist["ap_premium"] = hist[f"pe_{SYMBOL[TARGET]}"] / hist["peer_median_pe"] - 1
    return hist


def premium_stats(hist: pd.DataFrame) -> dict[str, float]:
    """Distribution of the premium and of Asian Paints' own P/E over the window (each trading day weighted equally)."""
    p, own, med = hist["ap_premium"], hist[f"pe_{SYMBOL[TARGET]}"], hist["peer_median_pe"]
    s: dict[str, float] = {"n_days": float(len(hist))}
    for k, q in [("p25", 0.25), ("median", 0.5), ("p75", 0.75)]:
        s[f"premium_{k}"] = float(p.quantile(q))
        s[f"own_pe_{k}"] = float(own.quantile(q))
    s.update({"premium_mean": float(p.mean()), "premium_min": float(p.min()), "premium_max": float(p.max()),
              "premium_now": float(p.iloc[-1]), "own_pe_min": float(own.min()), "own_pe_max": float(own.max()),
              "own_pe_now": float(own.iloc[-1]), "peer_pe_start": float(med.iloc[0]), "peer_pe_now": float(med.iloc[-1]),
              "own_pe_start": float(own.iloc[0])})
    yearly = hist.groupby("trailing_fy")["ap_premium"].median()
    for fy, v in yearly.items():
        s[f"premium_median_{fy}"] = float(v)
    return s


def relative_value(peer_pe: float, premium: float, eps: float) -> float:
    """Premium-adjusted value per share = peer median P/E x (1 + premium) x EPS."""
    return peer_pe * (1 + premium) * eps


def run(p3_comps: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> tuple[pd.DataFrame, dict[str, float]]:
    """Compute the history and the statistics from this project's data/ files and Project 3's comps table."""
    inputs = pd.read_csv(ROOT / "data" / "ratio_inputs.csv")
    prices = pd.read_csv(ROOT / "data" / "prices" / "prices_daily.csv", parse_dates=["Date"])
    shares = {r["company"]: float(r["shares_crore"]) for _, r in p3_comps.iterrows() if r["row_type"] in ("target", "peer")}
    adj = adjusted_pat(inputs)
    hist = pe_history(prices, shares, adj, start, end)
    stats = premium_stats(hist)
    for co in [TARGET] + PEERS:
        stats[f"shares_{SYMBOL[co]}"] = shares[co]
        for fy in adj.columns:
            stats[f"adjpat_{SYMBOL[co]}_{fy}"] = float(adj.loc[co, fy])
    return hist, stats


if __name__ == "__main__":
    p3 = Path(r"d:\Financeprojects\FinanceProject-branches\project-03-comparable-company-analysis"
              r"\03-comparable-company-analysis\outputs")
    comps = pd.read_csv(p3 / "comps_table.csv")
    h, st = run(comps, pd.Timestamp("2021-10-29"), pd.Timestamp("2026-10-30"))
    for k, v in st.items():
        print(f"{k}: {v:,.4f}")
    print(h.iloc[[0, -1]].T)
