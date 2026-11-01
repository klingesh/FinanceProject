"""Market application on the NSE NIFTY option chain of 30-Oct-2026.

Steps: parity-implied forwards per expiry, implied vols (Black-76 on the implied forward),
OTM smile, ATM term structure, VIX-style model-free variance, Greeks tables, binomial vs
Black-Scholes on market contracts, American-put illustration and realised volatility.
"""
from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from .binomial import binomial_greeks, binomial_price
from .black_scholes import bs_greeks, bs_price
from .implied_vol import implied_vol, implied_vol_black76

__all__ = [
    "R_SIMPLE",
    "R_CONT",
    "SPOT_CLOSE",
    "INDIA_VIX",
    "LOT_SIZE",
    "DIV_YIELD_FACTSHEET",
    "NOV_FUTURES_CLOSE",
    "implied_forwards",
    "add_implied_vols",
    "otm_smile",
    "interp_iv",
    "call_put_iv_gap",
    "nse_iv_convention",
    "atm_term_structure",
    "vix_style_variance",
    "interpolate_vol_30d",
    "greeks_table",
    "greek_profiles",
    "binomial_vs_bs",
    "american_put_premium",
    "realised_vol",
    "vix_vs_realised",
]

#: 91-day T-bill cut-off yield, RBI auction of 28-Oct-2026 (Economic Times), treated as annual.
R_SIMPLE = 0.0593
#: Continuously compounded equivalent used throughout: ln(1.0593).
R_CONT = float(np.log1p(R_SIMPLE))
#: NIFTY 50 close on 30-Oct-2026 (Yahoo ^NSEI; same as the NSE JSON underlyingValue).
SPOT_CLOSE = 23053.10
#: India VIX close on 30-Oct-2026 (Yahoo ^INDIAVIX).
INDIA_VIX = 15.30
#: NIFTY lot size (75 -> 65 for contracts expiring after 30-Dec-2025; all quote sizes in the snapshot are multiples of 65).
LOT_SIZE = 65
#: NIFTY 50 trailing 12-month dividend yield, NSE Indices NIFTY 50 factsheet dated 30-Oct-2026
#: (Fundamentals block: P/E 19.30, P/B 2.83, dividend yield 1.42%).
DIV_YIELD_FACTSHEET = 0.0142
#: NIFTY November 2026 futures close on 30-Oct-2026 (Capital Market news, 30-Oct-2026).
NOV_FUTURES_CLOSE = 23101.40


