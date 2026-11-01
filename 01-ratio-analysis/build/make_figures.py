"""Charts for the README, drawn with matplotlib from outputs/*.csv (run build/check_workbook.py first).

The workbook's own native Excel charts are exported separately by build/export_excel_charts.py.
Output: figures/fig1 ... fig5 (PNG, 150 dpi)

Usage:  python build/make_figures.py
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

from common import COMPANIES, FIGURES, OUTPUTS

FIGURES.mkdir(exist_ok=True)
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
SHORT = [c[1] for c in COMPANIES]
NAMES = {c[0]: c[1] for c in COMPANIES}
COLORS = {"Hero": "#1f77b4", "Bajaj": "#ff7f0e", "TVS": "#2ca02c", "Eicher": "#d62728"}
SOURCE = "Source: Screener.in Data Sheet exports (15-Oct-2026); ratios from TwoWheeler_Peer_Benchmark_FY2022-26.xlsx"

ratios = pd.read_csv(OUTPUTS / "ratios_FY2022-FY2026.csv")
ratios["short"] = ratios["company"].map(NAMES)
ratios["fy"] = ratios["fiscal_year"].str[2:].astype(int)


def value(key: str, short: str, fy: int = 2026) -> float:
    s = ratios[(ratios.ratio == key) & (ratios.short == short) & (ratios.fy == fy)]["value"]
    return float(s.iloc[0])


def save(fig, name: str):
    fig.text(0.01, -0.04, SOURCE, fontsize=7, color="#555555")
    fig.savefig(FIGURES / name, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("saved", name)


# ---------------------------------------------------------------- fig1: FY2026 scorecard heat map
ROWS = [  # key, label, scale, decimals, higher_is_better (None = not ranked)
    ("gross_margin", "Gross margin %", 100, 1, True),
    ("ebitda_margin", "EBITDA margin % (ex other income)", 100, 1, True),
    ("net_margin", "Net profit margin %", 100, 1, True),
    ("roe", "ROE %", 100, 1, True),
    ("roe_ex_oneoff", "ROE ex one-off gains % (approx.)", 100, 1, True),
    ("roa", "ROA %", 100, 1, True),
    ("roce_proxy", "ROCE proxy % (ex other income)", 100, 1, True),
    ("int_cover_ebit", "Interest cover (EBIT / interest) x", 1, 0, True),
    ("asset_turnover", "Asset turnover x", 1, 2, True),
    ("de_proxy", "Debt / equity x (ex leases)", 1, 2, False),
    ("inventory_days", "Inventory days", 1, 1, False),
    ("oi_share_pbt", "Other income as % of PBT", 100, 1, None),
]
vals = np.array([[value(k, s) * sc for s in SHORT] for k, _, sc, _, _ in ROWS])
med = np.median(vals, axis=1)
rank = np.full(vals.shape, np.nan)
for i, (_, _, _, _, hb) in enumerate(ROWS):
    if hb is None:
        continue
    order = np.argsort(-vals[i] if hb else vals[i])
    rank[i, order] = np.arange(1, 5)
cmap = LinearSegmentedColormap.from_list("rank", ["#1a9850", "#a6d96a", "#fdae61", "#d73027"])
fig, ax = plt.subplots(figsize=(9.5, 6.4))
shown = np.where(np.isnan(rank), 2.5, rank)
ax.imshow(shown, cmap=cmap, vmin=1, vmax=4, aspect="auto", alpha=0.75)
for i, (_, _, _, dp, hb) in enumerate(ROWS):
    for j in range(4):
        txt = f"{vals[i, j]:,.{dp}f}" + ("" if hb is None else f"  (#{int(rank[i, j])})")
        ax.text(j, i, txt, ha="center", va="center", fontsize=9,
                color="#222222" if hb is not None else "#444444")
    ax.text(4, i, f"{med[i]:,.{dp}f}", ha="center", va="center", fontsize=9)
ax.add_patch(plt.Rectangle((3.5, -0.5), 1, len(ROWS), color="#eeeeee", zorder=0))
for i, (_, _, _, _, hb) in enumerate(ROWS):
    if hb is None:
        for j in range(4):
            ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, color="#e0e0e0", zorder=1))
ax.set_xticks(range(5), SHORT + ["Median"])
ax.set_yticks(range(len(ROWS)), [r[1] for r in ROWS])
ax.xaxis.tick_top()
ax.set_xlim(-0.5, 4.5)
ax.tick_params(length=0)
for s in ax.spines.values():
    s.set_visible(False)
ax.set_title("FY2026 scorecard: rank among the four (#1 = best; green = better, red = worse)", pad=28, fontsize=11)
save(fig, "fig1_fy2026_scorecard.png")

# ---------------------------------------------------------------- fig2: DuPont split, FY2026
fig, axes = plt.subplots(1, 4, figsize=(12, 3.8))
parts = [("dupont_net_margin", "Net profit margin (%)", 100, "{:.1f}%"),
         ("dupont_asset_turnover", "Asset turnover (x)", 1, "{:.2f}x"),
         ("dupont_equity_multiplier", "Equity multiplier (x)", 1, "{:.2f}x"),
         ("roe", "ROE = product of the three (%)", 100, "{:.1f}%")]
for ax, (key, title, sc, fmt) in zip(axes, parts):
    v = [value(key, s) * sc for s in SHORT]
    bars = ax.bar(SHORT, v, color=[COLORS[s] for s in SHORT])
    for b, x in zip(bars, v):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height(), fmt.format(x), ha="center", va="bottom", fontsize=9)
    ax.set_title(title, fontsize=10)
    ax.set_ylim(0, max(v) * 1.2)
    ax.tick_params(axis="x", labelsize=9)
fig.suptitle("DuPont split of FY2026 ROE: same ROE, different engines", fontsize=12, y=1.03)
fig.tight_layout()
save(fig, "fig2_dupont_fy2026.png")

# ---------------------------------------------------------------- fig3: ROE and ROCE trends
fig, axes = plt.subplots(1, 2, figsize=(11, 4))
for ax, (key, title) in zip(axes, [("roe", "ROE (profit / average equity), %"),
                                   ("roce_proxy", "ROCE proxy (EBIT ex other income / avg equity + borrowings), %")]):
    for s in SHORT:
        sub = ratios[(ratios.ratio == key) & (ratios.short == s)].sort_values("fy")
        ax.plot(sub.fy, sub.value * 100, marker="o", color=COLORS[s], label=s)
        ax.annotate(f"{sub.value.iloc[-1] * 100:.1f}", (sub.fy.iloc[-1], sub.value.iloc[-1] * 100),
                    textcoords="offset points", xytext=(6, -3), fontsize=8, color=COLORS[s])
    ax.set_xticks(range(2022, 2027), [f"FY{y}" for y in range(2022, 2027)])
    ax.set_title(title, fontsize=10)
    ax.set_ylabel("%")
    ax.grid(axis="y", alpha=0.3)
axes[0].legend(frameon=False, fontsize=9)
fig.suptitle("Returns FY2022-FY2026: all four ended higher; Hero's ROCE rose the most (15.8% to 29.3%)",
             fontsize=12, y=1.02)
fig.tight_layout()
save(fig, "fig3_roe_roce_trends.png")

# ---------------------------------------------------------------- fig4: ROCE vs leverage, FY2026 (separate axes)
fig, axes = plt.subplots(1, 3, figsize=(12, 3.8))
for ax, (key, title, sc, fmt) in zip(axes, [("roce_proxy", "ROCE proxy (%)", 100, "{:.1f}%"),
                                            ("de_proxy", "Debt / equity (x, ex leases)", 1, "{:.2f}x"),
                                            ("roa", "ROA (%)", 100, "{:.1f}%")]):
    v = [value(key, s) * sc for s in SHORT]
    bars = ax.bar(SHORT, v, color=[COLORS[s] for s in SHORT])
    for b, x in zip(bars, v):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height(), fmt.format(x), ha="center", va="bottom", fontsize=9)
    ax.set_title(title, fontsize=10)
    ax.set_ylim(0, max(v) * 1.2)
fig.suptitle("FY2026: TVS's high ROE comes with 3.4x debt/equity (its finance arm) and the lowest ROA",
             fontsize=12, y=1.03)
fig.tight_layout()
save(fig, "fig4_roce_leverage_roa_fy2026.png")

# ---------------------------------------------------------------- fig5: effect of other income on margins, FY2026
fig, ax = plt.subplots(figsize=(8.5, 4))
x = np.arange(4)
ex = [value("ebitda_margin", s) * 100 for s in SHORT]
inc = [value("ebitda_margin_incl_oi", s) * 100 for s in SHORT]
oi = [value("oi_share_pbt", s) * 100 for s in SHORT]
ax.bar(x - 0.2, ex, 0.4, color="#4c72b0", label="EBITDA margin excluding other income (used in the ranking)")
ax.bar(x + 0.2, inc, 0.4, color="#c0c0c0", label="EBITDA margin including other income")
for i in range(4):
    ax.text(x[i] - 0.2, ex[i], f"{ex[i]:.1f}", ha="center", va="bottom", fontsize=9)
    ax.text(x[i] + 0.2, inc[i], f"{inc[i]:.1f}", ha="center", va="bottom", fontsize=9)
ax.set_xticks(x, [f"{s}\nOI = {o:.1f}% of PBT" for s, o in zip(SHORT, oi)], fontsize=8.5)
ax.set_ylabel("% of revenue")
ax.set_ylim(0, max(inc) * 1.25)
ax.legend(frameon=False, fontsize=8, loc="upper left")
ax.set_title("FY2026 margins with and without treasury income: Eicher gains the most", fontsize=11)
save(fig, "fig5_other_income_effect_fy2026.png")
