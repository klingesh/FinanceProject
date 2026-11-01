"""Write outputs/*.csv, figures/*.png and outputs/READY.txt from the recalculated workbook.

Every number is read from the values Excel cached in AsianPaints_Comps_and_DCF.xlsx, so the CSVs, charts,
PDF and READMEs cannot drift from the model.

Order:  python build/build_model.py  ->  python build/recalc_verify.py  ->  python build/make_outputs.py
        ->  python build/make_pdf.py
"""
from __future__ import annotations

import datetime as dt
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
XLSX = ROOT / "AsianPaints_Comps_and_DCF.xlsx"
OUT = ROOT / "outputs"
FIG = ROOT / "figures"

SYMBOLS = ["ASIANPAINT", "BERGEPAINT", "KANSAINER", "JSWDULUX", "INDIGOPNTS"]
SHORT = {"ASIANPAINT": "Asian\nPaints", "BERGEPAINT": "Berger\nPaints", "KANSAINER": "Kansai\nNerolac",
         "JSWDULUX": "JSW\nDulux", "INDIGOPNTS": "Indigo\nPaints"}
PRICE_DATE = "2026-10-30"
VALUATION_DATE = "2026-09-30"
SOURCE_NOTE = ("Source: AsianPaints_Comps_and_DCF.xlsx (this project). Prices: Yahoo Finance close 30-Oct-2026. "
               "Financials: Screener.in consolidated and company filings. Consensus and targets: S&P Global via "
               "stockanalysis.com.")
DPI = 150


# ----------------------------------------------------------------------------------------------
# Reading the workbook
# ----------------------------------------------------------------------------------------------
def cell(wb, ref: str):
    """Cached value of a 'Sheet!A1' reference."""
    sheet, addr = ref.split("!")
    return wb[sheet][addr].value


def clean(text) -> str:
    """Workbook labels use the rupee sign; CSVs use plain 'Rs' so any tool can read them."""
    return "" if text is None else str(text).replace("\u20b9", "Rs").strip()


def overall_checks(wb) -> tuple[str, str]:
    """Return (result, detail) of the 'Overall result' row on the Checks sheet."""
    ws = wb["Checks"]
    for r in range(1, ws.max_row + 1):
        if ws[f"B{r}"].value == "Overall result":
            return ws[f"C{r}"].value, ws[f"D{r}"].value
    raise KeyError("Overall result row not found on Checks")


def pct(v: float | None, nd: int = 2) -> float | None:
    """Fraction -> percent number, rounded."""
    return None if v is None else round(100 * float(v), nd)


def rnd(v, nd: int):
    return None if v is None or isinstance(v, str) else round(float(v), nd)


# ----------------------------------------------------------------------------------------------
# Tables
# ----------------------------------------------------------------------------------------------
COMP_COLS = [  # (csv column, Comps column, kind, decimals)
    ("ttm_end", "B", "text", 0),
    ("price_rs", "C", "num", 2),
    ("shares_crore", "D", "num", 4),
    ("market_cap_rs_cr", "E", "num", 1),
    ("debt_incl_leases_rs_cr", "F", "num", 1),
    ("minority_interest_rs_cr", "G", "num", 1),
    ("cash_and_liquid_investments_rs_cr", "H", "num", 1),
    ("enterprise_value_rs_cr", "I", "num", 1),
    ("ttm_revenue_rs_cr", "J", "num", 1),
    ("ttm_ebitda_rs_cr", "K", "num", 1),
    ("ttm_pat_for_pe_rs_cr", "L", "num", 1),
    ("ttm_eps_rs", "M", "num", 4),
    ("ebitda_margin_ttm_pct", "N", "pct", 4),
    ("revenue_cagr_fy23_fy26_pct", "O", "pct", 4),
    ("roce_fy26_pct", "P", "pct", 4),
    ("roe_fy26_pct", "Q", "pct", 4),
    ("ev_ebitda_ttm_x", "R", "num", 4),
    ("pe_ttm_x", "S", "num", 4),
    ("ev_sales_ttm_x", "T", "num", 4),
    ("fy27e_ebitda_consensus_rs_cr", "U", "num", 1),
    ("ev_ebitda_fy27e_x", "V", "num", 4),
    ("pe_fy27e_x", "W", "num", 4),
    ("memo_ev_ebitda_ttm_ex_noncurrent_investments_x", "X", "num", 4),
    ("flags", "Y", "text", 0),
]
# Multiples and percentages keep 4 decimals so that formatting them to 1 decimal later gives the same
# figure as the workbook (rounding twice, e.g. 44.947 -> 44.95 -> 45.0, would not).
STAT_LETTERS = {"N", "O", "P", "Q", "R", "S", "T", "V", "W", "X"}
STAT_ROWS = [(12, "Peer minimum"), (13, "Peer 25th percentile"), (14, "Peer median"),
             (15, "Peer 75th percentile"), (16, "Peer maximum")]


