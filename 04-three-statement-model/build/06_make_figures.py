"""Charts for the README from the verified model outputs (offline).

Reads outputs/model_outputs_by_scenario.csv (written by 05_verify_model.py from the Excel-calculated workbook)
and the historical tidy files in data/. Writes 150 dpi PNGs to figures/.

Run:  python build/06_make_figures.py
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "figures"
FIG.mkdir(exist_ok=True)
OUT = pd.read_csv(ROOT / "outputs" / "model_outputs_by_scenario.csv")
KPI = pd.read_csv(ROOT / "data" / "operating_kpis.csv").set_index("kpi")
IS = pd.read_csv(ROOT / "data" / "hist_income_statement.csv")
HY = ["FY2022", "FY2023", "FY2024", "FY2025", "FY2026"]
FY = ["FY2026A", "FY2027E", "FY2028E", "FY2029E", "FY2030E", "FY2031E"]
COL = {"Base": "#1F3864", "Bull": "#2E8B57", "Bear": "#C0392B"}
SRC = "Source: UltraTech audited results FY2022-FY2026; forecasts from UltraTech_3Statement_Model.xlsx (Excel-calculated)."
plt.rcParams.update({"font.size": 9, "axes.grid": True, "grid.alpha": 0.3, "axes.spines.top": False,
                     "axes.spines.right": False})


def series(scen: str, sheet: str, line: str) -> list[float]:
    row = OUT[(OUT.scenario == scen) & (OUT.sheet == sheet) & (OUT.line == line)].iloc[0]
    return [float(row[y]) for y in FY]


def hist_is(group: str) -> list[float]:
    return list(IS[IS.group == group][HY].sum())


def finish(fig, name: str) -> None:
    fig.text(0.01, 0.005, SRC, fontsize=7, color="#555555")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(FIG / name, dpi=150)
    plt.close(fig)
    print("saved", name)


def fig_revenue_ebitda() -> None:
    rev_h = hist_is("revenue")
    opex_groups = ["raw_material", "employee", "power_fuel", "freight", "other_exp"]
    ebitda_h = [r - sum(x) for r, x in zip(rev_h, zip(*[hist_is(g) for g in opex_groups]))]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for ax, key, hist, ttl in [(axes[0], "rev", rev_h, "Revenue from operations"),
                               (axes[1], "ebitda", ebitda_h, "EBITDA")]:
        ax.plot(HY, [v / 1000 for v in hist], color="#7F7F7F", marker="o", label="Reported FY2022-FY2026")
        for s in ("Bull", "Base", "Bear"):
            vals = series(s, "Income_Statement", key)
            ax.plot(["FY2026"] + FY[1:], [v / 1000 for v in vals], color=COL[s], marker="o", label=s)
        ax.set_title(f"{ttl} by scenario (Rs '000 crore)")
        ax.set_ylabel("Rs '000 crore")
        ax.tick_params(axis="x", rotation=45)
        ax.legend(fontsize=8)
    finish(fig, "fig1_revenue_ebitda_by_scenario.png")


def fig_leverage() -> None:
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for s in ("Bull", "Base", "Bear"):
        ax.plot(FY, series(s, "Balance_Sheet", "nd_e"), color=COL[s], marker="o", label=s)
    ax.axhline(1.0, color="#555555", ls="--", lw=1)
    ax.text(FY[-1], 1.03, "company ceiling: below 1.0x", ha="right", fontsize=8, color="#555555")
    ax.axhline(0, color="black", lw=0.6)
    ax.set_title("Net debt / EBITDA by scenario (x)")
    ax.set_ylabel("Net debt / EBITDA (x)")
    ax.legend()
    finish(fig, "fig2_net_debt_to_ebitda.png")


def fig_fcf_bridge() -> None:
    g = lambda sh, k: series("Base", sh, k)[1]  # noqa: E731  FY2027E
    wc = g("Cash_Flow", "d_inv") + g("Cash_Flow", "d_rec") + g("Cash_Flow", "d_pay")
    debt = g("Cash_Flow", "new") + g("Cash_Flow", "rep") + g("Cash_Flow", "rev")
    steps = [("EBITDA", g("Income_Statement", "ebitda"), "total"), ("Other income", g("Income_Statement", "oi"), "d"),
             ("Finance costs", -g("Income_Statement", "fin"), "d"), ("Tax", -g("Income_Statement", "tax"), "d"),
             ("Working capital", wc, "d"), ("CFO", g("Cash_Flow", "cfo"), "total"),
             ("Capex", g("Cash_Flow", "capex"), "d"), ("Free cash flow", g("Cash_Flow", "fcf"), "total"),
             ("Dividends", g("Cash_Flow", "div"), "d"), ("Net borrowing", debt, "d"),
             ("Change in cash", g("Cash_Flow", "net"), "total")]
    fig, ax = plt.subplots(figsize=(11, 4.6))
    level = 0.0
    for i, (lab, val, kind) in enumerate(steps):
        if kind == "total":
            bottom, height, color = 0, val, "#1F3864"
            level = val
        else:
            bottom = level if val >= 0 else level + val
            height, color = abs(val), "#2E8B57" if val >= 0 else "#C0392B"
            level += val
        ax.bar(i, height, bottom=bottom, color=color, width=0.65)
        ax.text(i, bottom + height + 250, f"{val:,.0f}", ha="center", fontsize=8)
    ax.set_xticks(range(len(steps)), [s[0] for s in steps], rotation=30, ha="right")
    ax.axhline(0, color="black", lw=0.6)
    ax.set_title("FY2027E cash bridge, Base case (Rs crore): EBITDA to free cash flow to change in cash")
    ax.set_ylabel("Rs crore")
    finish(fig, "fig3_fcf_bridge_fy27e_base.png")


def fig_capacity_volume() -> None:
    cap_h = [float(x) for x in KPI.loc["Grey cement capacity at year end (incl. 5.4 MTPA overseas)", HY]]
    vol_h = [float(x) for x in KPI.loc["Sales volume (consolidated)", HY]]
    years = HY + FY[1:]
    fig, ax = plt.subplots(figsize=(11, 4.6))
    x = range(len(years))
    cap_base = cap_h + series("Base", "Income_Statement", "cap_close")[1:]
    ax.bar(list(x), cap_base, color="#D9E1F2", edgecolor="#8EA9DB", label="Capacity at year end, Base (MTPA)")
    ax.plot(range(len(HY)), vol_h, color="#7F7F7F", marker="o", label="Sales volume, reported (MnT)")
    for s in ("Bull", "Base", "Bear"):
        vol = series(s, "Income_Statement", "vol")
        ax.plot(range(len(HY) - 1, len(years)), vol, color=COL[s], marker="o", label=f"Sales volume, {s} (MnT)")
        cap = series(s, "Income_Statement", "cap_close")
        if s != "Base":
            ax.plot(range(len(HY) - 1, len(years)), cap, color=COL[s], ls=":", lw=1.2,
                    label=f"Capacity, {s} (MTPA)")
    ax.set_xticks(list(x), years, rotation=45)
    ax.set_ylabel("MTPA / million tonnes")
    ax.set_title("Capacity vs sales volume: history and forecast by scenario")
    ax.legend(fontsize=7.5, ncol=2, loc="upper left")
    finish(fig, "fig4_capacity_vs_volume.png")


if __name__ == "__main__":
    fig_revenue_ebitda()
    fig_leverage()
    fig_fcf_bridge()
    fig_capacity_volume()
    print("EXIT_OK")
