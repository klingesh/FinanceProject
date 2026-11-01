"""Matplotlib figures for the README and notebook (150 dpi PNGs in figures/)."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter, PercentFormatter

from src.config import BENCHMARK, RF_ANNUAL, RF_ARITH, SOURCE_NOTE, STOCK_LABELS, WEIGHT_CAP

DPI = 150
STOCK_COLORS = dict(zip(STOCK_LABELS, plt.get_cmap("tab10").colors))
PORT_COLORS = {"Equal weight": "#7b3294", "Min variance": "#1f4e9c", "Max Sharpe": "#d7191c",
               "Min variance (20% cap)": "#5aa0d8", "Max Sharpe (20% cap)": "#f28e2b", "NIFTY 50": "black"}
RUPEE = "\u20b9"

plt.rcParams.update({"figure.dpi": 100, "axes.grid": True, "grid.alpha": 0.3, "axes.spines.top": False,
                     "axes.spines.right": False, "font.size": 9.5, "axes.titlesize": 11.5,
                     "axes.titleweight": "bold", "legend.fontsize": 8.5, "legend.frameon": False})


def _finish(fig: plt.Figure, path: Path | None, note: str = SOURCE_NOTE) -> plt.Figure:
    """Add the source note below the lowest tick label and save at 150 dpi if a path is given."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    y0 = min(ax.get_tightbbox(renderer).y0 for ax in fig.axes) / fig.bbox.height
    fig.text(0.01, y0 - 0.015, note, fontsize=7, color="0.4", ha="left", va="top")
    if path is not None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=DPI, bbox_inches="tight")
    return fig


def plot_cumulative_growth(growth: pd.DataFrame, path: Path | None = None) -> plt.Figure:
    """Growth of Rs 100 for each stock (thin) and NIFTY 50 (thick black), legend sorted by end value."""
    fig, ax = plt.subplots(figsize=(10, 5.6))
    end = growth.iloc[-1].sort_values(ascending=False)
    for c in end.index:
        if c == BENCHMARK:
            ax.plot(growth.index, growth[c], color="black", lw=2.4, label=f"NIFTY 50 (price index): {RUPEE}{end[c]:.0f}",
                    zorder=5)
        else:
            ax.plot(growth.index, growth[c], color=STOCK_COLORS[c], lw=1.2, label=f"{c}: {RUPEE}{end[c]:.0f}")
    ax.axhline(100, color="0.5", lw=0.8, ls=":")
    ax.set_title(f"Growth of {RUPEE}100 invested on 29-Oct-2021 (total return, dividends reinvested)")
    ax.set_ylabel(f"Value ({RUPEE})")
    ax.set_xlabel("Date")
    ax.legend(loc="upper left", ncol=2, title="Value on 30-Oct-2026")
    return _finish(fig, path, SOURCE_NOTE + ". Reliance and ITC adjusted for demergers.")


def plot_correlation_heatmap(corr: pd.DataFrame, path: Path | None = None) -> plt.Figure:
    """Annotated heatmap of the daily-return correlation matrix."""
    fig, ax = plt.subplots(figsize=(8.6, 7.2))
    im = ax.imshow(corr.to_numpy(), cmap="Blues", vmin=0, vmax=1)
    n = len(corr)
    ax.set_xticks(range(n), corr.columns, rotation=45, ha="right")
    ax.set_yticks(range(n), corr.index)
    for i in range(n):
        for j in range(n):
            v = corr.iat[i, j]
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=8, color="white" if v > 0.6 else "black")
    ax.grid(False)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="Correlation of daily returns")
    ax.set_title("Correlation of daily returns, Nov-2021 to Oct-2026")
    return _finish(fig, path)


