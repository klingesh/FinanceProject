"""Build the Asian Paints initiation report: figures/*.png, report/*.html and report/*.pdf.

Every number is read from files in this project (outputs/ from the ratio workbook, data/ snapshots), so the text
cannot drift from the workbook. Values that come from Project 3 (forecasts, DCF, comps, football field) live in ONE
dict, P3, below, filled by load_p3() from Project 3's output files (never typed in). load_p3() refreshes the copies in
data/p3/ when Project 3's folder is available and cross-checks them against Project 3's recalculated workbook;
otherwise it uses data/p3/, so the report also rebuilds offline. If no Project 3 files exist at all, the report falls
back to a DRAFT with yellow {{P3:key}} tags and *_DRAFT.* file names (phase 1 behaviour).

Steps: load data -> load Project 3 -> premium-adjusted relative value (build/relative_value.py) -> blended target and
rating -> charts -> HTML -> PDF with headless Edge -> read the PDF back with PyMuPDF and check the numbers against the
source files -> optional PNG previews of each page.

Run:  python build/build_report.py [--p3-dir <Project 3 folder>] [--preview-dir <folder>]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA, OUT, FIG, REP = ROOT / "data", ROOT / "outputs", ROOT / "figures", ROOT / "report"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
ASOF, REPORT_DATE = "30-Oct-2026", "1-Nov-2026"
TAX = 0.2517            # Indian corporate tax, new regime (s.115BAA): 22% + 10% surcharge + 4% cess
FX_SHARE_ASSUMED = 0.30  # ASSUMPTION for the rupee sensitivity: share of COGS priced in USD (not disclosed)
COS = ["Asian Paints", "Berger Paints", "Kansai Nerolac", "JSW Dulux", "Indigo Paints"]
SHORT = {"Asian Paints": "Asian Paints", "Berger Paints": "Berger", "Kansai Nerolac": "Kansai",
         "JSW Dulux": "JSW Dulux", "Indigo Paints": "Indigo"}
COL = {"Asian Paints": "#0b3d63", "Berger Paints": "#e07b00", "Kansai Nerolac": "#5b9a2e",
       "JSW Dulux": "#8e44ad", "Indigo Paints": "#2a9df4", "NIFTY 50": "#808080"}
FYS = ["FY2022", "FY2023", "FY2024", "FY2025", "FY2026"]

# ------------------------------------------------------------------------------------------------------------------
# PROJECT 3 INPUTS. load_p3() fills this dict from Project 3's outputs/*.csv (copied to data/p3/) and cross-checks
# them against AsianPaints_Comps_and_DCF.xlsx (openpyxl, data_only=True). No Project 3 number is typed in here.
# Units: Rs crore for revenue/EBITDA/PAT/FCFF, Rs per share for EPS and values, decimals for rates (0.127 = 12.7%).
# ------------------------------------------------------------------------------------------------------------------
P3_KEYS = """
fy27e_revenue fy28e_revenue fy29e_revenue fy27e_ebitda fy28e_ebitda fy29e_ebitda fy27e_pat fy28e_pat fy29e_pat
fy27e_eps fy28e_eps fy29e_eps fy26a_fcff fy27e_fcff fy28e_fcff fy29e_fcff h1_revenue h1_ebitda h1_growth h2_growth
h1_margin h2_margin late_growth_lo late_growth_hi ebitda_fy31e cons_eps27 cons_eps28 cons_rev27 cons_rev28 cons_ebitda27
wacc ke rf beta erp ke_damodaran terminal_g tv_share_ev exit_ev_ebitda exit_cross_x exit_cross_value exit_cross_g
reverse_dcf_g market_ev sum_pv_fcff pv_tv tv dcf_value dcf_low dcf_high dcf_grid_low dcf_grid_high market_ev_ebitda27
comps_q1 comps_median comps_q3 pe_ttm_peer_median ap_pe_ttm ap_pe_ttm_prem ev_q1 ev_median ev_q3 ev_peer_median
ev_peer_min ev_peer_max ap_ev_ebitda ap_ev_prem pe27_peer_median ap_pe27 ap_pe27_prem pe_drop_lo pe_drop_hi
peer_roce_median ttm_eps h1_wc_increase
relative_value rel_low rel_high rel_premium rel_p25 rel_p75 rel_premium_now rel_trailing_value peer_pe_now
peer_pe_start own_pe_median own_pe_min own_pe_max own_pe_start own_pe_now own_band_value
w_dcf w_comps w_rel football_field_png
""".split()
P3: dict[str, object] = {k: None for k in P3_KEYS}
P3_SRC: dict[str, str] = {}          # key -> source file and column/cell (written to outputs/p3_inputs_used.csv)
P3_FF: list[dict] = []               # football-field rows from Project 3 (outputs/football_field.csv)
P3_DEFAULT = ROOT.parent / "03-comparable-company-analysis"   # sibling folder in the FinanceProject repository
P3_SNAP = DATA / "p3"                                         # copies of Project 3's outputs (offline rebuilds)
P3_FILES = ["READY.txt", "dcf_summary.csv", "dcf_forecast.csv", "implied_values.csv", "comps_table.csv",
            "football_field.csv", "sensitivity_wacc_g.csv", "drop_one_sensitivity.csv"]
P3_FIGS = ["multiples_bar.png"]      # Project 3 charts used (README); copied to figures/ as p3_<name>

# Target weights. Fixed, with these reasons, BEFORE the blended target was computed (rating rule from phase 1).
WEIGHTS = {"dcf": 0.25, "comps": 0.25, "rel": 0.50}
WEIGHT_WHY = {
    "dcf": "Only cash-flow method; biased low here (5 explicit years, then 6% growth: exit at 7.6x EBITDA, below every peer)",
    "comps": "Today's market price for the sector; P/E median steady when any peer is dropped, but peers earn lower returns",
    "rel": "Matches the 12-month horizon and the premium paid for Asian Paints over 5 years; not 100%: the premium can shrink",
}
ALT_WEIGHTS = [("Equal weights", {"dcf": 1 / 3, "comps": 1 / 3, "rel": 1 / 3}),
               ("DCF-heavy", {"dcf": 0.50, "comps": 0.25, "rel": 0.25}),
               ("No DCF", {"dcf": 0.0, "comps": 0.25, "rel": 0.75})]
THESIS_WRITTEN_FOR = "SELL"   # the narrative below was written for this rating; the build fails if the rule disagrees


# ------------------------------------------------------------------------------------------------------------------
# formatting helpers
# ------------------------------------------------------------------------------------------------------------------
def f0(x: float) -> str:
    return f"{x:,.0f}"


def f1(x: float) -> str:
    return f"{x:,.1f}"


def f2(x: float) -> str:
    return f"{x:,.2f}"


def pc(x: float, d: int = 1) -> str:
    return f"{x * 100:.{d}f}%"


def spc(x: float, d: int = 1) -> str:
    return f"{x * 100:+.{d}f}%"


def xx(x: float, d: int = 2) -> str:
    return f"{x:.{d}f}x"


def rs(x: float, d: int = 0) -> str:
    return "&#8377;" + (f"{x:,.{d}f}")


USED_PLACEHOLDERS: list[str] = []


def ph(key: str, fmt=f0) -> str:
    """P3 value formatted, or a visible {{P3:key}} tag while phase 2 has not filled it."""
    v = P3.get(key)
    if v is None:
        USED_PLACEHOLDERS.append(key)
        return '<span class="p3">{{P3:' + key + '}}</span>'
    return fmt(v)


def is_draft() -> bool:
    return any(v is None for v in P3.values())


# ------------------------------------------------------------------------------------------------------------------
# Project 3 inputs (phase 2)
# ------------------------------------------------------------------------------------------------------------------
def _set(key: str, value, src: str, scale: float = 1.0) -> None:
    """Store one Project 3 number (scale=0.01 turns Project 3's percent numbers into decimals) and its source."""
    P3[key] = float(value) * scale
    P3_SRC[key] = src


def p3_tables(folder: Path) -> dict[str, pd.DataFrame]:
    """Project 3's output tables, read from data/p3/ (refreshed from Project 3's outputs/ when available)."""
    return {"summary": pd.read_csv(folder / "dcf_summary.csv").set_index("item"),
            "forecast": pd.read_csv(folder / "dcf_forecast.csv").set_index("line_item"),
            "implied": pd.read_csv(folder / "implied_values.csv").set_index("multiple"),
            "comps": pd.read_csv(folder / "comps_table.csv"),
            "ff": pd.read_csv(folder / "football_field.csv"),
            "drop": pd.read_csv(folder / "drop_one_sensitivity.csv").set_index("case")}


def crosscheck_p3_workbook(xlsx: Path, t: dict[str, pd.DataFrame]) -> tuple[list[str], int]:
    """Compare Project 3's CSV hand-off with the cached values of its Excel-recalculated workbook (read only)."""
    import openpyxl

    wb = openpyxl.load_workbook(xlsx, data_only=True)
    bad, count, lines = 0, 0, []
    for item, r in t["summary"].iterrows():          # every DCF/WACC item that names its workbook cell
        cell = r["workbook_cell"]
        if not isinstance(cell, str) or "!" not in cell:
            continue
        try:
            x = float(r["value"]) * (0.01 if r["units"] == "%" else 1.0)
        except (TypeError, ValueError):
            continue
        sheet, ref = cell.split("!")
        v = wb[sheet][ref].value
        count += 1
        if not (isinstance(v, (int, float)) and abs(v - x) <= 1e-3 * abs(x) + 1e-9):
            bad += 1
            lines.append(f"  MISMATCH {item}: csv {x} vs {cell} = {v}")
    ws = wb["Comps"]                                   # implied values per share, rows 21-25, columns D-F
    for row, mult in [(21, "EV/EBITDA TTM"), (22, "P/E TTM"), (23, "EV/Sales TTM"), (24, "EV/EBITDA FY27E"),
                      (25, "P/E FY27E")]:
        if not str(ws[f"A{row}"].value).startswith(mult):
            bad += 1
            lines.append(f"  MISMATCH Comps!A{row} label {ws[f'A{row}'].value!r}, expected {mult}")
            continue
        for col, q in zip("DEF", ["p25", "median", "p75"]):
            x = float(t["implied"].loc[mult, f"implied_rs_per_share_at_{q}"])
            v = ws[f"{col}{row}"].value
            count += 1
            if not (isinstance(v, (int, float)) and abs(v - x) <= 0.5):
                bad += 1
                lines.append(f"  MISMATCH {mult} {q}: csv {x} vs Comps!{col}{row} = {v}")
    vals = [c.value for row in wb["Checks"].iter_rows() for c in row]
    n_pass, n_fail = vals.count("PASS"), vals.count("FAIL")
    lines.insert(0, f"P3 workbook cross-check ({xlsx.name}): {count} values compared, {bad} mismatches; "
                    f"Checks sheet {n_pass} PASS / {n_fail} FAIL cells")
    return lines, bad + n_fail


def load_p3(p3_dir: Path | None) -> list[str]:
    """Fill P3 and P3_FF from Project 3's output files. Returns log lines; leaves P3 empty (draft) if none exist."""
    if p3_dir is not None and (p3_dir / "outputs" / "READY.txt").exists():
        P3_SNAP.mkdir(parents=True, exist_ok=True)
        for f in P3_FILES:
            shutil.copy2(p3_dir / "outputs" / f, P3_SNAP / f)
        FIG.mkdir(exist_ok=True)
        for f in P3_FIGS:
            shutil.copy2(p3_dir / "figures" / f, FIG / f"p3_{f}")
        where = f"Project 3 folder {p3_dir} (copied to data/p3/)"
    elif (P3_SNAP / "READY.txt").exists():
        where = "data/p3/ (Project 3 folder not found, saved copies used)"
    else:
        return ["Project 3 files not found: DRAFT mode with {{P3}} tags"]
    ready = (P3_SNAP / "READY.txt").read_text(encoding="utf-8").splitlines()
    log = [f"P3 source: {where}", f"P3 READY.txt: {ready[1].strip()} | {ready[2].strip()}"]
    t = p3_tables(P3_SNAP)
    xlsx = p3_dir / "AsianPaints_Comps_and_DCF.xlsx" if p3_dir is not None else None
    if xlsx is not None and xlsx.exists():
        lines, bad = crosscheck_p3_workbook(xlsx, t)
        log += lines
        log.append("P3 CROSS-CHECK " + ("PASSED" if bad == 0 else f"FAILED ({bad})"))
    else:
        log.append("P3 workbook not available: saved CSV values used without the workbook cross-check")
    fc, sm, iv, cp = t["forecast"], t["summary"], t["implied"], t["comps"]
    ff_src, sm_src, iv_src = "data/p3/dcf_forecast.csv", "data/p3/dcf_summary.csv", "data/p3/implied_values.csv"
    for fy, k in [("FY2027E", "fy27e"), ("FY2028E", "fy28e"), ("FY2029E", "fy29e")]:
        for line, key in [("revenue_rs_cr", "revenue"), ("ebitda_rs_cr", "ebitda"),
                          ("pat_attributable_to_owners_rs_cr", "pat"), ("eps_rs", "eps"), ("fcff_rs_cr", "fcff")]:
            _set(f"{k}_{key}", fc.loc[line, fy], f"{ff_src} {line} {fy}")
    _set("fy26a_fcff", fc.loc["fcff_rs_cr", "FY2026A"], f"{ff_src} fcff_rs_cr FY2026A")
    _set("h1_revenue", fc.loc["revenue_rs_cr", "H1_FY2027A"], f"{ff_src} revenue_rs_cr H1_FY2027A")
    _set("h1_ebitda", fc.loc["ebitda_rs_cr", "H1_FY2027A"], f"{ff_src} ebitda_rs_cr H1_FY2027A")
    _set("h1_growth", fc.loc["revenue_growth_pct", "H1_FY2027A"], f"{ff_src} revenue_growth_pct H1", 0.01)
    _set("h2_growth", fc.loc["revenue_growth_pct", "H2_FY2027E"], f"{ff_src} revenue_growth_pct H2", 0.01)
    _set("h1_margin", fc.loc["ebitda_margin_pct", "H1_FY2027A"], f"{ff_src} ebitda_margin_pct H1", 0.01)
    _set("h2_margin", fc.loc["ebitda_margin_pct", "H2_FY2027E"], f"{ff_src} ebitda_margin_pct H2", 0.01)
    late = [float(fc.loc["revenue_growth_pct", c]) for c in ["FY2028E", "FY2029E", "FY2030E", "FY2031E"]]
    _set("late_growth_lo", min(late), f"{ff_src} revenue_growth_pct FY2028E-FY2031E (min)", 0.01)
    _set("late_growth_hi", max(late), f"{ff_src} revenue_growth_pct FY2028E-FY2031E (max)", 0.01)
    _set("ebitda_fy31e", fc.loc["ebitda_rs_cr", "FY2031E"], f"{ff_src} ebitda_rs_cr FY2031E")
    _set("h1_wc_increase", fc.loc["increase_in_trade_working_capital_rs_cr", "H1_FY2027A"],
         f"{ff_src} increase_in_trade_working_capital_rs_cr H1_FY2027A")
    _set("cons_eps27", fc.loc["consensus_eps_rs", "FY2027E"], f"{ff_src} consensus_eps_rs FY2027E")
    _set("cons_eps28", fc.loc["consensus_eps_rs", "FY2028E"], f"{ff_src} consensus_eps_rs FY2028E")
    _set("cons_rev27", fc.loc["consensus_revenue_rs_cr", "FY2027E"], f"{ff_src} consensus_revenue_rs_cr FY2027E")
    _set("cons_rev28", fc.loc["consensus_revenue_rs_cr", "FY2028E"], f"{ff_src} consensus_revenue_rs_cr FY2028E")
    _set("cons_ebitda27", iv.loc["EV/EBITDA FY27E", "asian_paints_metric_value"],
         f"{iv_src} EV/EBITDA FY27E asian_paints_metric_value")

    def s(key: str, item: str, scale: float = 1.0) -> None:
        cell = sm.loc[item, "workbook_cell"]
        _set(key, sm.loc[item, "value"], f"{sm_src} {item}" + (f" (workbook {cell})" if isinstance(cell, str) else ""),
             scale)

    for key, item, scale in [
            ("wacc", "wacc_pct", 0.01), ("ke", "cost_of_equity_pct", 0.01), ("rf", "risk_free_rate_pct", 0.01),
            ("beta", "beta_used", 1), ("erp", "equity_risk_premium_pct", 0.01),
            ("ke_damodaran", "memo_cost_of_equity_damodaran_method_pct", 0.01),
            ("terminal_g", "terminal_growth_pct", 0.01), ("tv_share_ev", "terminal_value_share_of_ev_pct", 0.01),
            ("exit_ev_ebitda", "implied_exit_ev_ebitda_x", 1), ("exit_cross_x", "exit_multiple_cross_check_x", 1),
            ("exit_cross_value", "value_per_share_at_exit_multiple_rs", 1),
            ("exit_cross_g", "growth_implied_by_exit_multiple_pct", 0.01),
            ("reverse_dcf_g", "market_implied_perpetual_growth_pct", 0.01), ("market_ev", "market_ev_rs_cr", 1),
            ("sum_pv_fcff", "sum_pv_fcff_rs_cr", 1), ("pv_tv", "pv_terminal_value_rs_cr", 1),
            ("tv", "terminal_value_rs_cr", 1), ("dcf_value", "dcf_value_per_share_rs", 1),
            ("dcf_low", "dcf_range_inner_3x3_low_rs", 1), ("dcf_high", "dcf_range_inner_3x3_high_rs", 1),
            ("dcf_grid_low", "dcf_grid_5x5_low_rs", 1), ("dcf_grid_high", "dcf_grid_5x5_high_rs", 1),
            ("market_ev_ebitda27", "market_ev_to_fy27e_ebitda_x", 1)]:
        s(key, item, scale)

    def m(prefix: str, mult: str) -> None:
        for q, col in [("q1", "implied_rs_per_share_at_p25"), ("median", "implied_rs_per_share_at_median"),
                       ("q3", "implied_rs_per_share_at_p75")]:
            _set(f"{prefix}_{q}", iv.loc[mult, col], f"{iv_src} {mult} {col}")

    m("comps", "P/E TTM")                      # P/E is Project 3's steadier comps anchor (drop-one test)
    m("ev", "EV/EBITDA TTM")
    for key, mult, col, scale in [("pe_ttm_peer_median", "P/E TTM", "peer_median_x", 1),
                                  ("ap_pe_ttm", "P/E TTM", "asian_paints_multiple_x", 1),
                                  ("ap_pe_ttm_prem", "P/E TTM", "asian_paints_premium_to_peer_median_pct", 0.01),
                                  ("ev_peer_median", "EV/EBITDA TTM", "peer_median_x", 1),
                                  ("ev_peer_min", "EV/EBITDA TTM", "peer_min_x", 1),
                                  ("ev_peer_max", "EV/EBITDA TTM", "peer_max_x", 1),
                                  ("ap_ev_ebitda", "EV/EBITDA TTM", "asian_paints_multiple_x", 1),
                                  ("ap_ev_prem", "EV/EBITDA TTM", "asian_paints_premium_to_peer_median_pct", 0.01),
                                  ("pe27_peer_median", "P/E FY27E", "peer_median_x", 1),
                                  ("ap_pe27", "P/E FY27E", "asian_paints_multiple_x", 1),
                                  ("ap_pe27_prem", "P/E FY27E", "asian_paints_premium_to_peer_median_pct", 0.01),
                                  ("ttm_eps", "P/E TTM", "asian_paints_metric_value", 1)]:
        _set(key, iv.loc[mult, col], f"{iv_src} {mult} {col}", scale)
    dr = t["drop"]
    _set("pe_drop_lo", dr.loc["Lowest drop-one result", "implied_rs_per_share_pe"],
         "data/p3/drop_one_sensitivity.csv Lowest drop-one result")
    _set("pe_drop_hi", dr.loc["Highest drop-one result", "implied_rs_per_share_pe"],
         "data/p3/drop_one_sensitivity.csv Highest drop-one result")
    med = cp[cp["company"] == "Peer median"].iloc[0]
    _set("peer_roce_median", med["roce_fy26_pct"], "data/p3/comps_table.csv Peer median roce_fy26_pct", 0.01)
    P3_FF.clear()
    P3_FF.extend(t["ff"].to_dict("records"))
    P3["football_field_png"] = "fig8_football_field.png"
    P3_SRC["football_field_png"] = "drawn by this script from data/p3/football_field.csv plus Section 6 values"
    for k, w in WEIGHTS.items():
        P3[f"w_{k}"] = w
        P3_SRC[f"w_{k}"] = "build_report.py WEIGHTS (fixed before the target was computed)"
    log.append(f"P3 values loaded: {sum(v is not None for v in P3.values())} of {len(P3)} keys "
               f"(relative-value keys follow from build/relative_value.py)")
    return log


def fill_relative_value(n: dict) -> pd.DataFrame:
    """Premium-adjusted relative value (build/relative_value.py) from Project 3's comps table and this project's
    prices and PAT. Fills the rel_* and own_* keys of P3 and returns the daily P/E history."""
    import relative_value as rv

    comps = pd.read_csv(P3_SNAP / "comps_table.csv")
    hist, st = rv.run(comps, pd.Timestamp(n["px_base_date"]), pd.Timestamp(n["px_last_date"]))
    src = "build/relative_value.py (this report)"
    eps28, eps27, pe27 = P3["fy28e_eps"], P3["fy27e_eps"], P3["pe27_peer_median"]
    vals = {"rel_premium": st["premium_median"], "rel_p25": st["premium_p25"], "rel_p75": st["premium_p75"],
            "rel_premium_now": st["premium_now"], "peer_pe_now": st["peer_pe_now"], "peer_pe_start": st["peer_pe_start"],
            "own_pe_median": st["own_pe_median"], "own_pe_min": st["own_pe_min"], "own_pe_max": st["own_pe_max"],
            "own_pe_start": st["own_pe_start"], "own_pe_now": st["own_pe_now"],
            "relative_value": rv.relative_value(pe27, st["premium_median"], eps28),
            "rel_low": rv.relative_value(pe27, st["premium_p25"], eps28),
            "rel_high": rv.relative_value(pe27, st["premium_p75"], eps28),
            # cross-check on a trailing basis: today's trailing peer median x (1 + premium) x FY2027E EPS
            "rel_trailing_value": rv.relative_value(st["peer_pe_now"], st["premium_median"], eps27),
            # context only (not in the target): Asian Paints' own 5-year median trailing P/E x FY2027E EPS
            "own_band_value": st["own_pe_median"] * eps27}
    for k, v in vals.items():
        P3[k], P3_SRC[k] = float(v), src
    n["rel_days"] = st["n_days"]
    inputs = {"input_peer_median_pe_fy27e": pe27, "input_fy28e_eps": eps28, "input_fy27e_eps": eps27}
    stats = pd.Series({**st, **inputs, **vals})          # one row per item (vals repeats some stats keys)
    stats.rename_axis("item").rename("value").to_csv(OUT / "relative_value.csv")
    hist.round(4).to_csv(OUT / "pe_premium_history.csv")
    return hist


def valuation(n: dict) -> dict:
    """Blended 12-month target, upside and rating (Buy > +15%, Hold -10% to +15%, Sell < -10%) plus sensitivities."""
    keys = ["dcf_value", "comps_median", "relative_value", "w_dcf", "w_comps", "w_rel"]
    if any(P3[k] is None for k in keys):
        return {}
    parts = {"dcf": P3["dcf_value"], "comps": P3["comps_median"], "rel": P3["relative_value"]}

    def blend(w: dict[str, float], p: dict[str, float] = parts) -> float:
        return sum(w[k] * p[k] for k in w)

    tp = blend({k: P3[f"w_{k}"] for k in parts})
    out = {"target": tp, "upside": tp / n["price"] - 1}
    out["rating"] = rating_for(out["upside"])
    out["alts"] = []
    for name, w in ALT_WEIGHTS:
        v = blend(w)
        out["alts"].append({"name": name, "w": w, "target": v, "upside": v / n["price"] - 1,
                            "rating": rating_for(v / n["price"] - 1)})
    own = dict(parts, rel=P3["own_band_value"])
    v = blend(WEIGHTS, own)
    out["own"] = {"target": v, "upside": v / n["price"] - 1, "rating": rating_for(v / n["price"] - 1)}
    return out


# ------------------------------------------------------------------------------------------------------------------
# data
# ------------------------------------------------------------------------------------------------------------------
def load() -> dict:
    d: dict = {}
    rat = pd.read_csv(OUT / "ratios_fy2022_fy2026.csv")
    d["R"] = {(r["company"], r["code"]): r for _, r in rat.iterrows()}
    dup = pd.read_csv(OUT / "dupont_fy2022_fy2026.csv")
    d["D"] = {(r["company"], r["code"]): r for _, r in dup.iterrows()}
    d["peer"] = pd.read_csv(OUT / "peer_comparison_fy2026.csv").set_index("code")
    d["score"] = pd.read_csv(OUT / "scorecard.csv").set_index("company")
    d["checks"] = pd.read_csv(OUT / "workbook_checks.csv")
    inp = pd.read_csv(DATA / "ratio_inputs.csv")
    d["I"] = {(r["name"], r["code"]): r for _, r in inp.iterrows()}
    d["q2"] = pd.read_csv(DATA / "asianpaints_q2fy27_results.csv")
    d["psum"] = json.loads((DATA / "prices" / "price_summary.json").read_text(encoding="utf-8"))
    px = pd.read_csv(DATA / "prices" / "prices_daily.csv", parse_dates=["Date"])
    d["px"] = px.pivot_table(index="Date", columns="name", values="Close")
    scr = json.loads((DATA / "screener" / "screener_summary.json").read_text(encoding="utf-8"))
    d["scr"] = scr
    d["sh"] = pd.read_csv(DATA / "screener" / "ASIANPAINT_consolidated_shareholding_quarterly.csv").set_index("item")
    d["pl"] = pd.read_csv(DATA / "screener" / "ASIANPAINT_consolidated_profit-loss.csv").set_index("item")
    d["qtr"] = pd.read_csv(DATA / "screener" / "ASIANPAINT_consolidated_quarters.csv").set_index("item")
    sa = DATA / "stockanalysis"
    d["sa_tgt"] = pd.read_csv(sa / "ASIANPAINT_forecast_t0.csv", encoding="utf-8")
    d["sa_rat"] = pd.read_csv(sa / "ASIANPAINT_forecast_t1.csv").set_index("Rating")
    d["sa_est"] = pd.read_csv(sa / "ASIANPAINT_forecast_t3.csv").set_index("Fiscal Year | Period Ending")
    d["sa_brk"] = pd.read_csv(sa / "ASIANPAINT_forecast_t2.csv", encoding="utf-8")
    facts = json.loads((DATA / "research_facts.json").read_text(encoding="utf-8"))["facts"]
    d["F"] = {f["id"]: f for f in facts}
    return d


def num(text: str) -> float:
    """First number in a string such as 'Rs 2,22,534 Cr.' or 'â¹1,925' -> 222534.0 / 1925.0."""
    m = re.search(r"-?[\d,]+(?:\.\d+)?", str(text))
    return float(m.group(0).replace(",", "")) if m else float("nan")


def screener_top(scr: dict, symbol: str, field: str) -> float:
    """Top-of-page ratio from the Screener consolidated page (e.g. 'Market Cap', 'Stock P/E')."""
    return num(scr[f"{symbol}_consolidated"]["top_ratios"][field]["text"])


def ordinal(k: int) -> str:
    return f"{k}{'th' if 10 <= k % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(k % 10, 'th')}"


def compute(d: dict) -> dict:
    """All numbers quoted in the report, in one dict (also saved to outputs/report_numbers.csv)."""
    R, I, D, peer = d["R"], d["I"], d["D"], d["peer"]
    n: dict = {}
    ap = "Asian Paints"
    ps = d["psum"][ap]
    n["price"], n["hi52"], n["lo52"] = ps["close"], ps["high_52w"], ps["low_52w"]
    n["ret1"], n["ret3"], n["ret5"], n["tr5"] = ps["ret_1y"], ps["ret_3y"], ps["ret_5y"], ps["tr_5y"]
    nf = d["psum"]["NIFTY 50"]
    n["nifty"], n["nifty_ret1"], n["nifty_ret3"], n["nifty_ret5"] = nf["close"], nf["ret_1y"], nf["ret_3y"], nf["ret_5y"]
    n["mcap"] = screener_top(d["scr"], "ASIANPAINT", "Market Cap")
    n["pe_ttm"] = screener_top(d["scr"], "ASIANPAINT", "Stock P/E")
    n["bv"] = screener_top(d["scr"], "ASIANPAINT", "Book Value")
    n["dy"] = screener_top(d["scr"], "ASIANPAINT", "Dividend Yield") / 100
    n["shares_cr"] = n["mcap"] / n["price"]
    for sym, co in [("BERGEPAINT", "Berger Paints"), ("KANSAINER", "Kansai Nerolac"), ("JSWDULUX", "JSW Dulux"),
                    ("INDIGOPNTS", "Indigo Paints")]:
        n[f"pe_{co}"] = screener_top(d["scr"], sym, "Stock P/E")
        n[f"mcap_{co}"] = screener_top(d["scr"], sym, "Market Cap")
    n["eps_ttm"] = float(d["pl"].loc["EPS in Rs", "TTM"])
    pxs = d["px"][["Asian Paints", "NIFTY 50"]].dropna()      # 5-year window used for returns, chart and P/E premium
    last_day = pxs.index[-1]
    base_day = pxs.index[pxs.index <= last_day - pd.DateOffset(years=5)][-1]
    n["px_base_date"], n["px_last_date"] = base_day.strftime("%Y-%m-%d"), last_day.strftime("%Y-%m-%d")
    pl = d["pl"]                                              # 10-year EPS growth (Screener P&L, FY2016-FY2026)
    n["eps_fy2016"] = float(pl.loc["EPS in Rs", "Mar 2016"])
    n["eps_cagr10"] = (float(pl.loc["EPS in Rs", "Mar 2026"]) / n["eps_fy2016"]) ** 0.1 - 1
    for fy in ["FY2021"] + FYS:
        for code in ["REV", "COGS", "EBITDA", "DEP", "INT", "PBT", "PAT", "PATOWN", "EQCAP", "RES", "NCI", "BORR",
                     "LEASE", "TA", "CFO", "CAPEX", "CASH", "CASHSTI", "INV", "REC", "PAY", "OTHINC", "EXCEP"]:
            v = I[(ap, code)][fy]
            n[f"{code}_{fy}"] = float(v) if pd.notna(v) else float("nan")
        n[f"EPS_{fy}"] = n[f"PATOWN_{fy}"] / n["shares_cr"]
        n[f"EQ_{fy}"] = n[f"EQCAP_{fy}"] + n[f"RES_{fy}"]
        n[f"FCF_{fy}"] = n[f"CFO_{fy}"] - n[f"CAPEX_{fy}"]
        n[f"GP_{fy}"] = n[f"REV_{fy}"] - n[f"COGS_{fy}"]
        n[f"EBIT_{fy}"] = n[f"EBITDA_{fy}"] - n[f"DEP_{fy}"]
    n["cagr5"] = (n["REV_FY2026"] / n["REV_FY2021"]) ** (1 / 5) - 1
    n["cagr3"] = (n["REV_FY2026"] / n["REV_FY2023"]) ** (1 / 3) - 1
    for co in COS:
        for code in ["GM", "EBITDAM", "NPM_ADJ", "ROE", "ROE_ADJ", "ROCE", "AT", "DE", "NDEBITDA", "ICR", "INVD",
                     "RECD", "PAYD", "CCC", "REVG", "CFOE", "FCFM", "CR", "FAT"]:
            for fy in FYS + ["AVG5"]:
                n[f"{code}_{co}_{fy}"] = float(R[(co, code)][fy])
        for code in ["D5_TB", "D5_IB", "D5_EBITM", "D5_AT", "D5_EM", "D5_ROE", "D3_NPM", "D3_AT", "D3_EM", "D3_ROE"]:
            n[f"{code}_{co}"] = float(D[(co, code)]["FY2026"])
        n[f"REV26_{co}"] = float(I[(co, "REV")]["FY2026"])
    for code in peer.index:
        n[f"med_{code}"] = float(peer.loc[code, "peer_median"])
        r = peer.loc[code, f"rank_{ap}"]
        n[f"rank_{code}"] = int(r) if pd.notna(r) else None
    sc = d["score"]
    for co in COS:
        n[f"score26_{co}"], n[f"pos26_{co}"] = float(sc.loc[co, "weighted_rank_fy2026"]), int(sc.loc[co, "position_fy2026"])
        n[f"score5_{co}"], n[f"pos5_{co}"] = float(sc.loc[co, "weighted_rank_5yr"]), int(sc.loc[co, "position_5yr"])
    chk = d["checks"]
    status_col = [c for c in chk.columns if c.lower() in ("status", "result", "check_result")]
    sc_col = status_col[0] if status_col else chk.columns[-1]
    n["checks_total"] = int(len(chk))
    n["checks_pass"] = int((chk[sc_col].astype(str).str.upper() == "PASS").sum())
    # Q2 FY27
    q = d["q2"].set_index(["basis", "metric"])
    n["q2"] = q
    # consensus (StockAnalysis)
    est = d["sa_est"]
    col27 = [c for c in est.columns if c.startswith("FY 2027")][0]
    n["cons_rev27"] = num(est.loc["Revenue", col27]) * 100       # billions of INR -> Rs crore
    n["cons_eps27"] = num(est.loc["EPS", col27])
    n["cons_n27"] = int(num(est.loc["No. Analysts", col27]))
    n["cons_pe27"] = n["price"] / n["cons_eps27"]
    dps = est.loc["Dividend / Share"]
    for c in est.columns:
        if c.startswith("FY 20"):
            fy = "FY" + c[3:7]
            n[f"DPS_{fy}"] = num(dps[c])
    t = d["sa_tgt"].set_index(d["sa_tgt"].columns[0])
    for k in ["Low", "Average", "Median", "High"]:
        n[f"tgt_{k}"] = num(t.loc["Price", k])
    rat = d["sa_rat"]
    last = rat.columns[-1]
    n["ratings_month"] = last.replace("'", "20")
    for k in ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell", "Total"]:
        n[f"rat_{k}"] = int(rat.loc[k, last])
    # shareholding
    sh = d["sh"]
    lastq = sh.columns[-1]
    n["sh_q"] = lastq
    for k in ["Promoters", "FIIs", "DIIs", "Public", "Others"]:
        n[f"sh_{k}"] = float(sh.loc[k, lastq]) / 100
        n[f"sh0_{k}"] = float(sh.loc[k, sh.columns[0]]) / 100
    n["sh_q0"] = sh.columns[0]
    n["sh_holders"] = float(sh.loc["No. of Shareholders", lastq])
    # risk sensitivities on the FY2026 base (simple, transparent arithmetic)
    rev, cogs, ebitda, pat = n["REV_FY2026"], n["COGS_FY2026"], n["EBITDA_FY2026"], n["PATOWN_FY2026"]
    n["cogs_pct"] = cogs / rev
    n["s_rm"] = 0.01 * cogs
    n["s_disc"] = 0.01 * rev
    n["s_vol"] = 0.01 * rev * n["GM_Asian Paints_FY2026"]
    n["s_fx"] = FX_SHARE_ASSUMED * 0.05 * cogs
    n["s_margin_up"] = (n["EBITDAM_Asian Paints_FY2024"] - n["EBITDAM_Asian Paints_FY2026"]) * rev
    for k in ["s_rm", "s_disc", "s_vol", "s_fx", "s_margin_up"]:
        n[k + "_e"] = n[k] / ebitda
        n[k + "_eps"] = n[k] * (1 - TAX) / n["shares_cr"]
        n[k + "_p"] = n[k] * (1 - TAX) / pat
    n["s_pe5"] = 5 * n["eps_ttm"]
    n["avg_turn3"] = (n["REV_FY2024"] + n["REV_FY2025"] + n["REV_FY2026"]) / 3
    n["s_cci"] = 0.10 * n["avg_turn3"]
    n["s_cci_ps"] = n["s_cci"] / n["shares_cr"]
    return n


# ------------------------------------------------------------------------------------------------------------------
# charts (150 dpi PNG, saved in figures/ and used by the report and README)
# ------------------------------------------------------------------------------------------------------------------
HALF = (3.45, 2.45)   # half-page-width charts (inches): fonts print at about their nominal size
FULL = (6.9, 2.15)    # full-width charts


def style(ax, title: str, ylabel: str, src: str) -> None:
    """Common look: left title, light grid, wrapped source note at the bottom."""
    import textwrap

    wide = ax.figure.get_figwidth() > 5
    ax.set_title(title, fontsize=8.6 if not wide else 9.2, loc="left", fontweight="bold", color="#0b3d63")
    ax.set_ylabel(ylabel, fontsize=7.2)
    ax.tick_params(labelsize=6.8)
    ax.grid(axis="y", color="#dddddd", linewidth=0.6)
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    note = "\n".join(textwrap.wrap(src, 150 if wide else 78))
    ax.figure.text(0.01, 0.01, note, fontsize=5.6, color="#666666", ha="left", va="bottom")


def save(fig, name: str, bottom: float = 0.09) -> str:
    fig.tight_layout(rect=(0, bottom, 1, 1))
    fig.savefig(FIG / name, dpi=150)
    plt.close(fig)
    return name


def charts(d: dict, n: dict) -> dict[str, str]:
    FIG.mkdir(exist_ok=True)
    out: dict[str, str] = {}
    x = list(range(len(COS)))

    # 1. price vs NIFTY, rebased at the 5-year base date used for the returns (last close on or before ASOF - 5y)
    px = d["px"][["Asian Paints", "NIFTY 50"]].dropna()
    base_day = px.index[px.index <= px.index[-1] - pd.DateOffset(years=5)][-1]
    px = px[px.index >= base_day]
    reb = px / px.iloc[0] * 100
    n["px_base_day"] = base_day.strftime("%d-%b-%Y")
    fig, ax = plt.subplots(figsize=FULL)
    for c in reb.columns:
        ax.plot(reb.index, reb[c], color=COL[c], lw=1.4 if c == "Asian Paints" else 1.1,
                label=f"{c} ({spc(reb[c].iloc[-1] / 100 - 1)})")
    ax.axhline(100, color="#999999", lw=0.6, ls=":")
    ax.legend(fontsize=7.2, frameon=False, loc="upper left")
    style(ax, f"Share price vs NIFTY 50, rebased to 100 on {n['px_base_day']} (closing prices)", "Index (100 = start)",
          f"Source: Yahoo Finance (yfinance) daily closes, ASIANPAINT.NS and ^NSEI, to {ASOF}. Price return, dividends excluded.")
    out["price"] = save(fig, "fig1_price_vs_nifty.png", 0.06)

    # 2. ROE excl. one-offs and ROCE, FY2026
    fig, ax = plt.subplots(figsize=HALF)
    w = 0.38
    roe = [n[f"ROE_ADJ_{c}_FY2026"] * 100 for c in COS]
    roce = [n[f"ROCE_{c}_FY2026"] * 100 for c in COS]
    b1 = ax.bar([i - w / 2 for i in x], roe, w, color=[COL[c] for c in COS])
    b2 = ax.bar([i + w / 2 for i in x], roce, w, color=[COL[c] for c in COS], alpha=0.45)
    for bars in (b1, b2):
        for b in bars:
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.4, f"{b.get_height():.1f}", ha="center",
                    fontsize=5.8)
    ax.set_xticks(x, [SHORT[c] for c in COS], fontsize=6.6)
    ax.set_ylim(0, max(roe + roce) * 1.22)
    ax.legend([b1[0], b2[0]], ["ROE excl. one-offs (solid)", "ROCE (light)"], fontsize=6.2, frameon=False,
              loc="upper right")
    style(ax, "FY2026 ROE excl. one-offs and ROCE", "%",
          "Source: AsianPaints_Ratio_Analysis.xlsx (Ratios). JSW Dulux excludes its slump-sale gain.")
    out["returns"] = save(fig, "fig2_returns_fy2026.png")

    # 3. EBITDA margin trend
    fig, ax = plt.subplots(figsize=HALF)
    for c in COS:
        ax.plot([f[2:] for f in FYS], [n[f"EBITDAM_{c}_{fy}"] * 100 for fy in FYS], marker="o", ms=2.5, color=COL[c],
                lw=1.8 if c == "Asian Paints" else 1.0, label=SHORT[c])
    lo = min(n[f"EBITDAM_{c}_{fy}"] for c in COS for fy in FYS) * 100
    hi = max(n[f"EBITDAM_{c}_{fy}"] for c in COS for fy in FYS) * 100
    ax.set_ylim(lo - 1.5, hi + 5.5)
    ax.legend(fontsize=6, frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(0.5, 1.02))
    style(ax, "EBITDA margin before other income", "% of revenue",
          "Source: AsianPaints_Ratio_Analysis.xlsx (Ratios). Consolidated; Indigo FY2022-23 standalone.")
    out["margins"] = save(fig, "fig3_ebitda_margin_trend.png")

    # 4. working-capital days FY2026
    fig, ax = plt.subplots(figsize=HALF)
    inv = [n[f"INVD_{c}_FY2026"] for c in COS]
    rec = [n[f"RECD_{c}_FY2026"] for c in COS]
    pay = [-n[f"PAYD_{c}_FY2026"] for c in COS]
    ccc = [n[f"CCC_{c}_FY2026"] for c in COS]
    ax.bar(x, inv, 0.55, color="#0b3d63", label="Inventory days")
    ax.bar(x, rec, 0.55, bottom=inv, color="#7fa7c9", label="Receivable days")
    ax.bar(x, pay, 0.55, color="#e0a96d", label="Payable days (minus)")
    ax.scatter(x, ccc, color="#c0392b", zorder=3, s=14, label="Cash conversion cycle")
    for i, v in enumerate(ccc):
        ax.text(i + 0.3, v, f"{v:.0f}", fontsize=6, color="#c0392b", va="center")
    ax.axhline(0, color="#555555", lw=0.6)
    ax.set_xticks(x, [SHORT[c] for c in COS], fontsize=6.6)
    ax.legend(fontsize=5.8, frameon=False, ncol=2, loc="upper center", bbox_to_anchor=(0.5, 1.03))
    ax.set_ylim(min(pay) - 10, max(i + r for i, r in zip(inv, rec)) + 70)
    style(ax, "FY2026 working-capital days", "Days",
          "Source: AsianPaints_Ratio_Analysis.xlsx (Ratios). Inventory and payable days on COGS, receivables on revenue.")
    out["wc"] = save(fig, "fig4_working_capital_days.png")

    # 5. quarterly revenue and EBITDA margin (full width)
    qt = d["qtr"]
    cols = list(qt.columns)[-8:]
    sales = [float(qt.loc["Sales", c]) for c in cols]
    opm = [float(qt.loc["Operating Profit", c]) / float(qt.loc["Sales", c]) * 100 for c in cols]
    fig, ax = plt.subplots(figsize=FULL)
    ax.bar(range(len(cols)), sales, 0.6, color="#7fa7c9", label="Revenue from operations (Rs crore, left)")
    for i, v in enumerate(sales):
        ax.text(i, v / 2, f"{v:,.0f}", ha="center", va="center", fontsize=6.8, color="white", fontweight="bold")
    ax.set_xticks(range(len(cols)), [c.replace(" 20", "-") for c in cols], fontsize=6.8)
    ax.set_ylim(0, max(sales) * 1.65)
    ax2 = ax.twinx()
    ax2.plot(range(len(cols)), opm, color="#c0392b", marker="o", ms=3.5, lw=1.4, label="EBITDA margin (%, right)")
    for i, v in enumerate(opm):
        ax2.text(i, v + 0.6, f"{v:.1f}%", ha="center", fontsize=6.6, color="#c0392b")
    ax2.set_ylim(min(opm) - 12, max(opm) + 6.5)
    ax2.tick_params(labelsize=6.8)
    ax2.spines["top"].set_visible(False)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, fontsize=6.6, frameon=False, loc="upper left", ncol=2)
    style(ax, "Asian Paints quarterly revenue and EBITDA margin (consolidated)", "Rs crore",
          "Source: Screener.in consolidated quarterly results (company filings). EBITDA = operating profit before other income.")
    out["quarterly"] = save(fig, "fig5_quarterly.png", 0.06)

    # 6. shareholding
    sh = d["sh"]
    qs = list(sh.columns)
    cats = [("Promoters", "#0b3d63"), ("FIIs", "#2a9df4"), ("DIIs", "#5b9a2e"), ("Public", "#e0a96d"),
            ("Others", "#bbbbbb")]
    fig, ax = plt.subplots(figsize=HALF)
    bottom = [0.0] * len(qs)
    for k, c in cats:
        vals = [float(sh.loc[k, q]) for q in qs]
        ax.bar(range(len(qs)), vals, 0.7, bottom=bottom, color=c, label=k)
        if k in ("Promoters", "FIIs", "DIIs", "Public"):
            for i in (0, len(qs) - 1):
                ax.text(i, bottom[i] + vals[i] / 2, f"{vals[i]:.1f}", ha="center", va="center", fontsize=5.4,
                        color="white" if k != "Public" else "black")
        bottom = [b + v for b, v in zip(bottom, vals)]
    ax.set_xticks(range(len(qs)), [q.replace(" 20", "-") if i % 2 == 1 else "" for i, q in enumerate(qs)],
                  fontsize=6)
    ax.set_ylim(0, 118)
    ax.set_yticks([0, 20, 40, 60, 80, 100])
    ax.legend(fontsize=5.8, frameon=False, ncol=5, loc="upper center", bbox_to_anchor=(0.5, 1.03),
              handlelength=1, columnspacing=0.8)
    style(ax, "Shareholding pattern by quarter", "% of shares",
          "Source: Screener.in shareholding pattern (exchange filings), quarter ends Dec-2023 to Sep-2026.")
    out["shareholding"] = save(fig, "fig6_shareholding.png")

    # 7. Asian Paints trend: margins and returns
    fig, ax = plt.subplots(figsize=HALF)
    ap = "Asian Paints"
    for code, lab, c in [("GM", "Gross margin", "#7fa7c9"), ("ROCE", "ROCE", "#0b3d63"),
                         ("ROE_ADJ", "ROE excl. one-offs", "#c0392b"), ("EBITDAM", "EBITDA margin", "#e07b00")]:
        vals = [n[f"{code}_{ap}_{fy}"] * 100 for fy in FYS]
        ax.plot([f[2:] for f in FYS], vals, marker="o", ms=2.5, color=c, lw=1.3, label=lab)
        ax.text(len(FYS) - 1 + 0.12, vals[-1], f"{vals[-1]:.1f}", fontsize=5.8, color=c, va="center")
    ax.legend(fontsize=6, frameon=False, ncol=2, loc="upper center", bbox_to_anchor=(0.5, 1.03))
    ax.set_ylim(10, 60)
    ax.set_xlim(-0.3, len(FYS) - 0.4)
    style(ax, "Asian Paints: margins and returns", "%",
          "Source: AsianPaints_Ratio_Analysis.xlsx (Ratios), consolidated.")
    out["ap_trend"] = save(fig, "fig7_ap_margins_returns.png")

    val = n.get("val") or {}
    # 8. football field: Project 3's bars (outputs/football_field.csv) + this report's relative value and target
    if P3_FF and val:
        bars = [(r["method"], r["low_rs"], r["high_rs"], r["mid_rs"], "#4472c4") for r in P3_FF
                if r["bar_type"] == "valuation"]
        bars.append((f"Premium-adjusted P/E on FY2028E EPS (premium {P3['rel_p25'] * 100:.0f}-{P3['rel_p75'] * 100:.0f}%)",
                     P3["rel_low"], P3["rel_high"], P3["relative_value"], "#e07b00"))
        bars += [(r["method"], r["low_rs"], r["high_rs"], r["mid_rs"], "#bfbfbf") for r in P3_FF
                 if r["bar_type"] == "context"]
        fig, ax = plt.subplots(figsize=(6.9, 2.6))
        ys = list(range(len(bars)))[::-1]
        for y, (lab, lo, hi, mid, c) in zip(ys, bars):
            ax.barh(y, hi - lo, left=lo, height=0.58, color=c, edgecolor="#1f3a5a", lw=0.5)
            if pd.notna(mid):
                ax.plot([mid, mid], [y - 0.29, y + 0.29], color="black", lw=1.1)
            ax.text(lo - 25, y, f"{lo:,.0f}", ha="right", va="center", fontsize=6.4)
            ax.text(hi + 25, y, f"{hi:,.0f}", ha="left", va="center", fontsize=6.4)
        ax.set_yticks(ys, [b[0] for b in bars], fontsize=6.6)
        ax.axvline(n["price"], color="#c0392b", ls="--", lw=1.2)
        ax.axvline(val["target"], color="#2e7d32", ls="-", lw=1.4)
        top = len(bars) - 0.45
        ax.text(n["price"] + 20, top, f"Price Rs {n['price']:,.0f}", color="#c0392b", fontsize=6.6, va="bottom")
        ax.text(val["target"] - 20, top, f"Target Rs {val['target']:,.0f}", color="#2e7d32", fontsize=6.6,
                va="bottom", ha="right", fontweight="bold")
        ax.set_ylim(-0.6, len(bars) - 0.1)
        ax.set_xlim(0, max(b[2] for b in bars) * 1.1)
        ax.set_xlabel("Value per share (Rs)", fontsize=7)
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
        ax.grid(axis="x", color="#e5e5e5", lw=0.6)
        ax.tick_params(axis="x", labelsize=6.6)
        for s_ in ["top", "right"]:
            ax.spines[s_].set_visible(False)
        ax.set_title("Football field: value per share by method (Rs)", fontsize=9.2, loc="left", fontweight="bold",
                     color="#0b3d63", pad=12)
        ax.figure.text(0.01, 0.01, "Blue bars and grey context bars: Project 3 (outputs/football_field.csv); black line = "
                       "base case or median. Orange bar and target line: this report (Section 6).\nPrice: Yahoo Finance "
                       "close, 30-Oct-2026. Analyst targets: S&P Global via stockanalysis.com.", fontsize=5.6,
                       color="#666666", ha="left", va="bottom")
        out["ff"] = save(fig, P3["football_field_png"], 0.08)

    # 9. Asian Paints' trailing P/E premium to the peer median, 5 years (build/relative_value.py)
    hist = d.get("rel_hist")
    if hist is not None and len(hist):
        fig, ax = plt.subplots(figsize=HALF)
        prem = hist["ap_premium"] * 100
        ax.fill_between(prem.index, P3["rel_p25"] * 100, P3["rel_p75"] * 100, color="#dde7f0",
                        label="25th-75th percentile")
        ax.plot(prem.index, prem, color="#0b3d63", lw=0.9, label="Premium to peer median P/E")
        ax.axhline(P3["rel_premium"] * 100, color="#e07b00", lw=1.2, ls="--",
                   label=f"5-year median {P3['rel_premium'] * 100:.0f}%")
        ax.axhline(0, color="#999999", lw=0.6)
        ax.scatter([prem.index[-1]], [prem.iloc[-1]], color="#c0392b", s=12, zorder=4,
                   label=f"30-Oct-2026: {P3['rel_premium_now'] * 100:+.0f}%")
        ax.set_ylim(min(-10, prem.min() - 5), prem.max() + 12)
        ax.legend(fontsize=5.8, frameon=False, ncol=1, loc="upper left")
        style(ax, "P/E premium to the peer median", "% above the peer median P/E",
              "Source: Yahoo Finance closes x current shares / PAT to owners excl. one-offs of the last reported year "
              "(ratio workbook). Peers: Berger, Kansai, JSW Dulux, Indigo.")
        out["premium"] = save(fig, "fig9_pe_premium.png", 0.11)
    return out


