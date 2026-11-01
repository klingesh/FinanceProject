"""Model validation: textbook values, parity, convergence, early exercise, Greeks and implied vol.

`run_model_validation()` returns a table with one row per check and a PASS/FAIL status;
`print_checks()` prints it as PASS/FAIL lines. `convergence_study()` returns the binomial
convergence data used for the convergence figure.

Textbook references (J. Hull, Options, Futures, and Other Derivatives):
- BSM example: S = 42, K = 40, r = 10%, sigma = 20%, T = 0.5 -> call 4.76, put 0.81.
- American put tree: S = 50, K = 50, r = 10%, sigma = 40%, T = 5 months -> 4.49 with 5 steps;
  4.263, 4.272, 4.278 and 4.283 with 30, 50, 100 and 500 steps.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .binomial import binomial_greeks, binomial_price, early_exercise_boundary
from .black_scholes import bs_delta, bs_gamma, bs_greeks, bs_price, bs_rho, bs_theta, bs_vega, parity_residual
from .implied_vol import implied_vol, price_bounds

__all__ = ["HULL", "convergence_study", "run_model_validation", "check_row", "print_checks"]

HULL = {"S": 42.0, "K": 40.0, "T": 0.5, "r": 0.10, "sigma": 0.20, "q": 0.0}


def check_row(section: str, test: str, value: float, target: str, passed: bool, note: str = "") -> dict:
    """One validation result row."""
    return {"section": section, "test": test, "value": value, "target": target, "status": "PASS" if passed else "FAIL", "note": note}


def print_checks(df: pd.DataFrame) -> None:
    """Print validation rows as 'PASS | section | test | value | target'."""
    for _, r in df.iterrows():
        v = r["value"]
        vs = f"{v:.6g}" if isinstance(v, (float, np.floating)) else str(v)
        print(f"{r['status']:4s} | {r['section']:<14s} | {r['test']:<62s} | value {vs:<12s} | target {r['target']}")
    n_fail = int((df["status"] != "PASS").sum())
    print(f"{len(df) - n_fail}/{len(df)} checks passed")


def convergence_study(
    S: float = HULL["S"], K: float = HULL["K"], T: float = HULL["T"], r: float = HULL["r"], sigma: float = HULL["sigma"],
    q: float = 0.0, option: str = "call", n_min: int = 10, n_max: int = 1000,
) -> pd.DataFrame:
    """CRR, two-step-average CRR and Leisen-Reimer European prices for N = n_min..n_max, with errors vs BSM."""
    bs = float(bs_price(S, K, T, r, sigma, q, option))
    Ns = np.arange(n_min, n_max + 2)
    crr = np.array([binomial_price(S, K, T, r, sigma, q, option, N=int(n), method="crr") for n in Ns])
    rows = []
    for i, n in enumerate(Ns[:-1]):
        lr = binomial_price(S, K, T, r, sigma, q, option, N=int(n), method="lr") if n % 2 == 1 else np.nan
        rows.append({"N": int(n), "parity": "odd" if n % 2 else "even", "crr": crr[i], "crr_avg_N_N1": 0.5 * (crr[i] + crr[i + 1]), "lr": lr})
    df = pd.DataFrame(rows)
    df["bs"] = bs
    for col in ("crr", "crr_avg_N_N1", "lr"):
        df[f"{col}_err"] = df[col] - bs
    return df


def _fd_greeks(S, K, T, r, sigma, q, option, hS_delta, hS_gamma, h_sig=1e-4, h_T=1e-5, h_r=1e-5):
    """Central finite-difference Greeks of the BSM price."""
    P = lambda s=S, t=T, rr=r, sg=sigma: bs_price(s, K, t, rr, sg, q, option)  # noqa: E731
    return {
        "delta": (P(s=S + hS_delta) - P(s=S - hS_delta)) / (2 * hS_delta),
        "gamma": (P(s=S + hS_gamma) - 2 * P() + P(s=S - hS_gamma)) / hS_gamma**2,
        "vega": (P(sg=sigma + h_sig) - P(sg=sigma - h_sig)) / (2 * h_sig),
        "theta": -(P(t=T + h_T) - P(t=T - h_T)) / (2 * h_T),
        "rho": (P(rr=r + h_r) - P(rr=r - h_r)) / (2 * h_r),
    }


def _analytic_greeks(S, K, T, r, sigma, q, option):
    return {
        "delta": bs_delta(S, K, T, r, sigma, q, option),
        "gamma": bs_gamma(S, K, T, r, sigma, q),
        "vega": bs_vega(S, K, T, r, sigma, q),
        "theta": bs_theta(S, K, T, r, sigma, q, option),
        "rho": bs_rho(S, K, T, r, sigma, q, option),
    }


def run_model_validation(seed: int = 7) -> pd.DataFrame:
    """Run all model checks (no market data needed) and return the result table."""
    rows = []
    H = HULL
    args = (H["S"], H["K"], H["T"], H["r"], H["sigma"], H["q"])

    # --- Black-Scholes textbook values -----------------------------------------------------
    c = float(bs_price(*args, option="call"))
    p = float(bs_price(*args, option="put"))
    rows.append(check_row("BSM", "Hull example call price (S=42, K=40, r=10%, vol=20%, T=0.5)", c, "4.76 (2 dp)", round(c, 2) == 4.76))
    rows.append(check_row("BSM", "Hull example put price", p, "0.81 (2 dp)", round(p, 2) == 0.81))

    # --- Put-call parity on random contracts ------------------------------------------------
    rng = np.random.default_rng(seed)
    n = 10000
    S = rng.uniform(50, 150, n)
    K = rng.uniform(50, 150, n)
    T = rng.uniform(0.01, 3.0, n)
    r = rng.uniform(0.0, 0.10, n)
    q = rng.uniform(0.0, 0.05, n)
    sg = rng.uniform(0.05, 0.80, n)
    resid = np.abs(parity_residual(bs_price(S, K, T, r, sg, q, "call"), bs_price(S, K, T, r, sg, q, "put"), S, K, T, r, q))
    rows.append(check_row("Parity", "max |C - P - (S e^-qT - K e^-rT)|, 10,000 random contracts", float(resid.max()), "< 1e-10", resid.max() < 1e-10))

    # --- Analytic Greeks vs central finite differences --------------------------------------
    worst = 0.0
    for qq in (0.0, 0.03):
        for opt in ("call", "put"):
            a = _analytic_greeks(H["S"], H["K"], H["T"], H["r"], H["sigma"], qq, opt)
            f = _fd_greeks(H["S"], H["K"], H["T"], H["r"], H["sigma"], qq, opt, hS_delta=1e-3, hS_gamma=1e-2)
            worst = max(worst, max(abs(a[k] - f[k]) for k in a))
    rows.append(check_row("Greeks", "Hull example: max |analytic - finite difference| (5 Greeks, call+put, q=0 and 3%)", worst, "< 1e-4", worst < 1e-4))
    nifty = dict(S=23053.10, K=23100.0, T=24 / 365, r=np.log(1.0593), sigma=0.13, q=0.0285)
    worst_rel = 0.0
    for opt in ("call", "put"):
        a = _analytic_greeks(nifty["S"], nifty["K"], nifty["T"], nifty["r"], nifty["sigma"], nifty["q"], opt)
        f = _fd_greeks(nifty["S"], nifty["K"], nifty["T"], nifty["r"], nifty["sigma"], nifty["q"], opt, hS_delta=1.0, hS_gamma=5.0)
        worst_rel = max(worst_rel, max(abs(a[k] - f[k]) / abs(a[k]) for k in a))
    rows.append(check_row("Greeks", "NIFTY-size contract: max relative |analytic - finite difference|", worst_rel, "< 1e-4", worst_rel < 1e-4))

    # --- Implied volatility ------------------------------------------------------------------
    Ks = np.linspace(60, 140, 17)
    Ts = np.array([0.01, 0.05, 0.25, 1.0, 3.0])
    vols = np.array([0.05, 0.10, 0.20, 0.40, 0.80, 1.50])
    KK, TT, VV = np.meshgrid(Ks, Ts, vols, indexing="ij")
    max_err, n_cases, n_brent_case = 0.0, 0, 0
    for opt in ("call", "put"):
        for qq in (0.0, 0.03):
            pr = bs_price(100.0, KK, TT, 0.05, VV, qq, opt)
            lo, hi = price_bounds(100.0 * np.exp((0.05 - qq) * TT), KK, np.exp(-0.05 * TT), opt)
            vg = bs_vega(100.0, KK, TT, 0.05, VV, qq)
            ident = (pr - lo > 1e-10) & (hi - pr > 1e-10) & (vg > 1e-6)
            iv = implied_vol(pr, 100.0, KK, TT, 0.05, qq, opt)
            max_err = max(max_err, float(np.nanmax(np.abs(iv - VV)[ident])) if ident.any() else 0.0)
            if np.isnan(iv[ident]).any():
                max_err = np.inf
            n_cases += int(ident.sum())
    rows.append(check_row("Implied vol", f"Newton solver recovers input vol ({n_cases} identifiable contracts)", max_err, "< 1e-8", max_err < 1e-8,
                          "contracts priced within 1e-10 of a bound or with vega < 1e-6 are not identifiable in double precision"))
    # force the Brent fallback by capping Newton at one iteration
    sub = (slice(None), slice(1, 4), slice(1, 5))
    k_s, t_s, v_s = KK[sub], TT[sub], VV[sub]
    pr = bs_price(100.0, k_s, t_s, 0.05, v_s, 0.0, "call")
    lo, hi = price_bounds(100.0 * np.exp(0.05 * t_s), k_s, np.exp(-0.05 * t_s), "call")
    ident = (pr - lo > 1e-10) & (hi - pr > 1e-10) & (bs_vega(100.0, k_s, t_s, 0.05, v_s, 0.0) > 1e-6)
    iv_b, info_b = implied_vol(pr, 100.0, k_s, t_s, 0.05, 0.0, "call", max_iter=1, return_info=True)
    err_b = float(np.nanmax(np.abs(iv_b - v_s)[ident]))
    n_brent = int((info_b["method"][ident] == 1).sum())
    rows.append(check_row("Implied vol", f"Brent fallback recovers input vol (Newton capped at 1 step, {int(ident.sum())} contracts)", err_b, "< 1e-8",
                          err_b < 1e-8 and not np.isnan(iv_b[ident]).any(), f"{n_brent} solved by brentq"))
    bad_prices = np.array([2.0, 0.0, -1.0, 100.0, 150.0])  # call S=K=100: lower bound 2.47, upper bound 100
    iv_bad = implied_vol(bad_prices, 100.0, 100.0, 0.5, 0.05, 0.0, "call")
    rows.append(check_row("Implied vol", "prices outside no-arbitrage bounds return NaN (5 cases)", int(np.isnan(iv_bad).sum()), "5 of 5 NaN", bool(np.isnan(iv_bad).all())))

    # --- Binomial convergence ----------------------------------------------------------------
    crr1000 = float(binomial_price(*args, option="call", N=1000, method="crr"))
    rows.append(check_row("Binomial", "CRR European call, N=1000: |price - BSM|", abs(crr1000 - c), "< 1e-3", abs(crr1000 - c) < 1e-3))
    avg = 0.5 * (crr1000 + float(binomial_price(*args, option="call", N=1001, method="crr")))
    rows.append(check_row("Binomial", "CRR average of N=1000 and N=1001: |price - BSM|", abs(avg - c), "< 1e-4", abs(avg - c) < 1e-4))
    lr101 = float(binomial_price(*args, option="call", N=101, method="lr"))
    rows.append(check_row("Binomial", "Leisen-Reimer European call, N=101: |price - BSM|", abs(lr101 - c), "< 1e-5", abs(lr101 - c) < 1e-5))
    lr_put = float(binomial_price(*args, option="put", N=101, method="lr"))
    rows.append(check_row("Binomial", "Leisen-Reimer European put, N=101: |price - BSM|", abs(lr_put - p), "< 1e-5", abs(lr_put - p) < 1e-5))

    # --- American options ----------------------------------------------------------------------
    am_c = float(binomial_price(*args, option="call", N=1000, american=True))
    rows.append(check_row("American", "American call, no dividends: |American - European| (CRR N=1000)", abs(am_c - crr1000), "< 1e-12", abs(am_c - crr1000) < 1e-12))
    am_p = float(binomial_price(*args, option="put", N=1000, american=True))
    eu_p = float(binomial_price(*args, option="put", N=1000, american=False))
    rows.append(check_row("American", "American put - European put, Hull S=42 example (CRR N=1000)", am_p - eu_p, "> 0", am_p - eu_p > 0))
    hull_am = {N: float(binomial_price(50.0, 50.0, 5 / 12, 0.10, 0.40, 0.0, "put", N=N, american=True)) for N in (5, 30, 50, 100, 500)}
    rows.append(check_row("American", "Hull American put (S=K=50, r=10%, vol=40%, 5 months), 5 steps", hull_am[5], "4.49 (2 dp)", round(hull_am[5], 2) == 4.49))
    targets = {30: 4.263, 50: 4.272, 100: 4.278, 500: 4.283}
    ok = all(round(hull_am[N], 3) == v for N, v in targets.items())
    rows.append(check_row("American", "Same put with 30/50/100/500 steps", hull_am[500], "4.263/4.272/4.278/4.283 (3 dp)", ok,
                          " / ".join(f"{hull_am[N]:.4f}" for N in targets)))
    bnd = early_exercise_boundary(50.0, 50.0, 5 / 12, 0.10, 0.40, 0.0, "put", N=2000).dropna()
    perp = 2 * 0.10 / (2 * 0.10 + 0.40**2)
    inside = bool(((bnd["boundary_over_K"] <= 1 + 1e-12) & (bnd["boundary_over_K"] >= perp)).all())
    rows.append(check_row("American", "Put exercise boundary lies between perpetual limit 2r/(2r+vol^2) and K", float(bnd["boundary_over_K"].min()), f">= {perp:.4f} and <= 1", inside))

    # --- Tree Greeks vs BSM ------------------------------------------------------------------
    bsg = bs_greeks(*args, option="call")
    tg = binomial_greeks(*args, option="call", N=1000, method="crr")
    rel = {k: abs(tg[k] - bsg[k]) / abs(bsg[k]) for k in ("delta", "gamma", "theta", "vega", "rho")}
    worst_k = max(rel, key=rel.get)
    rows.append(check_row("Binomial", "CRR N=1000 tree Greeks vs BSM: max relative error", rel[worst_k], "< 0.5%", rel[worst_k] < 0.005,
                          ", ".join(f"{k} {v:.1e}" for k, v in rel.items())))
    return pd.DataFrame(rows)