def _conv(v, kind: str, nd: int):
    if kind == "text":
        return clean(v)
    if kind == "pct":
        return pct(v, nd)
    return rnd(v, nd)


def comps_table(wb) -> pd.DataFrame:
    """Company rows (Asian Paints first) followed by the peer statistics rows (Asian Paints excluded)."""
    ws = wb["Comps"]
    rows = []
    for i, sym in enumerate(SYMBOLS):
        r = 5 + i
        d = {"row_type": "target" if i == 0 else "peer", "company": clean(ws[f"A{r}"].value), "nse_symbol": sym}
        for name, col, kind, nd in COMP_COLS:
            d[name] = _conv(ws[f"{col}{r}"].value, kind, nd)
        rows.append(d)
    for r, label in STAT_ROWS:
        d = {"row_type": "peer_statistic", "company": label, "nse_symbol": ""}
        for name, col, kind, nd in COMP_COLS:
            d[name] = _conv(ws[f"{col}{r}"].value, kind, nd) if col in STAT_LETTERS else None
        rows.append(d)
    return pd.DataFrame(rows)


IMPLIED = [  # (Comps row, multiple, peer-statistic column, metric units)
    (21, "EV/EBITDA TTM", "R", "Rs crore"),
    (22, "P/E TTM", "S", "Rs per share"),
    (23, "EV/Sales TTM", "T", "Rs crore"),
    (24, "EV/EBITDA FY27E", "V", "Rs crore"),
    (25, "P/E FY27E", "W", "Rs per share"),
]


def implied_values(wb) -> pd.DataFrame:
    """Peer multiples (min, quartiles, max) and the Asian Paints value per share each one implies."""
    ws = wb["Comps"]
    price = float(ws["C5"].value)
    rows = []
    for r, mult, scol, units in IMPLIED:
        d = {
            "multiple": mult,
            "asian_paints_metric": clean(ws[f"A{r}"].value).split(" x ", 1)[1],
            "asian_paints_metric_value": rnd(ws[f"B{r}"].value, 2),
            "metric_units": units,
            "asian_paints_multiple_x": rnd(ws[f"I{r}"].value, 4),
            "peer_min_x": rnd(ws[f"{scol}12"].value, 4),
            "peer_p25_x": rnd(ws[f"{scol}13"].value, 4),
            "peer_median_x": rnd(ws[f"{scol}14"].value, 4),
            "peer_p75_x": rnd(ws[f"{scol}15"].value, 4),
            "peer_max_x": rnd(ws[f"{scol}16"].value, 4),
            "asian_paints_premium_to_peer_median_pct": pct(ws[f"{scol}17"].value, 4),
            "implied_rs_per_share_at_min": rnd(ws[f"C{r}"].value, 0),
            "implied_rs_per_share_at_p25": rnd(ws[f"D{r}"].value, 0),
            "implied_rs_per_share_at_median": rnd(ws[f"E{r}"].value, 0),
            "implied_rs_per_share_at_p75": rnd(ws[f"F{r}"].value, 0),
            "implied_rs_per_share_at_max": rnd(ws[f"G{r}"].value, 0),
            "median_implied_vs_price_pct": pct(ws[f"H{r}"].value, 4),
            "share_price_rs": price,
            "basis": clean(ws[f"J{r}"].value),
        }
        rows.append(d)
    return pd.DataFrame(rows)


def drop_one(wb) -> pd.DataFrame:
    """Median of the remaining three peers when each peer is dropped in turn."""
    ws = wb["Comps"]
    rows = []
    for r in range(30, 37):
        rows.append({
            "case": clean(ws[f"A{r}"].value),
            "median_ev_ebitda_ttm_x": rnd(ws[f"B{r}"].value, 4),
            "median_pe_ttm_x": rnd(ws[f"C{r}"].value, 4),
            "median_ev_sales_ttm_x": rnd(ws[f"D{r}"].value, 4),
            "implied_rs_per_share_ev_ebitda": rnd(ws[f"E{r}"].value, 0),
            "implied_rs_per_share_pe": rnd(ws[f"F{r}"].value, 0),
            "implied_rs_per_share_ev_sales": rnd(ws[f"G{r}"].value, 0),
        })
    return pd.DataFrame(rows)


