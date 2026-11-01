"""Figures for the README and notebook (matplotlib, 150 dpi PNG).

Each function draws one figure, saves it when `path` is given and returns the Figure, so the
notebook can display it inline and run_all.py can close it after saving.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import MultipleLocator, PercentFormatter
from scipy import stats

from . import config as cfg

SOURCE = ("Source: Yahoo Finance (yfinance) daily closes, patched with NSE bhavcopy closes; "
          "author's calculations. Data 1-Nov-2021 to 30-Oct-2026.")
ETF_COLORS = {"NIFTYBEES": "#1f77b4", "JUNIORBEES": "#17becf", "BANKBEES": "#9467bd",
              "MON100": "#ff7f0e", "GOLDBEES": "#c9a227", "SETF10GILT": "#2ca02c", "Portfolio": "#111111"}
METHOD_COLORS = ["#1f77b4", "#6baed6", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]
LAKH = 1e5


def _finish(fig: plt.Figure, path: Path | None, note: str = SOURCE) -> plt.Figure:
    fig.text(0.01, 0.005, note, fontsize=7, color="#555555", ha="left", va="bottom")
    if path is not None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=150, bbox_inches="tight")
    return fig


# ------------------------------------------------------------------ data overview
def plot_growth(prices: pd.DataFrame, port_ret: pd.Series, path: Path | None = None) -> plt.Figure:
    """Growth of Rs 100 for each ETF and the constant-weight portfolio."""
    p = prices[prices.index >= port_ret.index[0] - pd.Timedelta(days=7)]
    p = p[p.index <= port_ret.index[-1]]
    base = p.loc[:port_ret.index[0]].iloc[-2]
    fig, ax = plt.subplots(figsize=(10, 5))
    for t in cfg.TICKERS:
        lab = cfg.HOLDINGS[t][0]
        s = 100 * p[t] / base[t]
        ax.plot(s.index, s, lw=1.2, color=ETF_COLORS[lab], label=lab)
    g = 100 * (1 + port_ret).cumprod()
    ax.plot(g.index, g, lw=2.2, color="black", label="Portfolio (constant weights)")
    ax.set_title("Growth of Rs 100 invested on 29-Oct-2021")
    ax.set_ylabel("Value (Rs, start = 100)")
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b-%Y"))
    ax.grid(alpha=0.3)
    ax.legend(ncol=4, fontsize=8, loc="upper left")
    return _finish(fig, path)


def plot_rolling_vol(returns: pd.DataFrame, port_ret: pd.Series, sigma_ewma: pd.Series,
                     path: Path | None = None) -> plt.Figure:
    """Rolling 250-day annualised volatility of each ETF and of the portfolio."""
    ann = np.sqrt(cfg.TRADING_DAYS_PER_YEAR)
    win = cfg.RECENT_WINDOW
    fig, axes = plt.subplots(2, 1, figsize=(10, 7.5), sharex=True)
    for t in cfg.TICKERS:
        lab = cfg.HOLDINGS[t][0]
        axes[0].plot(returns.index, returns[t].rolling(win).std() * ann, color=ETF_COLORS[lab], lw=1.3, label=lab)
    axes[0].set_title("Rolling 1-year (250-day) volatility of each ETF")
    axes[0].set_ylabel("Annualised volatility")
    axes[0].yaxis.set_major_locator(MultipleLocator(0.05))
    axes[0].yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    axes[0].legend(ncol=3, fontsize=8, loc="upper left")
    axes[0].grid(alpha=0.3)
    axes[1].plot(port_ret.index, port_ret.rolling(win).std() * ann, color="black", lw=1.8,
                 label="Portfolio, rolling 250-day")
    axes[1].plot(sigma_ewma.index, sigma_ewma * ann, color="#d62728", lw=1.0, alpha=0.8,
                 label="Portfolio, EWMA (lambda = 0.94)")
    axes[1].set_title("Portfolio volatility: rolling 1-year vs EWMA")
    axes[1].set_ylabel("Annualised volatility")
    axes[1].yaxis.set_major_locator(MultipleLocator(0.02))
    axes[1].yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    axes[1].legend(fontsize=8, loc="upper left")
    axes[1].grid(alpha=0.3)
    axes[1].xaxis.set_major_locator(mdates.YearLocator())
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%b-%Y"))
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    return _finish(fig, path)


def plot_correlation(corr_full: pd.DataFrame, corr_recent: pd.DataFrame, titles: tuple[str, str],
                     path: Path | None = None) -> plt.Figure:
    """Side-by-side heatmaps: full-window and last-250-day correlation of daily returns."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 6.2))
    for ax, c, title in [(axes[0], corr_full, titles[0]), (axes[1], corr_recent, titles[1])]:
        im = ax.imshow(c.to_numpy(), cmap="RdBu_r", vmin=-1, vmax=1)
        ax.set_xticks(range(len(c)), c.columns, rotation=45, ha="right", fontsize=8)
        ax.set_yticks(range(len(c)), c.index, fontsize=8)
        for i in range(len(c)):
            for j in range(len(c)):
                v = c.iloc[i, j]
                ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=8,
                        color="white" if abs(v) > 0.6 else "black")
        ax.set_title(title, fontsize=10)
    fig.subplots_adjust(left=0.08, right=0.87, bottom=0.2, top=0.86, wspace=0.3)
    cax = fig.add_axes((0.89, 0.25, 0.015, 0.55))
    fig.colorbar(im, cax=cax, label="Correlation of daily returns")
    fig.suptitle("Correlation matrix of daily ETF returns", fontsize=12)
    return _finish(fig, path)


