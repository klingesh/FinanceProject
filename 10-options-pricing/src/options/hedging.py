"""Discrete delta hedging of a short European option under geometric Brownian motion.

The writer sells one option at its Black-Scholes value (implied vol sigma_implied), holds the
Black-Scholes delta in the underlying, rebalances at n_steps equally spaced dates, finances the
position at r and receives the dividend yield q on the units held. The index follows GBM with
volatility sigma_real and total expected return mu (default r, the risk-neutral drift). The
terminal hedging P&L in index points is

    P&L = cash_T + delta_{last} * S_T - payoff(S_T).

With sigma_real = sigma_implied the mean P&L is close to zero and its standard deviation falls
roughly as 1/sqrt(n_steps). With sigma_real above sigma_implied a short-gamma writer loses money.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .black_scholes import bs_delta, bs_price

__all__ = ["simulate_delta_hedge", "hedge_experiment"]


def simulate_delta_hedge(
    S0: float,
    K: float,
    T: float,
    r: float,
    q: float,
    sigma_implied: float,
    sigma_real: float | None = None,
    n_steps: int = 24,
    n_paths: int = 20000,
    seed: int = 42,
    mu: float | None = None,
    option: str = "call",
) -> np.ndarray:
    """Terminal P&L (index points per unit) of a short option hedged with BS deltas, one value per path."""
    sigma_real = sigma_implied if sigma_real is None else sigma_real
    mu = r if mu is None else mu
    rng = np.random.default_rng(seed)
    dt = T / n_steps
    S = np.full(n_paths, float(S0))
    premium = float(bs_price(S0, K, T, r, sigma_implied, q, option))
    delta = np.full(n_paths, float(bs_delta(S0, K, T, r, sigma_implied, q, option)))
    cash = premium - delta * S
    growth, carry = np.exp(r * dt), np.exp(q * dt) - 1.0
    drift = (mu - q - 0.5 * sigma_real**2) * dt
    vol = sigma_real * np.sqrt(dt)
    for k in range(n_steps):
        z = rng.standard_normal(n_paths)
        S_new = S * np.exp(drift + vol * z)
        cash = cash * growth + delta * S * carry
        S = S_new
        if k < n_steps - 1:
            tau = T - (k + 1) * dt
            new_delta = np.asarray(bs_delta(S, K, tau, r, sigma_implied, q, option))
            cash -= (new_delta - delta) * S
            delta = new_delta
    payoff = np.maximum(S - K, 0.0) if option == "call" else np.maximum(K - S, 0.0)
    return cash + delta * S - payoff


def hedge_experiment(
    S0: float,
    K: float,
    T: float,
    r: float,
    q: float,
    sigma_implied: float,
    steps_list: tuple[int, ...] = (6, 12, 24, 48, 96, 192),
    real_vols: tuple[float, ...] | None = None,
    n_paths: int = 20000,
    seed: int = 42,
    lot: int = 65,
) -> pd.DataFrame:
    """Summary statistics of hedging P&L across rebalancing frequencies and realised vols."""
    premium = float(bs_price(S0, K, T, r, sigma_implied, q, "call"))
    rows = []
    vols = (sigma_implied,) if real_vols is None else real_vols
    for sr in vols:
        for n in steps_list:
            pnl = simulate_delta_hedge(S0, K, T, r, q, sigma_implied, sr, n, n_paths, seed)
            rows.append(
                {
                    "sigma_implied": sigma_implied,
                    "sigma_real": sr,
                    "rebalances": n,
                    "mean_pts": pnl.mean(),
                    "std_pts": pnl.std(ddof=1),
                    "p05_pts": np.percentile(pnl, 5),
                    "p95_pts": np.percentile(pnl, 95),
                    "std_pct_of_premium": 100 * pnl.std(ddof=1) / premium,
                    "mean_per_lot_rs": pnl.mean() * lot,
                    "std_per_lot_rs": pnl.std(ddof=1) * lot,
                    "premium_pts": premium,
                }
            )
    return pd.DataFrame(rows)
