"""Rolling one-day-ahead VaR backtest and coverage tests.

Models (each re-estimated every day on the previous 250 daily returns):
    hs        historical simulation
    n_sample  normal, sigma = sample standard deviation of the window
    n_ewma    normal, sigma from the RiskMetrics EWMA covariance (lambda = 0.94)
    t_ewma    Student-t with EWMA sigma; degrees of freedom fitted by MLE on the window's
              EWMA-standardised returns
    fhs       filtered historical simulation: empirical quantile of the window's
              EWMA-standardised returns, rescaled by today's EWMA sigma
Tests: Kupiec proportion-of-failures, Christoffersen independence, conditional coverage and the
Basel traffic light (99% VaR, last 250 days). An exception is a day whose loss is larger than the
VaR forecast made the evening before: r_t < -VaR_t.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from scipy.special import xlogy

from . import var_models as vm

MODELS = {
    "hs": "Historical simulation",
    "n_sample": "Normal (sample sigma)",
    "n_ewma": "Normal (EWMA sigma)",
    "t_ewma": "Student-t (EWMA sigma)",
    "fhs": "Filtered HS (EWMA)",
}


def ewma_sigma_forecasts(asset_returns: pd.DataFrame, w: np.ndarray, lam: float, seed_window: int) -> pd.Series:
    """One-day-ahead EWMA portfolio sigma for every day of the sample.

    The recursion is seeded with the sample covariance of the first `seed_window` days. Forecasts
    are only used from day `seed_window` onward, when that seed is already known, so there is no
    look-ahead; by then the seed carries a weight of lam**seed_window (about 2e-7).
    """
    r = asset_returns.to_numpy()
    s = vm.ewma_covariance(r, lam, np.cov(r[:seed_window].T))
    sig = np.sqrt(np.einsum("i,tij,j->t", w, s[:-1], w))
    return pd.Series(sig, index=asset_returns.index, name="sigma_ewma")


def rolling_forecasts(port_ret: pd.Series, asset_returns: pd.DataFrame, w: np.ndarray, window: int,
                      alphas: tuple[float, ...], lam: float) -> pd.DataFrame:
    """VaR forecasts (positive loss fractions) for every day after the first `window` days."""
    r = port_ret.to_numpy()
    sig = ewma_sigma_forecasts(asset_returns, w, lam, window).to_numpy()
    e = r / sig  # EWMA-standardised returns
    rows = []
    for t in range(window, len(r)):
        win, ewin = r[t - window:t], e[t - window:t]
        nu = vm.fit_t_df(ewin)
        sd = win.std(ddof=1)
        row = {"date": port_ret.index[t], "ret": r[t], "sigma_ewma": sig[t], "sigma_sample": sd, "nu_t": nu}
        for a in alphas:
            k = int(round(a * 100))
            row[f"hs_{k}"] = vm.historical_var_es(win, a)[0]
            row[f"n_sample_{k}"] = stats.norm.ppf(a) * sd
            row[f"n_ewma_{k}"] = stats.norm.ppf(a) * sig[t]
            row[f"t_ewma_{k}"] = -vm.std_t_ppf(1 - a, nu) * sig[t]
            row[f"fhs_{k}"] = -vm.empirical_quantile(ewin, 1 - a) * sig[t]
        rows.append(row)
    return pd.DataFrame(rows).set_index("date")


def next_day_forecasts(port_ret: pd.Series, asset_returns: pd.DataFrame, w: np.ndarray, window: int,
                       alphas: tuple[float, ...], lam: float, value: float) -> pd.DataFrame:
    """VaR of every backtest model for the trading day after the sample, from the last `window` days."""
    r = port_ret.to_numpy()
    R = asset_returns.to_numpy()
    s = vm.ewma_covariance(R, lam, np.cov(R[:window].T))
    sig_hist = np.sqrt(np.einsum("i,tij,j->t", w, s[:-1], w))
    sig_next = float(np.sqrt(w @ s[-1] @ w))
    win, ewin = r[-window:], (r / sig_hist)[-window:]
    nu = vm.fit_t_df(ewin)
    rows = []
    for key, name in MODELS.items():
        row = {"model": name, "key": key}
        for a in alphas:
            k = int(round(a * 100))
            if key == "hs":
                v = vm.historical_var_es(win, a)[0]
            elif key == "n_sample":
                v = stats.norm.ppf(a) * win.std(ddof=1)
            elif key == "n_ewma":
                v = stats.norm.ppf(a) * sig_next
            elif key == "t_ewma":
                v = -vm.std_t_ppf(1 - a, nu) * sig_next
            else:
                v = -vm.empirical_quantile(ewin, 1 - a) * sig_next
            row[f"var{k}_inr"] = round(v * value, 0)
            row[f"var{k}_pct"] = round(100 * v, 4)
        rows.append(row)
    out = pd.DataFrame(rows)
    out.attrs.update({"sigma_ewma_next": sig_next, "nu_next": nu})
    return out


def residual_diagnostics(fc: pd.DataFrame) -> dict:
    """Moments and tail frequencies of the EWMA-standardised out-of-sample returns."""
    e = (fc["ret"] / fc["sigma_ewma"]).to_numpy()
    sk, ku = vm.sample_skew_kurt(e)
    return {"mean": float(e.mean()), "variance": float(e.var(ddof=1)), "skew": sk, "excess_kurtosis": ku,
            "share_below_-1.645": float((e < -stats.norm.ppf(0.95)).mean()),
            "share_below_-2.326": float((e < -stats.norm.ppf(0.99)).mean()),
            "nu_mean": float(fc["nu_t"].mean()), "nu_median": float(fc["nu_t"].median())}


def kupiec_pof(exceptions: np.ndarray, p: float) -> dict:
    """Kupiec (1995) proportion-of-failures test of H0: exception probability = p.

    LR = -2 ln[(1-p)^(n-x) p^x] + 2 ln[(1-x/n)^(n-x) (x/n)^x] ~ chi2(1).
    """
    i = np.asarray(exceptions, dtype=int)
    n, x = i.size, int(i.sum())
    ph = x / n
    ll0 = xlogy(n - x, 1 - p) + xlogy(x, p)
    ll1 = xlogy(n - x, 1 - ph) + xlogy(x, ph)
    lr = max(-2 * (ll0 - ll1), 0.0)
    return {"n": n, "exceptions": x, "rate": ph, "lr_pof": lr, "p_pof": float(stats.chi2.sf(lr, 1))}


def christoffersen_ind(exceptions: np.ndarray) -> dict:
    """Christoffersen (1998) independence test: is an exception more likely after an exception?

    Uses transition counts n_ij (i = yesterday, j = today) and compares a first-order Markov
    chain (pi01, pi11) with a constant probability pi. LR ~ chi2(1).
    """
    i = np.asarray(exceptions, dtype=int)
    prev, cur = i[:-1], i[1:]
    n00 = int(((prev == 0) & (cur == 0)).sum())
    n01 = int(((prev == 0) & (cur == 1)).sum())
    n10 = int(((prev == 1) & (cur == 0)).sum())
    n11 = int(((prev == 1) & (cur == 1)).sum())
    pi01 = n01 / (n00 + n01) if n00 + n01 else 0.0
    pi11 = n11 / (n10 + n11) if n10 + n11 else 0.0
    pi = (n01 + n11) / (n00 + n01 + n10 + n11)
    ll0 = xlogy(n00 + n10, 1 - pi) + xlogy(n01 + n11, pi)
    ll1 = xlogy(n00, 1 - pi01) + xlogy(n01, pi01) + xlogy(n10, 1 - pi11) + xlogy(n11, pi11)
    lr = max(-2 * (ll0 - ll1), 0.0)
    return {"n00": n00, "n01": n01, "n10": n10, "n11": n11, "pi01": pi01, "pi11": pi11,
            "lr_ind": lr, "p_ind": float(stats.chi2.sf(lr, 1))}


def conditional_coverage(exceptions: np.ndarray, p: float) -> dict:
    """Christoffersen (1998) conditional-coverage test: correct rate p AND no clustering.

    LR_cc = -2 ln[L(p) / L(pi01, pi11)] ~ chi2(2), both likelihoods on the n - 1 day-to-day transitions:
        L(p)          = (1-p)^(n00+n10) p^(n01+n11)
        L(pi01, pi11) = (1-pi01)^n00 pi01^n01 (1-pi11)^n10 pi11^n11
    This equals the Kupiec statistic on days 2..n plus LR_ind exactly. (Adding the Kupiec statistic on
    all n days instead, as some texts do, differs only by the first day's contribution.)
    """
    ind = christoffersen_ind(exceptions)
    n00, n01, n10, n11 = ind["n00"], ind["n01"], ind["n10"], ind["n11"]
    ll_p = xlogy(n00 + n10, 1 - p) + xlogy(n01 + n11, p)
    ll_1 = (xlogy(n00, 1 - ind["pi01"]) + xlogy(n01, ind["pi01"]) + xlogy(n10, 1 - ind["pi11"])
            + xlogy(n11, ind["pi11"]))
    lr = max(-2 * (ll_p - ll_1), 0.0)
    return {"lr_cc": lr, "p_cc": float(stats.chi2.sf(lr, 2))}


def basel_zone_bounds(days: int = 250, p: float = 0.01) -> tuple[int, int]:
    """Largest green and smallest red exception count from the Basel (1996) binomial rule.

    Green: cumulative binomial probability of x or fewer exceptions below 95%.
    Red: cumulative probability at or above 99.99%. For 250 days at 1% this gives (4, 10).
    """
    cdf = stats.binom.cdf(np.arange(days + 1), days, p)
    green_max = int(np.max(np.nonzero(cdf < 0.95)[0]))
    red_min = int(np.min(np.nonzero(cdf >= 0.9999)[0]))
    return green_max, red_min


def traffic_light(exceptions_250: int) -> str:
    """Basel zone for a 99% VaR model from exceptions in 250 days: green 0-4, yellow 5-9, red 10+."""
    if exceptions_250 <= 4:
        return "green"
    return "yellow" if exceptions_250 <= 9 else "red"


def backtest_summary(fc: pd.DataFrame, alphas: tuple[float, ...], last_n: int = 250,
                     test_size: float = 0.05) -> pd.DataFrame:
    """Coverage and independence tests for every model and confidence level."""
    rows = []
    for key, name in MODELS.items():
        for a in alphas:
            k = int(round(a * 100))
            exc = (fc["ret"] < -fc[f"{key}_{k}"]).to_numpy()
            pof = kupiec_pof(exc, 1 - a)
            ind = christoffersen_ind(exc)
            cc = conditional_coverage(exc, 1 - a)
            recent = kupiec_pof(exc[-last_n:], 1 - a)
            rows.append({
                "model": name, "key": key, "confidence": a, "days": pof["n"],
                "expected": round(pof["n"] * (1 - a), 1), "exceptions": pof["exceptions"],
                "rate_pct": round(100 * pof["rate"], 2),
                "lr_pof": round(pof["lr_pof"], 3), "p_pof": round(pof["p_pof"], 4),
                "n11": ind["n11"], "lr_ind": round(ind["lr_ind"], 3), "p_ind": round(ind["p_ind"], 4),
                "lr_cc": round(cc["lr_cc"], 3), "p_cc": round(cc["p_cc"], 4),
                "pof_verdict": "reject" if pof["p_pof"] < test_size else "accept",
                "ind_verdict": "reject" if ind["p_ind"] < test_size else "accept",
                "cc_verdict": "reject" if cc["p_cc"] < test_size else "accept",
                "exceptions_last250": recent["exceptions"],
                "expected_last250": round(last_n * (1 - a), 1),
                "p_pof_last250": round(recent["p_pof"], 4),
                "basel_zone_last250": traffic_light(recent["exceptions"]) if k == 99 else "",
                "avg_var_pct": round(100 * fc[f"{key}_{k}"].mean(), 3),
            })
    return pd.DataFrame(rows)
