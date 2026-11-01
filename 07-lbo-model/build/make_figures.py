"""Draw the README charts (figures/*.png) from the CSVs that finalise_with_excel.py exports to outputs/.

Charts (PNG, 150 dpi):
  01_revenue_ebitda.png         revenue, EBITDA and EBITDA margin: CY2021-CY2025 actual, CY2026E-CY2031E base case
  02_debt_paydown.png           debt outstanding by tranche and cash on hand, close to exit (base case)
  03_leverage_path.png          net debt / EBITDA and EBITDA / cash interest against the covenants, three cases
  04_returns_attribution.png    waterfall from sponsor equity invested to sponsor exit proceeds (base case)
  05_irr_heatmap.png            sponsor IRR: offer premium x exit multiple (Excel data table)
  06_irr_heatmap_operating.png  sponsor IRR: EBITDA margin change x revenue growth change (Excel data table)

Run:  python build/make_figures.py   (after build_lbo_model.py and finalise_with_excel.py)
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import Patch, Rectangle  # noqa: E402
from matplotlib.ticker import NullFormatter  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
FIG = ROOT / "figures"
FIG.mkdir(exist_ok=True)
DPI = 150
SOURCE = ("Source: author's model (Castrol_India_LBO_Model.xlsx) built from Castrol India filings and market data "
          "to the 30-Oct-2026 close. Educational project, not investment advice.")
C_TLA, C_TLB, C_MZ, C_RCF = "#1f4e79", "#5b9bd5", "#c55a11", "#7f7f7f"
C_POS, C_NEG, C_TOT = "#548235", "#c00000", "#1f4e79"
SCEN_STYLE = {"Base": ("#1f4e79", "-"), "Upside": ("#548235", "--"), "Downside": ("#c00000", "-.")}
HURDLE = 0.20


def note(fig: plt.Figure, text: str = SOURCE) -> None:
    """Add the source note at the bottom-left of a figure."""
    fig.text(0.01, 0.01, text, fontsize=7, color="#555555", ha="left", va="bottom", wrap=True)


def save(fig: plt.Figure, name: str) -> None:
    fig.savefig(FIG / name, dpi=DPI)
    plt.close(fig)
    print(f"saved figures/{name}")


def by_item(path: Path) -> pd.DataFrame:
    return pd.read_csv(path).set_index("item")


# ----------------------------------------------------------------------------- 1. revenue and EBITDA
def fig_revenue_ebitda() -> None:
    hist = by_item(OUT / "historical_summary.csv")
    fc = by_item(OUT / "base_operating_model.csv")
    hy = ["CY2021", "CY2022", "CY2023", "CY2024", "CY2025"]
    fy = list(fc.columns)
    years = hy + fy
    rev = [hist.loc["revenue_cr", y] for y in hy] + [fc.loc["revenue_cr", y] for y in fy]
    ebitda = [hist.loc["ebitda_cr", y] for y in hy] + [fc.loc["ebitda_cr", y] for y in fy]
    margin = [hist.loc["ebitda_margin", y] for y in hy] + [fc.loc["ebitda_margin", y] for y in fy]
    x = np.arange(len(years))
    actual = np.array([y in hy for y in years])
    fig, ax = plt.subplots(figsize=(11, 5.6))
    w = 0.38
    for i in range(len(years)):
        a = 1.0 if actual[i] else 0.55
        ax.bar(x[i] - w / 2, rev[i], w, color="#5b9bd5", alpha=a, edgecolor="#1f4e79" if not actual[i] else None,
               hatch=None if actual[i] else "//")
        ax.bar(x[i] + w / 2, ebitda[i], w, color="#1f4e79", alpha=a, edgecolor="#1f4e79",
               hatch=None if actual[i] else "//")
        ax.text(x[i] - w / 2, rev[i] + 90, f"{rev[i]:,.0f}", ha="center", va="bottom", fontsize=7, rotation=90)
        ax.text(x[i] + w / 2, ebitda[i] + 90, f"{ebitda[i]:,.0f}", ha="center", va="bottom", fontsize=7, rotation=90)
    ax.set_xticks(x, years)
    ax.set_ylabel("Rs crore")
    ax.set_ylim(0, max(rev) * 1.75)  # bars use the lower ~60% of the panel, the margin line sits above them
    ax.axvline(len(hy) - 0.5, color="#999999", lw=1, ls=":")
    ax.text(len(hy) - 0.45, max(rev) * 1.12, "forecast (base case) ->", fontsize=8, color="#555555")
    ax2 = ax.twinx()
    ax2.plot(x, np.array(margin) * 100, color="#c55a11", marker="o", lw=2)
    for i, m in enumerate(margin):
        ax2.text(x[i], m * 100 + 0.8, f"{m:.1%}", ha="center", fontsize=7, color="#c55a11")
    ax2.set_ylabel("EBITDA margin (%)")
    ax2.set_ylim(-10, 32)
    ax2.set_yticks([15, 20, 25, 30])
    fig.legend(handles=[Patch(color="#5b9bd5", label="Revenue (Rs crore)"),
                        Patch(color="#1f4e79", label="EBITDA (Rs crore)"),
                        plt.Line2D([], [], color="#c55a11", marker="o", label="EBITDA margin (%, right axis)"),
                        Patch(facecolor="white", edgecolor="#1f4e79", hatch="//", label="Forecast (hatched)")],
               loc="lower center", bbox_to_anchor=(0.5, 0.045), ncol=4, fontsize=8, frameon=False)
    ax.set_title("Castrol India: revenue and EBITDA, CY2021-CY2025 actual and CY2026E-CY2031E base case\n"
                 "(CY2026E = 9 months reported + Q4 estimate)", fontsize=11)
    fig.tight_layout(rect=(0, 0.09, 1, 1))
    note(fig)
    save(fig, "01_revenue_ebitda.png")


# ----------------------------------------------------------------------------- 2. debt paydown
def fig_debt_paydown() -> None:
    ds = by_item(OUT / "base_debt_schedule.csv")
    cols = list(ds.columns)
    labels = ["Close\n31-Dec-2026"] + cols[1:]
    x = np.arange(len(cols))
    fig, ax = plt.subplots(figsize=(10, 5.6))
    bottom = np.zeros(len(cols))
    for key, name, colr in [("term_loan_a_cr", "Term loan A (amortising)", C_TLA),
                            ("term_loan_b_cr", "Term loan B (1% a year + cash sweep)", C_TLB),
                            ("holdco_pik_notes_cr", "Holdco notes (cash + PIK coupon)", C_MZ),
                            ("revolver_cr", "Revolver", C_RCF)]:
        v = ds.loc[key, cols].to_numpy(dtype=float)
        if np.allclose(v, 0):
            continue
        ax.bar(x, v, 0.6, bottom=bottom, color=colr, label=name)
        bottom += v
    tot = ds.loc["total_debt_cr", cols].to_numpy(dtype=float)
    for i, t in enumerate(tot):
        ax.text(x[i], t + 60, f"{t:,.0f}", ha="center", fontsize=9, fontweight="bold")
    cash = ds.loc["cash_cr", cols].to_numpy(dtype=float)
    ax.plot(x, cash, color="#548235", marker="s", lw=2, label="Cash on balance sheet")
    lev = ds.loc["net_debt_ebitda_x", cols].to_numpy(dtype=float)
    for i, l in enumerate(lev):
        ax.text(x[i], -420, f"{l:.1f}x", ha="center", fontsize=8, color="#333333")
    ax.text(-0.75, -420, "Net debt /\nEBITDA", ha="right", va="center", fontsize=8, color="#333333")
    ax.set_xticks(x, labels)
    ax.set_ylim(-650, tot.max() * 1.15)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_ylabel("Rs crore")
    ax.legend(fontsize=8, frameon=False, loc="upper right")
    ax.set_title("Debt paydown by tranche, base case (Rs crore, year-end balances)\n"
                 "All cash above the Rs 300 crore minimum repays term loan B first, then term loan A", fontsize=11)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    note(fig)
    save(fig, "02_debt_paydown.png")


# ----------------------------------------------------------------------------- 3. leverage and cover vs covenants
def fig_leverage_path() -> None:
    cs = pd.read_csv(OUT / "scenario_credit_stats.csv")
    years = [c for c in cs.columns if c.startswith("CY")]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 5.4))
    for scen, (colr, ls) in SCEN_STYLE.items():
        sub = cs[cs["scenario"] == scen].set_index("item")
        a1.plot(years, sub.loc["net_debt_ebitda_x", years].astype(float), color=colr, ls=ls, marker="o", label=scen)
        a2.plot(years[1:], sub.loc["ebitda_cash_interest_x", years[1:]].astype(float), color=colr, ls=ls, marker="o",
                label=scen)
    base = cs[cs["scenario"] == "Base"].set_index("item")
    a1.step(years[1:], base.loc["covenant_max_net_leverage_x", years[1:]].astype(float), where="mid", color="black",
            ls=":", lw=1.8, label="Covenant: maximum")
    a2.step(years[1:], base.loc["covenant_min_icr_x", years[1:]].astype(float), where="mid", color="black", ls=":",
            lw=1.8, label="Covenant: minimum")
    a1.set_title("Net debt / EBITDA (x)", fontsize=10)
    a1.set_ylabel("x EBITDA")
    a1.axhline(0, color="#999999", lw=0.8)
    a1.set_xticks(years, ["Close"] + years[1:])
    a2.set_title("EBITDA / cash interest (x, log scale)", fontsize=10)
    a2.set_ylabel("x cash interest")
    a2.set_yscale("log")
    a2.set_yticks([2, 3, 4, 6, 10, 20, 50], ["2", "3", "4", "6", "10", "20", "50"])
    a2.yaxis.set_minor_formatter(NullFormatter())
    for a in (a1, a2):
        a.legend(fontsize=8, frameon=False)
        a.grid(axis="y", alpha=0.3)
    breached = []
    for scen in SCEN_STYLE:
        sub = cs[cs["scenario"] == scen].set_index("item")
        lev = sub.loc["net_debt_ebitda_x", years[1:]].astype(float).to_numpy()
        icr = sub.loc["ebitda_cash_interest_x", years[1:]].astype(float).to_numpy()
        if (lev > sub.loc["covenant_max_net_leverage_x", years[1:]].astype(float).to_numpy()).any() or \
                (icr < sub.loc["covenant_min_icr_x", years[1:]].astype(float).to_numpy()).any():
            breached.append(scen)
    status = "every case passes every test" if not breached else "breach in: " + ", ".join(breached)
    fig.suptitle(f"Credit statistics against the maintenance covenants, CY2027E-CY2031E ({status})", fontsize=11)
    fig.tight_layout(rect=(0, 0.05, 1, 0.95))
    note(fig)
    save(fig, "03_leverage_path.png")


# ----------------------------------------------------------------------------- 4. returns attribution waterfall
def fig_returns_attribution() -> None:
    at = pd.read_csv(OUT / "returns_attribution.csv").set_index("driver")["rs_crore"]
    steps = [("Sponsor equity\ninvested", at["Sponsor equity invested"], "total"),
             ("EBITDA growth\n(at entry multiple)", at["EBITDA growth"], "delta"),
             ("Multiple\nchange", at["Multiple change"], "delta"),
             ("Debt paydown\nand cash build", at["Debt paydown and cash build"], "delta"),
             ("Fees paid\nat close", at["Fees at close"], "delta"),
             ("Management\nincentive pool", at["Management incentive pool"], "delta"),
             ("Sponsor exit\nproceeds", at["Sponsor exit proceeds"], "total")]
    fig, ax = plt.subplots(figsize=(11, 5.6))
    level = 0.0
    for i, (lab, v, kind) in enumerate(steps):
        if kind == "total":
            ax.bar(i, v, 0.6, color=C_TOT)
            ax.text(i, v + 300, f"{v:,.0f}", ha="center", fontsize=9, fontweight="bold")
            level = v
        else:
            colr = C_POS if v >= 0 else C_NEG
            bottom = level if v >= 0 else level + v
            ax.bar(i, abs(v) if abs(v) > 0 else 0.0, 0.6, bottom=bottom, color=colr)
            ax.text(i, max(level, level + v) + 300, f"{v:+,.0f}", ha="center", fontsize=9)
            if i + 1 < len(steps):
                ax.plot([i - 0.3, i + 1.3], [level + v, level + v], color="#999999", lw=0.8, ls=":")
            level += v
    gain = at["Sponsor exit proceeds"] - at["Sponsor equity invested"]
    ax.set_xticks(range(len(steps)), [s[0] for s in steps], fontsize=8)
    ax.set_ylabel("Rs crore")
    ax.set_ylim(0, at["Sponsor exit proceeds"] * 1.12)
    ax.legend(handles=[Patch(color=C_TOT, label="Equity in / proceeds out"), Patch(color=C_POS, label="Adds value"),
                       Patch(color=C_NEG, label="Reduces value")], fontsize=8, frameon=False, loc="upper left")
    moic = at["Sponsor exit proceeds"] / at["Sponsor equity invested"]
    ax.set_title(f"Returns attribution, base case: Rs {gain:,.0f} crore gain on Rs "
                 f"{at['Sponsor equity invested']:,.0f} crore invested ({moic:.2f}x MOIC)", fontsize=11)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    note(fig)
    save(fig, "04_returns_attribution.png")


# ----------------------------------------------------------------------------- 5-6. IRR heatmaps
def heatmap(csv_name: str, fname: str, title: str, xlabel: str, ylabel: str, xfmt, yfmt,
            base_rc: tuple[int, int] | None, base_note: str) -> None:
    raw = pd.read_csv(OUT / csv_name)
    yvals = raw.iloc[:, 0].astype(float).to_numpy()
    xvals = np.array([float(c) for c in raw.columns[1:]])
    grid = raw.iloc[:, 1:].astype(float).to_numpy()
    fig, ax = plt.subplots(figsize=(10.5, 6.6))
    im = ax.imshow(grid * 100, cmap="RdYlGn", vmin=0, vmax=25, aspect="auto")
    for i in range(grid.shape[0]):
        for j in range(grid.shape[1]):
            v = grid[i, j]
            ax.text(j, i, f"{v:.1%}", ha="center", va="center", fontsize=9,
                    fontweight="bold" if v >= HURDLE else "normal", color="black")
            if v >= HURDLE:
                ax.add_patch(Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False, edgecolor="black", lw=2.2))
    if base_rc is not None:
        r, c = base_rc
        ax.add_patch(Rectangle((c - 0.5, r - 0.5), 1, 1, fill=False, edgecolor="#1f4e79", lw=2.2, ls="--"))
    ax.set_xticks(range(len(xvals)), [xfmt(v) for v in xvals])
    ax.set_yticks(range(len(yvals)), [yfmt(v) for v in yvals])
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    cb = fig.colorbar(im, ax=ax, shrink=0.85)
    cb.set_label("Sponsor IRR (%)")
    ax.set_title(title, fontsize=11)
    hurdle_txt = (f"Solid black box = IRR at or above the {HURDLE:.0%} hurdle." if (grid >= HURDLE).any()
                  else f"No cell reaches the {HURDLE:.0%} hurdle.")
    fig.text(0.01, 0.05, f"{hurdle_txt} {base_note}", fontsize=8, color="#333333")
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    note(fig)
    save(fig, fname)


def main() -> None:
    b = pd.read_csv(OUT / "scenario_summary.csv").set_index("scenario").loc["Base"]
    base_txt = (f"{float(b['premium_to_close']):.0%} premium (Rs {float(b['offer_price_rs']):,.0f}) and exit at the "
                f"{float(b['exit_multiple_x']):.1f}x entry multiple, IRR {float(b['irr']):.1%}")
    fig_revenue_ebitda()
    fig_debt_paydown()
    fig_leverage_path()
    fig_returns_attribution()
    heatmap("sensitivity_t1.csv", "05_irr_heatmap.png",
            "Sponsor IRR by offer premium and exit multiple (base operating case)",
            "Exit multiple (EV / CY2031E EBITDA, x)", "Offer premium to the 30-Oct-2026 close of Rs 188",
            lambda v: f"{v:.0f}x", lambda v: f"{v:.0%}", None, f"Base case: {base_txt}.")
    heatmap("sensitivity_t3.csv", "06_irr_heatmap_operating.png",
            "Sponsor IRR by EBITDA margin and revenue growth, change vs base case in every year CY2027E-CY2031E",
            "Change in annual revenue growth (percentage points)", "Change in EBITDA margin (percentage points)",
            lambda v: f"{v * 100:+.0f} pp", lambda v: f"{v * 100:+.0f} pp", (3, 3),
            f"Dashed blue box = base case: {base_txt}.")
    print("EXIT_OK")


if __name__ == "__main__":
    main()
