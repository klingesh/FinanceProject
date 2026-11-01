"""Matplotlib versions of the key charts for the README (reads the recalculated workbook).

Run after recalc_verify.py so that the workbook holds Excel-calculated values.
"""
from __future__ import annotations

import json
import math
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import openpyxl  # noqa: E402

import inputs as I  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
XLSX = os.path.join(ROOT, "Vriddhi_Foods_FPA_FY2027.xlsx")
FIG = os.path.join(ROOT, "figures")
NAVY, LIGHT, RED, GREEN, GREY = "#1F4E79", "#9DC3E6", "#C00000", "#70AD47", "#7F7F7F"
SRC = "Source: Vriddhi_Foods_FPA_FY2027.xlsx (fictional company; H1 = Apr-Sep 2026 actuals, Oct-Mar forecast)"

with open(os.path.join(HERE, "layout.json"), encoding="utf-8") as fh:
    LAY = json.load(fh)
R = LAY["R"]
MCOLS = [chr(ord("D") + i) for i in range(12)]
MONTHS = [m.strftime("%b-%y") for m in I.MONTHS]

plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titleweight": "bold", "axes.titlesize": 11})


def note(fig, text=SRC):
    fig.text(0.01, 0.01, text, fontsize=7, color=GREY, ha="left", va="bottom")


def row(ws, key, cols):
    return [ws[f"{c}{R[key]}"].value for c in cols]


def waterfall(ax, start_label, start, steps, end_label, end, ymin=0.0, fmt="{:+.1f}"):
    labels = [start_label] + [s[0] for s in steps] + [end_label]
    ax.bar(0, start - ymin, bottom=ymin, color=NAVY, width=0.6)
    ax.text(0, start, f"{start:,.1f}", ha="center", va="bottom", fontsize=8, fontweight="bold")
    cum = start
    for i, (_, v) in enumerate(steps, start=1):
        lo = min(cum, cum + v)
        ax.bar(i, abs(v), bottom=lo, color=GREEN if v >= 0 else RED, width=0.6)
        ax.plot([i - 1.3, i + 0.3], [cum, cum], color=GREY, lw=0.6, ls=":")
        y = cum + v if v >= 0 else cum
        ax.text(i, max(cum, cum + v), fmt.format(v), ha="center", va="bottom", fontsize=8)
        cum += v
    n = len(steps) + 1
    ax.plot([n - 1.3, n + 0.3], [cum, cum], color=GREY, lw=0.6, ls=":")
    ax.bar(n, end - ymin, bottom=ymin, color=NAVY, width=0.6)
    ax.text(n, end, f"{end:,.1f}", ha="center", va="bottom", fontsize=8, fontweight="bold")
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.set_ylim(bottom=ymin)
    assert abs(cum - end) < 1e-6, (cum, end)