def plot_risk_return(stats: pd.DataFrame, path: Path | None = None) -> plt.Figure:
    """Annualised volatility vs. annualised mean return; labels show the daily beta."""
    fig, ax = plt.subplots(figsize=(9, 6))
    st = stats.loc[STOCK_LABELS]
    sc = ax.scatter(st["ann_volatility"] * 100, st["ann_mean_return"] * 100, c=st["beta_daily"], cmap="coolwarm",
                    vmin=0.4, vmax=1.4, s=90, edgecolor="black", zorder=3)
    xmax = st["ann_volatility"].max() * 100
    for lab, r in st.iterrows():
        x, y = r["ann_volatility"] * 100, r["ann_mean_return"] * 100
        right_edge = x > xmax - 1.5   # put the label on the left for the right-most points
        ax.annotate(f"{lab} (\u03b2 {r['beta_daily']:.2f})", (x, y), xytext=(-6 if right_edge else 6, 5),
                    textcoords="offset points", fontsize=8.5, ha="right" if right_edge else "left")
    nb = stats.loc[BENCHMARK]
    ax.scatter(nb["ann_volatility"] * 100, nb["ann_mean_return"] * 100, marker="X", s=130, color="black", zorder=4)
    ax.annotate("NIFTY 50 (\u03b2 1.00)", (nb["ann_volatility"] * 100, nb["ann_mean_return"] * 100),
                xytext=(8, 6), textcoords="offset points", fontsize=8.5, fontweight="bold")
    ax.set_xlim(nb["ann_volatility"] * 100 - 1.0, xmax + 1.0)
    ax.axhline(RF_ARITH * 100, color="0.4", ls="--", lw=1)
    ax.text(xmax + 0.9, RF_ARITH * 100 - 0.9, f"risk-free {RF_ANNUAL:.2%} (91-day T-bill)", fontsize=8,
            color="0.3", ha="right")
    fig.colorbar(sc, ax=ax, label="Beta vs NIFTY 50 (daily excess returns)")
    ax.set_xlabel("Annualised volatility (%)")
    ax.set_ylabel("Annualised mean return (%)")
    ax.set_title("Risk and return of each stock, Nov-2021 to Oct-2026")
    return _finish(fig, path)


def plot_efficient_frontier(frontier: pd.DataFrame, mc: pd.DataFrame, points: dict[str, tuple[float, float]],
                            stocks: pd.DataFrame, tangency_sharpe: float, rf: float = RF_ARITH,
                            path: Path | None = None, title: str | None = None) -> plt.Figure:
    """Monte Carlo cloud, both frontiers, the CML and markers for portfolios, NIFTY and stocks.

    ``points`` maps a portfolio name to its (volatility, return); ``stocks`` has columns
    ann_volatility and ann_mean_return indexed by stock label.
    """
    fig, ax = plt.subplots(figsize=(10.5, 7))
    sc = ax.scatter(mc["volatility"] * 100, mc["return"] * 100, c=mc["sharpe"], cmap="viridis", s=3, alpha=0.5,
                    rasterized=True, zorder=1)
    fig.colorbar(sc, ax=ax, label="Sharpe ratio of random portfolio", fraction=0.04, pad=0.02)
    styles = {"long-only": ("#1f4e9c", "-"), "long-only, 20% cap": ("#f28e2b", "--")}
    for name, (col, ls) in styles.items():
        f = frontier[frontier["frontier"] == name]
        eff = f[f["branch"] == "efficient"].sort_values("return")
        ineff = f[f["branch"] == "inefficient"].sort_values("return")
        lab = "Efficient frontier, long-only" if name == "long-only" else "Efficient frontier, max 20% per stock"
        ax.plot(eff["volatility"] * 100, eff["return"] * 100, color=col, lw=2.2, ls=ls, label=lab, zorder=3)
        lower = pd.concat([ineff, eff.iloc[:1]]).sort_values("return")
        ax.plot(lower["volatility"] * 100, lower["return"] * 100, color=col, lw=1, ls=":", zorder=3)
    xmax = max(stocks["ann_volatility"].max() * 100 + 3, 35)
    xs = np.linspace(0, xmax, 50)
    ax.plot(xs, (rf + tangency_sharpe * xs / 100) * 100, color="#d7191c", lw=1.4, ls="-.",
            label=f"Capital market line (Sharpe {tangency_sharpe:.2f})", zorder=2)
    ax.scatter([0], [rf * 100], color="#d7191c", s=25, zorder=4)
    ax.annotate(f"rf {rf:.2%}", (0, rf * 100), xytext=(4, -12), textcoords="offset points", fontsize=8)
    markers = {"Min variance": ("D", 70), "Max Sharpe": ("*", 300), "Min variance (20% cap)": ("D", 55),
               "Max Sharpe (20% cap)": ("*", 220), "Equal weight": ("s", 70), "NIFTY 50": ("X", 120)}
    for name, (vol, ret) in points.items():
        mk, size = markers.get(name, ("o", 60))
        ax.scatter(vol * 100, ret * 100, marker=mk, s=size, color=PORT_COLORS.get(name, "grey"),
                   edgecolor="white", linewidth=0.8, zorder=6, label=name)
    ax.scatter(stocks["ann_volatility"] * 100, stocks["ann_mean_return"] * 100, color="0.25", s=22, zorder=5)
    for lab, r in stocks.iterrows():
        ax.annotate(lab, (r["ann_volatility"] * 100, r["ann_mean_return"] * 100), xytext=(4, 3),
                    textcoords="offset points", fontsize=7.5, color="0.2")
    ax.set_xlim(0, xmax)
    ymin = min(stocks["ann_mean_return"].min() * 100, 0) - 2
    ax.set_ylim(ymin, stocks["ann_mean_return"].max() * 100 + 6)
    ax.set_xlabel("Annualised volatility (%)")
    ax.set_ylabel("Annualised mean return (%)")
    ax.set_title(title or "Efficient frontier of 10 NSE large caps, Nov-2021 to Oct-2026")
    ax.legend(loc="upper left", fontsize=8)
    return _finish(fig, path, SOURCE_NOTE + ". 20,000 random portfolios (Dirichlet weights, seed 42).")


