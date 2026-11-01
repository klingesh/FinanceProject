"""Black-Scholes-Merton (BSM) and Black-76 pricing and Greeks for European options.

All functions are vectorised with numpy: every argument can be a scalar or an array, and
arguments broadcast against each other. Scalar inputs return Python floats.

Conventions
-----------
S      spot price of the underlying
K      strike
T      time to expiry in years (this project uses calendar days / 365)
r      continuously compounded risk-free rate (0.0576 = 5.76%)
sigma  volatility as a decimal (0.20 = 20%)
q      continuous dividend yield (or any carry adjustment), decimal
option "call" / "put" (also "c", "p", "ce", "pe"), or booleans where True means call

BSM with a dividend yield q is the same model as Black-76 on the forward
F = S * exp((r - q) * T) with discount factor DF = exp(-r * T). The pricing core below works
on (F, DF), so prices driven by a market-implied forward and prices driven by (S, r, q) use
exactly the same code.
"""
from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import ArrayLike
from scipy.special import ndtr

SQRT_2PI = np.sqrt(2.0 * np.pi)

__all__ = [
    "call_flag",
    "norm_pdf",
    "forward_price",
    "d1_d2",
    "black76_price",
    "black76_vega",
    "bs_price",
    "bs_delta",
    "bs_gamma",
    "bs_vega",
    "bs_theta",
    "bs_rho",
    "bs_greeks",
    "parity_residual",
    "put_from_call",
    "call_from_put",
    "forward_from_parity",
    "carry_from_forward",
    "dividend_yield_from_forward",
]


def _out(x: np.ndarray) -> Any:
    """Return a Python float for 0-d results and the array otherwise."""
    x = np.asarray(x)
    return float(x) if x.ndim == 0 else x


def call_flag(option: Any) -> np.ndarray:
    """Convert an option-type argument to a boolean array (True = call).

    Accepts strings ("call", "put", "c", "p", "ce", "pe", any case), booleans, or arrays of either.
    """
    arr = np.asarray(option)
    if arr.dtype.kind in ("U", "S", "O"):
        s = np.char.lower(arr.astype(str))
        is_call = np.isin(s, ["call", "c", "ce"])
        is_put = np.isin(s, ["put", "p", "pe"])
        if not np.all(is_call | is_put):
            raise ValueError(f"Unknown option type in {option!r}; use 'call' or 'put'.")
        return is_call
    return arr.astype(bool)


def norm_pdf(x: ArrayLike) -> np.ndarray:
    """Standard normal density n(x)."""
    x = np.asarray(x, dtype=float)
    return np.exp(-0.5 * x * x) / SQRT_2PI


def forward_price(S: ArrayLike, T: ArrayLike, r: ArrayLike, q: ArrayLike = 0.0) -> Any:
    """Forward price F = S * exp((r - q) * T)."""
    S, T, r, q = (np.asarray(a, dtype=float) for a in (S, T, r, q))
    return _out(S * np.exp((r - q) * T))