def main():
    os.makedirs(FIG, exist_ok=True)
    wb = openpyxl.load_workbook(XLSX, data_only=True)
    bud, act, fc = wb["Budget_PL"], wb["Actuals_H1"], wb["Forecast_6plus6"]
    pv, fo = wb["PVM_Bridge"], wb["FY_Outlook"]

    # 1. Net revenue by month
    b = row(bud, "nr_tot", MCOLS)
    a = row(act, "nr_tot", MCOLS[:6])
    f = row(fc, "nr_tot", MCOLS[6:])
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.bar(range(6), a, color=NAVY, width=0.6, label="Actual (Apr-Sep 2026)")
    ax.bar(range(6, 12), f, color=LIGHT, width=0.6, label="Forecast (Oct-26 to Mar-27)")
    ax.plot(range(12), b, color=RED, ls="--", marker="o", ms=3.5, lw=1.5, label="Budget")
    ax.set_xticks(range(12))
    ax.set_xticklabels(MONTHS)
    ax.set_ylabel("Net revenue (₹ crore)")
    ax.set_title("Vriddhi Foods: monthly net revenue, actual and forecast vs budget")
    ax.legend(frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.08))
    ax.set_ylim(0, max(b + a + f) * 1.15)
    fig.subplots_adjust(bottom=0.2)
    note(fig)
    fig.savefig(os.path.join(FIG, "revenue_actual_budget_forecast.png"), dpi=150)
    plt.close(fig)

    # 2. Gross margin % by month
    gb = row(bud, "r_gm", MCOLS)
    ga = row(act, "r_gm", MCOLS[:6])
    gf = row(fc, "r_gm", MCOLS[5:])
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(range(12), [x * 100 for x in gb], color=RED, ls="--", marker="o", ms=3.5, label="Budget")
    ax.plot(range(6), [x * 100 for x in ga], color=NAVY, marker="o", ms=3.5, label="Actual")
    ax.plot(range(5, 12), [x * 100 for x in gf], color=LIGHT, marker="o", ms=3.5, label="Forecast")
    ax.set_xticks(range(12))
    ax.set_xticklabels(MONTHS)
    ax.set_ylabel("Gross margin (% of net revenue)")
    ax.set_title("Gross margin by month: oil and sugar inflation, weak beverages in July-September")
    ax.legend(frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.08))
    fig.subplots_adjust(bottom=0.2)
    note(fig)
    fig.savefig(os.path.join(FIG, "gross_margin_by_month.png"), dpi=150)
    plt.close(fig)

    # 3. H1 EBITDA bridge
    eb = LAY["pvm_summ"]["eb"]
    labels = {"vol": "Volume", "mix": "Mix", "lp": "List price", "tsr": "Trade spend\n& channel mix",
              "mrate": "Material rate", "pcrate": "Packaging &\nconversion", "freight": "Freight", "ap": "A&P",
              "emp": "Employee\ncost", "oth": "Other\noverheads"}
    keys = list(labels)
    steps = [(labels[k], pv[f"C{eb[k]}"].value) for k in keys]
    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    waterfall(ax, "Budget\nEBITDA", pv[f"C{eb['start']}"].value, steps, "Actual\nEBITDA", pv[f"C{eb['pl']}"].value)
    ax.set_ylabel("₹ crore")
    ax.set_title("H1 FY2027 EBITDA bridge: budget to actual (₹ crore)")
    fig.subplots_adjust(bottom=0.24)
    note(fig)
    fig.savefig(os.path.join(FIG, "ebitda_bridge_h1.png"), dpi=150)
    plt.close(fig)

    # 4. H1 revenue PVM waterfall
    rv = LAY["pvm_summ"]["rev"]
    steps = [("Volume", pv[f"C{rv['vol']}"].value), ("Mix", pv[f"C{rv['mix']}"].value),
             ("List price", pv[f"C{rv['lp']}"].value),
             ("Trade spend\n& channel mix", pv[f"C{rv['tsr']}"].value)]
    start, end = pv[f"C{rv['start']}"].value, pv[f"C{rv['pl']}"].value
    lo = min(start, end, *(start + sum(v for _, v in steps[:i + 1]) for i in range(len(steps))))
    ymin = math.floor((lo - 8) / 10) * 10
    fig, ax = plt.subplots(figsize=(7.5, 4.4))
    waterfall(ax, "Budget net\nrevenue", start, steps, "Actual net\nrevenue", end, ymin=ymin, fmt="{:+.2f}")
    ax.set_ylabel("₹ crore")
    ax.set_title("H1 FY2027 net revenue: price-volume-mix bridge (₹ crore)")
    fig.subplots_adjust(bottom=0.22)
    note(fig, SRC + f". Y-axis starts at ₹{ymin:,.0f} crore.")
    fig.savefig(os.path.join(FIG, "revenue_pvm_h1.png"), dpi=150)
    plt.close(fig)

    # 5. FY EBITDA bridge, budget to 6+6 forecast
    ebf = LAY["fy_summ"]["eb"]
    steps = [(labels[k], fo[f"C{ebf[k]}"].value) for k in keys]
    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    waterfall(ax, "Budget\nFY EBITDA", fo[f"C{ebf['start']}"].value, steps, "6+6 FY\nEBITDA",
              fo[f"C{ebf['pl']}"].value)
    ax.set_ylabel("₹ crore")
    ax.set_title("FY2027 EBITDA bridge: budget to 6+6 forecast, base case (₹ crore)")
    fig.subplots_adjust(bottom=0.24)
    note(fig)
    fig.savefig(os.path.join(FIG, "ebitda_bridge_fy_forecast.png"), dpi=150)
    plt.close(fig)
    print("figures written:", sorted(os.listdir(FIG)))


if __name__ == "__main__":
    main()
