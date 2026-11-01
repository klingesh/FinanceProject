"""Return, risk and long-only mean-variance portfolio functions.

Conventions
- Daily simple returns r_t = P_t / P_{t-1} - 1 from adjusted close.
- Annualised arithmetic mean = mean(daily) x 252; annualised volatility = std(daily, ddof=1) x sqrt(252).
- Risk-free rate: daily rf = (1 + 5.93%)^(1/252) - 1. On the same arithmetic x252 basis this is
  ``RF_ARITH`` (about 5.76% a year), which is the rf used in annualised Sharpe ratios and in the
  optimiser, so the two always agree.
- CAGR uses calendar time from the base date (last close before the window) to the last date.
- Portfolios hold constant weights, i.e. they are rebalanced daily (an approximation).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from src.config import RF_ARITH, RF_DAILY, SEED, TRADING_DAYS

# ============================================================================ returns
def simple_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Simple returns P_t / P_{t-1} - 1; the first row (no previous price) is dropped."""
    return (prices / prices.shift(1) - 1).iloc[1:]


def window_returns(prices: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp
                   ) -> tuple[pd.DataFrame, pd.Timestamp]:
    """Daily returns dated inside [start, end] and the base date (last close before ``start``).

    The first return uses the base-date close, so the window compounds from the base date.
    """
    rets = simple_returns(prices)
    rets = rets.loc[(rets.index >= start) & (rets.index <= end)]
    base = prices.index[prices.index < rets.index[0]][-1]
    return rets, base