def _d1_d2_fwd(F: np.ndarray, K: np.ndarray, T: np.ndarray, sigma: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """d1 and d2 in forward form, with the sigma*sqrt(T) = 0 limit handled."""
    sd = sigma * np.sqrt(T)
    with np.errstate(divide="ignore", invalid="ignore"):
        x = np.log(F / K)
        d1 = np.where(sd > 0, x / sd + 0.5 * sd, np.where(x > 0, np.inf, np.where(x < 0, -np.inf, 0.0)))
        d2 = np.where(sd > 0, d1 - sd, d1)
    # a NaN input (e.g. a missing implied vol) must give NaN, not the zero-vol limit
    nan = np.isnan(sd) | np.isnan(x)
    return np.where(nan, np.nan, d1), np.where(nan, np.nan, d2)


def d1_d2(S: ArrayLike, K: ArrayLike, T: ArrayLike, r: ArrayLike, sigma: ArrayLike, q: ArrayLike = 0.0) -> tuple[Any, Any]:
    """BSM d1 = [ln(S/K) + (r - q + sigma^2/2) T] / (sigma sqrt(T)) and d2 = d1 - sigma sqrt(T)."""
    S, K, T, r, sigma, q = (np.asarray(a, dtype=float) for a in (S, K, T, r, sigma, q))
    d1, d2 = _d1_d2_fwd(S * np.exp((r - q) * T), K, T, sigma)
    return _out(d1), _out(d2)


def black76_price(F: ArrayLike, K: ArrayLike, T: ArrayLike, DF: ArrayLike, sigma: ArrayLike, option: Any = "call") -> Any:
    """Black-76 price of a European option on a forward F, discounted with DF.

    call = DF * [F N(d1) - K N(d2)],  put = DF * [K N(-d2) - F N(-d1)],
    d1 = [ln(F/K) + sigma^2 T / 2] / (sigma sqrt(T)),  d2 = d1 - sigma sqrt(T).
    """
    F, K, T, DF, sigma = (np.asarray(a, dtype=float) for a in (F, K, T, DF, sigma))
    is_call = call_flag(option)
    d1, d2 = _d1_d2_fwd(F, K, T, sigma)
    call = DF * (F * ndtr(d1) - K * ndtr(d2))
    put = DF * (K * ndtr(-d2) - F * ndtr(-d1))
    return _out(np.where(is_call, call, put))


def black76_vega(F: ArrayLike, K: ArrayLike, T: ArrayLike, DF: ArrayLike, sigma: ArrayLike) -> Any:
    """Black-76 vega per 1.00 change in volatility: DF * F * n(d1) * sqrt(T)."""
    F, K, T, DF, sigma = (np.asarray(a, dtype=float) for a in (F, K, T, DF, sigma))
    d1, _ = _d1_d2_fwd(F, K, T, sigma)
    return _out(DF * F * norm_pdf(d1) * np.sqrt(T))


def bs_price(S: ArrayLike, K: ArrayLike, T: ArrayLike, r: ArrayLike, sigma: ArrayLike, q: ArrayLike = 0.0, option: Any = "call") -> Any:
    """BSM price of a European call or put with continuous dividend yield q.

    call = S e^{-qT} N(d1) - K e^{-rT} N(d2),  put = K e^{-rT} N(-d2) - S e^{-qT} N(-d1).
    """
    S, K, T, r, sigma, q = (np.asarray(a, dtype=float) for a in (S, K, T, r, sigma, q))
    return black76_price(S * np.exp((r - q) * T), K, T, np.exp(-r * T), sigma, option)


def _prep(S, K, T, r, sigma, q):
    S, K, T, r, sigma, q = (np.asarray(a, dtype=float) for a in (S, K, T, r, sigma, q))
    d1, d2 = _d1_d2_fwd(S * np.exp((r - q) * T), K, T, sigma)
    return S, K, T, r, sigma, q, d1, d2


def bs_delta(S: ArrayLike, K: ArrayLike, T: ArrayLike, r: ArrayLike, sigma: ArrayLike, q: ArrayLike = 0.0, option: Any = "call") -> Any:
    """Delta dV/dS: call e^{-qT} N(d1), put -e^{-qT} N(-d1)."""
    S, K, T, r, sigma, q, d1, _ = _prep(S, K, T, r, sigma, q)
    is_call = call_flag(option)
    dq = np.exp(-q * T)
    return _out(np.where(is_call, dq * ndtr(d1), -dq * ndtr(-d1)))


def bs_gamma(S: ArrayLike, K: ArrayLike, T: ArrayLike, r: ArrayLike, sigma: ArrayLike, q: ArrayLike = 0.0) -> Any:
    """Gamma d2V/dS2 = e^{-qT} n(d1) / (S sigma sqrt(T)); the same for calls and puts."""
    S, K, T, r, sigma, q, d1, _ = _prep(S, K, T, r, sigma, q)
    return _out(np.exp(-q * T) * norm_pdf(d1) / (S * sigma * np.sqrt(T)))


def bs_vega(S: ArrayLike, K: ArrayLike, T: ArrayLike, r: ArrayLike, sigma: ArrayLike, q: ArrayLike = 0.0, per: str = "unit") -> Any:
    """Vega dV/dsigma = S e^{-qT} n(d1) sqrt(T).

    per="unit": change in value for a 1.00 (100 vol point) change in sigma.
    per="point": change in value for a 1 vol point (0.01) change in sigma.
    """
    S, K, T, r, sigma, q, d1, _ = _prep(S, K, T, r, sigma, q)
    v = S * np.exp(-q * T) * norm_pdf(d1) * np.sqrt(T)
    return _out(v * _scale(per, {"unit": 1.0, "point": 0.01}))


def bs_theta(S: ArrayLike, K: ArrayLike, T: ArrayLike, r: ArrayLike, sigma: ArrayLike, q: ArrayLike = 0.0, option: Any = "call", per: str = "year") -> Any:
    """Theta = -dV/dT (value change as calendar time passes, other inputs fixed).

    call: -S e^{-qT} n(d1) sigma / (2 sqrt(T)) - r K e^{-rT} N(d2) + q S e^{-qT} N(d1)
    put:  -S e^{-qT} n(d1) sigma / (2 sqrt(T)) + r K e^{-rT} N(-d2) - q S e^{-qT} N(-d1)
    per="year" (per 1.00 year) or per="day" (per calendar day = per year / 365).
    """
    S, K, T, r, sigma, q, d1, d2 = _prep(S, K, T, r, sigma, q)
    is_call = call_flag(option)
    dq, dr = np.exp(-q * T), np.exp(-r * T)
    decay = -S * dq * norm_pdf(d1) * sigma / (2.0 * np.sqrt(T))
    call = decay - r * K * dr * ndtr(d2) + q * S * dq * ndtr(d1)
    put = decay + r * K * dr * ndtr(-d2) - q * S * dq * ndtr(-d1)
    return _out(np.where(is_call, call, put) * _scale(per, {"year": 1.0, "day": 1.0 / 365.0}))


def bs_rho(S: ArrayLike, K: ArrayLike, T: ArrayLike, r: ArrayLike, sigma: ArrayLike, q: ArrayLike = 0.0, option: Any = "call", per: str = "unit") -> Any:
    """Rho dV/dr: call K T e^{-rT} N(d2), put -K T e^{-rT} N(-d2).

    per="unit" (per 1.00 change in r) or per="point" (per 1 percentage point = 0.01).
    """
    S, K, T, r, sigma, q, _, d2 = _prep(S, K, T, r, sigma, q)
    is_call = call_flag(option)
    dr = np.exp(-r * T)
    v = np.where(is_call, K * T * dr * ndtr(d2), -K * T * dr * ndtr(-d2))
    return _out(v * _scale(per, {"unit": 1.0, "point": 0.01}))


def _scale(per: str, table: dict[str, float]) -> float:
    if per not in table:
        raise ValueError(f"per must be one of {list(table)}, got {per!r}")
    return table[per]


def bs_greeks(S: ArrayLike, K: ArrayLike, T: ArrayLike, r: ArrayLike, sigma: ArrayLike, q: ArrayLike = 0.0, option: Any = "call") -> dict[str, Any]:
    """Price and all Greeks in one call, with both common scalings.

    Keys: price, delta, gamma, vega (per 1.00), vega_point (per vol point), theta (per year),
    theta_day (per calendar day), rho (per 1.00), rho_point (per 1% rate change).
    """
    args = (S, K, T, r, sigma, q)
    return {
        "price": bs_price(*args, option=option),
        "delta": bs_delta(*args, option=option),
        "gamma": bs_gamma(*args),
        "vega": bs_vega(*args, per="unit"),
        "vega_point": bs_vega(*args, per="point"),
        "theta": bs_theta(*args, option=option, per="year"),
        "theta_day": bs_theta(*args, option=option, per="day"),
        "rho": bs_rho(*args, option=option, per="unit"),
        "rho_point": bs_rho(*args, option=option, per="point"),
    }


# ---------------------------------------------------------------------------------------------
# Put-call parity helpers
# ---------------------------------------------------------------------------------------------
def parity_residual(call: ArrayLike, put: ArrayLike, S: ArrayLike, K: ArrayLike, T: ArrayLike, r: ArrayLike, q: ArrayLike = 0.0) -> Any:
    """Put-call parity residual C - P - (S e^{-qT} - K e^{-rT}); zero for consistent European prices."""
    call, put, S, K, T, r, q = (np.asarray(a, dtype=float) for a in (call, put, S, K, T, r, q))
    return _out(call - put - (S * np.exp(-q * T) - K * np.exp(-r * T)))


def put_from_call(call: ArrayLike, S: ArrayLike, K: ArrayLike, T: ArrayLike, r: ArrayLike, q: ArrayLike = 0.0) -> Any:
    """European put implied by parity: P = C - S e^{-qT} + K e^{-rT}."""
    call, S, K, T, r, q = (np.asarray(a, dtype=float) for a in (call, S, K, T, r, q))
    return _out(call - S * np.exp(-q * T) + K * np.exp(-r * T))


def call_from_put(put: ArrayLike, S: ArrayLike, K: ArrayLike, T: ArrayLike, r: ArrayLike, q: ArrayLike = 0.0) -> Any:
    """European call implied by parity: C = P + S e^{-qT} - K e^{-rT}."""
    put, S, K, T, r, q = (np.asarray(a, dtype=float) for a in (put, S, K, T, r, q))
    return _out(put + S * np.exp(-q * T) - K * np.exp(-r * T))


def forward_from_parity(call: ArrayLike, put: ArrayLike, K: ArrayLike, T: ArrayLike, r: ArrayLike) -> Any:
    """Forward implied by a call/put pair at the same strike: F = K + (C - P) e^{rT}."""
    call, put, K, T, r = (np.asarray(a, dtype=float) for a in (call, put, K, T, r))
    return _out(K + (call - put) * np.exp(r * T))


def carry_from_forward(F: ArrayLike, S: ArrayLike, T: ArrayLike) -> Any:
    """Annualised continuous carry b = r - q = ln(F/S) / T."""
    F, S, T = (np.asarray(a, dtype=float) for a in (F, S, T))
    return _out(np.log(F / S) / T)


def dividend_yield_from_forward(F: ArrayLike, S: ArrayLike, T: ArrayLike, r: ArrayLike) -> Any:
    """Implied continuous dividend yield q = r - ln(F/S) / T."""
    F, S, T, r = (np.asarray(a, dtype=float) for a in (F, S, T, r))
    return _out(r - np.log(F / S) / T)
