"""Implied volatility: vectorised Newton-Raphson on vega with a Brent (scipy brentq) fallback.

The solver works in Black-76 form (forward F, discount factor DF). `implied_vol` is the BSM
wrapper that builds F = S exp((r - q) T) and DF = exp(-r T).

No-arbitrage bounds (European options):
    call:  DF * max(F - K, 0) < C < DF * F
    put:   DF * max(K - F, 0) < P < DF * K
A price on or outside these bounds has no implied volatility and returns NaN.
"""
from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import ArrayLike
from scipy.optimize import brentq

from .black_scholes import _d1_d2_fwd, _out, black76_price, call_flag, norm_pdf

__all__ = ["price_bounds", "implied_vol_black76", "implied_vol"]

METHOD_NEWTON = 0
METHOD_BRENT = 1
METHOD_NONE = -1


def price_bounds(F: ArrayLike, K: ArrayLike, DF: ArrayLike, option: Any = "call") -> tuple[Any, Any]:
    """Lower and upper no-arbitrage bounds for a European option price (Black-76 inputs)."""
    F, K, DF = (np.asarray(a, dtype=float) for a in (F, K, DF))
    is_call = call_flag(option)
    lower = np.where(is_call, DF * np.maximum(F - K, 0.0), DF * np.maximum(K - F, 0.0))
    upper = np.where(is_call, DF * F, DF * K)
    return _out(lower), _out(upper)


def implied_vol_black76(
    price: ArrayLike,
    F: ArrayLike,
    K: ArrayLike,
    T: ArrayLike,
    DF: ArrayLike,
    option: Any = "call",
    *,
    tol: float = 1e-10,
    max_iter: int = 50,
    sigma_low: float = 1e-6,
    sigma_high: float = 5.0,
    return_info: bool = False,
) -> Any:
    """Implied volatility of European option prices under Black-76.

    Algorithm
    1. Reject prices outside the no-arbitrage bounds (NaN).
    2. Newton-Raphson on sigma with the analytic vega, started at the inflection point
       sigma* = sqrt(2 |ln(F/K)| / T) (clipped to [0.05, 1.0]); from there Newton converges
       monotonically in exact arithmetic. Each step keeps a bracket [lo, hi] that contains the
       root; a step that leaves the bracket, or a near-zero vega, falls back to bisection.
    3. Elements that have not converged after `max_iter` steps are solved with scipy brentq
       on [sigma_low, sigma_high].

    Returns the implied vol (decimal). With return_info=True also returns a dict with
    "method" (0 Newton, 1 Brent, -1 no solution) and "iterations" arrays.
    """
    price, F, K, T, DF = (np.asarray(a, dtype=float) for a in (price, F, K, T, DF))
    is_call = call_flag(option)
    price, F, K, T, DF, is_call = np.broadcast_arrays(price, F, K, T, DF, is_call)
    shape = price.shape
    p, f, k, t, df, c = (a.reshape(-1).copy() for a in (price, F, K, T, DF, is_call))

    n = p.size
    sigma = np.full(n, np.nan)
    method = np.full(n, METHOD_NONE, dtype=int)
    iters = np.zeros(n, dtype=int)

    lower, upper = price_bounds(f, k, df, c)
    lower, upper = np.atleast_1d(lower), np.atleast_1d(upper)
    finite = np.isfinite(p) & np.isfinite(f) & np.isfinite(k) & np.isfinite(t) & np.isfinite(df)
    ok = finite & (t > 0) & (f > 0) & (k > 0) & (p > lower) & (p < upper)
    # The target must also lie inside the price range spanned by [sigma_low, sigma_high].
    if ok.any():
        idx = np.where(ok)[0]
        p_lo = np.atleast_1d(black76_price(f[idx], k[idx], t[idx], df[idx], sigma_low, c[idx]))
        p_hi = np.atleast_1d(black76_price(f[idx], k[idx], t[idx], df[idx], sigma_high, c[idx]))
        ok[idx] = (p[idx] >= p_lo) & (p[idx] <= p_hi)

    idx = np.where(ok)[0]
    if idx.size:
        pp, ff, kk, tt, dd, cc = p[idx], f[idx], k[idx], t[idx], df[idx], c[idx]
        x = np.log(ff / kk)
        s = np.clip(np.sqrt(2.0 * np.abs(x) / tt), 0.05, 1.0)
        lo = np.full(idx.size, sigma_low)
        hi = np.full(idx.size, sigma_high)
        done = np.zeros(idx.size, dtype=bool)
        it_count = np.zeros(idx.size, dtype=int)
        for _ in range(max_iter):
            act = ~done
            if not act.any():
                break
            sa = s[act]
            model = np.atleast_1d(black76_price(ff[act], kk[act], tt[act], dd[act], sa, cc[act]))
            diff = model - pp[act]
            d1, _ = _d1_d2_fwd(ff[act], kk[act], tt[act], sa)
            vega = dd[act] * ff[act] * norm_pdf(d1) * np.sqrt(tt[act])
            # shrink the bracket using the sign of the pricing error (price is increasing in sigma)
            hi_a = np.where(diff > 0, np.minimum(hi[act], sa), hi[act])
            lo_a = np.where(diff < 0, np.maximum(lo[act], sa), lo[act])
            with np.errstate(divide="ignore", invalid="ignore"):
                s_new = sa - diff / vega
            bad = ~np.isfinite(s_new) | (s_new <= lo_a) | (s_new >= hi_a) | (vega < 1e-12 * dd[act] * ff[act])
            s_new = np.where(bad, 0.5 * (lo_a + hi_a), s_new)
            conv = (np.abs(s_new - sa) < tol) | (diff == 0)
            s[act], lo[act], hi[act] = s_new, lo_a, hi_a
            it_count[act] += 1
            done[act] = conv
        sigma[idx[done]] = s[done]
        method[idx[done]] = METHOD_NEWTON
        iters[idx] = it_count

        # Brent fallback for anything Newton did not finish
        for j in np.where(~done)[0]:
            g = idx[j]

            def err(v: float, g: int = g) -> float:
                return float(black76_price(f[g], k[g], t[g], df[g], v, c[g])) - p[g]

            try:
                sigma[g] = brentq(err, sigma_low, sigma_high, xtol=1e-14, rtol=1e-14, maxiter=500)
                method[g] = METHOD_BRENT
            except ValueError:
                sigma[g] = np.nan
                method[g] = METHOD_NONE

    sigma = sigma.reshape(shape)
    if return_info:
        return _out(sigma), {"method": method.reshape(shape), "iterations": iters.reshape(shape)}
    return _out(sigma)


def implied_vol(
    price: ArrayLike,
    S: ArrayLike,
    K: ArrayLike,
    T: ArrayLike,
    r: ArrayLike,
    q: ArrayLike = 0.0,
    option: Any = "call",
    **kwargs: Any,
) -> Any:
    """BSM implied volatility (continuous dividend yield q). See `implied_vol_black76` for options."""
    S, T, r, q = (np.asarray(a, dtype=float) for a in (S, T, r, q))
    F = S * np.exp((r - q) * T)
    DF = np.exp(-r * T)
    return implied_vol_black76(price, F, K, T, DF, option, **kwargs)