DCF_ITEMS = [  # (item, cell, units, decimals, note)
    ("valuation_date", None, "date", None, "30-Sep-2026 balance sheet; cash flows discounted from this date"),
    ("price_date", None, "date", None, "Yahoo Finance close"),
    ("share_price_rs", "DCF!B65", "Rs per share", 2, ""),
    ("dcf_value_per_share_rs", "DCF!B64", "Rs per share", 2, "Base case"),
    ("upside_vs_price_pct", "DCF!B66", "%", 2, "Value / price - 1"),
    ("verdict", "DCF!B67", "text", None, ""),
    ("wacc_pct", "WACC!B28", "%", 2, ""),
    ("terminal_growth_pct", "DCF!B50", "%", 2, "Judgment"),
    ("risk_free_rate_pct", "WACC!B5", "%", 2, "India 10-year G-sec, 30-Oct-2026"),
    ("beta_regression_5y_weekly", "WACC!B6", "beta", 3, "OLS vs NIFTY 50, 260 weeks"),
    ("beta_blume_adjusted", "WACC!B7", "beta", 3, "0.67 x raw + 0.33"),
    ("beta_peer_median", "WACC!B8", "beta", 3, "Four peers, same method"),
    ("beta_used", "WACC!B9", "beta", 3, "Judgment"),
    ("equity_risk_premium_pct", "WACC!B10", "%", 2, "Judgment"),
    ("cost_of_equity_pct", "WACC!B11", "%", 2, "rf + beta x ERP"),
    ("memo_cost_of_equity_damodaran_method_pct", "WACC!B14", "%", 2, "(rf - default spread) + beta x total ERP"),
    ("pre_tax_cost_of_debt_pct", "WACC!B18", "%", 2, "rf + 1.0%"),
    ("tax_rate_pct", "WACC!B20", "%", 2, "s.115BAA"),
    ("after_tax_cost_of_debt_pct", "WACC!B21", "%", 2, ""),
    ("equity_weight_pct", "WACC!B26", "%", 2, "Market values"),
    ("debt_weight_pct", "WACC!B27", "%", 2, "Debt incl. leases"),
    ("sum_pv_fcff_rs_cr", "DCF!B48", "Rs crore", 1, "H2 FY2027E to FY2031E"),
    ("fcff_fy2031e_rs_cr", "DCF!B51", "Rs crore", 1, ""),
    ("terminal_value_rs_cr", "DCF!B52", "Rs crore", 1, "Gordon growth, end-FY2031E"),
    ("pv_terminal_value_rs_cr", "DCF!B53", "Rs crore", 1, ""),
    ("enterprise_value_rs_cr", "DCF!B54", "Rs crore", 1, ""),
    ("plus_cash_and_bank_rs_cr", "DCF!B55", "Rs crore", 2, "30-Sep-2026"),
    ("plus_current_investments_rs_cr", "DCF!B56", "Rs crore", 2, "Liquid mutual funds"),
    ("plus_noncurrent_investments_rs_cr", "DCF!B57", "Rs crore", 2, "Incl. associates, book value"),
    ("less_borrowings_rs_cr", "DCF!B58", "Rs crore", 2, ""),
    ("less_lease_liabilities_rs_cr", "DCF!B59", "Rs crore", 2, ""),
    ("less_minority_interest_rs_cr", "DCF!B60", "Rs crore", 2, "Book value"),
    ("net_adjustments_ev_to_equity_rs_cr", "DCF!B61", "Rs crore", 2, ""),
    ("equity_value_rs_cr", "DCF!B62", "Rs crore", 1, ""),
    ("diluted_shares_crore", "DCF!B63", "crore shares", 4, ""),
    ("terminal_value_share_of_ev_pct", "DCF!B70", "%", 1, ""),
    ("implied_exit_ev_ebitda_x", "DCF!B72", "x", 2, "Gordon TV / FY2031E EBITDA"),
    ("exit_multiple_cross_check_x", "DCF!B73", "x", 2, "Peer median EV/EBITDA TTM"),
    ("value_per_share_at_exit_multiple_rs", "DCF!B76", "Rs per share", 2, "Cross-check only"),
    ("growth_implied_by_exit_multiple_pct", "DCF!B77", "%", 2, ""),
    ("market_ev_rs_cr", "DCF!B78", "Rs crore", 1, "Market cap - net adjustments"),
    ("market_implied_perpetual_growth_pct", "DCF!B80", "%", 2, "g that makes the DCF equal the price"),
    ("market_ev_to_fy27e_ebitda_x", "DCF!B81", "x", 2, ""),
    ("dcf_ev_to_fy27e_ebitda_x", "DCF!B82", "x", 2, ""),
    ("dcf_range_inner_3x3_low_rs", "Sensitivity!B24", "Rs per share", 0, "WACC +/-0.5 pp, g +/-0.5 pp"),
    ("dcf_range_inner_3x3_high_rs", "Sensitivity!B25", "Rs per share", 0, "WACC +/-0.5 pp, g +/-0.5 pp"),
    ("dcf_grid_5x5_low_rs", "Sensitivity!B26", "Rs per share", 0, "WACC +/-1.0 pp, g +/-1.0 pp"),
    ("dcf_grid_5x5_high_rs", "Sensitivity!C26", "Rs per share", 0, "WACC +/-1.0 pp, g +/-1.0 pp"),
]


