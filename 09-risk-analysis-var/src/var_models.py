"""Value-at-Risk and Expected Shortfall models.

Conventions used throughout
---------------------------
* Inputs are simple daily returns in decimals. VaR and ES are returned as positive loss
  fractions of portfolio value; multiply by the portfolio value for rupees.
* For confidence level alpha (0.95 or 0.99) and tail probability p = 1 - alpha:
      VaR = -Q_p(r)                 (Q_p = p-quantile of the return distribution)
      ES  = -E[r | r <= Q_p(r)]     (average loss on the days beyond VaR)
* Parametric and Monte Carlo models assume a zero expected daily return unless `mu` is given.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import integrate, optimize, stats


# ------------------------------------------------------------------ historical simulation
def empirical_quantile(x: np.ndarray, p: float) -> float:
    """Sample p-quantile with linear interpolation between order statistics.

    Position h = (n - 1) p in the ascending sort; Q = x[floor h] + (h - floor h)(x[floor h + 1] - x[floor h]).
    This is Hyndman-Fan type 7, the default of numpy.quantile and pandas.Series.quantile.
    """
    xs = np.sort(np.asarray(x, dtype=float))
    h = (xs.size - 1) * p
    lo = int(np.floor(h))
    hi = min(lo + 1, xs.size - 1)
    return float(xs[lo] + (h - lo) * (xs[hi] - xs[lo]))


def historical_var_es(returns: np.ndarray, alpha: float) -> tuple[float, float]:
    """Historical-simulation VaR and ES: empirical quantile and mean of returns at or below it.

    With the type-7 quantile the tail holds floor((n - 1) p) + 1 observations, all of them losses at
    least as large as VaR: 13 of 1,240 days at 99% (n p = 12.4), 62 at 95%, 3 of 250 days at 99%,
    and exactly n p = 1,000 of 100,000 Monte Carlo scenarios at 99%. ES >= VaR by construction.
    """
    r = np.asarray(returns, dtype=float)
    q = empirical_quantile(r, 1 - alpha)
    return -q, -float(r[r <= q].mean())


def acerbi_tasche_es(returns: np.ndarray, alpha: float) -> float:
    """Alternative ES estimator: (1 / (n p)) x [sum of the floor(n p) worst returns + fractional next one].

    This is the sample version of ES = (1/p) * integral_0^p Q(u) du (Acerbi and Tasche, 2002). It is
    reported only as a robustness check of `historical_var_es`; the two differ when n p is not an integer.
    """
    xs = np.sort(np.asarray(returns, dtype=float))
    m = xs.size * (1 - alpha)
    k = int(np.floor(m))
    return -float((xs[:k].sum() + (m - k) * xs[k]) / m)


def es_standard_error(sims: np.ndarray, alpha: float) -> float:
    """Asymptotic standard error of the tail-mean ES estimate from n iid scenarios.

    Var(ES_hat) = [Var(L | L >= VaR) + (1 - p)(ES - VaR)^2] / (n p), with L = -return and p = 1 - alpha.
    Used to judge whether a Monte Carlo ES is close enough to its closed-form value.
    """
    r = np.asarray(sims, dtype=float)
    var, es = historical_var_es(r, alpha)
    tail = -r[r <= -var]
    p = 1 - alpha
    return float(np.sqrt((tail.var(ddof=1) + (1 - p) * (es - var) ** 2) / (r.size * p)))


# ------------------------------------------------------------------ parametric normal
def portfolio_sigma(cov: np.ndarray, w: np.ndarray) -> float:
    """Portfolio standard deviation sigma_p = sqrt(w' Sigma w)."""
    return float(np.sqrt(w @ cov @ w))


def normal_var_es(sigma: float, alpha: float, mu: float = 0.0) -> tuple[float, float]:
    """Normal VaR = z_alpha sigma - mu and ES = sigma phi(z_alpha) / (1 - alpha) - mu."""
    z = stats.norm.ppf(alpha)
    return z * sigma - mu, sigma * stats.norm.pdf(z) / (1 - alpha) - mu


def ewma_covariance(returns: np.ndarray, lam: float, seed_cov: np.ndarray) -> np.ndarray:
    """RiskMetrics EWMA covariance forecasts (zero-mean returns).

    S[0] = seed_cov and S[t+1] = lam S[t] + (1 - lam) r_t r_t'. S[t] is the forecast for day t
    made with data up to day t-1, so S[n] (the last element) is the forecast for the next
    trading day after the sample.
    """
    r = np.asarray(returns, dtype=float)
    n, k = r.shape
    s = np.empty((n + 1, k, k))
    s[0] = seed_cov
    for t in range(n):
        s[t + 1] = lam * s[t] + (1 - lam) * np.outer(r[t], r[t])
    return s


def sample_skew_kurt(returns: np.ndarray) -> tuple[float, float]:
    """Bias-corrected sample skewness and excess kurtosis."""
    r = np.asarray(returns, dtype=float)
    return float(stats.skew(r, bias=False)), float(stats.kurtosis(r, fisher=True, bias=False))


# ------------------------------------------------------------------ Cornish-Fisher
def cornish_fisher_z(z: np.ndarray | float, skew: float, exkurt: float) -> np.ndarray | float:
    """Cornish-Fisher adjusted standard-normal quantile.

    z_cf = z + (z^2 - 1) S/6 + (z^3 - 3z) K/24 - (2z^3 - 5z) S^2/36,
    with S = skewness and K = excess kurtosis.
    """
    return (z + (z**2 - 1) * skew / 6 + (z**3 - 3 * z) * exkurt / 24
            - (2 * z**3 - 5 * z) * skew**2 / 36)


def cornish_fisher_var_es(sigma: float, alpha: float, skew: float, exkurt: float,
                          mu: float = 0.0) -> tuple[float, float]:
    """Modified (Cornish-Fisher) VaR, and the ES implied by the Cornish-Fisher quantile function.

    VaR = -(mu + sigma z_cf) with z = Phi^-1(1 - alpha).
    ES  = -(mu + sigma E[z_cf(Z) | Z <= z]) where Z ~ N(0,1); the tail average has a closed form
    because z_cf is a cubic in z and the partial moments of the normal are known:
        int_{-inf}^{a} phi = Phi(a), int z phi = -phi(a), int z^2 phi = Phi(a) - a phi(a),
        int z^3 phi = -(a^2 + 2) phi(a).
    """
    p = 1 - alpha
    a = stats.norm.ppf(p)
    zcf = cornish_fisher_z(a, skew, exkurt)
    ph = stats.norm.pdf(a)
    m0, m1, m2, m3 = p, -ph, p - a * ph, -(a**2 + 2) * ph
    tail_int = (m1 + skew / 6 * (m2 - m0) + exkurt / 24 * (m3 - 3 * m1)
                - skew**2 / 36 * (2 * m3 - 5 * m1))
    return -(mu + sigma * zcf), -(mu + sigma * tail_int / p)


def cornish_fisher_es_numeric(sigma: float, alpha: float, skew: float, exkurt: float) -> float:
    """Numerical check of the Cornish-Fisher ES: (1/p) * integral_0^p of the CF quantile."""
    p = 1 - alpha
    val, _ = integrate.quad(lambda u: cornish_fisher_z(stats.norm.ppf(u), skew, exkurt), 0, p, limit=200)
    return -sigma * val / p


def cornish_fisher_is_monotone(skew: float, exkurt: float, z_min: float = -5.0, z_max: float = 0.0) -> bool:
    """True if z_cf(z) increases on [z_min, z_max], i.e. the expansion is a valid tail quantile."""
    z = np.linspace(z_min, z_max, 2001)
    return bool(np.all(np.diff(cornish_fisher_z(z, skew, exkurt)) > 0))


# ------------------------------------------------------------------ Student-t
def std_t_logpdf(z: np.ndarray, nu: float) -> np.ndarray:
    """Log density of a Student-t rescaled to unit variance (requires nu > 2)."""
    s = np.sqrt((nu - 2) / nu)
    return stats.t.logpdf(z / s, nu) - np.log(s)


def fit_t_df(z: np.ndarray, lo: float = 2.05, hi: float = 200.0) -> float:
    """Maximum-likelihood degrees of freedom of a unit-variance Student-t fitted to `z`.

    `z` should already be standardised (mean about 0, variance about 1); only the shape
    parameter nu is estimated, so the fitted distribution keeps the sample variance.
    """
    z = np.asarray(z, dtype=float)
    res = optimize.minimize_scalar(lambda nu: -np.sum(std_t_logpdf(z, nu)), bounds=(lo, hi),
                                   method="bounded", options={"xatol": 1e-4})
    return float(res.x)


def t_df_from_kurtosis(exkurt: float) -> float:
    """Degrees of freedom matching the excess kurtosis of a Student-t: K = 6 / (nu - 4)."""
    return 4 + 6 / exkurt if exkurt > 0 else np.inf


def std_t_ppf(p: float, nu: float) -> float:
    """Quantile of the unit-variance Student-t."""
    return float(stats.t.ppf(p, nu) * np.sqrt((nu - 2) / nu))


def student_t_var_es(sigma: float, alpha: float, nu: float, mu: float = 0.0) -> tuple[float, float]:
    """Analytic VaR and ES of a Student-t with standard deviation sigma.

    VaR = sigma sqrt((nu-2)/nu) t_nu^-1(alpha) - mu
    ES  = sigma sqrt((nu-2)/nu) f_nu(q) (nu + q^2) / ((nu - 1)(1 - alpha)) - mu,  q = t_nu^-1(alpha)
    """
    s = np.sqrt((nu - 2) / nu)
    q = stats.t.ppf(alpha, nu)
    var = sigma * s * q - mu
    es = sigma * s * stats.t.pdf(q, nu) * (nu + q**2) / ((nu - 1) * (1 - alpha)) - mu
    return float(var), float(es)


def student_t_es_numeric(sigma: float, alpha: float, nu: float) -> float:
    """Numerical check of the Student-t ES: (1/p) * integral_0^p of the unit-variance t quantile, times sigma."""
    p = 1 - alpha
    val, _ = integrate.quad(lambda u: std_t_ppf(u, nu), 0, p, limit=200)
    return -sigma * val / p


# ------------------------------------------------------------------ Monte Carlo
def simulate_normal(cov: np.ndarray, n: int, rng: np.random.Generator) -> np.ndarray:
    """n draws of the asset-return vector from N(0, cov) via the Cholesky factor: r = L z."""
    chol = np.linalg.cholesky(cov)
    return rng.standard_normal((n, cov.shape[0])) @ chol.T


def simulate_student_t(cov: np.ndarray, nu: float, n: int, rng: np.random.Generator) -> np.ndarray:
    """n draws from a multivariate Student-t with nu degrees of freedom and covariance `cov`.

    r = L_s z sqrt(nu / W), W ~ chi2(nu), where L_s is the Cholesky factor of the scale matrix
    cov (nu - 2) / nu. The rescaling makes Cov(r) = cov, so the t and normal simulations share
    the same covariance and differ only in tail shape.
    """
    chol = np.linalg.cholesky(cov * (nu - 2) / nu)
    z = rng.standard_normal((n, cov.shape[0])) @ chol.T
    w = rng.chisquare(nu, size=n)
    return z * np.sqrt(nu / w)[:, None]


def simulate_horizon_returns(cov: np.ndarray, n_paths: int, horizon: int, rng: np.random.Generator,
                             nu: float | None = None) -> np.ndarray:
    """Compounded `horizon`-day simple returns per asset from iid daily draws (normal or t).

    Daily simple returns are floored at -99% so a simulated price cannot turn negative; with daily
    volatilities of 0.3-1.5% the floor is never close to binding for the normal model.
    """
    growth = np.ones((n_paths, cov.shape[0]))
    for _ in range(horizon):
        daily = simulate_normal(cov, n_paths, rng) if nu is None else simulate_student_t(cov, nu, n_paths, rng)
        growth *= 1 + np.maximum(daily, -0.99)
    return growth - 1


def nested_convergence(port_sims: np.ndarray, alpha: float, sizes: list[int]) -> pd.Series:
    """VaR estimate from the first n simulated portfolio returns, for each n in `sizes`."""
    return pd.Series({n: historical_var_es(port_sims[:n], alpha)[0] for n in sizes})


def replicated_convergence(cov: np.ndarray, w: np.ndarray, alpha: float, sizes: list[int], n_reps: int,
                           seed: int, nu: float | None = None) -> pd.DataFrame:
    """Sampling distribution of the Monte Carlo VaR: n_reps independent runs for each size.

    Independent child streams come from numpy SeedSequence(seed).spawn(n_reps).
    Returns a DataFrame (rows = sizes) with mean, 2.5% and 97.5% percentiles of the estimates.
    """
    children = np.random.SeedSequence(seed).spawn(n_reps)
    est = np.empty((n_reps, len(sizes)))
    for i, child in enumerate(children):
        rng = np.random.default_rng(child)
        for j, n in enumerate(sizes):
            sims = simulate_normal(cov, n, rng) if nu is None else simulate_student_t(cov, nu, n, rng)
            est[i, j] = historical_var_es(sims @ w, alpha)[0]
    return pd.DataFrame({"mean": est.mean(0), "p2_5": np.percentile(est, 2.5, axis=0),
                         "p97_5": np.percentile(est, 97.5, axis=0), "sd": est.std(0, ddof=1)}, index=sizes)


# ------------------------------------------------------------------ multi-day horizon
def overlapping_horizon_returns(prices: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Overlapping `horizon`-day simple returns P_t / P_{t-h} - 1 for each asset."""
    return (prices / prices.shift(horizon) - 1).dropna()


# ------------------------------------------------------------------ risk decomposition
def var_decomposition(cov: np.ndarray, w: np.ndarray, value: float, alpha: float,
                      labels: list[str]) -> pd.DataFrame:
    """Parametric-normal VaR decomposition (Euler allocation).

    marginal_i  = dVaR / d(rupee position_i) = z (Sigma w)_i / sigma_p
    component_i = position_i * marginal_i        (sums exactly to portfolio VaR)
    standalone_i = z sigma_i position_i          (VaR of the position on its own)
    """
    z = stats.norm.ppf(alpha)
    sig_p = portfolio_sigma(cov, w)
    marginal = z * (cov @ w) / sig_p
    position = w * value
    component = position * marginal
    standalone = z * np.sqrt(np.diag(cov)) * position
    out = pd.DataFrame({"weight": w, "position_inr": position, "vol_daily_pct": 100 * np.sqrt(np.diag(cov)),
                        "standalone_var_inr": standalone, "marginal_var_per_inr": marginal,
                        "component_var_inr": component,
                        "contribution_pct": 100 * component / (z * sig_p * value)}, index=labels)
    return out
