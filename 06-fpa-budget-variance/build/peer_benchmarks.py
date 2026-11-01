"""Summarise listed-peer benchmarks from the saved Screener files (offline) into data/peer_benchmarks.csv.

Reads source_data/screener/csv/<SYMBOL>_profit-loss.csv, _quarters.csv and _expenses_breakdown.csv
(saved by build/fetch_source_data.py) and writes one row per peer for its latest full fiscal year:
revenue, revenue growth, material / employee / manufacturing / other cost as % of sales (Screener's
expense schedule), operating margin (OPM %, i.e. EBITDA margin before other income), net margin, and the
latest reported quarter with its year-on-year growth.

Run:  python build/peer_benchmarks.py
"""
from __future__ import annotations

import json
import os
import re

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCR = os.path.join(ROOT, "source_data", "screener")
CSV = os.path.join(SCR, "csv")
OUT = os.path.join(ROOT, "data", "peer_benchmarks.csv")


def _row(df: pd.DataFrame, pattern: str):
    m = df[df["item"].astype(str).str.match(pattern, na=False)]
    return m.iloc[0] if len(m) else None


def _num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(v) else v


def latest_col(df: pd.DataFrame, prefix: str, sales_pattern=r"^(Sales|Revenue)"):
    """Latest column (e.g. 'Mar 2026') whose Sales value is reported."""
    s = _row(df, sales_pattern)
    cols = [c for c in df.columns if re.match(prefix, str(c))]
    good = [c for c in cols if s is not None and _num(s[c]) is not None]
    return good[-1] if good else None


def prior_col(col: str) -> str:
    mon, yr = col.split()
    return f"{mon} {int(yr) - 1}"


def summarise() -> pd.DataFrame:
    with open(os.path.join(SCR, "screener_summary.json"), encoding="utf-8") as fh:
        meta = json.load(fh)["peers"]
    out = []
    for sym, info in meta.items():
        pl = pd.read_csv(os.path.join(CSV, f"{sym}_profit-loss.csv"))
        fy = latest_col(pl, r"^Mar \d{4}$")
        if fy is None:
            continue
        py = prior_col(fy)
        sales = _row(pl, r"^(Sales|Revenue)")
        opm = _row(pl, r"^OPM")
        np_ = _row(pl, r"^Net Profit")
        rev, rev_py = _num(sales[fy]), _num(sales.get(py))
        rec = {"symbol": sym, "company": info["name"], "segment": info["segment"], "screener_view": info["view"],
               "fiscal_year": "FY" + fy.split()[1], "revenue_rs_cr": rev,
               "revenue_growth_pct": (rev / rev_py - 1) * 100 if rev and rev_py else None,
               "opm_pct": _num(opm[fy]) if opm is not None else None,
               "net_margin_pct": (_num(np_[fy]) / rev * 100) if np_ is not None and rev and _num(np_[fy]) is not None
               else None}
        ex_path = os.path.join(CSV, f"{sym}_expenses_breakdown.csv")
        if os.path.exists(ex_path):
            ex = pd.read_csv(ex_path)
            for pat, key in ((r"^Material", "material_cost_pct"), (r"^Employee", "employee_cost_pct"),
                             (r"^Manufacturing", "manufacturing_cost_pct"), (r"^Other", "other_cost_pct")):
                r = _row(ex, pat)
                rec[key] = _num(r[fy]) if r is not None and fy in ex.columns else None
        qpath = os.path.join(CSV, f"{sym}_quarters.csv")
        if os.path.exists(qpath):
            q = pd.read_csv(qpath)
            lq = latest_col(q, r"^[A-Z][a-z]{2} \d{4}$")
            if lq:
                qs, qo = _row(q, r"^(Sales|Revenue)"), _row(q, r"^OPM")
                cur, prev = _num(qs[lq]), _num(qs.get(prior_col(lq)))
                rec.update({"latest_quarter": lq, "latest_q_revenue_rs_cr": cur,
                            "latest_q_growth_pct": (cur / prev - 1) * 100 if cur and prev else None,
                            "latest_q_opm_pct": _num(qo[lq]) if qo is not None else None})
        rec["source_file"] = f"source_data/screener/{info['xlsx']}"
        rec["source_url"] = info["url"]
        out.append(rec)
    cols = ["symbol", "company", "segment", "screener_view", "fiscal_year", "revenue_rs_cr", "revenue_growth_pct",
            "material_cost_pct", "employee_cost_pct", "manufacturing_cost_pct", "other_cost_pct", "opm_pct",
            "net_margin_pct", "latest_quarter", "latest_q_revenue_rs_cr", "latest_q_growth_pct", "latest_q_opm_pct",
            "source_file", "source_url"]
    df = pd.DataFrame(out)
    for c in cols:
        if c not in df.columns:
            df[c] = None
    return df[cols]


def main():
    df = summarise()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    df.round(2).to_csv(OUT, index=False)
    with pd.option_context("display.width", 220, "display.max_columns", 30):
        print(df.drop(columns=["source_url", "source_file", "segment"]).round(1).to_string(index=False))
    cur = df[df["fiscal_year"] == df["fiscal_year"].max()]
    print("\nMedian of current peers:",
          {k: round(float(cur[k].median()), 1) for k in ("revenue_growth_pct", "material_cost_pct",
                                                           "employee_cost_pct", "opm_pct", "net_margin_pct")
           if cur[k].notna().any()})
    print(f"Saved {OUT}")


if __name__ == "__main__":
    main()