# ------------------------------------------------------------------------------------------------------------------
# HTML
# ------------------------------------------------------------------------------------------------------------------
CSS = """
@page { size: A4; margin: 11mm 11mm 12mm 11mm; }
* { box-sizing: border-box; }
body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 8.6pt; line-height: 1.32; color: #1b1b1b; margin: 0; }
.page1 { break-after: page; }
.appendix table { font-size: 7.2pt; }
.appendix td { padding: 0.38mm 1.0mm; }
.appendix th { padding: 0.55mm 1.0mm; }
h2, h3 { break-after: avoid; }
table, img.chart, .grid2, .keep, .box, .draft { break-inside: avoid; }
td.l, th.l { text-align: left; }
.topbar { display: flex; justify-content: space-between; font-size: 7.6pt; color: #555; border-bottom: 2px solid #0b3d63;
          padding-bottom: 1mm; margin-bottom: 2mm; }
h1 { font-size: 15pt; color: #0b3d63; margin: 0 0 1mm 0; line-height: 1.15; }
h2 { font-size: 11pt; color: #0b3d63; border-bottom: 1.2px solid #0b3d63; margin: 3mm 0 1.5mm 0; padding-bottom: 0.6mm; }
h3 { font-size: 9.2pt; color: #0b3d63; margin: 2.2mm 0 0.8mm 0; }
p { margin: 0 0 1.4mm 0; }
ul { margin: 0 0 1.4mm 0; padding-left: 4.2mm; }
li { margin-bottom: 0.7mm; }
table { border-collapse: collapse; width: 100%; font-size: 7.7pt; margin: 0.8mm 0 1.6mm 0; }
th { background: #0b3d63; color: #fff; font-weight: 600; padding: 0.8mm 1.2mm; text-align: right; }
td { padding: 0.55mm 1.2mm; border-bottom: 0.5px solid #d4d4d4; text-align: right; }
th:first-child, td:first-child { text-align: left; }
td.l, th.l { text-align: left; }
tr.sub td { background: #eef3f8; font-weight: 600; }
tr.ap td { background: #f3f7fb; font-weight: 600; }
.p3 { background: #fff2cc; color: #7a5200; font-weight: 700; border: 1px dashed #c9a400; padding: 0 0.6mm;
      font-size: 0.92em; white-space: nowrap; }
.note { font-size: 7pt; color: #555; }
.small { font-size: 7.4pt; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 4mm; }
.grid-sum { display: grid; grid-template-columns: 63mm 1fr; gap: 4mm; }
.box { border: 1px solid #0b3d63; background: #f3f7fb; padding: 2mm 2.4mm; }
.box table { font-size: 7.8pt; margin: 0; }
.box td { border-bottom: 0.5px solid #c9d6e3; padding: 0.55mm 0.8mm; }
.rating { font-size: 13pt; font-weight: 700; color: #0b3d63; text-align: center; margin: 0 0 1.5mm 0; }
.draft { background: #fff2cc; border: 1px dashed #c9a400; padding: 1.2mm 2mm; font-size: 7.6pt; margin-bottom: 2mm; }
img.chart { width: 100%; display: block; margin: 0.5mm 0 1.2mm 0; }
.src { font-size: 6.3pt; line-height: 1.24; color: #444; columns: 2; column-gap: 5mm; }
.src p { margin: 0 0 0.7mm 0; break-inside: avoid; overflow-wrap: anywhere; }
.pill { display: inline-block; background: #0b3d63; color: #fff; padding: 0 1.4mm; border-radius: 1mm; font-size: 7.2pt; }
.r-sell { color: #b03a2e; } .r-buy { color: #2e7d32; } .r-hold { color: #8a6d00; }
.compact table { font-size: 7.3pt; }
.compact td { padding: 0.42mm 1.0mm; }
.compact th { padding: 0.6mm 1.0mm; }
.grid-val { display: grid; grid-template-columns: 1.08fr 0.92fr; gap: 4mm; }
"""