# ---------------------------------------------------------------------------------------------
# Forwards
# ---------------------------------------------------------------------------------------------
def implied_forwards(df: pd.DataFrame, r: float = R_CONT, spot: float = SPOT_CLOSE, n_strikes: int = 5) -> pd.DataFrame:
    """Parity-implied forward per expiry from usable call/put pairs near the money.

    For each strike with a usable call and put: F_K = K + (C_mid - P_mid) e^{rT}. The forward is
    the median F_K over the `n_strikes` pairs with the smallest |C - P| (closest to ATM). The
    bid/ask band uses F_low = K + (C_bid - P_ask) e^{rT} and F_high = K + (C_ask - P_bid) e^{rT};
    the reported interval is [max F_low, min F_high] over the same strikes.
    The carry b = ln(F/S)/T and the implied yield q = r - b are relative to the given spot.
    A regression of (C - P) on K over strikes within 3% of spot also gives an implied discount
    factor (slope = -DF), reported as r_ols for reference.
    """
    rows = []
    use = df[df["usable"]]
    for exp, g in use.groupby("expiry"):
        T = float(g["T"].iloc[0])
        DF = float(np.exp(-r * T))
        c = g[g["option_type"] == "C"].set_index("strike")[["bid", "ask", "mid"]]
        p = g[g["option_type"] == "P"].set_index("strike")[["bid", "ask", "mid"]]
        pair = c.join(p, lsuffix="_c", rsuffix="_p", how="inner")
        if pair.empty:
            continue
        K = pair.index.to_numpy(dtype=float)
        pair["cp"] = pair["mid_c"] - pair["mid_p"]
        pair["F_K"] = K + pair["cp"] / DF
        pair["F_lo"] = K + (pair["bid_c"] - pair["ask_p"]) / DF
        pair["F_hi"] = K + (pair["ask_c"] - pair["bid_p"]) / DF
        near = pair.loc[pair["cp"].abs().nsmallest(n_strikes).index].sort_index()
        F = float(near["F_K"].median())
        w = pair[(pair.index >= 0.97 * spot) & (pair.index <= 1.03 * spot)]
        r_ols = np.nan
        if len(w) >= 4:
            slope, _ = np.polyfit(w.index.to_numpy(dtype=float), w["cp"].to_numpy(), 1)
            r_ols = -np.log(-slope) / T if slope < 0 else np.nan
        b = float(np.log(F / spot) / T)
        F_theory = spot * np.exp((r - DIV_YIELD_FACTSHEET) * T)
        rows.append(
            {
                "expiry": exp,
                "days": int(g["days"].iloc[0]),
                "T": T,
                "DF": DF,
                "n_pairs": len(pair),
                "strikes_used": " ".join(str(int(k)) for k in near.index),
                "F": F,
                "F_min": float(near["F_K"].min()),
                "F_max": float(near["F_K"].max()),
                "F_bidask_low": float(near["F_lo"].max()),
                "F_bidask_high": float(near["F_hi"].min()),
                "F_minus_spot": F - spot,
                "F_over_spot_pct": 100 * (F / spot - 1),
                "carry_b": b,
                "q_implied": r - b,
                "pv_gap_points": spot - DF * F,
                "F_theory_div_yield": F_theory,
                "F_minus_theory": F - F_theory,
                "r_ols": r_ols,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------------------------
# Implied volatilities
# ---------------------------------------------------------------------------------------------
def add_implied_vols(
    df: pd.DataFrame,
    fwd: pd.DataFrame,
    r: float = R_CONT,
    spot: float = SPOT_CLOSE,
    r_nse: float | None = None,
) -> pd.DataFrame:
    """Add own implied vols for usable quotes (Black-76 on the parity forward of each expiry).

    New columns: F, DF, q_implied, fwd_moneyness (K/F), log_moneyness (ln K/F), otm flag,
    iv (from mid), iv_bid, iv_ask, iv_method (0 Newton, 1 Brent, -1 none), iv_nse (decimal),
    iv_spot_div (spot, q = factsheet dividend yield, mid price; shows the cost of a wrong forward),
    and iv_nse_replica (spot, q = 0, last price, rate r_nse) when r_nse is given.
    """
    out = df.merge(fwd[["expiry", "F", "DF", "q_implied"]], on="expiry", how="left")
    out["fwd_moneyness"] = out["strike"] / out["F"]
    out["log_moneyness"] = np.log(out["fwd_moneyness"])
    is_call = out["option_type"].eq("C").to_numpy()
    out["otm"] = np.where(is_call, out["strike"] >= out["F"], out["strike"] < out["F"])
    out["iv_nse"] = out["iv_nse_pct"].where(out["iv_nse_pct"] > 0) / 100.0
    for col in ("iv", "iv_bid", "iv_ask", "iv_spot_div", "iv_nse_replica"):
        out[col] = np.nan
    out["iv_method"] = -1
    m = out["usable"].to_numpy() & out["F"].notna().to_numpy()
    if m.any():
        sub = out.loc[m]
        args = (sub["F"].to_numpy(), sub["strike"].to_numpy(), sub["T"].to_numpy(), sub["DF"].to_numpy())
        flag = is_call[m]
        iv, info = implied_vol_black76(sub["mid"].to_numpy(), *args, flag, return_info=True)
        out.loc[m, "iv"] = iv
        out.loc[m, "iv_method"] = info["method"]
        out.loc[m, "iv_bid"] = implied_vol_black76(sub["bid"].to_numpy(), *args, flag)
        out.loc[m, "iv_ask"] = implied_vol_black76(sub["ask"].to_numpy(), *args, flag)
        out.loc[m, "iv_spot_div"] = implied_vol(
            sub["mid"].to_numpy(), spot, sub["strike"].to_numpy(), sub["T"].to_numpy(), r, DIV_YIELD_FACTSHEET, flag
        )
        if r_nse is not None:
            last = sub["last"].where(sub["last"] > 0).to_numpy()
            out.loc[m, "iv_nse_replica"] = implied_vol(last, spot, sub["strike"].to_numpy(), sub["T"].to_numpy(), r_nse, 0.0, flag)
    return out


def otm_smile(df_iv: pd.DataFrame, expiry: pd.Timestamp | str) -> pd.DataFrame:
    """Out-of-the-money smile for one expiry: puts with K < F, calls with K >= F (usable quotes only)."""
    expiry = pd.Timestamp(expiry)
    g = df_iv[(df_iv["expiry"] == expiry) & df_iv["usable"] & df_iv["otm"] & df_iv["iv"].notna()]
    cols = [
        "expiry", "days", "T", "strike", "option_type", "F", "fwd_moneyness", "log_moneyness", "bid", "ask", "mid",
        "rel_spread", "open_interest", "volume", "iv", "iv_bid", "iv_ask", "iv_nse", "iv_spot_div",
    ]
    return g.sort_values("strike")[cols].reset_index(drop=True)


def interp_iv(smile: pd.DataFrame, fwd_moneyness: float | Iterable[float]) -> np.ndarray | float:
    """Linear interpolation of the smile IV in log-moneyness ln(K/F); NaN outside the quoted range."""
    x = np.log(np.asarray(fwd_moneyness, dtype=float))
    xs, ys = smile["log_moneyness"].to_numpy(), smile["iv"].to_numpy()
    res = np.interp(x, xs, ys, left=np.nan, right=np.nan)
    return float(res) if res.ndim == 0 else res


def call_put_iv_gap(df_iv: pd.DataFrame, expiry: pd.Timestamp | str) -> pd.DataFrame:
    """Call IV minus put IV at the same strike (own IVs and NSE IVs) for one expiry."""
    expiry = pd.Timestamp(expiry)
    g = df_iv[(df_iv["expiry"] == expiry) & df_iv["usable"]]
    c = g[g["option_type"] == "C"].set_index("strike")
    p = g[g["option_type"] == "P"].set_index("strike")
    j = c[["iv", "iv_nse", "iv_spot_div", "fwd_moneyness"]].join(p[["iv", "iv_nse", "iv_spot_div"]], lsuffix="_call", rsuffix="_put", how="inner")
    j["gap_own"] = j["iv_call"] - j["iv_put"]
    j["gap_nse"] = j["iv_nse_call"] - j["iv_nse_put"]
    j["gap_spot_div"] = j["iv_spot_div_call"] - j["iv_spot_div_put"]
    return j.reset_index()


def nse_iv_convention(df: pd.DataFrame, spot: float = SPOT_CLOSE, band: float = 0.03) -> tuple[float, pd.DataFrame]:
    """Back out the interest rate that reproduces NSE's impliedVolatility field.

    Assumes NSE applies Black-Scholes to the last traded price with the index spot, no dividends
    and T = calendar days / 365. For each usable contract within `band` of spot, solve for the rate
    r such that BS(spot, K, T, r, IV_nse) = last price; return the median and the per-contract table.
    """
    g = df[df["usable"] & (df["last"] > 0) & (df["iv_nse_pct"] > 0) & ((df["strike"] / spot - 1).abs() <= band)]
    rates = []
    for _, row in g.iterrows():
        is_c = row["option_type"] == "C"

        def f(rr: float, row=row, is_c=is_c) -> float:
            return float(bs_price(spot, row["strike"], row["T"], rr, row["iv_nse_pct"] / 100, 0.0, is_c)) - row["last"]

        try:
            rates.append(brentq(f, -0.5, 0.5))
        except ValueError:
            rates.append(np.nan)
    tab = g[["expiry", "strike", "option_type", "last", "iv_nse_pct"]].copy()
    tab["r_reproducing_nse_iv"] = rates
    return float(np.nanmedian(rates)), tab.reset_index(drop=True)


# ---------------------------------------------------------------------------------------------
# Term structure and VIX-style variance
# ---------------------------------------------------------------------------------------------
def vix_style_variance(chain: pd.DataFrame, F: float, T: float, r: float = R_CONT) -> dict[str, float]:
    """Model-free variance of one expiry with the CBOE VIX formula.

    sigma^2 = (2/T) sum_i (dK_i / K_i^2) e^{rT} Q(K_i) - (1/T) (F/K0 - 1)^2
    K0 is the first strike at or below F; Q is the put mid below K0, the call mid above K0 and the
    average of both at K0. Strikes need a two-sided quote; moving away from K0 the strip stops
    after two consecutive strikes without one. dK_i is half the distance between the neighbours.
    """
    two_sided = (chain["bid"] > 0) & (chain["ask"] > 0)
    calls = chain[(chain["option_type"] == "C")].set_index("strike")
    puts = chain[(chain["option_type"] == "P")].set_index("strike")
    ok_c = set(chain.loc[two_sided & (chain["option_type"] == "C"), "strike"])
    ok_p = set(chain.loc[two_sided & (chain["option_type"] == "P"), "strike"])
    strikes = np.array(sorted(set(calls.index) | set(puts.index)), dtype=float)
    K0 = float(strikes[strikes <= F].max())
    sel: list[tuple[float, float]] = []
    run = 0
    for k in strikes[strikes < K0][::-1]:
        if k in ok_p:
            sel.append((k, float(puts.loc[k, "mid"])))
            run = 0
        else:
            run += 1
            if run >= 2:
                break
    run = 0
    for k in strikes[strikes > K0]:
        if k in ok_c:
            sel.append((k, float(calls.loc[k, "mid"])))
            run = 0
        else:
            run += 1
            if run >= 2:
                break
    sel.append((K0, 0.5 * (float(calls.loc[K0, "mid"]) + float(puts.loc[K0, "mid"]))))
    strip = pd.DataFrame(sel, columns=["K", "Q"]).sort_values("K").reset_index(drop=True)
    K = strip["K"].to_numpy()
    dK = np.empty_like(K)
    dK[1:-1] = 0.5 * (K[2:] - K[:-2])
    dK[0] = K[1] - K[0]
    dK[-1] = K[-1] - K[-2]
    contrib = dK / K**2 * np.exp(r * T) * strip["Q"].to_numpy()
    var = 2.0 / T * contrib.sum() - (F / K0 - 1.0) ** 2 / T
    return {"variance": float(var), "vol": float(np.sqrt(var)), "K0": K0, "n_strikes": int(len(K)), "K_min": float(K.min()), "K_max": float(K.max())}


def interpolate_vol_30d(T1: float, vol1: float, T2: float, vol2: float, target_days: float = 30.0) -> float:
    """Interpolate total variance sigma^2 T linearly in time to a constant 30-day maturity (CBOE convention)."""
    T30 = target_days / 365.0
    w1 = (T2 - T30) / (T2 - T1)
    w2 = (T30 - T1) / (T2 - T1)
    var = (T1 * vol1**2 * w1 + T2 * vol2**2 * w2) / T30
    return float(np.sqrt(var))


def atm_term_structure(df_iv: pd.DataFrame, fwd: pd.DataFrame, r: float = R_CONT) -> pd.DataFrame:
    """ATM implied vol (at K = F, from the OTM smile) and VIX-style vol for every expiry."""
    rows = []
    for _, f in fwd.iterrows():
        sm = otm_smile(df_iv, f["expiry"])
        atm = interp_iv(sm, 1.0) if len(sm) >= 2 else np.nan
        chain = df_iv[df_iv["expiry"] == f["expiry"]]
        vix = vix_style_variance(chain, f["F"], f["T"], r)
        rows.append(
            {
                "expiry": f["expiry"],
                "days": int(f["days"]),
                "T": f["T"],
                "F": f["F"],
                "atm_iv": atm,
                "iv_95": interp_iv(sm, 0.95) if len(sm) >= 2 else np.nan,
                "iv_105": interp_iv(sm, 1.05) if len(sm) >= 2 else np.nan,
                "atm_total_variance": atm**2 * f["T"],
                "model_free_vol": vix["vol"],
                "model_free_strikes": vix["n_strikes"],
                "model_free_K_range": f"{int(vix['K_min'])}-{int(vix['K_max'])}",
                "n_otm_quotes": len(sm),
            }
        )
    ts = pd.DataFrame(rows)
    ts["skew_95_105"] = ts["iv_95"] - ts["iv_105"]
    return ts


# ---------------------------------------------------------------------------------------------
# Greeks and binomial comparisons
# ---------------------------------------------------------------------------------------------
def greeks_table(
    contracts: list[dict],
    df_iv: pd.DataFrame,
    fwd: pd.DataFrame,
    spot: float = SPOT_CLOSE,
    r: float = R_CONT,
    lot: int = LOT_SIZE,
    n_tree: int = 1000,
) -> pd.DataFrame:
    """BSM Greeks (spot-based, q = expiry's implied yield) for listed contracts, with CRR tree Greeks.

    contracts: dicts with keys label, expiry, strike, option_type ("C"/"P").
    Units: delta per 1 index point move (dimensionless), gamma per index point, vega in points per
    1 vol point, theta in points per calendar day, rho in points per 1 percentage point of r.
    Per-lot rupee values multiply index points by the lot size (1 point = Rs 1 per unit).
    """
    rows = []
    for c in contracts:
        exp = pd.Timestamp(c["expiry"])
        sel = df_iv[(df_iv["expiry"] == exp) & (df_iv["strike"] == c["strike"]) & (df_iv["option_type"] == c["option_type"])]
        if sel.empty:
            raise KeyError(f"contract not found: {c}")
        row = sel.iloc[0]
        q = float(fwd.loc[fwd["expiry"] == exp, "q_implied"].iloc[0])
        opt = "call" if c["option_type"] == "C" else "put"
        g = bs_greeks(spot, row["strike"], row["T"], r, row["iv"], q, opt)
        tg = binomial_greeks(spot, row["strike"], row["T"], r, row["iv"], q, opt, N=n_tree, method="crr")
        rows.append(
            {
                "label": c["label"],
                "expiry": exp.date(),
                "days": int(row["days"]),
                "strike": row["strike"],
                "type": opt,
                "strike_over_spot": row["strike"] / spot,
                "bid": row["bid"],
                "ask": row["ask"],
                "mid": row["mid"],
                "iv_own": row["iv"],
                "iv_nse": row["iv_nse"],
                "bs_price": g["price"],
                "delta": g["delta"],
                "gamma": g["gamma"],
                "vega_per_volpt": g["vega_point"],
                "theta_per_day": g["theta_day"],
                "rho_per_pct": g["rho_point"],
                "tree_price": tg["price"],
                "tree_delta": tg["delta"],
                "tree_gamma": tg["gamma"],
                "tree_vega_per_volpt": tg["vega_point"],
                "tree_theta_per_day": tg["theta_day"],
                "tree_rho_per_pct": tg["rho_point"],
                "premium_per_lot_rs": row["mid"] * lot,
                "delta_notional_per_lot_rs": g["delta"] * spot * lot,
                "gamma_per_lot_per_100pts": g["gamma"] * lot * 100,
                "vega_per_lot_rs": g["vega_point"] * lot,
                "theta_per_lot_rs": g["theta_day"] * lot,
            }
        )
    return pd.DataFrame(rows)


def greek_profiles(
    spots: np.ndarray, strike: float, maturities: list[dict], r: float = R_CONT
) -> pd.DataFrame:
    """Call delta, gamma, vega (per vol point) and theta (per day) across spot levels.

    maturities: dicts with label, T, sigma, q. Returns a long frame (label, spot, greek columns).
    """
    frames = []
    for m in maturities:
        g = bs_greeks(spots, strike, m["T"], r, m["sigma"], m["q"], "call")
        gp = bs_greeks(spots, strike, m["T"], r, m["sigma"], m["q"], "put")
        frames.append(
            pd.DataFrame(
                {
                    "label": m["label"],
                    "spot": spots,
                    "call_delta": g["delta"],
                    "put_delta": gp["delta"],
                    "gamma": g["gamma"],
                    "vega_per_volpt": g["vega_point"],
                    "call_theta_per_day": g["theta_day"],
                    "put_theta_per_day": gp["theta_day"],
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def binomial_vs_bs(smile: pd.DataFrame, q: float, spot: float = SPOT_CLOSE, r: float = R_CONT, n_crr: int = 1000, n_lr: int = 501) -> pd.DataFrame:
    """Price every smile contract with BSM, CRR and Leisen-Reimer (European) at its own implied vol."""
    K = smile["strike"].to_numpy()
    T = smile["T"].to_numpy()
    iv = smile["iv"].to_numpy()
    flag = smile["option_type"].eq("C").to_numpy()
    out = smile[["strike", "option_type", "mid", "iv"]].copy()
    out["bs"] = bs_price(spot, K, T, r, iv, q, flag)
    out["crr"] = binomial_price(spot, K, T, r, iv, q, flag, N=n_crr, method="crr")
    out["lr"] = binomial_price(spot, K, T, r, iv, q, flag, N=n_lr, method="lr")
    out["bs_minus_mid"] = out["bs"] - out["mid"]
    out["crr_minus_bs"] = out["crr"] - out["bs"]
    out["lr_minus_bs"] = out["lr"] - out["bs"]
    return out


def american_put_premium(
    strikes: np.ndarray, smile: pd.DataFrame, T: float, q: float, spot: float = SPOT_CLOSE, r: float = R_CONT, n: int = 1000
) -> pd.DataFrame:
    """European vs American put on the same terms (CRR, N steps), vol taken from the market smile."""
    strikes = np.asarray(strikes, dtype=float)
    F = float(smile["F"].iloc[0])
    iv = interp_iv(smile, strikes / F)
    eu = binomial_price(spot, strikes, T, r, iv, q, "put", N=n, american=False)
    am = binomial_price(spot, strikes, T, r, iv, q, "put", N=n, american=True)
    bs = bs_price(spot, strikes, T, r, iv, q, "put")
    out = pd.DataFrame({"strike": strikes, "strike_over_spot": strikes / spot, "iv": iv, "bs_european": bs, "crr_european": eu, "crr_american": am})
    out["early_exercise_premium"] = out["crr_american"] - out["crr_european"]
    out["premium_pct_of_european"] = 100 * out["early_exercise_premium"] / out["crr_european"]
    return out


# ---------------------------------------------------------------------------------------------
# Realised volatility
# ---------------------------------------------------------------------------------------------
def realised_vol(close: pd.Series, window: int = 21, periods_per_year: int = 252) -> pd.Series:
    """Trailing close-to-close realised volatility (annualised, decimal)."""
    ret = np.log(close).diff()
    return ret.rolling(window).std() * np.sqrt(periods_per_year)


def vix_vs_realised(vix: pd.Series, close: pd.Series, window: int = 21) -> pd.DataFrame:
    """India VIX next to trailing and next-`window`-day realised NIFTY volatility (all in %)."""
    df = pd.concat({"vix": vix, "close": close}, axis=1, join="inner").dropna()
    ret = np.log(df["close"]).diff()
    df["rv_trailing"] = 100 * ret.rolling(window).std() * np.sqrt(252)
    df["rv_next"] = df["rv_trailing"].shift(-window)
    return df
