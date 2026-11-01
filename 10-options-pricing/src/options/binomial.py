"""Binomial trees for European and American options: Cox-Ross-Rubinstein and Leisen-Reimer.

Backward induction is vectorised over the nodes of each time step and over contracts: pass
arrays for S, K, T, r, sigma, q or option type and every contract is priced in the same loop
(node arrays have shape (n_contracts, n_nodes)).

CRR (Cox, Ross and Rubinstein, 1979), with dt = T / N:
    u = exp(sigma sqrt(dt)),  d = 1 / u,  p = (exp((r - q) dt) - d) / (u - d)
Leisen-Reimer (1996), N odd, Peizer-Pratt inversion h(z, n):
    p = h(d2, N),  p' = h(d1, N),  u = exp((r - q) dt) p' / p,  d = (exp((r - q) dt) - p u) / (1 - p)
Option value at a node: V = exp(-r dt) [p V_up + (1 - p) V_down]; American options take
max(V, exercise value) at every node.

Greeks from the tree: delta and gamma from the nodes at steps 1 and 2, theta from the middle
node at step 2 (t = 2 dt) against the root, vega and rho by central bump-and-revalue.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import ArrayLike

from .black_scholes import _d1_d2_fwd, _out, call_flag

__all__ = [
    "crr_params",
    "lr_params",
    "binomial_price",
    "binomial_price_two_step_average",
    "binomial_greeks",
    "early_exercise_boundary",
]


def crr_params(T: ArrayLike, r: ArrayLike, sigma: ArrayLike, q: ArrayLike, N: int) -> tuple[Any, Any, Any, Any, Any]:
    """CRR lattice parameters (dt, u, d, p, one-step discount factor)."""
    T, r, sigma, q = (np.asarray(a, dtype=float) for a in (T, r, sigma, q))
    dt = T / N
    u = np.exp(sigma * np.sqrt(dt))
    d = 1.0 / u
    p = (np.exp((r - q) * dt) - d) / (u - d)
    return _out(dt), _out(u), _out(d), _out(p), _out(np.exp(-r * dt))


def _pp_inversion(z: np.ndarray, n: int) -> np.ndarray:
    """Peizer-Pratt method-2 inversion used by Leisen-Reimer: maps a normal quantile z to a binomial probability."""
    a = z / (n + 1.0 / 3.0 + 0.1 / (n + 1.0))
    return 0.5 + np.sign(z) * np.sqrt(np.maximum(0.25 - 0.25 * np.exp(-a * a * (n + 1.0 / 6.0)), 0.0))


def lr_params(S: ArrayLike, K: ArrayLike, T: ArrayLike, r: ArrayLike, sigma: ArrayLike, q: ArrayLike, N: int) -> tuple[Any, Any, Any, Any, Any]:
    """Leisen-Reimer lattice parameters (dt, u, d, p, one-step discount factor). N must be odd."""
    if N % 2 == 0:
        raise ValueError("Leisen-Reimer needs an odd number of steps")
    S, K, T, r, sigma, q = (np.asarray(a, dtype=float) for a in (S, K, T, r, sigma, q))
    dt = T / N
    a = np.exp((r - q) * dt)
    d1, d2 = _d1_d2_fwd(S * np.exp((r - q) * T), K, T, sigma)
    p = _pp_inversion(d2, N)
    pbar = _pp_inversion(d1, N)
    u = a * pbar / p
    d = (a - p * u) / (1.0 - p)
    return _out(dt), _out(u), _out(d), _out(p), _out(np.exp(-r * dt))


def _broadcast(S, K, T, r, sigma, q, option):
    is_call = call_flag(option)
    arrs = np.broadcast_arrays(*(np.asarray(a, dtype=float) for a in (S, K, T, r, sigma, q)), is_call)
    shape = arrs[0].shape
    return shape, [np.ascontiguousarray(a).reshape(-1) for a in arrs]


def _tree(S, K, T, r, sigma, q, is_call, N, american, method, boundary=False):
    """Core backward induction on flat arrays of contracts.

    Returns (price, saved, boundary_array, dt) where saved[i] = (stock nodes, option values) at
    steps i = 1 and 2, and boundary_array[:, i] is the early-exercise boundary at step i (NaN if no
    node is exercised).
    """
    if method == "crr":
        dt, u, d, p, disc = (np.atleast_1d(x) for x in crr_params(T, r, sigma, q, N))
    elif method == "lr":
        dt, u, d, p, disc = (np.atleast_1d(x) for x in lr_params(S, K, T, r, sigma, q, N))
    else:
        raise ValueError("method must be 'crr' or 'lr'")
    m = S.size
    lnS, lnu, lnd = np.log(S)[:, None], np.log(u)[:, None], np.log(d)[:, None]
    jj = np.arange(N + 1)
    Kc, cc = K[:, None], is_call[:, None]

    def nodes(i: int) -> np.ndarray:
        j = jj[: i + 1]
        return np.exp(lnS + j * lnu + (i - j) * lnd)

    def exercise(Sn: np.ndarray) -> np.ndarray:
        return np.where(cc, np.maximum(Sn - Kc, 0.0), np.maximum(Kc - Sn, 0.0))

    V = exercise(nodes(N))
    pc, qc, dc = p[:, None], 1.0 - p[:, None], disc[:, None]
    saved: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    bnd = np.full((m, N), np.nan) if boundary else None
    for i in range(N - 1, -1, -1):
        V = dc * (pc * V[:, 1:] + qc * V[:, :-1])
        need_nodes = american or i <= 2
        Sn = nodes(i) if need_nodes else None
        if american:
            ex = exercise(Sn)
            if boundary:
                hit = (ex > V + 1e-12 * Kc) & (ex > 0)
                # puts: highest exercised node; calls: lowest exercised node
                put_b = np.where(hit, Sn, -np.inf).max(axis=1)
                call_b = np.where(hit, Sn, np.inf).min(axis=1)
                b = np.where(is_call, call_b, put_b)
                bnd[:, i] = np.where(np.isfinite(b), b, np.nan)
            V = np.maximum(V, ex)
        if 1 <= i <= 2:
            saved[i] = (Sn, V.copy())
    return V[:, 0], saved, bnd, dt


def binomial_price(
    S: ArrayLike,
    K: ArrayLike,
    T: ArrayLike,
    r: ArrayLike,
    sigma: ArrayLike,
    q: ArrayLike = 0.0,
    option: Any = "call",
    N: int = 500,
    american: bool = False,
    method: str = "crr",
) -> Any:
    """Binomial price of a European (american=False) or American (american=True) option.

    method="crr" (Cox-Ross-Rubinstein) or "lr" (Leisen-Reimer; an even N is raised to N + 1).
    """
    if method == "lr" and N % 2 == 0:
        N += 1
    shape, (s, k, t, rr, sg, qq, c) = _broadcast(S, K, T, r, sigma, q, option)
    price, _, _, _ = _tree(s, k, t, rr, sg, qq, c.astype(bool), N, american, method)
    return _out(price.reshape(shape))


def binomial_price_two_step_average(
    S: ArrayLike, K: ArrayLike, T: ArrayLike, r: ArrayLike, sigma: ArrayLike, q: ArrayLike = 0.0,
    option: Any = "call", N: int = 500, american: bool = False,
) -> Any:
    """Average of the CRR prices with N and N + 1 steps; cancels most of the odd/even oscillation."""
    a = np.asarray(binomial_price(S, K, T, r, sigma, q, option, N, american, "crr"))
    b = np.asarray(binomial_price(S, K, T, r, sigma, q, option, N + 1, american, "crr"))
    return _out(0.5 * (a + b))


def binomial_greeks(
    S: ArrayLike,
    K: ArrayLike,
    T: ArrayLike,
    r: ArrayLike,
    sigma: ArrayLike,
    q: ArrayLike = 0.0,
    option: Any = "call",
    N: int = 500,
    american: bool = False,
    method: str = "crr",
    d_sigma: float = 1e-3,
    d_r: float = 1e-4,
) -> dict[str, Any]:
    """Price and Greeks from a binomial tree.

    delta = (V_u - V_d) / (S_u - S_d) at step 1
    gamma = [(V_uu - V_ud)/(S_uu - S_ud) - (V_ud - V_dd)/(S_ud - S_dd)] / [(S_uu - S_dd) / 2] at step 2
    theta = (V_ud - V_0) / (2 dt), per year; for trees where S_ud != S_0 (Leisen-Reimer) the
            move in S is removed with a delta-gamma correction first
    vega, rho: central differences of the tree price with bumps d_sigma and d_r.
    Keys follow `bs_greeks`: price, delta, gamma, vega, vega_point, theta, theta_day, rho, rho_point.
    """
    if method == "lr" and N % 2 == 0:
        N += 1
    if N < 3:
        raise ValueError("need N >= 3 steps for tree Greeks")
    shape, (s, k, t, rr, sg, qq, c) = _broadcast(S, K, T, r, sigma, q, option)
    c = c.astype(bool)
    price, saved, _, dt = _tree(s, k, t, rr, sg, qq, c, N, american, method)
    S1, V1 = saved[1]
    S2, V2 = saved[2]
    delta = (V1[:, 1] - V1[:, 0]) / (S1[:, 1] - S1[:, 0])
    gamma = ((V2[:, 2] - V2[:, 1]) / (S2[:, 2] - S2[:, 1]) - (V2[:, 1] - V2[:, 0]) / (S2[:, 1] - S2[:, 0])) / (
        0.5 * (S2[:, 2] - S2[:, 0])
    )
    dS = S2[:, 1] - s
    theta = (V2[:, 1] - price - delta * dS - 0.5 * gamma * dS**2) / (2.0 * dt)

    def reprice(sig: np.ndarray, rate: np.ndarray) -> np.ndarray:
        return _tree(s, k, t, rate, sig, qq, c, N, american, method)[0]

    vega = (reprice(sg + d_sigma, rr) - reprice(sg - d_sigma, rr)) / (2.0 * d_sigma)
    rho = (reprice(sg, rr + d_r) - reprice(sg, rr - d_r)) / (2.0 * d_r)
    out = {
        "price": price,
        "delta": delta,
        "gamma": gamma,
        "vega": vega,
        "vega_point": vega * 0.01,
        "theta": theta,
        "theta_day": theta / 365.0,
        "rho": rho,
        "rho_point": rho * 0.01,
    }
    return {key: _out(val.reshape(shape)) for key, val in out.items()}


def early_exercise_boundary(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    q: float = 0.0,
    option: str = "put",
    N: int = 2000,
    method: str = "crr",
) -> pd.DataFrame:
    """Early-exercise boundary of an American option from a binomial tree.

    For a put the boundary at each step is the highest stock price at which immediate exercise is
    worth more than continuing; for a call it is the lowest such price. Because tree nodes sit on a
    grid, the reported boundary is the geometric midpoint between the last exercised node and its
    neighbour on the continuation side.

    Returns a DataFrame with t (years from today), tau (years to expiry), boundary and
    boundary_over_K. The expiry point uses the known limit: K for a put when r >= q, K * r / q otherwise.
    """
    if method == "lr" and N % 2 == 0:
        N += 1
    shape, (s, k, t, rr, sg, qq, c) = _broadcast(S, K, T, r, sigma, q, option)
    c = c.astype(bool)
    _, _, bnd, dt = _tree(s, k, t, rr, sg, qq, c, N, True, method, boundary=True)
    if method == "crr":
        _, u, d, _, _ = crr_params(T, r, sigma, q, N)
    else:
        _, u, d, _, _ = lr_params(S, K, T, r, sigma, q, N)
    # nodes at one step are spaced by a factor u/d (= u^2 for CRR); move half a spacing
    # (geometrically) from the last exercised node towards the continuation region
    step = float(np.sqrt(u / d))
    b = bnd[0] * (step if not c[0] else 1.0 / step)
    times = np.arange(N) * float(dt[0])
    df = pd.DataFrame({"t": times, "tau": T - times, "boundary": b})
    if c[0]:
        limit = K * max(1.0, r / q) if q > 0 else np.inf
    else:
        limit = K if r >= q else K * r / q
    df = pd.concat([df, pd.DataFrame({"t": [T], "tau": [0.0], "boundary": [limit]})], ignore_index=True)
    df["boundary_over_K"] = df["boundary"] / K
    return df