def plot_weights(weights: pd.DataFrame, path: Path | None = None) -> plt.Figure:
    """Side-by-side bars: min variance and max Sharpe, each unconstrained vs. 20% cap."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), sharey=True)
    pairs = [("Min variance", "min_variance", "min_variance_cap20"), ("Max Sharpe", "max_sharpe", "max_sharpe_cap20")]
    x = np.arange(len(weights))
    for ax, (title, a, b) in zip(axes, pairs):
        ax.bar(x - 0.2, weights[a] * 100, width=0.4, color=PORT_COLORS[title], label="Long-only")
        ax.bar(x + 0.2, weights[b] * 100, width=0.4, color=PORT_COLORS[f"{title} (20% cap)"], label="Max 20% per stock")
        for xi, (va, vb) in enumerate(zip(weights[a], weights[b])):
            if va > 0.005:
                ax.text(xi - 0.2, va * 100 + 0.8, f"{va * 100:.0f}", ha="center", fontsize=7)
            if vb > 0.005:
                ax.text(xi + 0.2, vb * 100 + 0.8, f"{vb * 100:.0f}", ha="center", fontsize=7)
        ax.axhline(WEIGHT_CAP * 100, color="0.3", ls="--", lw=0.9)
        ax.set_xticks(x, weights.index, rotation=45, ha="right")
        ax.set_title(f"{title} portfolio weights")
        ax.yaxis.set_major_formatter(PercentFormatter(decimals=0))
        ax.legend(loc="upper right")
    axes[0].set_ylabel("Weight (%)")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    return _finish(fig, path, SOURCE_NOTE + ". Weights estimated on Nov-2021 to Oct-2026 daily returns.")


def plot_drawdowns(drawdowns: pd.DataFrame, path: Path | None = None) -> plt.Figure:
    """Drawdown from the running peak for selected portfolios and NIFTY 50."""
    fig, ax = plt.subplots(figsize=(10, 4.8))
    for c in drawdowns.columns:
        label = f"{c} (max {drawdowns[c].min():.1%})"
        if c == "NIFTY 50":
            ax.fill_between(drawdowns.index, drawdowns[c] * 100, 0, color="0.75", alpha=0.7, lw=0, label=label,
                            zorder=1)
        else:
            ax.plot(drawdowns.index, drawdowns[c] * 100, color=PORT_COLORS.get(c, None), lw=1.2, label=label,
                    zorder=3)
    ax.yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax.set_ylabel("Drawdown from previous peak (%)")
    ax.set_xlabel("Date")
    ax.set_title("Drawdowns, Nov-2021 to Oct-2026 (weights from the full sample)")
    ax.legend(loc="lower left")
    return _finish(fig, path)


def plot_oos_growth(growth: pd.DataFrame, path: Path | None = None) -> plt.Figure:
    """Growth of Rs 100 over the hold-out period for weights estimated on Nov-2021 to Oct-2024."""
    fig, ax = plt.subplots(figsize=(10, 5))
    end = growth.iloc[-1].sort_values(ascending=False)
    for c in end.index:
        ax.plot(growth.index, growth[c], color=PORT_COLORS.get(c), lw=2.2 if c == "NIFTY 50" else 1.6,
                label=f"{c}: {RUPEE}{end[c]:.0f}")
    ax.axhline(100, color="0.5", lw=0.8, ls=":")
    ax.set_ylabel(f"Value ({RUPEE})")
    ax.set_xlabel("Date")
    ax.set_title(f"Out-of-sample: growth of {RUPEE}100 from 31-Oct-2024\n"
                 "(weights fitted on Nov-2021 to Oct-2024 returns, then held to 30-Oct-2026)")
    ax.legend(loc="upper left", title="Value on 30-Oct-2026")
    return _finish(fig, path, SOURCE_NOTE + ". Constant weights, rebalanced daily; NIFTY 50 is a price index.")
