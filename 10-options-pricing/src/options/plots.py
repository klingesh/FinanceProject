"""Matplotlib figures for the README and notebook (150 dpi PNG, titles, axis units, source notes)."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from .analysis import DIV_YIELD_FACTSHEET, R_CONT

__all__ = [
    "plot_convergence",
    "plot_smile",
    "plot_term_structure",
    "plot_greek_profiles",
    "plot_early_exercise",
    "plot_hedging",
    "plot_vix_history",
]

NSE_SOURCE = "Source: NSE NIFTY option chain, 30-Oct-2026 close (snapshot 15:40 IST); author calculations."
plt.rcParams.update({"axes.grid": True, "grid.alpha": 0.3, "axes.spines.top": False, "axes.spines.right": False, "font.size": 10})


def _finish(fig: plt.Figure, path: str | Path | None, source: str) -> plt.Figure:
    fig.text(0.01, 0.01, source, fontsize=8, color="0.35", ha="left", va="bottom")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    if path is not None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=150)
    return fig


def plot_convergence(conv: pd.DataFrame, path: str | Path | None = None, n_zoom: int = 200) -> plt.Figure:
    """Left: CRR error for odd and even N. Right: absolute error on log axes for CRR, CRR average and Leisen-Reimer."""
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.8))
    z = conv[conv["N"] <= n_zoom]
    for par, col in (("even", "tab:blue"), ("odd", "tab:orange")):
        s = z[z["parity"] == par]
        a1.plot(s["N"], s["crr_err"], marker="o", ms=2.5, lw=0.8, color=col, label=f"CRR, {par} N")
    a1.axhline(0, color="k", lw=0.8)
    a1.set_title("CRR error oscillates between odd and even N")
    a1.set_xlabel("Number of steps N")
    a1.set_ylabel("Binomial price - Black-Scholes price (price units)")
    a1.legend()
    a2.loglog(conv["N"], conv["crr_err"].abs(), lw=0.6, color="0.6", label="CRR")
    a2.loglog(conv["N"], conv["crr_avg_N_N1_err"].abs(), lw=0.8, color="tab:blue", label="CRR, average of N and N+1")
    lr = conv.dropna(subset=["lr"])
    a2.loglog(lr["N"], lr["lr_err"].abs(), lw=1.2, color="tab:green", label="Leisen-Reimer (odd N)")
    n = conv["N"].to_numpy(dtype=float)
    a2.loglog(n, 0.5 / n, ls="--", color="k", lw=0.8, label="slope 1/N")
    a2.loglog(n, 0.05 / n**2, ls=":", color="k", lw=1.0, label="slope 1/N^2")
    a2.set_title("Absolute pricing error vs steps (log-log)")
    a2.set_xlabel("Number of steps N")
    a2.set_ylabel("|binomial - Black-Scholes| (price units)")
    a2.legend(fontsize=8)
    fig.suptitle("Binomial convergence to Black-Scholes: European call S=42, K=40, r=10%, vol=20%, T=0.5", fontsize=11)
    return _finish(fig, path, "Source: Hull's textbook example; author calculations.")


def plot_smile(smile: pd.DataFrame, gap: pd.DataFrame, title_expiry: str, F: float, spot: float, path: str | Path | None = None) -> plt.Figure:
    """Left: OTM implied-vol smile (own IV with bid/ask band, NSE IV). Right: call IV minus put IV per strike."""
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12.5, 5), gridspec_kw={"width_ratios": [1.6, 1]})
    puts = smile[smile["option_type"] == "P"]
    calls = smile[smile["option_type"] == "C"]
    a1.fill_between(smile["strike"], 100 * smile["iv_bid"], 100 * smile["iv_ask"], color="tab:blue", alpha=0.15, label="bid-ask IV range")
    a1.plot(puts["strike"], 100 * puts["iv"], "o-", ms=3.5, color="tab:red", label="OTM puts, own IV (mid)")
    a1.plot(calls["strike"], 100 * calls["iv"], "o-", ms=3.5, color="tab:blue", label="OTM calls, own IV (mid)")
    a1.plot(smile["strike"], 100 * smile["iv_nse"], "x", ms=4, color="0.4", label="NSE reported IV")
    a1.axvline(F, color="k", lw=0.8, ls="--", label=f"parity forward {F:,.0f}")
    a1.axvline(spot, color="0.5", lw=0.8, ls=":", label=f"spot {spot:,.0f}")
    a1.set_title(f"NIFTY implied volatility smile, expiry {title_expiry}")
    a1.set_xlabel("Strike (index points)")
    a1.set_ylabel("Implied volatility (% p.a.)")
    a1.legend(fontsize=8)
    near = gap[(gap["fwd_moneyness"] > 0.95) & (gap["fwd_moneyness"] < 1.05)]
    a2.axhline(0, color="k", lw=0.8)
    a2.plot(near["strike"], 100 * near["gap_own"], "o-", ms=3, color="tab:green", label="own IV (parity forward)")
    a2.plot(near["strike"], 100 * near["gap_spot_div"], "s-", ms=3, color="tab:purple",
            label=f"own IV, spot with q = {100 * DIV_YIELD_FACTSHEET:.2f}% (factsheet)")
    a2.plot(near["strike"], 100 * near["gap_nse"], "x-", ms=4, color="0.4", label="NSE reported IV")
    a2.set_title("Call IV minus put IV at the same strike")
    a2.set_xlabel("Strike (index points)")
    a2.set_ylabel("Vol points")
    a2.legend(fontsize=8)
    return _finish(fig, path, NSE_SOURCE)


def plot_term_structure(ts: pd.DataFrame, vix: float, atm30: float, mf30: float, rv21: float, path: str | Path | None = None) -> plt.Figure:
    """ATM implied vol and model-free vol by expiry, with India VIX and 30-day interpolations."""
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(ts["days"], 100 * ts["atm_iv"], "o-", color="tab:blue", label="ATM implied vol (K = forward)")
    ax.plot(ts["days"], 100 * ts["model_free_vol"], "s--", color="tab:orange", ms=4, label="model-free (VIX formula) vol per expiry")
    ax.scatter([30], [vix], marker="*", s=180, color="tab:red", zorder=5, label=f"India VIX close {vix:.2f}")
    ax.scatter([30], [100 * atm30], marker="D", s=50, color="tab:blue", zorder=5, label=f"30-day ATM vol {100 * atm30:.2f}")
    ax.scatter([30], [100 * mf30], marker="D", s=50, color="tab:orange", zorder=5, label=f"30-day model-free vol {100 * mf30:.2f}")
    ax.axhline(100 * rv21, color="0.5", ls=":", lw=1, label=f"NIFTY 21-day realised vol {100 * rv21:.2f}")
    for _, r in ts.iterrows():
        ax.annotate(pd.Timestamp(r["expiry"]).strftime("%d-%b"), (r["days"], 100 * r["atm_iv"]), textcoords="offset points", xytext=(0, -14), ha="center", fontsize=8)
    first = ts.iloc[0]
    ax.annotate("4 calendar days incl. a weekend:\nvol measured on a calendar clock", (first["days"], 100 * first["atm_iv"]), textcoords="offset points",
                xytext=(14, 4), fontsize=8, color="0.3")
    lo = min(100 * ts["atm_iv"].min(), 100 * rv21) - 0.6
    hi = max(100 * ts["model_free_vol"].max(), vix) + 0.4
    ax.set_ylim(lo, hi)
    ax.set_title("NIFTY volatility term structure on 30-Oct-2026")
    ax.set_xlabel("Calendar days to expiry")
    ax.set_ylabel("Volatility (% p.a.)")
    ax.legend(fontsize=8, loc="lower right")
    return _finish(fig, path, NSE_SOURCE + " India VIX and NIFTY: Yahoo Finance.")


def plot_greek_profiles(prof: pd.DataFrame, strike: float, spot: float, path: str | Path | None = None) -> plt.Figure:
    """Call delta, gamma, vega and theta against spot for several maturities."""
    fig, axes = plt.subplots(2, 2, figsize=(11.5, 8), sharex=True)
    specs = [
        ("call_delta", "Delta (call)", "Delta"),
        ("gamma", "Gamma", "Gamma (per index point)"),
        ("vega_per_volpt", "Vega", "Index points per 1 vol point"),
        ("call_theta_per_day", "Theta (call)", "Index points per calendar day"),
    ]
    colors = ["tab:red", "tab:blue", "tab:green", "tab:purple"]
    for ax, (col, title, ylab) in zip(axes.ravel(), specs):
        for (label, g), colr in zip(prof.groupby("label", sort=False), colors):
            ax.plot(g["spot"], g[col], color=colr, label=label)
        ax.axvline(strike, color="k", lw=0.7, ls="--")
        ax.axvline(spot, color="0.5", lw=0.7, ls=":")
        ax.set_title(title)
        ax.set_ylabel(ylab)
    for ax in axes[1]:
        ax.set_xlabel("NIFTY spot (index points)")
    axes[0, 0].legend(fontsize=8)
    fig.suptitle(f"Black-Scholes Greeks of a NIFTY {strike:,.0f} call by maturity "
                 f"(each at its own ATM IV; r = {100 * R_CONT:.2f}%, q = {100 * DIV_YIELD_FACTSHEET:.2f}%)", fontsize=11)
    return _finish(fig, path, NSE_SOURCE + f" Dashed line: strike; dotted line: spot {spot:,.2f}.")


def plot_early_exercise(boundaries: dict[str, pd.DataFrame], perpetual: float, premium: pd.DataFrame, spot: float, path: str | Path | None = None,
                        title_left: str = "", title_right: str = "") -> plt.Figure:
    """Left: American put exercise boundary S*/K vs time to expiry. Right: early-exercise premium by strike.

    Tree boundaries move in discrete node steps; each level is plotted at the mean time to expiry
    over which it holds, which turns the staircase into a smooth curve.
    """
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.8))
    for (label, b), colr in zip(boundaries.items(), ("tab:blue", "tab:orange", "tab:green")):
        # even steps share one node grid (odd steps use the interleaved grid), so use even steps only
        steps = b.iloc[:-1].iloc[::2].dropna(subset=["boundary"]).copy()
        steps["boundary_over_K"] = steps["boundary_over_K"].round(8)  # same node level, tiny float differences
        lv = steps.groupby("boundary_over_K", as_index=False)["tau"].mean().sort_values("tau")
        lv = pd.concat([pd.DataFrame({"tau": [0.0], "boundary_over_K": [b["boundary_over_K"].iloc[-1]]}), lv], ignore_index=True)
        a1.plot(lv["tau"], lv["boundary_over_K"], color=colr, label=label)
    a1.axhline(perpetual, color="k", ls="--", lw=0.8, label=f"perpetual put limit (q = 0): {perpetual:.3f}")
    a1.set_title(title_left or "American put: early-exercise boundary")
    a1.set_xlabel("Time to expiry (years)")
    a1.set_ylabel("Critical index level / strike")
    a1.legend(fontsize=8)
    a2.bar(premium["strike"], premium["early_exercise_premium"], width=150, color="tab:purple")
    a2.axvline(spot, color="0.5", ls=":", lw=1, label=f"spot {spot:,.0f}")
    a2.set_title(title_right or "Early-exercise premium (illustration)")
    a2.set_xlabel("Put strike (index points)")
    a2.set_ylabel("American - European price (index points)")
    a2.legend(fontsize=8, loc="upper left")
    return _finish(fig, path, "Source: CRR trees, author calculations. NIFTY options are European; the American values are hypothetical.")


def plot_hedging(pnl: np.ndarray, summary: pd.DataFrame, premium: float, path: str | Path | None = None, label: str = "") -> plt.Figure:
    """Left: P&L histogram of a daily-hedged short call. Right: P&L std vs number of rebalances."""
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.8))
    a1.hist(pnl, bins=80, color="tab:blue", alpha=0.8)
    a1.axvline(pnl.mean(), color="k", lw=1, label=f"mean {pnl.mean():.1f} pts")
    a1.set_title(label or "Hedging P&L, daily rebalancing")
    a1.set_xlabel("Terminal hedging P&L (index points per unit)")
    a1.set_ylabel("Number of paths")
    a1.legend(fontsize=8)
    base = summary[np.isclose(summary["sigma_real"], summary["sigma_implied"])]
    a2.loglog(base["rebalances"], base["std_pts"], "o-", color="tab:blue", label="simulated std")
    n0, s0 = base["rebalances"].iloc[0], base["std_pts"].iloc[0]
    a2.loglog(base["rebalances"], s0 * np.sqrt(n0 / base["rebalances"]), "k--", lw=0.8, label="1/sqrt(n) reference")
    a2.set_title(f"P&L std vs rebalancing frequency (premium {premium:.0f} pts)")
    a2.set_xlabel("Number of rebalances over the option's life")
    a2.set_ylabel("Std of hedging P&L (index points)")
    ticks = [t for t in (10, 15, 20, 30, 40, 60, 80, 100, 150) if base["std_pts"].min() * 0.8 <= t <= base["std_pts"].max() * 1.25]
    a2.set_yticks(ticks)
    a2.yaxis.set_major_formatter(mticker.ScalarFormatter())
    a2.yaxis.set_minor_formatter(mticker.NullFormatter())
    a2.set_xticks(base["rebalances"].tolist())
    a2.xaxis.set_major_formatter(mticker.ScalarFormatter())
    a2.xaxis.set_minor_formatter(mticker.NullFormatter())
    a2.legend(fontsize=8)
    return _finish(fig, path, "Source: GBM simulation at the 23-Nov-2026 ATM implied vol, 20,000 paths, seed 42; no transaction costs.")


def plot_vix_history(vr: pd.DataFrame, path: str | Path | None = None) -> plt.Figure:
    """India VIX against trailing 21-day realised NIFTY volatility."""
    fig, ax = plt.subplots(figsize=(11, 4.8))
    ax.plot(vr.index, vr["vix"], color="tab:red", lw=1, label="India VIX (30-day implied, %)")
    ax.plot(vr.index, vr["rv_trailing"], color="tab:blue", lw=1, alpha=0.8, label="NIFTY 21-day realised vol (%)")
    ax.set_title("India VIX vs realised NIFTY volatility, Oct-2021 to Oct-2026")
    ax.set_xlabel("Date")
    ax.set_ylabel("Volatility (% p.a.)")
    ax.legend(fontsize=8)
    return _finish(fig, path, "Source: Yahoo Finance (^INDIAVIX, ^NSEI) daily closes; author calculations.")