def weekly_returns(prices: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Friday-to-Friday simple returns using the last close of each week, for weeks ending in [start, end]."""
    wk = prices.loc[prices.index <= end].resample("W-FRI").last()
    r = (wk / wk.shift(1) - 1).iloc[1:]
    return r.loc[(r.index >= start) & (r.index <= end)]


def wealth_index(returns: pd.DataFrame | pd.Series, base_date: pd.Timestamp,
                 start_value: float = 100.0) -> pd.DataFrame | pd.Series:
    """Value of ``start_value`` invested at the base-date close, compounding the returns."""
    growth = (1 + returns).cumprod() * start_value
    if isinstance(returns, pd.Series):
        first = pd.Series([start_value], index=[base_date], name=returns.name)
    else:
        first = pd.DataFrame([[start_value] * returns.shape[1]], index=[base_date], columns=returns.columns)
    return pd.concat([first, growth])


# ============================================================================ single-series statistics
def annualised_mean(r: pd.DataFrame | pd.Series, periods: int = TRADING_DAYS):
    """Arithmetic mean return x periods per year."""
    return r.mean() * periods


def annualised_vol(r: pd.DataFrame | pd.Series, periods: int = TRADING_DAYS):
    """Sample standard deviation (ddof=1) x sqrt(periods per year)."""
    return r.std(ddof=1) * np.sqrt(periods)


def cagr(r: pd.Series, base_date: pd.Timestamp) -> float:
    """Compound annual growth rate over calendar time from ``base_date`` to the last return date."""
    growth = float((1 + r).prod())
    years = (r.index[-1] - base_date).days / 365.25
    return growth ** (1 / years) - 1


def sharpe_ratio(r: pd.Series, rf: float = RF_DAILY, periods: int = TRADING_DAYS) -> float:
    """Annualised Sharpe ratio: mean excess return x periods / (std x sqrt(periods))."""
    return float((r - rf).mean() * periods / (r.std(ddof=1) * np.sqrt(periods)))


def downside_deviation(r: pd.Series, mar: float = RF_DAILY, periods: int = TRADING_DAYS) -> float:
    """Annualised downside deviation below the minimum acceptable return ``mar`` (all observations)."""
    shortfall = np.minimum(r - mar, 0.0)
    return float(np.sqrt(np.mean(shortfall ** 2)) * np.sqrt(periods))


def sortino_ratio(r: pd.Series, rf: float = RF_DAILY, periods: int = TRADING_DAYS) -> float:
    """Annualised mean excess return over the annualised downside deviation (target = rf)."""
    return float((r - rf).mean() * periods / downside_deviation(r, rf, periods))


def drawdown_series(r: pd.Series | pd.DataFrame, base_date: pd.Timestamp) -> pd.Series | pd.DataFrame:
    """Drawdown from the running peak of the wealth index (0 at a new high)."""
    w = wealth_index(r, base_date, 1.0)
    return w / w.cummax() - 1


def max_drawdown(r: pd.Series, base_date: pd.Timestamp) -> dict:
    """Maximum drawdown with peak, trough and recovery dates (recovery is NaT if not regained)."""
    w = wealth_index(r, base_date, 1.0)
    dd = w / w.cummax() - 1
    trough = dd.idxmin()
    peak = w.loc[:trough].idxmax()
    after = w.loc[trough:]
    rec = after.index[after >= w.loc[peak]]
    return {"max_drawdown": float(dd.min()), "peak": peak, "trough": trough,
            "recovery": rec[0] if len(rec) else pd.NaT}


# ============================================================================ regressions
def ols(y: np.ndarray, x: np.ndarray) -> dict:
    """OLS of y on [1, x] (x may have several columns). Returns coefficients, standard errors, R-squared."""
    y = np.asarray(y, dtype=float)
    x = np.asarray(x, dtype=float)
    if x.ndim == 1:
        x = x[:, None]
    X = np.column_stack([np.ones(len(y)), x])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ coef
    n, k = X.shape
    s2 = resid @ resid / (n - k)
    cov = s2 * np.linalg.inv(X.T @ X)
    sst = ((y - y.mean()) ** 2).sum()
    return {"coef": coef, "se": np.sqrt(np.diag(cov)), "r2": 1 - resid @ resid / sst, "n": n}


def capm_regression(r: pd.Series, m: pd.Series, rf: float, periods: int) -> dict:
    """Market model on excess returns: (r - rf) = alpha + beta (m - rf) + e.

    Returns beta, its standard error, Jensen's alpha annualised (alpha x periods), the alpha
    t-statistic, R-squared and the number of observations.
    """
    res = ols((r - rf).to_numpy(), (m - rf).to_numpy())
    alpha, beta = res["coef"]
    a_se, b_se = res["se"]
    return {"beta": float(beta), "beta_se": float(b_se), "alpha_ann": float(alpha * periods),
            "alpha_t": float(alpha / a_se) if a_se > 0 else np.nan, "r2": float(res["r2"]), "n": res["n"]}


def dimson_beta(r: pd.Series, m: pd.Series, rf: float, lags: int = 1) -> float:
    """Dimson (1979) beta: sum of slopes on lagged, current and leading market excess returns."""
    y = r - rf
    mx = m - rf
    cols = {f"m{k:+d}": mx.shift(-k) for k in range(-lags, lags + 1)}  # k<0 lag, k>0 lead
    df = pd.concat([y.rename("y"), pd.DataFrame(cols)], axis=1).dropna()
    res = ols(df["y"].to_numpy(), df.drop(columns="y").to_numpy())
    return float(res["coef"][1:].sum())


# ============================================================================ asset table
def asset_statistics(daily: pd.DataFrame, weekly: pd.DataFrame, bench: str, base_date: pd.Timestamp,
                     rf_daily: float, rf_weekly: float, periods: int = TRADING_DAYS,
                     weeks: int = 52) -> pd.DataFrame:
    """Return and risk statistics for every column of ``daily`` against the benchmark column."""
    rows = {}
    for c in daily.columns:
        r, m = daily[c], daily[bench]
        reg = capm_regression(r, m, rf_daily, periods)
        regw = capm_regression(weekly[c], weekly[bench], rf_weekly, weeks)
        mdd = max_drawdown(r, base_date)
        mean_excess = float((r - rf_daily).mean() * periods)
        rows[c] = {
            "total_return": float((1 + r).prod() - 1),
            "ann_mean_return": float(annualised_mean(r, periods)),
            # standard error of the annualised mean: sigma_annual / sqrt(years of data)
            "ann_mean_se": float(annualised_vol(r, periods) / np.sqrt(len(r) / periods)),
            "cagr": cagr(r, base_date),
            "ann_volatility": float(annualised_vol(r, periods)),
            "beta_daily": reg["beta"], "beta_daily_se": reg["beta_se"],
            "beta_weekly": regw["beta"], "beta_weekly_se": regw["beta_se"],
            "beta_dimson": dimson_beta(r, m, rf_daily),
            "jensen_alpha_ann": reg["alpha_ann"], "alpha_t_stat": reg["alpha_t"],
            "r_squared": reg["r2"], "r_squared_weekly": regw["r2"],
            "sharpe": sharpe_ratio(r, rf_daily, periods),
            "sortino": sortino_ratio(r, rf_daily, periods),
            "treynor": mean_excess / reg["beta"],
            "max_drawdown": mdd["max_drawdown"], "mdd_peak": mdd["peak"].date(), "mdd_trough": mdd["trough"].date(),
            "n_daily": reg["n"], "n_weekly": regw["n"],
        }
    out = pd.DataFrame(rows).T
    num = [c for c in out.columns if c not in ("mdd_peak", "mdd_trough")]
    out[num] = out[num].astype(float)
    if bench in out.index:  # the benchmark regressed on itself: alpha is 0 by construction
        out.loc[bench, ["jensen_alpha_ann", "beta_daily_se", "beta_weekly_se"]] = 0.0
        out.loc[bench, "alpha_t_stat"] = np.nan
    return out


# ============================================================================ portfolio maths
def portfolio_point(w: np.ndarray, mu: np.ndarray, cov: np.ndarray, rf: float = RF_ARITH) -> tuple[float, float, float]:
    """Annualised (return, volatility, Sharpe) of weights ``w``."""
    ret = float(w @ mu)
    vol = float(np.sqrt(w @ cov @ w))
    return ret, vol, (ret - rf) / vol


def effective_n(w: np.ndarray) -> float:
    """Effective number of holdings, 1 / sum(w^2) (10 for equal weight, 1 for a single stock)."""
    return float(1.0 / np.sum(np.asarray(w) ** 2))


def risk_contributions(w: np.ndarray, cov: np.ndarray) -> np.ndarray:
    """Share of portfolio variance from each asset: w_i (Cov w)_i / (w' Cov w); sums to 1."""
    cw = cov @ w
    return w * cw / (w @ cw)


def _clean_weights(w: np.ndarray, cap: float) -> np.ndarray:
    """Clip solver noise (e.g. -1e-17) into [0, cap] and renormalise to sum to 1."""
    w = np.clip(np.asarray(w, dtype=float), 0.0, cap)
    w[w < 1e-9] = 0.0
    return w / w.sum()


def extreme_return_portfolio(mu: np.ndarray, cap: float = 1.0, highest: bool = True) -> np.ndarray:
    """Long-only, fully invested weights with the highest (or lowest) return under a per-asset cap.

    Greedy: fill the best assets up to the cap until fully invested (exact for this LP).
    """
    order = np.argsort(-mu if highest else mu)
    w = np.zeros(len(mu))
    left = 1.0
    for i in order:
        w[i] = min(cap, left)
        left -= w[i]
        if left <= 1e-15:
            break
    return w


def _feasible_starts(n: int, cap: float, k: int, seed: int) -> list[np.ndarray]:
    """Equal weight plus ``k`` random Dirichlet points that respect the cap (rejection sampling)."""
    rng = np.random.default_rng(seed)
    starts = [np.full(n, 1.0 / n)]
    while len(starts) < k + 1:
        w = rng.dirichlet(np.ones(n))
        if w.max() <= cap:
            starts.append(w)
    return starts


def min_variance(mu: np.ndarray, cov: np.ndarray, cap: float = 1.0, target: float | None = None,
                 x0: np.ndarray | None = None) -> np.ndarray:
    """Long-only, fully invested minimum-variance weights, optionally with w'mu = target (SLSQP).

    Several starting points are tried; the feasible solution with the lowest variance is kept.
    """
    n = len(mu)
    bounds = [(0.0, cap)] * n
    if target is not None:
        hi, lo = extreme_return_portfolio(mu, cap, True), extreme_return_portfolio(mu, cap, False)
        if target >= hi @ mu - 1e-12:
            return hi
        if target <= lo @ mu + 1e-12:
            return lo
    cons = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0, "jac": lambda w: np.ones(n)}]
    if target is not None:
        cons.append({"type": "eq", "fun": lambda w: w @ mu - target, "jac": lambda w: mu})
    starts = ([x0] if x0 is not None else []) + _feasible_starts(n, cap, 3, SEED)
    best, best_var = None, np.inf
    for s in starts:
        res = minimize(lambda w: w @ cov @ w, s, jac=lambda w: 2 * cov @ w, method="SLSQP",
                       bounds=bounds, constraints=cons, options={"ftol": 1e-15, "maxiter": 2000})
        w = res.x
        feasible = (abs(w.sum() - 1) < 1e-8 and w.min() > -1e-8 and w.max() < cap + 1e-8
                    and (target is None or abs(w @ mu - target) < 1e-8))
        if feasible and w @ cov @ w < best_var:
            best, best_var = w, w @ cov @ w
    if best is None:
        raise RuntimeError(f"min_variance failed (target={target}, cap={cap})")
    return _clean_weights(best, cap)


