"""Charts for the README, drawn with matplotlib from outputs/*.csv (run build/check_model.py first).

Output: figures/fig1 ... fig5 (PNG, 150 dpi)

Usage:  python build/make_figures.py
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from common import FIGURES, OUTPUTS

FIGURES.mkdir(exist_ok=True)
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
SOURCE = ("Source: TCS_DCF_Model.xlsx (statements from S&P Global Market Intelligence via stockanalysis.com; "
          "valuation date 30-Sep-2026; price 19-Oct-2026)")
S = dict(pd.read_csv(OUTPUTS / "dcf_summary.csv").values)
S = {k: (float(v) if k not in ("valuation_date", "price_date") else v) for k, v in S.items()}
F = pd.read_csv(OUTPUTS / "fcff_history_and_forecast.csv")
G1 = pd.read_csv(OUTPUTS / "sensitivity_value_per_share_wacc_x_g.csv", index_col=0)
G4 = pd.read_csv(OUTPUTS / "sensitivity_value_per_share_beta_x_erp.csv", index_col=0)
RV = pd.read_csv(OUTPUTS / "reverse_dcf_growth_path.csv")
PRICE, VPS = S["price_rs"], S["value_per_share_rs"]


def save(fig, name):
    fig.text(0.01, -0.03, SOURCE, fontsize=7, color="#555555")
    fig.savefig(FIGURES / name, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("saved", name)


# ---------------------------------------------------------------- fig1: FCFF history and forecast
fig, ax = plt.subplots(figsize=(10, 4.2))
hist = F["year"].str.endswith("A")
colors = np.where(hist, "#4c72b0", "#9ecae1")
x = np.arange(len(F))
ax.bar(x, F["fcff"] / 1000, color=colors)
for i, v in enumerate(F["fcff"] / 1000):
    ax.text(i, v, f"{v:,.1f}", ha="center", va="bottom", fontsize=8)
k27 = int(np.where(F["year"] == "FY2027E")[0][0])
ax.bar(k27, F.loc[k27, "counted_in_valuation"] / 1000, color="none", edgecolor="#d62728", hatch="//", lw=1)
ax.set_xticks(x, F["year"].str.replace("FY20", "FY"), fontsize=9)
ax.set_ylabel("FCFF, Rs thousand crore")
ax.set_ylim(0, F["fcff"].max() / 1000 * 1.45)
ax2 = ax.twinx()
ax2.plot(x, F["fcff_margin"] * 100, color="#333333", marker="o", ms=3, lw=1)
ax2.set_ylabel("FCFF margin, % of revenue")
ax2.set_ylim(8, 20)
ax2.spines["top"].set_visible(False)
ax.legend(handles=[Patch(color="#4c72b0", label="actual (FY2022-FY2026)"),
                   Patch(color="#9ecae1", label="forecast (FY2027E-FY2031E)"),
                   Patch(facecolor="none", edgecolor="#d62728", hatch="//",
                         label="part of FY2027E counted (0.50 of the year after 30-Sep-2026)"),
                   Line2D([], [], color="#333333", marker="o", ms=3, label="FCFF margin (right axis)")],
          frameon=False, fontsize=8, loc="upper left", ncol=2)
ax.set_title("Free cash flow to the firm: actual FY2022-FY2026 (dark) and forecast FY2027E-FY2031E (light)",
             fontsize=11)
save(fig, "fig1_fcff_history_and_forecast.png")

# ---------------------------------------------------------------- fig2: EV to equity value bridge
steps = [("PV of FCFF\nFY27E-FY31E", S["sum_pv_fcff_rs_cr"]), ("PV of terminal\nvalue", S["pv_terminal_value_rs_cr"]),
         ("Enterprise\nvalue", None), ("+ cash and\ninvestments", S["cash_rs_cr"]), ("- lease\nliabilities", -S["lease_debt_rs_cr"]),
         ("- minority\ninterests", -S["minority_interests_rs_cr"]), ("Equity\nvalue", None)]
fig, ax = plt.subplots(figsize=(10, 4.4))
run = 0.0
for i, (lab, v) in enumerate(steps):
    if v is None:
        ax.bar(i, run / 1e5, color="#4c72b0")
        ax.text(i, run / 1e5, f"{run:,.0f}", ha="center", va="bottom", fontsize=9, fontweight="bold")
        continue
    bottom = run if v >= 0 else run + v
    ax.bar(i, abs(v) / 1e5, bottom=bottom / 1e5, color="#55a868" if v >= 0 else "#c44e52")
    ax.text(i, (run + max(v, 0)) / 1e5, f"{v:+,.0f}", ha="center", va="bottom", fontsize=9)
    run += v
ax.set_xticks(range(len(steps)), [s[0] for s in steps], fontsize=9)
ax.set_ylabel("Rs lakh crore")
ax.set_ylim(0, run / 1e5 * 1.15)
ax.set_title(f"From cash flows to value per share: Rs {S['equity_value_rs_cr']:,.0f} crore / "
             f"{S['diluted_shares_cr']:.1f} crore shares = Rs {VPS:,.0f}  "
             f"(terminal value = {S['terminal_value_share_of_ev']:.0%} of EV)", fontsize=10.5)
save(fig, "fig2_ev_to_equity_bridge.png")

# ---------------------------------------------------------------- fig3: WACC x g sensitivity heat map
vals = G1.values
fig, ax = plt.subplots(figsize=(7.5, 4.6))
im = ax.imshow(vals / PRICE - 1, cmap="RdYlGn", vmin=-0.35, vmax=0.35, aspect="auto")
for i in range(5):
    for j in range(5):
        ax.text(j, i, f"{vals[i, j]:,.0f}\n({vals[i, j] / PRICE - 1:+.0%})", ha="center", va="center",
                fontsize=9, fontweight="bold" if (i, j) == (2, 2) else "normal")
ax.set_xticks(range(5), [c.replace("g=", "") for c in G1.columns])
ax.set_yticks(range(5), [f"{float(w.strip('%')):.2f}%" for w in G1.index])
ax.set_xlabel("Terminal growth g")
ax.set_ylabel("WACC")
cb = fig.colorbar(im, ax=ax, fraction=0.04)
cb.set_label("value / price - 1")
ax.set_title(f"Value per share (Rs) and gap to the Rs {PRICE:,.2f} price: {int(S['sensitivity_cells_above_price'])} "
             "of 25 cells are above it", fontsize=10)
save(fig, "fig3_sensitivity_wacc_g.png")

# ---------------------------------------------------------------- fig4: valuation range
rows = [("DCF: WACC +/-1 pp x g +/-1 pp", G1.values.min(), G1.values.max()),
        ("DCF: beta 0.6-1.0 x ERP 5-7%", G4.values.min(), G4.values.max()),
        ("Exit multiple 11.4x EV/EBITDA (cross-check)", S["value_per_share_exit_multiple_rs"],
         S["value_per_share_exit_multiple_rs"]),
        ("Analyst average target, S&P (Oct and Jul 2026)", 2390.26, 2470.0)]
fig, ax = plt.subplots(figsize=(9.5, 3.9))
for i, (lab, lo, hi) in enumerate(rows):
    if hi - lo < 1:
        ax.plot(lo, i, "D", color="#8172b2", ms=8, zorder=3)
        ax.text(lo - 25, i, f"{lo:,.0f}", va="center", ha="right", fontsize=9)
    else:
        ax.barh(i, hi - lo, left=lo, height=0.5, color="#9ecae1" if i < 2 else "#c7c7c7")
        ax.text(lo - 20, i, f"{lo:,.0f}", va="center", ha="right", fontsize=9)
        ax.text(hi + 20, i, f"{hi:,.0f}", va="center", fontsize=9)
ax.axvline(VPS, color="#4c72b0", lw=2)
box = dict(facecolor="white", edgecolor="none", pad=1.5)
ax.text(VPS, -0.95, f"DCF base Rs {VPS:,.0f}", ha="center", fontsize=9, color="#4c72b0", bbox=box)
ax.axvline(PRICE, color="#d62728", lw=2, ls="--")
ax.text(PRICE, -0.95, f"price Rs {PRICE:,.0f}", ha="center", fontsize=9, color="#d62728", bbox=box)
ax.set_yticks(range(len(rows)), [r[0] for r in rows])
ax.set_ylim(len(rows) - 0.5, -1.25)
ax.set_xlim(1450, 2950)
ax.set_xlabel("Rs per share")
ax.set_title("Where the market price sits against the DCF ranges", fontsize=11, pad=12)
fig.text(0.01, -0.06, SOURCE, fontsize=7, color="#555555")
fig.savefig(FIGURES / "fig4_valuation_range.png", dpi=150, bbox_inches="tight")
plt.close(fig)
print("saved fig4_valuation_range.png")

# ---------------------------------------------------------------- fig5: reverse DCF growth path
hist = F[F["year"].str.endswith("A")].copy()
hist_growth = hist["revenue"].pct_change().iloc[1:] * 100
fig, ax = plt.subplots(figsize=(9, 4))
yrs_h = [f"FY{y[4:6]}" for y in hist["year"].iloc[1:]]
yrs_f = [f"FY{y[4:6]}E" for y in RV["year"]]
ax.plot(yrs_h, hist_growth, color="#555555", marker="o", label="actual revenue growth")
ax.plot(yrs_f, RV["base_growth"] * 100, color="#4c72b0", marker="o", label="base case (model)")
ax.plot(yrs_f, RV["market_implied_growth"] * 100, color="#d62728", marker="o",
        label=f"needed to justify Rs {PRICE:,.0f} (+{S['reverse_dcf_extra_growth_pp'] * 100:.1f} pp every year)")
for xs, ys in ((yrs_f, RV["base_growth"] * 100), (yrs_f, RV["market_implied_growth"] * 100), (yrs_h, hist_growth)):
    for a, b in zip(xs, ys):
        ax.text(a, b + 0.5, f"{b:.1f}", ha="center", fontsize=8)
ax.set_ylabel("revenue growth, % a year")
ax.set_ylim(0, 20)
ax.legend(frameon=False, fontsize=9)
ax.set_title(f"Reverse DCF: the price needs ~{S['reverse_dcf_extra_growth_pp'] * 100:.1f} pp more growth a year, "
             f"or a WACC of {S['reverse_dcf_wacc']:.1%} (beta {S['reverse_dcf_beta']:.2f})", fontsize=10.5)
save(fig, "fig5_reverse_dcf_growth.png")