def table(header: list[str], rows: list[list[str]], cls: list[str] | None = None, widths: list[str] | None = None,
          left: set[int] | None = None) -> str:
    """HTML table. cls = optional row classes; widths = column widths; left = column indexes to left-align (text)."""
    left = left or set()
    cells = []
    for i, c in enumerate(header):
        style_attr = f" style='width:{widths[i]}'" if widths else ""
        lc = " class='l'" if i in left else ""
        cells.append(f"<th{style_attr}{lc}>{c}</th>")
    h = "".join(cells)
    body = []
    for i, r in enumerate(rows):
        k = f" class='{cls[i]}'" if cls and cls[i] else ""
        body.append(f"<tr{k}>" + "".join(f"<td{(' class=' + chr(39) + 'l' + chr(39)) if j in left else ''}>{c}</td>"
                                         for j, c in enumerate(r)) + "</tr>")
    return f"<table><thead><tr>{h}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def rating_for(upside: float) -> str:
    return "BUY" if upside > 0.15 else ("SELL" if upside < -0.10 else "HOLD")


def build_html(d: dict, n: dict, figs: dict[str, str]) -> str:
    F = d["F"]
    ap = "Asian Paints"
    q = n["q2"]
    val = n.get("val") or {}
    if val:
        tp, up = val["target"], val["upside"]
        rating_html, tp_html, up_html = val["rating"], rs(tp), spc(up)
        rating_cls = {"BUY": "r-buy", "HOLD": "r-hold", "SELL": "r-sell"}[val["rating"]]
    else:
        rating_html, tp_html, up_html = ph("rating"), ph("target_price"), ph("upside")
        rating_cls = ""
    alt = {a["name"]: a for a in val.get("alts", [])}

    def g(basis: str, metric: str, col: str) -> float:
        return float(q.loc[(basis, metric), col])

    def yoy(basis: str, metric: str, cur: str = "Q2FY27", prev: str = "Q2FY26") -> float:
        return g(basis, metric, cur) / g(basis, metric, prev) - 1

    m_q2 = g("Consolidated", "PBDIT (before other income)", "Q2FY27") / g("Consolidated", "Net sales", "Q2FY27")
    m_q2p = g("Consolidated", "PBDIT (before other income)", "Q2FY26") / g("Consolidated", "Net sales", "Q2FY26")
    m_h1 = g("Consolidated", "PBDIT (before other income)", "H1FY27") / g("Consolidated", "Net sales", "H1FY27")
    m_h1p = g("Consolidated", "PBDIT (before other income)", "H1FY26") / g("Consolidated", "Net sales", "H1FY26")

    def sm(col: str) -> float:   # standalone PBDIT margin (the basis of management's 18-20% guidance band)
        return g("Standalone", "PBDIT (before other income)", col) / g("Standalone", "Net sales", col)

    s_q2, s_q2p, s_h1, s_h1p = sm("Q2FY27"), sm("Q2FY26"), sm("H1FY27"), sm("H1FY26")
    cgm, cgm0 = g("Margin", "Consolidated gross margin", "Q2FY27"), g("Margin", "Consolidated gross margin", "Q2FY26")
    n.update({"m_q2": m_q2, "m_q2p": m_q2p, "m_h1": m_h1, "m_h1p": m_h1p, "s_q2": s_q2, "s_h1": s_h1})

    # ---------- key financials (page 1) ----------
    def est(key_rev: str, key_ebitda: str, key_pat: str, key_eps: str, prev_rev: float | None) -> list[str]:
        r, e, p, s = (P3[k] for k in (key_rev, key_ebitda, key_pat, key_eps))
        return [ph(key_rev), (spc(r / prev_rev - 1) if (r is not None and prev_rev) else ph(key_rev + "_growth")),
                ph(key_ebitda), (pc(e / r) if (e is not None and r is not None) else ph(key_ebitda + "_margin")),
                ph(key_pat), ph(key_eps, f2), (xx(n["price"] / s, 1) if s is not None else ph(key_eps + "_pe")),
                "-", "-"]

    a25 = [f0(n["REV_FY2025"]), spc(n["REVG_Asian Paints_FY2025"]), f0(n["EBITDA_FY2025"]),
           pc(n["EBITDAM_Asian Paints_FY2025"]), f0(n["PATOWN_FY2025"]), f2(n["EPS_FY2025"]),
           xx(n["price"] / n["EPS_FY2025"], 1), pc(n["ROE_ADJ_Asian Paints_FY2025"]), f2(n["DPS_FY2025"])]
    a26 = [f0(n["REV_FY2026"]), spc(n["REVG_Asian Paints_FY2026"]), f0(n["EBITDA_FY2026"]),
           pc(n["EBITDAM_Asian Paints_FY2026"]), f0(n["PATOWN_FY2026"]), f2(n["EPS_FY2026"]),
           xx(n["price"] / n["EPS_FY2026"], 1), pc(n["ROE_ADJ_Asian Paints_FY2026"]), f2(n["DPS_FY2026"])]
    e27 = est("fy27e_revenue", "fy27e_ebitda", "fy27e_pat", "fy27e_eps", n["REV_FY2026"])
    e28 = est("fy28e_revenue", "fy28e_ebitda", "fy28e_pat", "fy28e_eps", P3["fy27e_revenue"])
    ce27 = P3["cons_ebitda27"]
    cons = [f0(n["cons_rev27"]), spc(n["cons_rev27"] / n["REV_FY2026"] - 1), ph("cons_ebitda27"),
            pc(ce27 / n["cons_rev27"]) if ce27 else ph("cons_ebitda27_margin"), "", f2(n["cons_eps27"]),
            xx(n["cons_pe27"], 1), "", f2(n["DPS_FY2027"]) if "DPS_FY2027" in n else ""]
    c28r, c28e = P3["cons_rev28"], P3["cons_eps28"]
    cons28 = [ph("cons_rev28"), spc(c28r / n["cons_rev27"] - 1) if c28r else ph("cons_rev28_growth"), "", "", "",
              ph("cons_eps28", f2), xx(n["price"] / c28e, 1) if c28e else ph("cons_eps28_pe"), "", ""]
    labels = ["Revenue (&#8377; cr)", "Revenue growth", "EBITDA (&#8377; cr)", "EBITDA margin", "PAT to owners (&#8377; cr)",
              "EPS (&#8377;)", f"P/E at {rs(n['price'])} (x)", "ROE excl. one-offs", "Dividend per share (&#8377;)"]
    kf_rows = [[labels[i], a25[i], a26[i], e27[i], e28[i], cons[i], cons28[i]] for i in range(len(labels))]
    kf = table(["Year to March", "FY25A", "FY26A", "FY27E (P3)", "FY28E (P3)", "Consensus FY27E", "Consensus FY28E"],
               kf_rows)

    nodcf = alt.get("No DCF", {})
    thesis_bullets = f"""
<ul>
<li><b>Best business in the group.</b> FY2026 ROE excluding one-offs {pc(n['ROE_ADJ_Asian Paints_FY2026'])} and ROCE
{pc(n['ROCE_Asian Paints_FY2026'])}, against peer medians of {pc(n['med_ROE_ADJ'])} and {pc(n['med_ROCE'])}; first of five on
our weighted ratio scorecard for FY2026 and for the 5-year average.</li>
<li><b>Growth is back, margins are not.</b> H1 FY27 consolidated net sales rose {spc(yoy('Consolidated', 'Net sales', 'H1FY27', 'H1FY26'))};
Q2 decorative volume grew {g('Growth', 'Decorative India volume growth', 'Q2FY27'):.1f}%. But Q2 PBDIT margin fell to {pc(m_q2)}
from {pc(m_q2p)} as input costs rose faster than prices.</li>
<li><b>Competition has changed the industry.</b> Birla Opus claims about 10% of decorative revenue within two years and
about 24% of organised capacity; JSW now owns Dulux. Industry estimates put Asian Paints' share near 52%, down from about 59%.</li>
<li><b>The price assumes a long runway.</b> At {xx(n['cons_pe27'], 1)} FY27E consensus EPS, free cash flow must grow
{ph('reverse_dcf_g', lambda v: pc(v, 2))} a year forever after FY2031 to justify {rs(n['price'])} (Project 3 reverse DCF).
Project 3's DCF gives {ph('dcf_value', rs)} and peer P/E multiples {ph('comps_q1', rs)}-{ph('comps_q3', rs)}.</li>
<li><b>{rating_html}, 12-month target {tp_html} ({up_html}).</b> Weights: 25% DCF, 25% peer comps, 50% a P/E that keeps
Asian Paints' 5-year median premium of {ph('rel_premium', lambda v: pc(v, 0))} to peers, on FY2028E EPS
({ph('relative_value', rs)}). With no weight on the DCF the target is {rs(nodcf['target']) if nodcf else ph('nodcf')}
({spc(nodcf['upside']) if nodcf else ''}, {nodcf.get('rating', '').title() if nodcf else ''}).</li>
</ul>"""

    draft_note = ""
    if is_draft():
        draft_note = ("<div class='draft'><b>DRAFT (phase 1).</b> Yellow tags such as <span class='p3'>{{P3:dcf_value}}</span> "
                      "are values that will come from Project 3 (comps and DCF). The rating is not set until then.</div>")

    summary_box = f"""
<div class='box'>
<div class='rating {rating_cls}'>Rating: {rating_html}</div>
<table>
<tr><td>12-month target</td><td>{tp_html}</td></tr>
<tr><td>Price, {ASOF}</td><td>{rs(n['price'], 2)}</td></tr>
<tr><td>Upside / (downside)</td><td>{up_html}</td></tr>
<tr><td>Market cap (&#8377; cr)</td><td>{f0(n['mcap'])}</td></tr>
<tr><td>52-week range (&#8377;)</td><td>{f0(n['lo52'])} - {f0(n['hi52'])}</td></tr>
<tr><td>Shares (cr)</td><td>{f2(n['shares_cr'])}</td></tr>
<tr><td>P/E, trailing</td><td>{xx(n['pe_ttm'], 1)}</td></tr>
<tr><td>P/E, FY27E consensus</td><td>{xx(n['cons_pe27'], 1)}</td></tr>
<tr><td>Price / book</td><td>{xx(n['price'] / n['bv'], 1)}</td></tr>
<tr><td>Dividend yield</td><td>{pc(n['dy'], 2)}</td></tr>
<tr><td>Promoters, {n['sh_q'].replace(' 20', '-')}</td><td>{pc(n['sh_Promoters'], 2)}</td></tr>
<tr><td>NIFTY 50</td><td>{f2(n['nifty'])}</td></tr>
<tr><td>Return 1y/3y/5y</td><td>{spc(n['ret1'], 0)}/{spc(n['ret3'], 0)}/{spc(n['ret5'], 0)}</td></tr>
<tr><td>NIFTY 1y/3y/5y</td><td>{spc(n['nifty_ret1'], 0)}/{spc(n['nifty_ret3'], 0)}/{spc(n['nifty_ret5'], 0)}</td></tr>
</table></div>"""

    page1 = f"""
<section class='page1'>
<div class='topbar'><span>Equity research | Initiation of coverage | India, paints and coatings</span><span>{REPORT_DATE} | prices as of {ASOF}</span></div>
<h1>Asian Paints Ltd (NSE: ASIANPAINT): the best business in Indian paints, priced as if the new competition will not matter</h1>
{draft_note}
<div class='grid-sum'>
<div>{summary_box}
<p class='note' style='margin-top:1.5mm'>Sources: Yahoo Finance, Screener.in (market cap, P/E, book value, dividend yield),
StockAnalysis.com (consensus, {n['cons_n27']} analysts), company filings. Consolidated figures, &#8377; crore unless stated.</p></div>
<div><h3 style='margin-top:0'>Investment summary</h3>{thesis_bullets}</div>
</div>
<h3>Key financials (consolidated)</h3>
{kf}
<p class='note'>FY25A-FY26A from company filings via the ratio workbook; EPS = PAT to owners / {f2(n['shares_cr'])} cr shares.
FY27E-FY28E from Project 3's DCF model (FY27E = H1 FY27 actual + H2 forecast). ROE and dividends are not forecast.
Consensus = S&amp;P Global via StockAnalysis.com (FY27E downloaded 1-Nov-2026; FY28E as collected by Project 3).</p>
<img class='chart' src='../figures/{figs['price']}' alt='price vs NIFTY'>
</section>"""

    # ---------- page 2: thesis ----------
    rev_ratio = n["REV_FY2026"] / n["REV26_Berger Paints"]
    page2 = f"""
<section class='flow'>
<h2>1. Investment thesis</h2>
<h3>Pillar 1: still the best business in Indian paints</h3>
<p>Asian Paints earns more on its capital than any listed rival. In FY2026 its ROE excluding one-offs was
{pc(n['ROE_ADJ_Asian Paints_FY2026'])} (peer median {pc(n['med_ROE_ADJ'])}), ROCE {pc(n['ROCE_Asian Paints_FY2026'])}
(median {pc(n['med_ROCE'])}) and EBITDA margin {pc(n['EBITDAM_Asian Paints_FY2026'])} (median {pc(n['med_EBITDAM'])}).
Cash conversion was the best of the five: cash from operations was {pc(n['CFOE_Asian Paints_FY2026'], 0)} of EBITDA and the
free-cash-flow margin {pc(n['FCFM_Asian Paints_FY2026'])} (median {pc(n['med_FCFM'])}). The balance sheet holds net cash
(net debt / EBITDA {xx(n['NDEBITDA_Asian Paints_FY2026'])}). The moat is scale and reach: revenue of &#8377;{f0(n['REV_FY2026'])} cr
is {rev_ratio:.1f}x Berger's, it billed 72,873 dealers in FY2026, runs 2.29 million KL of in-house decorative capacity and
added about 6,000 retail touchpoints in the year. Scale spreads advertising, tinting machines and logistics over more litres,
which is why Asian Paints converts a similar gross margin ({pc(n['GM_Asian Paints_FY2026'])} vs Indigo's
{pc(n['GM_Indigo Paints_FY2026'])}) into a higher operating margin.</p>
<h3>Pillar 2: volumes have recovered; margins carry the near-term risk</h3>
<p>Demand improved through FY2026 and H1 FY27. Consolidated net sales grew {spc(yoy('Consolidated', 'Net sales'))} in Q2 FY27
and {spc(yoy('Consolidated', 'Net sales', 'H1FY27', 'H1FY26'))} in H1. Decorative volume grew {g('Growth', 'Decorative India volume growth', 'Q2FY27'):.1f}%
in Q2 (about {g('Growth', 'Decorative India volume growth', 'H1FY27'):.0f}% in H1), and industrial coatings grew
{g('Growth', 'Industrial coatings value growth', 'Q2FY27'):.1f}%. The problem is cost. Crude-linked raw materials rose sharply in 2026;
management estimated inflation near 20% in May against about 11% of price increases. Standalone gross margin fell to
{g('Margin', 'Standalone gross margin', 'Q2FY27'):.1f}% in Q2 ({(g('Margin', 'Standalone gross margin', 'Q2FY27') - g('Margin', 'Standalone gross margin', 'Q2FY26')) * 100:+.0f} bp)
and consolidated PBDIT margin to {pc(m_q2)}. Management kept its 18-20% standalone EBITDA margin band for FY27
(standalone H1: {pc(s_h1)}; Q2: {pc(s_q2)}),
is taking further staggered price increases and has commissioned phase 1 of its VAE emulsion plant, which it expects to give
a 300-500 bp cost advantage on the products that use it. The margin path in H2 FY27 is the main swing factor for earnings.</p>
<h3>Pillar 3: competition is now permanent, so the premium has to be earned</h3>
<p>Two large groups now compete head-on. Grasim launched Birla Opus in 2024, built 1,332 million litres of capacity (about
24% of the organised industry) and says it reached about 10% revenue share of decorative paints within two years. The JSW
group, whose JSW Paints is about five years old, bought 60.76% of Akzo Nobel India in December 2025 and renamed it JSW Dulux. Industry estimates put Asian Paints' decorative share at about 59%
around March 2024 and about 52% a year later. The effect is visible in our ratios: ROE excluding one-offs fell from
{pc(n['ROE_ADJ_Asian Paints_FY2024'])} in FY2024 to {pc(n['ROE_ADJ_Asian Paints_FY2026'])} in FY2026, EBITDA margin from
{pc(n['EBITDAM_Asian Paints_FY2024'])} to {pc(n['EBITDAM_Asian Paints_FY2026'])}, and revenue grew only {pc(n['cagr3'])} a year
over FY2023-FY2026 against {pc(n['cagr5'])} a year over FY2021-FY2026. Management said in May 2026 that discounting to
dealers and contractors shows no let-up.</p>
<h3>What the price already assumes, and our rating</h3>
<p>At {rs(n['price'])} the stock trades on {xx(n['pe_ttm'], 1)} trailing earnings and {xx(n['cons_pe27'], 1)} FY27E consensus EPS
of {rs(n['cons_eps27'], 2)}. Listed peers trade at {xx(n['pe_Berger Paints'], 1)} (Berger), {xx(n['pe_JSW Dulux'], 1)} (JSW Dulux),
{xx(n['pe_Indigo Paints'], 1)} (Indigo) and {xx(n['pe_Kansai Nerolac'], 1)} (Kansai) trailing earnings (Screener, {ASOF}).
The share price fell {spc(n['ret5'])} in five years while the NIFTY 50 rose {spc(n['nifty_ret5'])}, but the whole sector fell
with it: the peer median trailing P/E dropped from {ph('peer_pe_start', lambda v: xx(v, 1))} to {ph('peer_pe_now', lambda v: xx(v, 1))}
(our calculation, Section 6). Relative to peers Asian Paints is not cheaper than usual: its P/E premium is
{ph('rel_premium_now', lambda v: pc(v, 0))} against a 5-year median of {ph('rel_premium', lambda v: pc(v, 0))}. On cash flows the gap is
wider. To reach {rs(n['price'])}, Project 3's DCF needs free cash flow to grow {ph('reverse_dcf_g', lambda v: pc(v, 2))} a year
forever after FY2031, which means the business would still be worth about {xx(n.get('impl_exit', float('nan')), 0)} EBITDA in
FY2031, close to today's {ph('ap_ev_ebitda', lambda v: xx(v, 1))}. Revenue grew {pc(n['cagr3'])} a year over FY2023-FY2026. Our
12-month target of {tp_html} ({up_html}) blends DCF, peer comps and a premium-adjusted P/E (Section 6). Under our rule
(Buy above +15%, Hold from -10% to +15%, Sell below -10%) the rating is <b>{rating_html}</b>. The call is about the price:
Asian Paints remains the strongest business in the group.</p>
<p class='note'>Sources: ratio workbook (outputs/ratios_fy2022_fy2026.csv, peer_comparison_fy2026.csv); Q2 FY27 results and
investor presentation (29-Oct-2026); Q4 FY26 call transcript (29-May-2026); Grasim and press reports listed in Appendix C.</p>
</section>"""

    # ---------- page 3: company and industry ----------
    seg_rows = []
    for basis, metric, lab in [("Consolidated", "Net sales", "Consolidated net sales"),
                               ("Standalone", "Net sales", "Standalone (mainly decorative India)"),
                               ("Segment", "International net sales", "International (14 countries)"),
                               ("Segment", "PPGAP net sales (auto/industrial JV)", "PPGAP JV: auto OE, refinish, marine"),
                               ("Segment", "APPPG net sales (protective/powder JV)", "APPPG JV: protective, powder"),
                               ("Segment", "Kitchen net sales", "Home decor: kitchens"),
                               ("Segment", "Bath fittings net sales", "Home decor: bath fittings")]:
        seg_rows.append([lab, f1(g(basis, metric, "Q2FY27")), spc(yoy(basis, metric)), f1(g(basis, metric, "H1FY27")),
                         spc(yoy(basis, metric, "H1FY27", "H1FY26"))])
    seg = table(["Business (&#8377; cr)", "Q2 FY27", "YoY", "H1 FY27", "YoY"], seg_rows, ["sub"] + [""] * 6)
    comp_rows = [
        ["Birla Opus (Grasim)", "Launched 2024; 1,332 mn litres capacity (about 24% of organised capacity); claims about 10% decorative revenue share; Q1 FY27 paints revenue &#8377;1,661 cr (+64%)", "Grasim; BusinessWorld 31-Oct-2026; NDTV Profit 13-Aug-2026"],
        ["JSW Dulux (ex Akzo Nobel India)", "JSW Paints bought 60.76% from AkzoNobel on 10-Dec-2025; renamed 11-Mar-2026; now the No. 3 decorative player", "JSW press release; ET BrandEquity 13-Mar-2026"],
        ["Pidilite (Haisha Paints)", "Entered decorative paints in select regions, aimed at price-point gaps", "ET BrandEquity 7-Mar-2024"],
        ["Incumbents (Berger, Kansai, Indigo)", "Defending share with dealer discounts and incentives; dealers report steep discounts to clear stock since Aug-2026", "Moneycontrol 27-Oct-2026; AP Q4 FY26 call"],
    ]
    comp = table(["Player", "What changed", "Source"], comp_rows, widths=["22%", "56%", "22%"], left={0, 1, 2})
    page3 = f"""
<section class='flow'>
<h2>2. Company and industry overview</h2>
<div class='grid2'>
<div>
<h3>What Asian Paints does</h3>
<p>Asian Paints is India's largest paint and decor company (FY2026 consolidated turnover &#8377;35,516 cr per the company).
Decorative paints for homes (interior and exterior emulsions, enamels, waterproofing, putty) sold through dealers are the core.
It also owns two industrial-coatings joint ventures with PPG, international paint businesses in 14 countries (Middle East,
South Asia, Africa, South Pacific) and a home-decor arm (kitchens, bath fittings, lighting, uPVC windows, 74 Beautiful Homes
stores). Brands include Royale, Apex, Apcolite, Tractor and Ace.</p>
<p><b>Assets.</b> In-house decorative capacity 2.29 million KL a year (13 plants plus 30 outsourced processing centres);
25 paint plants across the group. 72,873 dealers and distributors billed in FY2026 (75,793 in FY2025), with 99% of sales
through them and no dealer concentration (top 10 = 0.9%). Phase 1 of a 150,000 MT VAE emulsion plant at Dahej started in
Q2 FY27 (total project about &#8377;3,250 cr), the first step into making its own key raw materials.</p>
</div>
<div>
<h3>Business mix, Q2 and H1 FY27</h3>
{seg}
<p class='note'>Source: Q2 FY27 press release (data/asianpaints_q2fy27_results.csv). Segments overlap with standalone and
are not additive. JV figures are 100% of the JV.</p>
</div>
</div>
<h3>Industry: size, demand drivers, raw materials</h3>
<p>The domestic paint industry was about &#8377;77,500 cr in FY2025 (Kansai Nerolac estimate, up from &#8377;75,000 cr), with
decorative paint the larger part. Demand comes from repainting (homes are repainted every few years, so demand is steadier than
new construction), new housing and real estate, rural incomes and the monsoon. The June-September 2026 monsoon delivered about
87% of the long-period average, the weakest since 2015, a risk for rural demand in H2 FY27. Raw materials are about
{pc(n['cogs_pct'], 0)} of Asian Paints' revenue (FY2026 COGS / revenue). The main inputs are crude-linked monomers, solvents and
emulsions, and titanium dioxide (white pigment). India reimposed anti-dumping duty of USD 460-681 a tonne on some Chinese
TiO2 for five years in October 2026. The rupee at 95.15 per US dollar (30-Oct-2026) raises the cost of imported inputs.</p>
<h3>Competition</h3>
{comp}
<div class='grid2'>
<div><img class='chart' src='../figures/{figs['shareholding']}' alt='shareholding'></div>
<div>
<h3 style='margin-top:0'>Shareholders and dividends</h3>
<p>Promoters held {pc(n['sh_Promoters'], 2)} at {n['sh_q']}. Domestic institutions rose from {pc(n['sh0_DIIs'])} ({n['sh_q0']}) to
{pc(n['sh_DIIs'])}, while foreign investors fell from {pc(n['sh0_FIIs'])} to {pc(n['sh_FIIs'])}. Dividends per share were
&#8377;{f2(n['DPS_FY2022'])}, {f2(n['DPS_FY2023'])}, {f2(n['DPS_FY2024'])}, {f2(n['DPS_FY2025'])} and {f2(n['DPS_FY2026'])} for
FY2022-FY2026, about {pc(n['DPS_FY2026'] / n['EPS_FY2026'], 0)} of FY2026 EPS. The FY27 interim dividend is &#8377;5.75
(record date 4-Nov-2026).</p>
</div></div>
</section>"""

    # ---------- page 4: financial analysis ----------
    def peer_row(code: str, lab: str, kind: str) -> list[str]:
        fmt = {"pct": pc, "x": xx, "x1": lambda v: xx(v, 1), "days": f0}[kind]
        vals = [fmt(n[f"{code}_{c}_FY2026"]) for c in COS]
        rank = n.get(f"rank_{code}")
        return [lab] + vals + [fmt(n[f"med_{code}"]), str(rank) if rank else "-"]

    pr = [peer_row(*x) for x in [
        ("GM", "Gross margin", "pct"), ("EBITDAM", "EBITDA margin (before other income)", "pct"),
        ("NPM_ADJ", "Net margin excl. one-offs", "pct"), ("ROE_ADJ", "ROE excl. one-offs", "pct"),
        ("ROCE", "ROCE (EBIT / avg capital employed)", "pct"), ("AT", "Asset turnover", "x"),
        ("CR", "Current ratio", "x"), ("DE", "Debt / equity (incl. leases)", "x"),
        ("NDEBITDA", "Net debt / EBITDA (negative = net cash)", "x"), ("ICR", "Interest cover (x)", "x1"),
        ("INVD", "Inventory days", "days"), ("RECD", "Receivable days", "days"), ("PAYD", "Payable days", "days"),
        ("CCC", "Cash conversion cycle (days)", "days"), ("REVG", "Revenue growth", "pct"),
        ("CFOE", "Cash from operations / EBITDA", "pct"), ("FCFM", "Free-cash-flow margin", "pct")]]
    ptab = table(["FY2026", "Asian Paints", "Berger", "Kansai", "JSW Dulux", "Indigo", "Peer median", "AP rank"], pr)
    page4 = f"""
<section class='flow'>
<h2>3. Financial analysis: ratios and DuPont against four listed peers</h2>
<p>The ratio workbook (<i>AsianPaints_Ratio_Analysis.xlsx</i>, live Excel formulas, {n['checks_pass']} of {n['checks_total']} checks PASS)
compares Asian Paints with Berger Paints, Kansai Nerolac, JSW Dulux and Indigo Paints over FY2022-FY2026 on consolidated data.
Cost of goods sold is the company-reported total of materials, traded goods and inventory change; one-off items come from the
filings. Rank 1 = best of five; the peer median excludes Asian Paints.</p>
{ptab}
<div class='grid2'>
<div><img class='chart' src='../figures/{figs['returns']}' alt='returns'></div>
<div><img class='chart' src='../figures/{figs['margins']}' alt='margins'></div>
</div>
<p><b>Reading the table.</b> Asian Paints leads on EBITDA margin, ROE excluding one-offs, ROCE, cash conversion and free cash
flow. Indigo has the highest gross margin ({pc(n['GM_Indigo Paints_FY2026'])}) but a smaller scale. JSW Dulux's reported ROE of
{pc(n['ROE_JSW Dulux_FY2026'], 0)} comes from the gain on its slump sale to AkzoNobel; excluding it, ROE is
{pc(n['ROE_ADJ_JSW Dulux_FY2026'])}. Asian Paints' weak spot is working capital: payable days of {f0(n['PAYD_Asian Paints_FY2026'])}
are the lowest of the five and its cash conversion cycle of {f0(n['CCC_Asian Paints_FY2026'])} days ranks
{ordinal(n['rank_CCC'])}. It also carries more lease and term debt than peers (D/E {xx(n['DE_Asian Paints_FY2026'])}), although it has net cash.</p>
</section>"""

    # ---------- page 5: DuPont, trend, working capital, scorecard ----------
    dup_rows = []
    for c in COS:
        dup_rows.append([c, xx(n[f"D5_TB_{c}"]), xx(n[f"D5_IB_{c}"]), pc(n[f"D5_EBITM_{c}"]), xx(n[f"D5_AT_{c}"]),
                         xx(n[f"D5_EM_{c}"]), pc(n[f"D5_ROE_{c}"]), pc(n[f"D3_NPM_{c}"]),
                         pc(n[f"ROE_ADJ_{c}_FY2026"])])
    dtab = table(["FY2026", "Tax burden", "Interest burden", "EBIT margin", "Asset turnover", "Equity multiplier",
                  "ROE (product)", "Net margin", "ROE excl. one-offs"], dup_rows, ["ap"] + [""] * 4)
    sc_rows = [[c, f2(n[f"score26_{c}"]), str(n[f"pos26_{c}"]), f2(n[f"score5_{c}"]), str(n[f"pos5_{c}"])]
               for c in sorted(COS, key=lambda c: n[f"pos26_{c}"])]
    stab = table(["Weighted scorecard (lower = better)", "FY2026 score", "FY2026 place", "5-yr avg score", "5-yr place"],
                 sc_rows, ["ap"] + [""] * 4)
    page5 = f"""
<section class='flow'>
<h3>DuPont: where the ROE lead comes from (FY2026)</h3>
{dtab}
<p>5-step DuPont: ROE = tax burden (PAT / PBT) x interest burden (PBT / EBIT) x EBIT margin x asset turnover x equity multiplier
(average assets / average equity). The product equals ROE for every company and year (workbook check). Asian Paints' lead comes
from its EBIT margin ({pc(n['D5_EBITM_Asian Paints'])} vs {pc(n['D5_EBITM_Berger Paints'])} at Berger), not from leverage
(equity multiplier {xx(n['D5_EM_Asian Paints'])} vs {xx(n['D5_EM_Berger Paints'])}). Its asset turnover is lower than Berger's
({xx(n['D5_AT_Asian Paints'])} vs {xx(n['D5_AT_Berger Paints'])}) because it holds large investments and new capacity
(Dahej VAE) that is not yet earning.</p>
<div class='grid2'>
<div><img class='chart' src='../figures/{figs['ap_trend']}' alt='AP trend'></div>
<div><img class='chart' src='../figures/{figs['wc']}' alt='working capital'></div>
</div>
<p><b>Trend.</b> Asian Paints' returns peaked in FY2024 (ROE excluding one-offs {pc(n['ROE_ADJ_Asian Paints_FY2024'])}, ROCE
{pc(n['ROCE_Asian Paints_FY2024'])}) when raw materials were cheap. Gross margin has held at {pc(n['GM_Asian Paints_FY2026'])}
in FY2026, but higher spending on advertising, discounts and new businesses cut the EBITDA margin to
{pc(n['EBITDAM_Asian Paints_FY2026'])}, and capex of &#8377;{f0(n['CAPEX_FY2024'])} cr in FY2024 and &#8377;{f0(n['CAPEX_FY2025'])} cr in
FY2025 enlarged the asset base. Five-year averages: ROE excluding one-offs {pc(n['ROE_ADJ_Asian Paints_AVG5'])},
ROCE {pc(n['ROCE_Asian Paints_AVG5'])}, EBITDA margin {pc(n['EBITDAM_Asian Paints_AVG5'])}.</p>
<h3>Scorecard and conclusion</h3>
{stab}
<p>The scorecard ranks each company on the workbook's ratios with weights set before the results (Peer_Comparison sheet,
section C). Asian Paints is first on the FY2026 data and on 5-year averages. It is still the strongest business in the
group on returns, margins and cash, which supports a quality premium. The gap has narrowed since FY2024, and JSW Dulux
is second on 5-year averages. The investment question is whether Asian Paints can hold its lead as competition rises,
and whether the price already reflects it. Section 6 finds that the price assumes more than the lead is likely to deliver.</p>
</section>"""

    # ---------- page 6: recent results ----------
    res_rows = []
    for basis, metric, lab, cls in [("Consolidated", "Net sales", "Net sales", "sub"),
                                    ("Consolidated", "PBDIT (before other income)", "PBDIT (EBITDA before other income)", ""),
                                    ("Consolidated", "Profit before tax", "Profit before tax", ""),
                                    ("Consolidated", "Net profit after minority interest", "PAT after minority interest", ""),
                                    ("Standalone", "Net sales", "Standalone net sales", "sub"),
                                    ("Standalone", "PBDIT (before other income)", "Standalone PBDIT", ""),
                                    ("Standalone", "Net profit", "Standalone PAT", "")]:
        res_rows.append(([lab, f1(g(basis, metric, "Q2FY27")), f1(g(basis, metric, "Q2FY26")), spc(yoy(basis, metric)),
                          f1(g(basis, metric, "H1FY27")), f1(g(basis, metric, "H1FY26")),
                          spc(yoy(basis, metric, "H1FY27", "H1FY26"))], cls))
    res_rows.append((["PBDIT margin (consolidated)", pc(m_q2), pc(m_q2p), f"{(m_q2 - m_q2p) * 1e4:+.0f} bp", pc(m_h1),
                      pc(m_h1p), f"{(m_h1 - m_h1p) * 1e4:+.0f} bp"], ""))
    res_rows.append((["PBDIT margin (standalone)", pc(s_q2), pc(s_q2p), f"{(s_q2 - s_q2p) * 1e4:+.0f} bp", pc(s_h1),
                      pc(s_h1p), f"{(s_h1 - s_h1p) * 1e4:+.0f} bp"], ""))
    gs, gs0 = g("Margin", "Standalone gross margin", "Q2FY27"), g("Margin", "Standalone gross margin", "Q2FY26")
    gh, gh0 = g("Margin", "Standalone gross margin", "H1FY27"), g("Margin", "Standalone gross margin", "H1FY26")
    res_rows.append((["Gross margin (standalone)", f"{gs:.1f}%", f"{gs0:.1f}%", f"{(gs - gs0) * 100:+.0f} bp", f"{gh:.1f}%",
                      f"{gh0:.1f}%", f"{(gh - gh0) * 100:+.0f} bp"], ""))
    rtab = table(["&#8377; crore", "Q2 FY27", "Q2 FY26", "YoY", "H1 FY27", "H1 FY26", "YoY"], [r for r, _ in res_rows],
                 [c for _, c in res_rows])
    brk_rows = [["Jefferies", "Buy", "3,025 (from 3,350)", "Margins to improve in H2 on mix, festive demand and price rises"],
                ["Goldman Sachs", "Sell", "2,375 (from 2,725)", "Revenue beat, EBITDA missed; expects a further 3.5% price rise in Q3"],
                ["Systematix", "Buy", "2,885 (from 3,285)", "Volume growth of 8-10% over FY27-FY29; H2 gross margin -120 bp YoY"],
                ["Dolat Capital", "Buy", "2,870 (from 3,320)", "EBITDA and PAT missed; TiO2 anti-dumping duty adds cost"]]
    btab = table(["Broker (30-Oct-2026)", "Rating", "Target &#8377;", "View"], brk_rows, widths=["17%", "9%", "19%", "55%"],
                 left={0, 1, 3})
    page6 = f"""
<section class='flow'>
<h2>4. Recent results: Q2 and H1 FY27 (reported 29-Oct-2026)</h2>
{rtab}
<p class='note'>Source: Asian Paints Q2 FY27 results and press release, investor presentation (29-Oct-2026); typed into
data/asianpaints_q2fy27_results.csv with page references. Consolidated revenue from operations was &#8377;9,976.5 cr (net sales
plus other operating revenue).</p>
<img class='chart' src='../figures/{figs['quarterly']}' alt='quarterly'>
<div class='grid2'>
<div>
<h3>What happened</h3>
<ul>
<li><b>Volume held up.</b> Decorative volume +{g('Growth', 'Decorative India volume growth', 'Q2FY27'):.1f}% and value
+{g('Growth', 'Decorative India value growth', 'Q2FY27'):.1f}%; the gap is price increases (about 12% calibrated pricing).
Rural led urban. New products are about 18% of revenue.</li>
<li><b>Other businesses grew faster.</b> Industrial coatings +{g('Growth', 'Industrial coatings value growth', 'Q2FY27'):.1f}%,
international {spc(yoy('Segment', 'International net sales'))} ({g('Growth', 'International growth in constant currency', 'Q2FY27'):.1f}%
in constant currency), but international PBT fell 31% to &#8377;52.7 cr.</li>
<li><b>Margins fell.</b> Higher-cost inventory flowed through after the steep Q1 inflation; prices lagged costs. Consolidated
gross margin was {cgm:.1f}% ({(cgm - cgm0) * 100:+.0f} bp).</li>
<li><b>H1 is still up.</b> H1 PAT {spc(yoy('Consolidated', 'Net profit after minority interest', 'H1FY27', 'H1FY26'))} on a
strong Q1; standalone H1 PBDIT margin of {pc(s_h1)} is inside the 18-20% guidance band (Q2 alone: {pc(s_q2)}).</li>
</ul></div>
<div>
<h3>Management view and what to watch</h3>
<ul>
<li>FY27 EBITDA margin guidance of 18-20% kept; further staggered price increases from November.</li>
<li>Price increases of about 7% in Q1 and 5% in Q2 against about 3% more inflation in Q2 (call summary).</li>
<li>The Q2 transcript was not yet filed when data was collected; we use the press release, presentation and published call
summaries, and the Q4 FY26 transcript for guidance.</li>
<li>Watch: H2 gross margin, festive and wedding-season volumes, discounting by new entrants, VAE ramp-up.</li>
</ul></div></div>
<h3>Broker reactions after the results</h3>
{btab}
<p class='note'>Source: The Economic Times, 30-Oct-2026 (targets as reported). StockAnalysis.com consensus, {n['ratings_month']}:
{n['rat_Strong Buy']} strong buy, {n['rat_Buy']} buy, {n['rat_Hold']} hold, {n['rat_Sell']} sell, {n['rat_Strong Sell']} strong sell
({n['rat_Total']} ratings); price targets low {rs(n['tgt_Low'])}, average {rs(n['tgt_Average'])}, median {rs(n['tgt_Median'])},
high {rs(n['tgt_High'])}.</p>
</section>"""

    # ---------- page 7: forecasts and valuation ----------
    def gr(cur: str, prev_v) -> str:
        cv = P3[cur]
        if cv is None or prev_v is None:
            return ph(cur + "_growth")
        return spc(cv / prev_v - 1)

    def mg(e: str, r: str) -> str:
        return pc(P3[e] / P3[r]) if (P3[e] is not None and P3[r] is not None) else ph(e + "_margin")

    def eg(cur, prev) -> str:
        return spc(cur / prev - 1) if (cur is not None and prev) else ""

    fc_rows = [
        ["Revenue (&#8377; cr)", f0(n["REV_FY2026"]), ph("fy27e_revenue"), ph("fy28e_revenue"), ph("fy29e_revenue")],
        ["Revenue growth", spc(n["REVG_Asian Paints_FY2026"]), gr("fy27e_revenue", n["REV_FY2026"]),
         gr("fy28e_revenue", P3["fy27e_revenue"]), gr("fy29e_revenue", P3["fy28e_revenue"])],
        ["EBITDA (&#8377; cr)", f0(n["EBITDA_FY2026"]), ph("fy27e_ebitda"), ph("fy28e_ebitda"), ph("fy29e_ebitda")],
        ["EBITDA margin", pc(n["EBITDAM_Asian Paints_FY2026"]), mg("fy27e_ebitda", "fy27e_revenue"),
         mg("fy28e_ebitda", "fy28e_revenue"), mg("fy29e_ebitda", "fy29e_revenue")],
        ["PAT to owners (&#8377; cr)", f0(n["PATOWN_FY2026"]), ph("fy27e_pat"), ph("fy28e_pat"), ph("fy29e_pat")],
        ["EPS (&#8377;)", f2(n["EPS_FY2026"]), ph("fy27e_eps", f2), ph("fy28e_eps", f2), ph("fy29e_eps", f2)],
        ["EPS growth", eg(n["EPS_FY2026"], n["EPS_FY2025"]), eg(P3["fy27e_eps"], n["EPS_FY2026"]),
         eg(P3["fy28e_eps"], P3["fy27e_eps"]), eg(P3["fy29e_eps"], P3["fy28e_eps"])],
        ["Free cash flow to the firm (&#8377; cr, Project 3)", ph("fy26a_fcff"), ph("fy27e_fcff"), ph("fy28e_fcff"),
         ph("fy29e_fcff")],
        ["Consensus revenue (&#8377; cr)", "", ph("cons_rev27"), ph("cons_rev28"), "n/a"],
        ["Consensus EPS (&#8377;)", "", ph("cons_eps27", f2), ph("cons_eps28", f2), "n/a"],
        ["Project 3 EPS vs consensus", "", eg(P3["fy27e_eps"], P3["cons_eps27"]), eg(P3["fy28e_eps"], P3["cons_eps28"]),
         ""],
    ]
    ftab = table(["Year to March", "FY26A", "FY27E", "FY28E", "FY29E"], fc_rows,
                 ["sub", "", "", "", "", "sub", "", "", "", "", ""])
    final = bool(val) and not is_draft()
    if not final:   # phase-1 fallback: Project 3 files missing
        page7 = (f"<section class='flow'><h2>5. Forecasts (FY2027E-FY2029E)</h2>{ftab}<h2>6. Valuation</h2>"
                 f"<div class='draft'>Valuation needs Project 3: {ph('dcf_value')} {ph('comps_median')} "
                 f"{ph('relative_value')} {ph('football_field_png', str)}</div></section>")
    else:
        V = P3
        price = n["price"]
        m27 = V["fy27e_ebitda"] / V["fy27e_revenue"]
        cm27 = V["cons_ebitda27"] / V["cons_rev27"]
        cm_h2 = (V["cons_ebitda27"] - V["h1_ebitda"]) / (V["cons_rev27"] - V["h1_revenue"])
        gs_bp = (g("Margin", "Standalone gross margin", "Q2FY27") - g("Margin", "Standalone gross margin", "Q2FY26")) * 100
        n.update({"m27": m27, "cm27": cm27, "cm_h2": cm_h2})
        fc_text = f"""
<p>The forecasts are Project 3's DCF forecasts, so the earnings table and the valuation use one set of numbers. FY2027E is
H1 FY27 as reported (revenue from operations &#8377;{f0(V['h1_revenue'])} cr, {spc(V['h1_growth'])}; EBITDA margin {pc(V['h1_margin'])})
plus an H2 forecast of {spc(V['h2_growth'])} revenue growth at a {pc(V['h2_margin'])} margin, after Q2's {pc(m_q2)}. From FY2028E
revenue grows {pc(V['late_growth_lo'])}-{pc(V['late_growth_hi'])} a year and the margin recovers to
{pc(V['fy28e_ebitda'] / V['fy28e_revenue'])}-{pc(V['fy29e_ebitda'] / V['fy29e_revenue'])}. Free cash flow dips in FY2027E because
trade working capital rose by &#8377;{f0(V['h1_wc_increase'])} cr in H1.</p>
<p><b>Project 3 vs consensus.</b> Project 3's EPS is {spc(V['fy27e_eps'] / V['cons_eps27'] - 1)} against consensus in FY2027E
({rs(V['fy27e_eps'], 2)} vs {rs(V['cons_eps27'], 2)}, {n['cons_n27']} analysts) and {spc(V['fy28e_eps'] / V['cons_eps28'] - 1)} in
FY2028E ({rs(V['fy28e_eps'], 2)} vs {rs(V['cons_eps28'], 2)}). Revenue is close ({spc(V['fy27e_revenue'] / V['cons_rev27'] - 1)} in
FY2027E, {spc(V['fy28e_revenue'] / V['cons_rev28'] - 1)} in FY2028E), so the gap is the margin. Consensus EBITDA of
&#8377;{f0(V['cons_ebitda27'])} cr implies {pc(cm27)} for FY2027E and about {pc(cm_h2)} in H2, against Project 3's {pc(m27)} and
{pc(V['h2_margin'])}: analysts expect price increases to restore margins sooner. We keep Project 3's more cautious view because
Q2 standalone gross margin fell {gs_bp:.0f} bp and the anti-dumping duty on Chinese titanium dioxide reimposed in October 2026
adds cost in H2.</p>"""
        dcf_rows = [
            [f"WACC (cost of equity {pc(V['ke'], 2)} = {pc(V['rf'], 2)} + {V['beta']:.2f} x {pc(V['erp'])})", pc(V["wacc"], 2)],
            ["Terminal growth after FY2031E", pc(V["terminal_g"])],
            ["Terminal value: share of EV; multiple of FY2031E EBITDA",
             f"{pc(V['tv_share_ev'], 0)}; {xx(V['exit_ev_ebitda'], 1)}"],
            [f"<b>DCF value per share</b> (vs price {spc(V['dcf_value'] / price - 1, 0)})", f"<b>{rs(V['dcf_value'])}</b>"],
            ["WACC and g +/-0.5 pp (+/-1.0 pp)",
             f"{f0(V['dcf_low'])}-{f0(V['dcf_high'])} ({f0(V['dcf_grid_low'])}-{f0(V['dcf_grid_high'])})"],
            [f"Same cash flows, exit at the peer median {xx(V['exit_cross_x'], 1)} EBITDA", rs(V["exit_cross_value"])],
            [f"Perpetual growth implied by {rs(price)} (reverse DCF)", pc(V["reverse_dcf_g"], 2)],
            [f"FY2031E EV/EBITDA implied by {rs(price)}", xx(n["impl_exit"], 1)]]
        comps_rows = [
            ["P/E, TTM", xx(V["pe_ttm_peer_median"], 1), xx(V["ap_pe_ttm"], 1),
             f"{f0(V['comps_q1'])} / <b>{f0(V['comps_median'])}</b> / {f0(V['comps_q3'])}"],
            ["EV/EBITDA, TTM", xx(V["ev_peer_median"], 1), xx(V["ap_ev_ebitda"], 1),
             f"{f0(V['ev_q1'])} / {f0(V['ev_median'])} / {f0(V['ev_q3'])}"],
            ["P/E, FY2027E consensus", xx(V["pe27_peer_median"], 1), xx(V["ap_pe27"], 1), "used in the P/E lens below"]]
        prem_pe = V["pe27_peer_median"] * (1 + V["rel_premium"])
        rel_rows = [
            ["5-year median premium to the peer median P/E (25th-75th)",
             f"{pc(V['rel_premium'], 1)} ({pc(V['rel_p25'], 0)}-{pc(V['rel_p75'], 0)})"],
            ["x peer median P/E on FY2027E consensus EPS (Project 3)", xx(V["pe27_peer_median"], 1)],
            ["= premium-adjusted P/E", xx(prem_pe, 1)],
            ["x FY2028E EPS (Project 3)", rs(V["fy28e_eps"], 2)],
            ["<b>= premium-adjusted value</b> (premium 25th-75th)",
             f"<b>{rs(V['relative_value'])}</b> ({f0(V['rel_low'])}-{f0(V['rel_high'])})"],
            [f"Cross-check, trailing: {xx(V['peer_pe_now'], 1)} x (1 + {pc(V['rel_premium'], 0)}) x FY2027E EPS",
             rs(V["rel_trailing_value"])],
            [f"Not used: own 5-year median P/E {xx(V['own_pe_median'], 1)} x FY2027E EPS", rs(V["own_band_value"])]]
        wpc = {k: pc(V[f"w_{k}"], 0) for k in ("dcf", "comps", "rel")}
        blend_rows = [
            ["DCF (Project 3)", rs(V["dcf_value"]), wpc["dcf"], WEIGHT_WHY["dcf"]],
            ["Peer comps, P/E median (Project 3)", rs(V["comps_median"]), wpc["comps"], WEIGHT_WHY["comps"]],
            ["Premium-adjusted P/E (this report)", rs(V["relative_value"]), wpc["rel"], WEIGHT_WHY["rel"]],
            ["<b>12-month target price</b>", f"<b>{tp_html}</b>", "100%",
             f"Upside vs {rs(price, 2)}: <b>{up_html}</b>. Rating: <b>{rating_html}</b>"]]
        btab2 = table(["Component", "&#8377;/share", "Weight", "Why this weight (fixed before the target was calculated)"],
                      blend_rows, ["", "", "", "ap"], widths=["24%", "9%", "8%", "59%"], left={0, 3})

        def wtxt(w: dict[str, float]) -> str:
            return " / ".join(f"{w[k] * 100:.0f}" for k in ("dcf", "comps", "rel"))

        own = val["own"]
        sens_rows = [["<b>Base case</b>", wtxt(WEIGHTS), f"<b>{rs(tp)}</b>", spc(up), f"<b>{rating_html}</b>"]]
        sens_rows += [[a["name"], wtxt(a["w"]), rs(a["target"]), spc(a["upside"]), a["rating"]] for a in val["alts"]]
        sens_rows.append(["Base weights, own P/E band as the relative lens", wtxt(WEIGHTS), rs(own["target"]),
                          spc(own["upside"]), own["rating"]])
        stab2 = table(["Weighting", "DCF / comps / rel. (%)", "Target &#8377;", "Upside", "Rating"], sens_rows,
                      ["ap", "", "", "", ""])
        eq, nd = alt["Equal weights"], alt["No DCF"]
        min_peer_ev, max_peer_ev = V["ev_peer_min"], V["ev_peer_max"]
        why_dcf = f"""
<p><b>Why the DCF is far below the price.</b> Three features of a five-year DCF push the value down for a business like this.
(1) <i>Horizon.</i> Growth falls straight to {pc(V['terminal_g'])} after FY2031, so {pc(V['tv_share_ev'], 0)} of the value sits in a
terminal value worth only {xx(V['exit_ev_ebitda'], 1)} FY2031E EBITDA, below every listed peer today
({xx(min_peer_ev, 1)}-{xx(max_peer_ev, 1)}). With a {xx(V['exit_cross_x'], 1)} exit multiple the same cash flows give
{rs(V['exit_cross_value'])}. (2) <i>Reinvestment.</i> At a {pc(n['ROCE_Asian Paints_FY2026'])} ROCE each extra year of growth adds
value, and a five-year horizon stops counting it; EPS grew {pc(n['eps_cagr10'])} a year over FY2016-FY2026, above the
{pc(V['terminal_g'])} terminal rate. (3) <i>Discount rate.</i> The {pc(V['ke'], 2)} cost of equity adds a {pc(V['erp'])} premium to
a G-sec yield that already contains India's default spread; Damodaran's method gives {pc(V['ke_damodaran'], 2)}. The discount
rate is not the main gap: the most generous corner of the grid (WACC -1 pp, g +1 pp) still gives only {rs(V['dcf_grid_high'])}.
<b>Reverse DCF.</b> At {rs(price)} free cash flow must grow {pc(V['reverse_dcf_g'], 2)} a year forever after FY2031, only
{(V['wacc'] - V['reverse_dcf_g']) * 100:.1f} points below the WACC. Put another way, the market expects Asian Paints to be
worth about {xx(n['impl_exit'], 0)} EBITDA in FY2031, close to today's {xx(V['ap_ev_ebitda'], 1)}: it is paying for a high-growth
phase that lasts well beyond five years. That may happen, but revenue grew {pc(n['cagr3'])} a year over FY2023-FY2026 and two
large new competitors are adding capacity, so we do not pay for it in full.</p>"""
        rel_text = f"""
<p>This lens asks what Asian Paints is worth if it keeps the P/E premium the market has paid for it over peers, at today's peer
multiple. For each of the {n['rel_days']:,.0f} trading days from {pd.Timestamp(n['px_base_date']):%d-%b-%Y} to {ASOF}, each
company's P/E = market value (close x today's shares; Yahoo restates past prices for bonus issues and splits) / PAT to owners
excluding one-offs of the last reported year, and the premium is Asian Paints' P/E over the median of the four peers. We apply
the 5-year median premium to the peers' median P/E on FY2027E consensus EPS (all five companies on the same year) and to
FY2028E EPS, the year the market will price in 12 months. We use the premium rather than Asian Paints' own P/E band because
the whole sector de-rated: the peer median fell from {xx(V['peer_pe_start'], 1)} to {xx(V['peer_pe_now'], 1)}, and Asian Paints
from {xx(V['own_pe_start'], 1)} to {xx(V['own_pe_now'], 1)} (own 5-year range {xx(V['own_pe_min'], 0)}-{xx(V['own_pe_max'], 0)}).</p>"""
        concl = f"""
<p><b>Rating: {rating_html}.</b> The blended target of {tp_html} is {pc(abs(up))} {'below' if up < 0 else 'above'} the price.
How far below depends on the DCF weight, but every weighting puts the target under the price: {rs(eq['target'])} with equal
weights, and {rs(nd['target'])} ({spc(nd['upside'])}, a {nd['rating'].title()}) with no weight on the DCF. Only Asian Paints' own 2021-26 P/E band (median
{xx(V['own_pe_median'], 1)}) would lift the target to about the price ({rs(own['target'])}); we do not use it because that band
comes from years when the whole sector traded near {xx(V['peer_pe_start'], 0)} earnings, before the new entrants. Our target is
below the lowest analyst target ({rs(n['tgt_Low'])}); the median target of {rs(n['tgt_Median'])} is
{xx(n['tgt_Median'] / n['cons_eps27'], 1)} consensus FY27E EPS, above today's multiple. What would change our view: an EBITDA
margin back above 20% with 8-10% volume growth, or evidence that Birla Opus and JSW Dulux are cutting discounts.</p>"""
        page7 = f"""
<section class='flow'>
<h2>5. Forecasts (FY2027E-FY2029E, from Project 3)</h2>
{ftab}
{fc_text}
<h2>6. Valuation</h2>
<div class='grid-val compact'>
<div><h3 style='margin-top:0'>DCF (Project 3)</h3>{table(['Input / output', 'Value'], dcf_rows)}</div>
<div><h3 style='margin-top:0'>Peer comps (Project 3)</h3>
{table(['Multiple', 'Peer median', 'Asian Paints', '&#8377;/share at 25th / median / 75th'], comps_rows)}
<p class='note'>Peer median excludes Asian Paints; TTM to Sep-2026 for Asian Paints and Indigo, Jun-2026 for the other three.
P/E is the steadier anchor: dropping any one peer moves its value only between {rs(V['pe_drop_lo'])} and
{rs(V['pe_drop_hi'])}. Asian Paints' premium to the median: {pc(V['ap_pe_ttm_prem'], 0)} on P/E, {pc(V['ap_ev_prem'], 0)} on
EV/EBITDA. Source: Project 3 (AsianPaints_Comps_and_DCF.xlsx, outputs/*.csv).</p></div>
</div>
{why_dcf}
<h3>Premium-adjusted relative value (this report)</h3>
{rel_text}
<div class='grid-val compact keep'>
<div>{table(['Step', 'Value'], rel_rows)}</div>
<div><img class='chart' src='../figures/{figs['premium']}' alt='P/E premium'></div>
</div>
<h3>Target price, sensitivity and rating</h3>
<div class='compact'>{btab2}</div>
<div class='grid-val compact keep'>
<div>{stab2}</div>
<div>{concl}</div>
</div>
<img class='chart' src='../figures/{figs['ff']}' alt='football field'>
<p class='note'>Analyst targets (StockAnalysis.com, {n['ratings_month']}): low {rs(n['tgt_Low'])}, average {rs(n['tgt_Average'])},
median {rs(n['tgt_Median'])}, high {rs(n['tgt_High'])}; 52-week range {rs(n['lo52'])}-{rs(n['hi52'])}. The DCF and comps values
are as of 30-Sep / 30-Oct-2026 and are not rolled forward.</p>
</section>"""

    # ---------- page 8: risks, ESG ----------
    risk_rows = [
        ["Downside", "Raw-material inflation not passed on", f"Each 1% rise in COGS (&#8377;{f0(n['COGS_FY2026'])} cr) costs &#8377;{f0(n['s_rm'])} cr of EBITDA ({pc(n['s_rm_e'])}), &#8377;{f2(n['s_rm_eps'])} of EPS"],
        ["Downside", "Price war / dealer discounting", f"Each 1% of revenue in extra discounts = &#8377;{f0(n['s_disc'])} cr ({pc(n['s_disc_e'])} of EBITDA, &#8377;{f2(n['s_disc_eps'])} EPS)"],
        ["Downside", "Market-share loss to Birla Opus, JSW Dulux", f"Each 1% of lost revenue at a {pc(n['GM_Asian Paints_FY2026'])} gross margin = &#8377;{f0(n['s_vol'])} cr of gross profit ({pc(n['s_vol_e'])} of EBITDA)"],
        ["Downside", "Weaker rupee (USD/INR 95.15)", f"If {pc(FX_SHARE_ASSUMED, 0)} of COGS is USD-linked (assumption), a 5% fall in the rupee = &#8377;{f0(n['s_fx'])} cr ({pc(n['s_fx_e'])} of EBITDA)"],
        ["Downside", "De-rating of the multiple", f"Each 5x change in P/E on TTM EPS of &#8377;{f2(n['eps_ttm'])} = &#8377;{f0(n['s_pe5'])} per share ({pc(n['s_pe5'] / n['price'])} of the price)"],
        ["Downside", "CCI abuse-of-dominance probe", f"Tail risk: the Act allows a penalty of up to 10% of 3-year average turnover (&#8377;{f0(n['s_cci'])} cr, &#8377;{f0(n['s_cci_ps'])}/share); remedies on dealer terms are more likely"],
        ["Downside", "Weak monsoon (87% of LPA in 2026)", "Slower rural repainting in H2 FY27; rural led urban growth in Q2"],
        ["Upside", "Margin recovery as costs ease", f"EBITDA margin back to FY2024's {pc(n['EBITDAM_Asian Paints_FY2024'])} on FY2026 revenue = +&#8377;{f0(n['s_margin_up'])} cr ({pc(n['s_margin_up_e'])}, &#8377;{f2(n['s_margin_up_eps'])} EPS)"],
        ["Upside", "Backward integration (VAE, VAM)", "Management expects a 300-500 bp cost advantage on products using in-house VAE; phase 2 adds VAM"],
        ["Upside", "Price rises stick, volumes hold at 8-10%", "Systematix estimates 19-20% cumulative price increases since April; volume target 8-10% (management)"],
        ["Upside", "Competition rationalises", "If new entrants cut discounts to chase profit, margins and share stabilise"],
    ]
    rktab = table(["Type", "Risk", "Sensitivity (FY2026 base, tax 25.17%)"], risk_rows, widths=["9%", "29%", "62%"],
                  left={0, 1, 2})
    page8 = f"""
<section class='flow'>
<div class='keep'>
<h2>7. Risks</h2>
<p>With a {rating_html} rating, the upside risks are the ones that would prove the call wrong; the largest is a margin
recovery, which on FY2026 revenue alone would add &#8377;{f2(n['s_margin_up_eps'])} to EPS.</p>
{rktab}
</div>
<p class='note'>Sensitivities are simple one-factor arithmetic on FY2026 figures (revenue &#8377;{f0(n['REV_FY2026'])} cr, COGS
&#8377;{f0(n['COGS_FY2026'])} cr, EBITDA &#8377;{f0(n['EBITDA_FY2026'])} cr, {f2(n['shares_cr'])} cr shares), before any offsetting
price action. The USD-linked share of COGS is not disclosed; {pc(FX_SHARE_ASSUMED, 0)} is an assumption for illustration.</p>
<h2>8. ESG and governance</h2>
<div class='grid2'>
<div>
<h3>Environment and social</h3>
<ul>
<li>Renewable electricity 57% of use in FY2026 and 62% in H1 FY27 (target 100% by 2030).</li>
<li>Scope 1+2 emissions per KL of paint down 69% (FY2026) and 71% (H1 FY27) from the base year (target 80%).</li>
<li>Fresh-water replenishment 5.9x consumption in FY2026; recycled plastic 40% of packaging (target 60%).</li>
<li>CSR spend &#8377;114.6 cr in FY2026; 9.45 lakh painters and contractors trained.</li>
</ul></div>
<div>
<h3>Governance</h3>
<ul>
<li>Promoter group holds {pc(n['sh_Promoters'], 2)}; institutions {pc(n['sh_FIIs'] + n['sh_DIIs'])}; {n['sh_holders']:,.0f} shareholders.</li>
<li>Statutory auditor: Deloitte Haskins &amp; Sells LLP. Dividend payout about 60% of earnings for FY2022-FY2026.</li>
<li>Competition Commission of India: a Director General investigation into alleged abuse of dominance (dealer exclusivity,
supplier restrictions) was ordered in July 2025 on Grasim's complaint; the Supreme Court declined to hear Asian Paints'
challenge in October 2025. No final order as of {ASOF}.</li>
</ul></div></div>
<p class='note'>Sources: Q2 FY27 investor presentation (sustainability slide), Integrated Annual Report FY2025-26, CCI order
(1-Jul-2025), ET BrandEquity (14-Oct-2025).</p>
</section>"""

    # ---------- page 9: appendix ----------
    def row(lab: str, key: str, fmt=f0) -> list[str]:
        return [lab] + [fmt(n[f"{key}_{fy}"]) for fy in FYS]

    fin_rows = [row("Revenue from operations", "REV"), row("Cost of goods sold", "COGS"), row("Gross profit", "GP"),
                row("EBITDA (before other income)", "EBITDA"), row("Depreciation", "DEP"), row("EBIT (before other income)", "EBIT"),
                row("Other income (incl. one-offs)", "OTHINC"), row("Finance costs", "INT"), row("Profit before tax", "PBT"),
                row("PAT to owners", "PATOWN"), row("EPS (&#8377;)", "EPS", f2), row("Total assets", "TA"),
                row("Equity (owners)", "EQ"), row("Borrowings incl. leases", "BORR"), row("Cash from operations", "CFO"),
                row("Capex", "CAPEX"), row("Free cash flow (CFO - capex)", "FCF")]
    fin = table(["&#8377; crore, consolidated"] + FYS, fin_rows,
                ["sub", "", "", "sub", "", "", "", "", "", "sub", "", "sub", "", "", "sub", "", ""])
    rat_codes = [("GM", "Gross margin", pc), ("EBITDAM", "EBITDA margin", pc), ("ROE_ADJ", "ROE excl. one-offs", pc),
                 ("ROCE", "ROCE", pc), ("AT", "Asset turnover", xx), ("CCC", "Cash conversion cycle (days)", f0),
                 ("FCFM", "Free-cash-flow margin", pc)]
    rat_rows = [[lab] + [fmt(n[f"{code}_Asian Paints_{fy}"]) for fy in FYS] + [fmt(n[f"{code}_Asian Paints_AVG5"])]
                for code, lab, fmt in rat_codes]
    rtab2 = table(["Asian Paints ratios"] + FYS + ["5-yr avg"], rat_rows)
    seen, src_items = set(), []
    for f in d["F"].values():
        key = f["url"]
        if key in seen:
            continue
        seen.add(key)
        src_items.append(f"<p><b>{f['source']}</b> ({f['date']}). {f['url']}</p>")
    data_src = ("<p><b>Screener.in</b> consolidated and standalone pages and schedules API, 5 companies (downloaded 1-Nov-2026). "
                "https://www.screener.in/company/ASIANPAINT/consolidated/</p>"
                "<p><b>StockAnalysis.com</b> (S&amp;P Global data): statements, statistics, forecast, dividends (1-Nov-2026). "
                "https://stockanalysis.com/quote/nse/ASIANPAINT/forecast/</p>"
                "<p><b>NSE XBRL annual results</b> FY2021-FY2024 for COGS and exceptional items. https://www.nseindia.com</p>"
                "<p><b>Yahoo Finance</b> via yfinance: ASIANPAINT.NS, peers, ^NSEI daily closes to 30-Oct-2026.</p>"
                "<p><b>Company results PDFs</b> (Q4 FY26, Q2 FY27) from NSE announcements; list in source_data/README.md.</p>"
                "<p><b>Project 3</b> of this portfolio (comps and DCF on Asian Paints): AsianPaints_Comps_and_DCF.xlsx and "
                "outputs/*.csv, final 1-Nov-2026 (22 of 22 checks PASS); copies in data/p3/. Forecasts, DCF, comps, "
                "football-field bars and FY2028E consensus EPS.</p>")
    page9 = f"""
<section class='appendix'>
<h2>Appendix A. Financial summary, FY2022-FY2026 (consolidated)</h2>
{fin}
<h2>Appendix B. Asian Paints ratio history</h2>
{rtab2}
<p class='note'>All values from AsianPaints_Ratio_Analysis.xlsx (Raw_Data, Ratios sheets; {n['checks_pass']}/{n['checks_total']} checks PASS).
Averages use opening and closing balances (FY2021 balance sheet = opening for FY2022).</p>
<h2>Appendix C. Sources</h2>
<div class='src'>{data_src}{''.join(src_items)}</div>
<p class='note' style='margin-top:2mm'><b>Disclaimer.</b> Educational project, not investment advice. The author holds no position.
Forecasts and valuation are the author's own and may be wrong. Third-party market-share figures are industry estimates.</p>
</section>"""

    title = "Asian Paints initiation report" + (" (DRAFT)" if is_draft() else f": {rating_html}, target {rs(tp, 0)}"
                                                 .replace("&#8377;", "Rs "))
    return (f"<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'><title>{title}</title>"
            f"<style>{CSS}</style></head><body>{page1}{page2}{page3}{page4}{page5}{page6}{page7}{page8}{page9}</body></html>")