def dcf_summary(wb) -> pd.DataFrame:
    rows = []
    for item, ref, units, nd, note in DCF_ITEMS:
        if item == "valuation_date":
            v = VALUATION_DATE
        elif item == "price_date":
            v = PRICE_DATE
        else:
            raw = cell(wb, ref)
            if units == "text":
                v = clean(raw)
            elif units == "%":
                v = pct(raw, 4)          # 4 decimals: later 1-2 decimal formatting matches the workbook
            elif units in ("x", "beta"):
                v = rnd(raw, 4)
            else:
                v = rnd(raw, nd)
        rows.append({"item": item, "value": v, "units": units, "workbook_cell": ref or "", "note": note})
    return pd.DataFrame(rows)


PERIODS = [("B", "FY2026A"), ("C", "H1_FY2027A"), ("D", "H2_FY2027E"), ("E", "FY2027E"), ("F", "FY2028E"),
           ("G", "FY2029E"), ("H", "FY2030E"), ("I", "FY2031E")]
FORECAST_ROWS = [  # (DCF row, line item, units)
    (5, "revenue_growth_pct", "%"), (6, "revenue_rs_cr", "Rs crore"), (7, "ebitda_margin_pct", "%"),
    (8, "ebitda_rs_cr", "Rs crore"), (10, "depreciation_amortisation_rs_cr", "Rs crore"),
    (11, "ebit_rs_cr", "Rs crore"), (13, "tax_on_ebit_rs_cr", "Rs crore"), (14, "nopat_rs_cr", "Rs crore"),
    (17, "capex_rs_cr", "Rs crore"), (19, "new_leases_rs_cr", "Rs crore"),
    (20, "trade_working_capital_period_end_rs_cr", "Rs crore"),
    (21, "increase_in_trade_working_capital_rs_cr", "Rs crore"), (22, "fcff_rs_cr", "Rs crore"),
    (23, "fcff_margin_pct", "%"), (25, "discount_period_years", "years"), (26, "discount_factor", "factor"),
    (27, "pv_of_fcff_rs_cr", "Rs crore"), (31, "other_income_rs_cr", "Rs crore"),
    (32, "finance_costs_rs_cr", "Rs crore"), (33, "share_of_associates_rs_cr", "Rs crore"),
    (35, "profit_before_tax_rs_cr", "Rs crore"), (37, "tax_rs_cr", "Rs crore"),
    (38, "profit_after_tax_rs_cr", "Rs crore"), (39, "minority_interest_rs_cr", "Rs crore"),
    (40, "pat_attributable_to_owners_rs_cr", "Rs crore"), (41, "eps_rs", "Rs per share"),
    (42, "consensus_eps_rs", "Rs per share"), (44, "consensus_revenue_rs_cr", "Rs crore"),
]


def dcf_forecast(wb) -> pd.DataFrame:
    """Forecast lines by period (H1/H2 columns are half-years; FY2027E = H1 actual + H2 estimate)."""
    ws = wb["DCF"]
    rows = []
    for r, item, units in FORECAST_ROWS:
        d = {"line_item": item, "units": units}
        for col, per in PERIODS:
            v = ws[f"{col}{r}"].value
            if v is None or isinstance(v, str):
                d[per] = None
            elif units == "%":
                d[per] = pct(v, 4)
            elif units in ("years", "factor"):
                d[per] = round(float(v), 4)
            else:
                d[per] = round(float(v), 2)
        rows.append(d)
    return pd.DataFrame(rows)


def football_field(wb) -> pd.DataFrame:
    ws = wb["Football_Field"]
    rows = []
    for r in range(5, 11):
        mid = ws[f"D{r}"].value
        method = clean(ws[f"A{r}"].value)
        rows.append({
            "method": method,
            "bar_type": "context" if r in (5, 10) else "valuation",
            "low_rs": rnd(ws[f"B{r}"].value, 0),
            "high_rs": rnd(ws[f"C{r}"].value, 0),
            "mid_rs": rnd(mid, 0) if not isinstance(mid, str) else None,
            "price_inside_range": ws[f"F{r}"].value,
            "share_price_rs": rnd(ws["B11"].value, 2),
            "basis": clean(ws[f"E{r}"].value),
        })
    return pd.DataFrame(rows)


def sensitivity_grid(wb) -> pd.DataFrame:
    ws = wb["Sensitivity"]
    gs = [ws[f"{c}6"].value for c in "CDEFG"]
    rows = []
    for r in range(7, 12):
        d = {"wacc_pct": pct(ws[f"B{r}"].value, 2)}
        for c, g in zip("CDEFG", gs):
            d[f"g_{100 * g:.2f}_pct"] = rnd(ws[f"{c}{r}"].value, 1)
        rows.append(d)
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------------------------
# Figures
# ----------------------------------------------------------------------------------------------
def _rs(v: float, _pos=None) -> str:
    return f"{v:,.0f}"