def max_sharpe(mu: np.ndarray, cov: np.ndarray, rf: float = RF_ARITH, cap: float = 1.0,
               n_starts: int = 20, seed: int = SEED) -> np.ndarray:
    """Long-only tangency portfolio: maximise (w'mu - rf) / sqrt(w'Cov w) with SLSQP, multi-start."""
    n = len(mu)
    bounds = [(0.0, cap)] * n

    def neg_sharpe(w: np.ndarray) -> float:
        return -(w @ mu - rf) / np.sqrt(w @ cov @ w)

    def grad(w: np.ndarray) -> np.ndarray:
        cw = cov @ w
        s = np.sqrt(w @ cw)
        e = w @ mu - rf
        return -(mu / s - e * cw / s ** 3)

    cons = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0, "jac": lambda w: np.ones(n)}]
    starts = _feasible_starts(n, cap, n_starts, seed) + [min_variance(mu, cov, cap)]
    if cap >= 1.0:
        starts += [np.eye(n)[i] for i in range(n)]
    best, best_val = None, np.inf
    for s in starts:
        res = minimize(neg_sharpe, s, jac=grad, method="SLSQP", bounds=bounds, constraints=cons,
                       options={"ftol": 1e-15, "maxiter": 2000})
        w = res.x
        feasible = abs(w.sum() - 1) < 1e-8 and w.min() > -1e-8 and w.max() < cap + 1e-8
        if feasible and neg_sharpe(w) < best_val:
            best, best_val = w, neg_sharpe(w)
    if best is None:
        raise RuntimeError("max_sharpe failed")
    return _clean_weights(best, cap)