# ------------------------------------------------------------------ VaR results
def plot_return_histogram(port_ret: pd.Series, value: float, lines_99: dict[str, tuple[float, float]],
                          path: Path | None = None) -> plt.Figure:
    """Histogram of daily P&L with 99% VaR (solid) and ES (dashed) of every method."""
    pnl = port_ret * value / LAKH
    sd = pnl.std()
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), gridspec_kw={"width_ratios": [1.15, 1]})
    ax = axes[0]
    ax.hist(pnl, bins=90, color="#9ecae1", edgecolor="white", lw=0.3, density=True, label="Daily P&L")
    x = np.linspace(pnl.min(), pnl.max(), 400)
    ax.plot(x, stats.norm.pdf(x, 0, sd), color="#ff7f0e", lw=1.5, label="Normal, same sigma")
    hv, he = lines_99["Historical (full window)"]
    ax.axvline(-hv * value / LAKH, color="#1f77b4", lw=1.6, label="99% VaR, historical")
    ax.axvline(-he * value / LAKH, color="#1f77b4", lw=1.6, ls="--", label="99% ES, historical")
    ax.set_title(f"Daily portfolio P&L, {pnl.index[0]:%d-%b-%Y} to {pnl.index[-1]:%d-%b-%Y} ({len(pnl):,} days)")
    ax.set_xlabel("Daily P&L on a Rs 1 crore portfolio (Rs lakh)")
    ax.set_ylabel("Density")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    ax = axes[1]
    tail = pnl[pnl < -0.5]
    ax.hist(tail, bins=40, color="#c6dbef", edgecolor="white", lw=0.3, label="Days with a loss above Rs 0.5 lakh")
    ymax = ax.get_ylim()[1]
    for (name, (v, e)), col in zip(lines_99.items(), METHOD_COLORS):
        ax.axvline(-v * value / LAKH, color=col, lw=1.6,
                   label=f"{name}: VaR {v * value / LAKH:.2f}, ES {e * value / LAKH:.2f}")
        ax.axvline(-e * value / LAKH, color=col, lw=1.2, ls="--")
    ax.set_ylim(0, ymax * 1.6)
    ax.set_title("Left tail: 99% VaR (solid) and ES (dashed) by method")
    ax.set_xlabel("Daily P&L (Rs lakh)")
    ax.set_ylabel("Number of days")
    ax.legend(fontsize=7, loc="upper left", title="1-day 99%, Rs lakh", title_fontsize=7, framealpha=0.95)
    ax.grid(alpha=0.3)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    return _finish(fig, path)