# ------------------------------------------------------------------------------------------------------------------
# PDF and checks
# ------------------------------------------------------------------------------------------------------------------
def print_pdf(html_path: Path, pdf_path: Path) -> bool:
    if not EDGE.exists():
        print("Edge not found:", EDGE)
        return False
    prof = Path(tempfile.mkdtemp(prefix="p05_edge_"))
    cmd = [str(EDGE), "--headless", "--disable-gpu", "--no-first-run", f"--user-data-dir={prof}",
           f"--print-to-pdf={pdf_path}", "--no-pdf-header-footer", "--print-to-pdf-no-header", html_path.as_uri()]
    try:
        if pdf_path.exists():
            pdf_path.unlink()
        subprocess.run(cmd, check=False, timeout=180, capture_output=True)
    finally:
        shutil.rmtree(prof, ignore_errors=True)
    return pdf_path.exists() and pdf_path.stat().st_size > 10_000


def p3_expect(n: dict) -> dict[str, str]:
    """Strings the PDF must contain, built straight from the source files (data/p3/*.csv and outputs/relative_value.csv),
    not from the P3 dict, so a wrong mapping in load_p3() would show up as a MISS. Target and sensitivities are
    recomputed here from those files."""
    fc = pd.read_csv(P3_SNAP / "dcf_forecast.csv").set_index("line_item")
    sm = pd.read_csv(P3_SNAP / "dcf_summary.csv").set_index("item")["value"]
    iv = pd.read_csv(P3_SNAP / "implied_values.csv").set_index("multiple")
    dr = pd.read_csv(P3_SNAP / "drop_one_sensitivity.csv").set_index("case")
    rv = pd.read_csv(OUT / "relative_value.csv").set_index("item")["value"].astype(float)

    def f(item: str) -> float:
        return float(sm[item])

    yrs = ["FY2027E", "FY2028E", "FY2029E"]
    e = {f"forecast {lab}": " ".join(fmt(float(fc.loc[line, c])) for c in yrs) for line, lab, fmt in [
        ("revenue_rs_cr", "revenue", f0), ("ebitda_rs_cr", "EBITDA", f0),
        ("pat_attributable_to_owners_rs_cr", "PAT", f0), ("eps_rs", "EPS", f2)]}
    e["forecast FCFF"] = " ".join(f0(float(fc.loc["fcff_rs_cr", c])) for c in ["FY2026A"] + yrs)
    e["consensus EPS FY27E FY28E"] = " ".join(f2(float(fc.loc["consensus_eps_rs", c])) for c in yrs[:2])
    e["consensus revenue FY27E FY28E"] = " ".join(f0(float(fc.loc["consensus_revenue_rs_cr", c])) for c in yrs[:2])
    e["WACC"] = pc(f("wacc_pct") / 100, 2)
    e["cost of equity"] = (f"{pc(f('cost_of_equity_pct') / 100, 2)} = {pc(f('risk_free_rate_pct') / 100, 2)} + "
                           f"{f('beta_used'):.2f} x {pc(f('equity_risk_premium_pct') / 100)}")
    e["TV share; exit multiple"] = f"{pc(f('terminal_value_share_of_ev_pct') / 100, 0)}; {xx(f('implied_exit_ev_ebitda_x'), 1)}"
    e["DCF value"] = f"(vs price {spc(f('dcf_value_per_share_rs') / n['price'] - 1, 0)}) {f0(f('dcf_value_per_share_rs'))}"
    e["DCF ranges"] = (f"{f0(f('dcf_range_inner_3x3_low_rs'))}-{f0(f('dcf_range_inner_3x3_high_rs'))} "
                       f"({f0(f('dcf_grid_5x5_low_rs'))}-{f0(f('dcf_grid_5x5_high_rs'))})")
    e["exit-multiple cross-check"] = f"EBITDA {f0(f('value_per_share_at_exit_multiple_rs'))}"
    e["reverse DCF g"] = f"(reverse DCF) {pc(f('market_implied_perpetual_growth_pct') / 100, 2)}"
    df_tv = f("pv_terminal_value_rs_cr") / f("terminal_value_rs_cr")
    impl = (f("market_ev_rs_cr") - f("sum_pv_fcff_rs_cr")) / df_tv / float(fc.loc["ebitda_rs_cr", "FY2031E"])
    e["implied FY2031E exit multiple"] = f"implied by 2,320 {xx(impl, 1)}"
    for mult, lab in [("P/E TTM", "comps P/E"), ("EV/EBITDA TTM", "comps EV/EBITDA")]:
        r = iv.loc[mult]
        e[lab] = " / ".join(f0(float(r[f"implied_rs_per_share_at_{q}"])) for q in ["p25", "median", "p75"])
        e[lab + " multiples"] = f"{xx(float(r['peer_median_x']), 1)} {xx(float(r['asian_paints_multiple_x']), 1)}"
    r27 = iv.loc["P/E FY27E"]
    e["P/E FY27E multiples"] = f"{xx(float(r27['peer_median_x']), 1)} {xx(float(r27['asian_paints_multiple_x']), 1)}"
    e["drop-one P/E range"] = (f"between {f0(float(dr.loc['Lowest drop-one result', 'implied_rs_per_share_pe']))} and "
                               f"{f0(float(dr.loc['Highest drop-one result', 'implied_rs_per_share_pe']))}")
    prem, eps28 = rv["premium_median"], float(fc.loc["eps_rs", "FY2028E"])
    rel = float(r27["peer_median_x"]) * (1 + prem) * eps28
    e["premium median and quartiles"] = f"{pc(prem, 1)} ({pc(rv['premium_p25'], 0)}-{pc(rv['premium_p75'], 0)})"
    e["premium-adjusted P/E"] = f"premium-adjusted P/E {xx(float(r27['peer_median_x']) * (1 + prem), 1)}"
    e["relative value and range"] = (f"{f0(rel)} ({f0(float(r27['peer_median_x']) * (1 + rv['premium_p25']) * eps28)}-"
                                     f"{f0(float(r27['peer_median_x']) * (1 + rv['premium_p75']) * eps28)})")
    parts = {"dcf": f("dcf_value_per_share_rs"), "comps": float(iv.loc["P/E TTM", "implied_rs_per_share_at_median"]),
             "rel": rel}
    tp = sum(WEIGHTS[k] * parts[k] for k in parts)
    up = tp / n["price"] - 1
    e["target row"] = (f"12-month target price {f0(tp)} 100% Upside vs {f2(n['price'])}: {spc(up)}. "
                       f"Rating: {rating_for(up)}")
    e["page 1 rating"] = f"Rating: {rating_for(up)} 12-month target {f0(tp)}"
    for name, w in ALT_WEIGHTS:
        v = sum(w[k] * parts[k] for k in parts)
        wt = " / ".join(f"{w[k] * 100:.0f}" for k in ("dcf", "comps", "rel"))
        e[f"sensitivity {name}"] = f"{name} {wt} {f0(v)} {spc(v / n['price'] - 1)} {rating_for(v / n['price'] - 1)}"
    own = dict(parts, rel=rv["own_pe_median"] * float(fc.loc["eps_rs", "FY2027E"]))
    v = sum(WEIGHTS[k] * own[k] for k in own)
    e["sensitivity own band"] = f"relative lens 25 / 25 / 50 {f0(v)} {spc(v / n['price'] - 1)} {rating_for(v / n['price'] - 1)}"
    return e