def max_sharpe_convex(mu: np.ndarray, cov: np.ndarray, rf: float = RF_ARITH, cap: float = 1.0) -> np.ndarray:
    """Cross-check of the tangency portfolio through its convex form.

    minimise y' Cov y  s.t. (mu - rf)' y = 1, y >= 0, y_i <= cap * sum(y);  then w = y / sum(y).
    Valid when at least one asset has mu > rf.
    """
    n = len(mu)
    ex = mu - rf
    if ex.max() <= 0:
        raise ValueError("no asset beats the risk-free rate")
    cons = [{"type": "eq", "fun": lambda y: y @ ex - 1.0, "jac": lambda y: ex}]
    if cap < 1.0:
        cons.append({"type": "ineq", "fun": lambda y: cap * y.sum() - y,
                     "jac": lambda y: cap * np.ones((n, n)) - np.eye(n)})
    w0 = np.where(ex > 0, ex, 0.0)
    w0 = np.minimum(w0 / w0.sum(), cap)
    y0 = w0 / max(w0 @ ex, 1e-6)
    res = minimize(lambda y: y @ cov @ y, y0, jac=lambda y: 2 * cov @ y, method="SLSQP",
                   bounds=[(0.0, None)] * n, constraints=cons, options={"ftol": 1e-15, "maxiter": 2000})
    return _clean_weights(res.x / res.x.sum(), cap)


def efficient_frontier(mu: np.ndarray, cov: np.ndarray, rf: float = RF_ARITH, cap: float = 1.0,
                       n_points: int = 60, n_lower: int = 20, labels: list[str] | None = None) -> pd.DataFrame:
    """Minimum-variance frontier for a grid of target returns.

    ``n_points`` targets run from the minimum-variance return to the highest achievable return
    (the efficient branch); ``n_lower`` extra targets cover the inefficient branch below it.
    """
    labels = labels or [f"w{i}" for i in range(len(mu))]
    w_gmv = min_variance(mu, cov, cap)
    r_gmv = float(w_gmv @ mu)
    r_hi = float(extreme_return_portfolio(mu, cap, True) @ mu)
    r_lo = float(extreme_return_portfolio(mu, cap, False) @ mu)
    rows = []
    prev = w_gmv
    for i, t in enumerate(np.linspace(r_gmv, r_hi, n_points)):
        w = w_gmv if i == 0 else min_variance(mu, cov, cap, t, x0=prev)
        prev = w
        rows.append(("efficient", t, w))
    prev = w_gmv
    for t in np.linspace(r_gmv, r_lo, n_lower + 1)[1:]:
        w = min_variance(mu, cov, cap, t, x0=prev)
        prev = w
        rows.append(("inefficient", t, w))
    out = []
    for branch, t, w in rows:
        ret, vol, sr = portfolio_point(w, mu, cov, rf)
        out.append({"branch": branch, "target_return": t, "return": ret, "volatility": vol, "sharpe": sr,
                    **dict(zip(labels, w))})
    df = pd.DataFrame(out)
    return df.sort_values("return").reset_index(drop=True)