def add_source(fig, width_chars: int, y: float = 0.012, extra: str = "") -> None:
    """Source note at the bottom of the figure, wrapped to fit the figure width."""
    text = "\n".join(textwrap.wrap((extra + " " if extra else "") + SOURCE_NOTE, width_chars))
    fig.text(0.01, y, text, fontsize=6.8, color="#595959", va="bottom")


LABEL_BOX = dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.9)


def fig_football(ff: pd.DataFrame, price: float, path: Path) -> None:
    colours = {"context": "#BFBFBF", "valuation": "#4472C4"}
    fig, ax = plt.subplots(figsize=(10.5, 6.0))
    n = len(ff)
    ys = np.arange(n)[::-1]
    for y, (_, r) in zip(ys, ff.iterrows()):
        ax.barh(y, r.high_rs - r.low_rs, left=r.low_rs, height=0.56, color=colours[r.bar_type],
                edgecolor="#1F3864", linewidth=0.8)
        if r.mid_rs is not None and not pd.isna(r.mid_rs):
            ax.plot([r.mid_rs, r.mid_rs], [y - 0.28, y + 0.28], color="#1F1F1F", lw=1.6)
        ax.text(r.low_rs - 35, y, _rs(r.low_rs), ha="right", va="center", fontsize=8.5)
        ax.text(r.high_rs + 35, y, _rs(r.high_rs), ha="left", va="center", fontsize=8.5)
    ax.axvline(price, color="#C00000", ls="--", lw=1.8)
    ax.text(price + 25, n - 0.45, f"Price Rs {price:,.0f}", color="#C00000", fontsize=9, va="bottom")
    ax.set_yticks(ys)
    ax.set_yticklabels(ff["method"])
    ax.set_xlim(0, 3600)
    ax.set_ylim(-0.7, n - 0.1)
    ax.xaxis.set_major_formatter(FuncFormatter(_rs))
    ax.set_xlabel("Value per share (Rs)")
    ax.grid(axis="x", alpha=0.3)
    ax.set_axisbelow(True)
    ax.set_title("Asian Paints: value per share by method vs the 30-Oct-2026 share price")
    handles = [Patch(facecolor=colours["valuation"], edgecolor="#1F3864", label="Valuation method (low-high)"),
               Patch(facecolor=colours["context"], edgecolor="#1F3864", label="Market context (not a valuation)"),
               Line2D([0], [0], color="#1F1F1F", lw=1.6, label="Mid point (base DCF, peer median, median target)"),
               Line2D([0], [0], color="#C00000", ls="--", lw=1.8, label="Share price, 30-Oct-2026 close")]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.42, -0.13), ncol=2, fontsize=8, frameon=False)
    add_source(fig, 175)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(path, dpi=DPI)
    plt.close(fig)


def fig_multiples(comps: pd.DataFrame, path: Path) -> None:
    co = comps[comps.row_type.isin(["target", "peer"])]
    med = comps[comps.company == "Peer median"].iloc[0]
    panels = [("ev_ebitda_ttm_x", "EV/EBITDA, TTM", "{:.1f}x"), ("pe_ttm_x", "P/E, TTM", "{:.1f}x"),
              ("ev_sales_ttm_x", "EV/Sales, TTM", "{:.2f}x")]
    fig, axes = plt.subplots(1, 3, figsize=(12.5, 4.9))
    names = [SHORT[s] for s in co.nse_symbol]
    colours = ["#1F4E78"] + ["#9DC3E6"] * (len(co) - 1)
    for ax, (col, title, fmt) in zip(axes, panels):
        vals = co[col].astype(float).values
        ax.bar(names, vals, color=colours, edgecolor="#1F3864", linewidth=0.6)
        for i, v in enumerate(vals):
            ax.text(i, v + 0.012 * max(vals), fmt.format(v), ha="center", va="bottom", fontsize=8.5,
                    bbox=LABEL_BOX, zorder=5)
        m = float(med[col])
        ax.axhline(m, color="#C55A11", ls="--", lw=1.4, label=f"Peer median {fmt.format(m)}")
        ax.set_title(title)
        ax.set_ylabel("Multiple (x)")
        ax.set_ylim(0, max(vals) * 1.18)
        ax.tick_params(axis="x", labelsize=8.5)
        ax.legend(loc="upper right", fontsize=8)
        ax.grid(axis="y", alpha=0.3)
        ax.set_axisbelow(True)
    fig.suptitle("Trading multiples: Asian Paints (dark) vs four listed paint peers, prices of 30-Oct-2026",
                 fontsize=11.5)
    fig.text(0.01, 0.045, "TTM ends Sep-2026 for Asian Paints and Indigo Paints, Jun-2026 for Berger, Kansai Nerolac "
                          "and JSW Dulux. JSW Dulux P/E excludes a Rs 1,578 cr after-tax exceptional gain. "
                          "Peer median excludes Asian Paints.", fontsize=7.2, color="#404040")
    fig.text(0.01, 0.012, SOURCE_NOTE, fontsize=6.8, color="#595959")
    fig.tight_layout(rect=(0, 0.07, 1, 0.95))
    fig.savefig(path, dpi=DPI)
    plt.close(fig)