def plot_var_comparison(summary: pd.DataFrame, path: Path | None = None) -> plt.Figure:
    """Grouped bars of 1-day VaR and ES at 95% and 99% for every method (Rs lakh)."""
    s = summary[summary["horizon_days"] == 1]
    methods = list(dict.fromkeys(s["method"]))
    combos = [(0.95, "var_inr", "VaR 95%", "#9ecae1"), (0.95, "es_inr", "ES 95%", "#3182bd"),
              (0.99, "var_inr", "VaR 99%", "#fdae6b"), (0.99, "es_inr", "ES 99%", "#e6550d")]
    fig, ax = plt.subplots(figsize=(11, 6))
    h = 0.2
    y = np.arange(len(methods))
    for k, (a, col, lab, color) in enumerate(combos):
        vals = [s[(s["method"] == m) & (s["confidence"] == a)][col].iloc[0] / LAKH for m in methods]
        bars = ax.barh(y + (k - 1.5) * h, vals, height=h, color=color, label=lab)
        for b, v in zip(bars, vals):
            ax.text(v + 0.02, b.get_y() + h / 2, f"{v:.2f}", va="center", fontsize=7)
    ax.set_yticks(y, methods, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("1-day loss on a Rs 1 crore portfolio (Rs lakh; Rs 1 lakh = 1% of value)")
    ax.set_title("1-day VaR and Expected Shortfall by method")
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    return _finish(fig, path)


def plot_mc_convergence(nested: dict[str, pd.Series], bands: dict[str, pd.DataFrame],
                        analytic: dict[str, float], value: float, path: Path | None = None) -> plt.Figure:
    """99% Monte Carlo VaR against the number of simulations, with 95% sampling bands."""
    fig, ax = plt.subplots(figsize=(10, 5.5))
    colors = {"Normal": "#9467bd", "Student-t": "#8c564b"}
    for name, ser in nested.items():
        c = colors[name]
        b = bands[name]
        ax.fill_between(b.index, b["p2_5"] * value / LAKH, b["p97_5"] * value / LAKH, color=c, alpha=0.15,
                        label=f"{name}: 95% range of 200 independent runs")
        ax.plot(ser.index, ser * value / LAKH, color=c, lw=1.8, marker="o", ms=3,
                label=f"{name}: first n of the seed-42 run")
        ax.axhline(analytic[name] * value / LAKH, color=c, ls="--", lw=1.2,
                   label=f"{name}: analytic value {analytic[name] * value / LAKH:.3f}")
    ax.set_xscale("log")
    ax.set_xlabel("Number of simulated 1-day scenarios (log scale)")
    ax.set_ylabel("1-day 99% VaR (Rs lakh)")
    ax.set_title("Monte Carlo convergence of the 1-day 99% VaR")
    ax.legend(fontsize=8, ncol=2, loc="upper right")
    ax.grid(alpha=0.3, which="both")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    return _finish(fig, path)


def plot_component_var(decomp: pd.DataFrame, port_var: float, path: Path | None = None) -> plt.Figure:
    """Weights vs VaR contributions, and standalone vs component VaR per ETF."""
    labels = list(decomp.index)
    y = np.arange(len(labels))
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    ax = axes[0]
    ax.barh(y - 0.2, 100 * decomp["weight"], height=0.4, color="#bdbdbd", label="Portfolio weight")
    ax.barh(y + 0.2, decomp["contribution_pct"], height=0.4,
            color=[ETF_COLORS[lab] for lab in labels], label="Share of 99% VaR")
    for i, (wv, cv) in enumerate(zip(100 * decomp["weight"], decomp["contribution_pct"])):
        ax.text(max(wv, 0) + 0.5, i - 0.2, f"{wv:.0f}%", va="center", fontsize=8)
        ax.text(max(cv, 0) + 0.5, i + 0.2, f"{cv:.1f}%", va="center", fontsize=8)
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.axvline(0, color="black", lw=0.8)
    ax.set_xlim(min(0.0, 1.2 * decomp["contribution_pct"].min()),
                1.18 * max(100 * decomp["weight"].max(), decomp["contribution_pct"].max()))
    ax.set_xlabel("Percent")
    ax.set_title("Weight vs share of portfolio VaR (Euler allocation)")
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(axis="x", alpha=0.3)
    ax = axes[1]
    ax.barh(y - 0.2, decomp["standalone_var_inr"] / LAKH, height=0.4, color="#bdbdbd", label="Standalone VaR")
    ax.barh(y + 0.2, decomp["component_var_inr"] / LAKH, height=0.4,
            color=[ETF_COLORS[lab] for lab in labels], label="Component VaR")
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.axvline(0, color="black", lw=0.8)
    undiv = decomp["standalone_var_inr"].sum() / LAKH
    ax.set_title(f"Standalone vs component 99% VaR (Rs lakh)\nsum of standalone {undiv:.2f}, "
                 f"portfolio {port_var / LAKH:.2f}, diversification benefit {undiv - port_var / LAKH:.2f}",
                 fontsize=10)
    ax.set_xlabel("1-day 99% VaR (Rs lakh)")
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(axis="x", alpha=0.3)
    fig.suptitle("Parametric normal 1-day 99% VaR decomposition (full-window sample covariance)", fontsize=11)
    fig.tight_layout(rect=(0, 0.03, 1, 0.97))
    return _finish(fig, path)


def plot_backtest(fc: pd.DataFrame, value: float, models: dict[str, str], path: Path | None = None) -> plt.Figure:
    """Daily P&L against the negative of 95% and 99% VaR forecasts, exceptions marked."""
    fig, axes = plt.subplots(len(models), 1, figsize=(11, 3.1 * len(models)), sharex=True)
    pnl = fc["ret"] * value / LAKH
    for ax, (key, name) in zip(np.atleast_1d(axes), models.items()):
        ax.bar(pnl.index, pnl, width=1.0, color="#bdbdbd", label="Daily P&L")
        for k, col in [(95, "#fd8d3c"), (99, "#cb181d")]:
            v = -fc[f"{key}_{k}"] * value / LAKH
            ax.plot(v.index, v, color=col, lw=1.0, label=f"-VaR {k}%")
            exc = pnl < v
            ax.scatter(pnl.index[exc], pnl[exc], s=14 if k == 99 else 8, color=col, zorder=3,
                       marker="x" if k == 99 else "o",
                       label=f"{k}% exceptions: {int(exc.sum())} of {len(exc)}")
        ax.set_title(name, fontsize=10)
        ax.set_ylabel("Rs lakh")
        ax.legend(fontsize=7, ncol=5, loc="lower left")
        ax.grid(alpha=0.3)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b-%Y"))
    fig.suptitle("Backtest: one-day-ahead VaR from a rolling 250-day window vs realised P&L", fontsize=12)
    fig.tight_layout(rect=(0, 0.02, 1, 0.98))
    return _finish(fig, path)