def random_portfolios(mu: np.ndarray, cov: np.ndarray, rf: float = RF_ARITH, n: int = 20_000,
                      seed: int = SEED) -> tuple[pd.DataFrame, np.ndarray]:
    """Monte Carlo cloud of long-only portfolios with Dirichlet(1,...,1) weights (uniform on the simplex)."""
    rng = np.random.default_rng(seed)
    W = rng.dirichlet(np.ones(len(mu)), size=n)
    ret = W @ mu
    vol = np.sqrt(np.einsum("ij,jk,ik->i", W, cov, W))
    return pd.DataFrame({"return": ret, "volatility": vol, "sharpe": (ret - rf) / vol}), W


def capital_market_line(vols: np.ndarray, rf: float, tangency_sharpe: float) -> np.ndarray:
    """Expected return on the CML: rf + Sharpe_T x volatility."""
    return rf + tangency_sharpe * np.asarray(vols)


def tangency_kkt_table(w: np.ndarray, mu: np.ndarray, cov: np.ndarray, rf: float = RF_ARITH,
                       labels: list[str] | None = None) -> pd.DataFrame:
    """Optimality check for the long-only tangency portfolio.

    With beta_i = (Cov w)_i / (w' Cov w), held stocks satisfy (mu_i - rf) = beta_i (mu_T - rf);
    excluded stocks fall short of it: (mu_i - rf) <= beta_i (mu_T - rf).
    """
    cw = cov @ w
    beta_t = cw / (w @ cw)
    mu_t = float(w @ mu)
    required = beta_t * (mu_t - rf)
    return pd.DataFrame({"weight": w, "excess_return": mu - rf, "beta_vs_tangency": beta_t,
                         "required_excess_return": required, "shortfall": (mu - rf) - required},
                        index=labels)


# ============================================================================ portfolio return series
def portfolio_returns(returns: pd.DataFrame, w: pd.Series | np.ndarray) -> pd.Series:
    """Constant-weight portfolio rebalanced daily: r_p,t = sum_i w_i r_i,t."""
    w = pd.Series(w, index=returns.columns) if not isinstance(w, pd.Series) else w.reindex(returns.columns)
    return returns @ w


def buy_and_hold_returns(returns: pd.DataFrame, w: pd.Series | np.ndarray) -> pd.Series:
    """Weights set once at the start and left to drift with prices (no rebalancing)."""
    w = np.asarray(w if not isinstance(w, pd.Series) else w.reindex(returns.columns), dtype=float)
    value = (1 + returns).cumprod() @ w
    prev = value.shift(1)
    prev.iloc[0] = 1.0
    return value / prev - 1


def performance_summary(r: pd.Series, m: pd.Series, base_date: pd.Timestamp, rf: float = RF_DAILY,
                        periods: int = TRADING_DAYS) -> dict:
    """Headline statistics of a return series against the market series ``m``."""
    reg = capm_regression(r, m, rf, periods)
    if r.equals(m):  # the market against itself: alpha is exactly 0 (avoid printing -0.0%)
        reg["alpha_ann"] = 0.0
    mdd = max_drawdown(r, base_date)
    return {"ann_mean_return": float(annualised_mean(r, periods)), "cagr": cagr(r, base_date),
            "ann_volatility": float(annualised_vol(r, periods)), "sharpe": sharpe_ratio(r, rf, periods),
            "sortino": sortino_ratio(r, rf, periods), "beta": reg["beta"], "jensen_alpha_ann": reg["alpha_ann"],
            "max_drawdown": mdd["max_drawdown"], "total_return": float((1 + r).prod() - 1)}