def fig_margin_vs_multiple(comps: pd.DataFrame, path: Path) -> None:
    co = comps[comps.row_type.isin(["target", "peer"])].reset_index(drop=True)
    med = comps[comps.company == "Peer median"].iloc[0]
    x = co["ebitda_margin_ttm_pct"].astype(float).values
    y = co["ev_ebitda_ttm_x"].astype(float).values
    mc = co["market_cap_rs_cr"].astype(float).values
    sizes = 80 + 1500 * np.sqrt(mc / mc.max())
    colours = ["#1F4E78"] + ["#9DC3E6"] * (len(co) - 1)
    fig, ax = plt.subplots(figsize=(8.6, 5.8))
    ax.scatter(x, y, s=sizes, c=colours, edgecolors="#1F3864", linewidths=0.8, alpha=0.85, zorder=3)
    offsets = {"ASIANPAINT": (-12, 26), "BERGEPAINT": (14, 14), "KANSAINER": (14, -4), "JSWDULUX": (-16, 14),
               "INDIGOPNTS": (14, -10)}
    for i, sym in enumerate(co.nse_symbol):
        dx, dy = offsets[sym]
        label = f"{co.company[i]}\n{x[i]:.1f}%, {y[i]:.1f}x\nmcap Rs {mc[i]:,.0f} cr"
        ax.annotate(label, (x[i], y[i]), textcoords="offset points", xytext=(dx, dy),
                    ha="right" if dx < 0 else "left", fontsize=8, zorder=4)
    ax.axhline(float(med["ev_ebitda_ttm_x"]), color="#7F7F7F", ls=":", lw=1.3,
               label=f"Peer median EV/EBITDA {float(med['ev_ebitda_ttm_x']):.1f}x")
    ax.axvline(float(med["ebitda_margin_ttm_pct"]), color="#7F7F7F", ls="--", lw=1.0,
               label=f"Peer median EBITDA margin {float(med['ebitda_margin_ttm_pct']):.1f}%")
    ax.set_xlim(10, 21)
    ax.set_ylim(8, 36)
    ax.set_xlabel("EBITDA margin, TTM (%)")
    ax.set_ylabel("EV/EBITDA, TTM (x)")
    ax.set_title("EBITDA margin vs EV/EBITDA (bubble area grows with market cap)")
    ax.grid(alpha=0.3)
    ax.set_axisbelow(True)
    ax.legend(loc="lower right", fontsize=8)
    add_source(fig, 150, extra="TTM ends Sep-2026 for Asian Paints and Indigo Paints, Jun-2026 for the others.")
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(path, dpi=DPI)
    plt.close(fig)