def check_pdf(pdf_path: Path, n: dict, preview: Path | None) -> list[str]:
    import pymupdf

    doc = pymupdf.open(pdf_path)
    text = "\n".join(p.get_text() for p in doc)
    flat = re.sub(r"\s+", " ", text).replace("\u20b9", "")
    expect = {
        "price": f2(n["price"]), "market cap": f0(n["mcap"]), "FY26 revenue": f0(n["REV_FY2026"]),
        "FY26 EBITDA": f0(n["EBITDA_FY2026"]), "FY26 PAT": f0(n["PATOWN_FY2026"]), "FY26 EPS": f2(n["EPS_FY2026"]),
        "ROE adj": pc(n["ROE_ADJ_Asian Paints_FY2026"]), "ROCE": pc(n["ROCE_Asian Paints_FY2026"]),
        "EBITDA margin": pc(n["EBITDAM_Asian Paints_FY2026"]), "Q2 net sales": "9,953.9", "Q2 PAT": "1,067.6",
        "H1 net sales": "20,475.3", "Q2 PBDIT margin": pc(m) if (m := n.get("m_q2")) else "",
        "consensus EPS": f2(n["cons_eps27"]), "target low": f0(n["tgt_Low"]), "target avg": f0(n["tgt_Average"]),
        "target median": f0(n["tgt_Median"]), "target high": f0(n["tgt_High"]), "NIFTY": f2(n["nifty"]),
        "promoters": pc(n["sh_Promoters"], 2), "checks": f"{n['checks_pass']} of {n['checks_total']}",
        "5y return": spc(n["ret5"]), "scorecard AP": f2(n["score26_Asian Paints"]),
        "disclaimer": "Educational project, not investment advice. The author holds no position.",
    }
    if not is_draft():
        expect.update(p3_expect(n))
    lines = [f"PDF: {pdf_path.name}, {doc.page_count} pages, {pdf_path.stat().st_size / 1e6:.2f} MB"]
    bad = 0
    for k, v in expect.items():
        ok = v.replace("\u20b9", "") in flat
        bad += (not ok)
        lines.append(f"  {'OK  ' if ok else 'MISS'} {k}: {v}")
    if not is_draft():
        val = n.get("val") or {}
        same = val.get("rating") == THESIS_WRITTEN_FOR
        bad += (not same)
        lines.append(f"  {'OK  ' if same else 'MISS'} rating from the rule ({val.get('rating')}) = rating the thesis text "
                     f"was written for ({THESIS_WRITTEN_FOR})")
    tags = sorted(set(re.findall(r"\{\{P3:([a-z0-9_]+)\}\}", flat)))
    lines.append(f"  P3 placeholders still in the PDF: {len(tags)} keys -> {', '.join(tags) if tags else 'none'}")
    lines.append(f"  page count {'OK' if 5 <= doc.page_count <= 10 else 'OUT OF RANGE'} (target 7-9)")
    lines.append("CHECK " + ("PASSED" if bad == 0 else f"FAILED ({bad} missing)"))
    if preview:
        preview.mkdir(parents=True, exist_ok=True)
        for i, p in enumerate(doc):
            p.get_pixmap(dpi=70).save(preview / f"page_{i + 1}.png")
    return lines


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p3-dir", default=str(P3_DEFAULT),
                    help="Project 3 folder (03-comparable-company-analysis); if missing, data/p3/ copies are used")
    ap.add_argument("--preview-dir", default=None, help="folder for PNG previews of each PDF page")
    args = ap.parse_args()
    d = load()
    n = compute(d)
    log = load_p3(Path(args.p3_dir) if args.p3_dir else None)
    if P3["fy28e_eps"] is not None:
        d["rel_hist"] = fill_relative_value(n)
        df_tv = P3["pv_tv"] / P3["tv"]            # discount factor Project 3 applies to the terminal value
        n["impl_exit"] = (P3["market_ev"] - P3["sum_pv_fcff"]) / df_tv / P3["ebitda_fy31e"]
        n["val"] = valuation(n)
        v = n["val"]
        rows = [{"case": "Base case", "w_dcf": WEIGHTS["dcf"], "w_comps": WEIGHTS["comps"], "w_rel": WEIGHTS["rel"],
                 "target_rs": v["target"], "upside": v["upside"], "rating": v["rating"]}]
        rows += [{"case": a["name"], "w_dcf": a["w"]["dcf"], "w_comps": a["w"]["comps"], "w_rel": a["w"]["rel"],
                  "target_rs": a["target"], "upside": a["upside"], "rating": a["rating"]} for a in v["alts"]]
        rows.append({"case": "Base weights, own 5-year P/E band as the relative lens", "w_dcf": WEIGHTS["dcf"],
                     "w_comps": WEIGHTS["comps"], "w_rel": WEIGHTS["rel"], "target_rs": v["own"]["target"],
                     "upside": v["own"]["upside"], "rating": v["own"]["rating"]})
        comp = pd.DataFrame(rows)
        comp.insert(1, "dcf_rs", P3["dcf_value"])
        comp.insert(2, "comps_rs", P3["comps_median"])
        comp.insert(3, "relative_rs", [P3["relative_value"]] * (len(rows) - 1) + [P3["own_band_value"]])
        comp.round(4).to_csv(OUT / "valuation_summary.csv", index=False)
        pd.DataFrame([{"key": k, "value": P3[k], "source": P3_SRC.get(k, "")} for k in P3_KEYS]).to_csv(
            OUT / "p3_inputs_used.csv", index=False)
        log.append(f"Valuation: DCF {P3['dcf_value']:.2f}, comps {P3['comps_median']:.0f}, relative "
                   f"{P3['relative_value']:.2f} -> target {v['target']:.2f}, upside {v['upside']:+.2%}, rating {v['rating']}; "
                   + "; ".join(f"{a['name']} {a['target']:.0f} ({a['rating']})" for a in v["alts"])
                   + f"; own band {v['own']['target']:.0f} ({v['own']['rating']})")
        log.append(f"P3 dict after the relative value: {sum(x is not None for x in P3.values())} of {len(P3)} keys filled; "
                   "sources in outputs/p3_inputs_used.csv")
    figs = charts(d, n)
    REP.mkdir(exist_ok=True)
    stem = "AsianPaints_Initiation_Report" + ("_DRAFT" if is_draft() else "")
    html = build_html(d, n, figs)
    html_path = REP / f"{stem}.html"
    html_path.write_text(html, encoding="utf-8")
    pdf_path = REP / f"{stem}.pdf"
    if not is_draft():                             # the final report replaces the phase-1 draft files
        for old in REP.glob("AsianPaints_Initiation_Report_DRAFT.*"):
            old.unlink()
    log.append(f"HTML: {html_path.name} ({len(html) / 1e3:.0f} KB); figures: {', '.join(figs.values())}")
    if print_pdf(html_path, pdf_path):
        log += check_pdf(pdf_path, n, Path(args.preview_dir) if args.preview_dir else None)
    else:
        log.append("PDF FAILED: Edge did not produce a file")
    keys = sorted(set(USED_PLACEHOLDERS))
    log.append(f"P3 keys used in HTML ({len(keys)}): {', '.join(keys)}")
    simple = {k: v for k, v in n.items() if isinstance(v, (int, float))}
    pd.Series(simple, name="value").rename_axis("name").to_csv(OUT / "report_numbers.csv")
    (OUT / "report_build_log.txt").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    main()