# ----------------------------------------------------------------------------------------------
# READY.txt (Project 5 waits for this file)
# ----------------------------------------------------------------------------------------------
def ready_text(wb, iv: pd.DataFrame, ff: pd.DataFrame, fc: pd.DataFrame, dcf: pd.DataFrame,
               checks: tuple[str, str]) -> str:
    v = dict(zip(dcf["item"], dcf["value"]))
    fcx = fc.set_index("line_item")
    lines = [
        "READY - Project 3 (Asian Paints comps + DCF): workbook and outputs are final.",
        f"Written {dt.datetime.now():%d-%b-%Y %H:%M} by build/make_outputs.py from the Excel-recalculated workbook.",
        f"Workbook: AsianPaints_Comps_and_DCF.xlsx | Checks sheet: {checks[0]} ({checks[1]})",
        "Price date: 30-Oct-2026 close (Yahoo Finance). Valuation / balance-sheet date: 30-Sep-2026.",
        "Units: Rs crore unless stated; per-share values in Rs.",
        "",
        "== Headline ==",
        f"Share price (30-Oct-2026): Rs {v['share_price_rs']:,.2f}",
        f"DCF value per share (base): Rs {v['dcf_value_per_share_rs']:,.2f}  (vs price {v['upside_vs_price_pct']:+.1f}%)",
        f"WACC: {v['wacc_pct']:.2f}%  (Ke {v['cost_of_equity_pct']:.2f}% = rf {v['risk_free_rate_pct']:.2f}% + beta "
        f"{v['beta_used']:.2f} x ERP {v['equity_risk_premium_pct']:.2f}%; Kd after tax "
        f"{v['after_tax_cost_of_debt_pct']:.2f}%; D/(D+E) {v['debt_weight_pct']:.2f}%)",
        f"Terminal growth g: {v['terminal_growth_pct']:.2f}%",
        f"DCF range, inner 3x3 of the WACC x g grid (+/-0.5 pp each): Rs {v['dcf_range_inner_3x3_low_rs']:,.0f} - "
        f"{v['dcf_range_inner_3x3_high_rs']:,.0f}; full 5x5 grid Rs {v['dcf_grid_5x5_low_rs']:,.0f} - "
        f"{v['dcf_grid_5x5_high_rs']:,.0f}",
        f"Enterprise value Rs {v['enterprise_value_rs_cr']:,.0f} cr; equity value Rs {v['equity_value_rs_cr']:,.0f} cr; "
        f"terminal value {v['terminal_value_share_of_ev_pct']:.1f}% of EV; implied exit EV/EBITDA "
        f"{v['implied_exit_ev_ebitda_x']:.1f}x",
        f"Cross-check: exit multiple {v['exit_multiple_cross_check_x']:.1f}x (peer median) gives Rs "
        f"{v['value_per_share_at_exit_multiple_rs']:,.0f}/share; perpetual growth implied by the market price "
        f"{v['market_implied_perpetual_growth_pct']:.2f}%",
        "",
        "== Comps: implied Asian Paints value per share (Rs) ==",
        "multiple            | peer 25th / median / 75th (x) | implied 25th / median / 75th (Rs) | min - max (Rs) | AP own multiple",
    ]
    for _, r in iv.iterrows():
        xf = "{:.2f}" if r.multiple.startswith("EV/Sales") else "{:.1f}"
        lines.append(
            f"{r.multiple:<19} | {xf.format(r.peer_p25_x)} / {xf.format(r.peer_median_x)} / {xf.format(r.peer_p75_x)}"
            f" | {r.implied_rs_per_share_at_p25:,.0f} / {r.implied_rs_per_share_at_median:,.0f} / "
            f"{r.implied_rs_per_share_at_p75:,.0f} | {r.implied_rs_per_share_at_min:,.0f} - "
            f"{r.implied_rs_per_share_at_max:,.0f} | {xf.format(r.asian_paints_multiple_x)}x "
            f"(premium {r.asian_paints_premium_to_peer_median_pct:+.1f}% to median)")
    lines += ["", "== Football field ranges (Rs per share) =="]
    for _, r in ff.iterrows():
        mid = "n/a" if r.mid_rs is None or pd.isna(r.mid_rs) else f"{r.mid_rs:,.0f}"
        lines.append(f"{r.method:<40} low {r.low_rs:>6,.0f}  high {r.high_rs:>6,.0f}  mid {mid:>6}  "
                     f"price inside: {r.price_inside_range}  [{r.bar_type}]")
    lines.append(f"{'Share price, 30-Oct-2026 close':<40} {v['share_price_rs']:,.2f}")
    lines += ["", "== Forecast (DCF sheet; Rs crore, EPS in Rs) ==",
              f"{'line':<34}{'FY2026A':>10}{'FY2027E':>10}{'FY2028E':>10}{'FY2029E':>10}"]
    for item, label, fmt in [("revenue_rs_cr", "Revenue", "{:,.0f}"), ("revenue_growth_pct", "Revenue growth (%)", "{:.1f}"),
                             ("ebitda_rs_cr", "EBITDA", "{:,.0f}"), ("ebitda_margin_pct", "EBITDA margin (%)", "{:.1f}"),
                             ("pat_attributable_to_owners_rs_cr", "PAT attributable to owners", "{:,.0f}"),
                             ("eps_rs", "EPS (Rs, 95.92 cr shares)", "{:.2f}"),
                             ("consensus_eps_rs", "Consensus EPS (Rs, S&P)", "{:.2f}"),
                             ("fcff_rs_cr", "FCFF", "{:,.0f}")]:
        row = fcx.loc[item]
        cells = []
        for per in ["FY2026A", "FY2027E", "FY2028E", "FY2029E"]:
            x = row[per]
            cells.append(f"{'' if x is None or pd.isna(x) else fmt.format(x):>10}")
        lines.append(f"{label:<34}" + "".join(cells))
    lines += ["FY2027E = H1 FY2027 actual (filed 29-Oct-2026) + H2 FY2027E forecast.",
              "",
              "== Files ==",
              "outputs/comps_table.csv, outputs/implied_values.csv, outputs/drop_one_sensitivity.csv,",
              "outputs/dcf_summary.csv, outputs/dcf_forecast.csv, outputs/sensitivity_wacc_g.csv, outputs/football_field.csv",
              "figures/football_field.png, figures/multiples_bar.png, figures/margin_vs_multiple.png",
              "Percent columns in the CSVs are percent numbers (12.68 = 12.68%)."]
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------------------------
def main() -> None:
    OUT.mkdir(exist_ok=True)
    FIG.mkdir(exist_ok=True)
    wb = load_workbook(XLSX, data_only=True)
    checks = overall_checks(wb)
    assert checks[0] == "PASS", f"Checks sheet says {checks}; fix the workbook first"

    comps = comps_table(wb)
    iv = implied_values(wb)
    d1 = drop_one(wb)
    dcf = dcf_summary(wb)
    fc = dcf_forecast(wb)
    ff = football_field(wb)
    grid = sensitivity_grid(wb)

    # Validation (PASS/FAIL lines; any failure stops before READY.txt is written)
    v = dict(zip(dcf["item"], dcf["value"]))
    results = []

    def check(name: str, ok: bool) -> None:
        results.append(f"{'PASS' if ok else 'FAIL'}  {name}")

    num_cols = [c for c, _, k, _ in COMP_COLS if k != "text"]
    co = comps[comps.row_type != "peer_statistic"]
    check("No missing values in the five company rows", co[num_cols].notna().all().all())
    check("Margins/ROCE/ROE stored as percent numbers (1-100)",
          bool(((co[["ebitda_margin_ttm_pct", "roce_fy26_pct", "roe_fy26_pct"]] > 1) &
                (co[["ebitda_margin_ttm_pct", "roce_fy26_pct", "roe_fy26_pct"]] < 100)).all().all()))
    q = iv[["implied_rs_per_share_at_min", "implied_rs_per_share_at_p25", "implied_rs_per_share_at_median",
            "implied_rs_per_share_at_p75", "implied_rs_per_share_at_max"]].values
    check("Implied values ordered min <= 25th <= median <= 75th <= max", bool((np.diff(q, axis=1) >= 0).all()))
    check("Football field low <= high on every bar", bool((ff.low_rs <= ff.high_rs).all()))
    centre = float(wb["Sensitivity"]["E9"].value)
    check("Sensitivity grid centre equals the DCF value", abs(centre - float(cell(wb, "DCF!B64"))) < 0.01)
    check("DCF bar in the football field = inner 3x3 of the grid",
          ff.loc[1, "low_rs"] == v["dcf_range_inner_3x3_low_rs"] and ff.loc[1, "high_rs"] == v["dcf_range_inner_3x3_high_rs"])
    check("EV/EBITDA comps bar = 25th-75th implied values",
          ff.loc[2, "low_rs"] == iv.loc[0, "implied_rs_per_share_at_p25"]
          and ff.loc[2, "high_rs"] == iv.loc[0, "implied_rs_per_share_at_p75"])
    fcx = fc.set_index("line_item")
    check("FY2027E revenue = H1 FY2027A + H2 FY2027E",
          abs(fcx.loc["revenue_rs_cr", "FY2027E"] - fcx.loc["revenue_rs_cr", "H1_FY2027A"]
              - fcx.loc["revenue_rs_cr", "H2_FY2027E"]) < 0.05)
    check("WACC above g", v["wacc_pct"] > v["terminal_growth_pct"])

    files = {
        "comps_table.csv": comps, "implied_values.csv": iv, "drop_one_sensitivity.csv": d1,
        "dcf_summary.csv": dcf, "dcf_forecast.csv": fc, "football_field.csv": ff, "sensitivity_wacc_g.csv": grid,
    }
    for name, df in files.items():
        df.to_csv(OUT / name, index=False, encoding="utf-8")
    back = pd.read_csv(OUT / "implied_values.csv")
    check("CSV round trip (implied_values.csv medians)",
          bool(np.allclose(back["implied_rs_per_share_at_median"], iv["implied_rs_per_share_at_median"])))

    fig_football(ff, float(v["share_price_rs"]), FIG / "football_field.png")
    fig_multiples(comps, FIG / "multiples_bar.png")
    fig_margin_vs_multiple(comps, FIG / "margin_vs_multiple.png")
    check("Three figures written", all((FIG / f).stat().st_size > 20_000 for f in
                                       ["football_field.png", "multiples_bar.png", "margin_vs_multiple.png"]))

    print("\n".join(results))
    if any(r.startswith("FAIL") for r in results):
        raise SystemExit("Validation failed: READY.txt not written")
    (OUT / "READY.txt").write_text(ready_text(wb, iv, ff, fc, dcf, checks), encoding="utf-8")
    print("READY.txt written")
    print(f"DCF {v['dcf_value_per_share_rs']} | WACC {v['wacc_pct']} | g {v['terminal_growth_pct']} | "
          f"price {v['share_price_rs']}")


if __name__ == "__main__":
    main()
