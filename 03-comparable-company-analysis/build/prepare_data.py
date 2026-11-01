"""Turn the raw files in source_data/ into tidy model inputs in data/ (offline step, no internet needed).

Outputs (all Rs crore unless stated):
- data/peer_inputs.csv            one row per company: price, shares, TTM P&L, balance sheet, consensus
- data/asian_paints_history.csv   Asian Paints FY2022A-FY2026A, H1 FY26A, H1 FY27A, TTM (DCF base data)
- data/beta_weekly_returns.csv    5 years of weekly returns, Asian Paints and peers vs NIFTY 50
- data/beta_summary.csv           OLS regression betas (5y weekly, 2y weekly, 5y monthly)
- data/price_targets.csv          S&P Global consensus price targets (stockanalysis.com forecast pages)
- data/prepare_log.txt            reconciliations between sources and other checks
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "source_data"
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
LOG: list[str] = []

PRICE_DATE = pd.Timestamp("2026-10-30")          # Friday close used for all prices
WEEK52_START = pd.Timestamp("2025-10-31")        # 52 weeks ending 30-Oct-2026

COMPANIES = [
    # symbol, display name, Yahoo ticker, role, results date of the latest quarter in the TTM, note
    ("ASIANPAINT", "Asian Paints", "ASIANPAINT.NS", "Target", "2026-10-29",
     "Q2 FY27 results filed 29-Oct-2026 at 14:04 IST, during market hours"),
    ("BERGEPAINT", "Berger Paints", "BERGEPAINT.NS", "Peer", "2026-08-05",
     "Q2 FY27 board meeting on 5-Nov-2026, so TTM ends Jun-2026"),
    ("KANSAINER", "Kansai Nerolac", "KANSAINER.NS", "Peer", "2026-08-03",
     "Q2 FY27 board meeting on 4-Nov-2026, so TTM ends Jun-2026"),
    ("JSWDULUX", "JSW Dulux", "JSWDULUX.NS", "Peer", "2026-08-11",
     "Q2 FY27 results due around the 4-Nov-2026 investor call, so TTM ends Jun-2026"),
    ("INDIGOPNTS", "Indigo Paints", "INDIGOPNTS.NS", "Peer", "2026-10-30",
     "Q2 FY27 results filed 30-Oct-2026 at 17:41 IST, after the market close"),
]


def log(msg: str) -> None:
    LOG.append(msg)
    print(msg)


def num(x) -> float:
    """Parse '1,234.5', '-', '' or numbers into float (NaN when missing)."""
    if x is None:
        return float("nan")
    if isinstance(x, (int, float, np.floating)):
        return float(x)
    s = str(x).replace(",", "").replace("%", "").replace("\u20b9", "").replace("â¹", "").strip()
    if s in ("", "-", "--", "nan", "None"):
        return float("nan")
    try:
        return float(s)
    except ValueError:
        return float("nan")


# ---------------------------------------------------------------------------------------------
# Screener.in helpers
# ---------------------------------------------------------------------------------------------
def screener_table(sym: str, section: str) -> pd.DataFrame:
    df = pd.read_csv(SRC / "screener" / f"{sym}_{section}.csv")
    return df.set_index("item")


def schedule(sym: str, section: str, parent: str) -> pd.DataFrame:
    """Screener schedule JSON -> DataFrame (rows = line items, columns = periods)."""
    f = SRC / "screener" / "schedules" / f"{sym}_consolidated_{section}_{parent.replace(' ', '_')}.json"
    d = json.loads(f.read_text(encoding="utf-8"))["data"]
    rows = {k: {p: num(v) for p, v in vals.items()} for k, vals in d.items()
            if isinstance(vals, dict) and k not in ("setAttributes", "isExpandable")}
    return pd.DataFrame(rows).T


# ---------------------------------------------------------------------------------------------
# stockanalysis.com helpers (values in INR millions -> Rs crore = / 10)
# ---------------------------------------------------------------------------------------------
def sa_table(sym: str, page: str, idx: int) -> pd.DataFrame:
    df = pd.read_csv(SRC / "stockanalysis" / "raw" / f"{sym}_{page}_table{idx}.csv")
    return df.set_index(df.columns[0])


def sa_value(df: pd.DataFrame, row: str, date_text: str) -> float:
    cols = [c for c in df.columns if date_text in c]
    if not cols or row not in df.index:
        return float("nan")
    return num(df.loc[row, cols[0]])


def sa_estimates(sym: str) -> dict:
    """Consensus estimates embedded in the forecast page (S&P Global Market Intelligence)."""
    t = (SRC / "stockanalysis" / "raw" / f"{sym}_forecast.html").read_text(encoding="utf-8")
    out = {}
    m = re.search(r"estimates:\{stats:\{annual:\{(.*?)\}\},quarterly", t)
    block = m.group(1) if m else ""
    for key in ("epsThis", "epsNext", "revenueThis", "revenueNext"):
        mm = re.search(key + r":\{last:([-\d.e]+|null),this:([-\d.e]+|null)", block)
        out[key] = float(mm.group(2)) if mm and mm.group(2) != "null" else float("nan")
    m = re.search(r"table:\{annual:\{(.*?)\},quarterly", t)
    tab = m.group(1) if m else ""

    def arr(name: str) -> list:
        mm = re.search(r"(?<![A-Za-z])" + name + r":\[(.*?)\]", tab)
        return [x.strip().strip('"') for x in mm.group(1).split(",")] if mm else []

    dates = arr("dates")
    if "2027-03-31" in dates:
        i = dates.index("2027-03-31")
        for name in ("revenue", "netIncome", "operatingIncome", "analysts", "eps"):
            vals = arr(name)
            out[f"fy27_{name}"] = num(vals[i]) if i < len(vals) else float("nan")
    return out


def sa_shares(sym: str) -> float:
    """Exact share count (S&P 'Current Share Class') from the statistics page, in crore."""
    t = (SRC / "stockanalysis" / "raw" / f"{sym}_statistics.html").read_text(encoding="utf-8")
    m = re.search(r'id:"sharesOutClass",title:"Current Share Class",value:"[^"]*",hover:"([\d,]+)"', t)
    if not m:
        m = re.search(r'id:"sharesout",title:"Shares Outstanding",value:"[^"]*",hover:"([\d,]+)"', t)
    return num(m.group(1)) / 1e7 if m else float("nan")


def money(x) -> float:
    """'₹1,925' (possibly mis-decoded as 'â‚¹1,925') -> 1925.0"""
    s = re.sub(r"[^\d.\-]", "", str(x))
    return float(s) if s not in ("", "-", ".") else float("nan")


def sa_price_targets(sym: str) -> dict:
    """Consensus price-target range shown on the forecast page (table 0), plus the analyst count."""
    df = pd.read_csv(SRC / "stockanalysis" / "raw" / f"{sym}_forecast_table0.csv")
    if "Low" not in df.columns or df.empty or not (df.iloc[:, 0] == "Price").any():
        return {}
    row = df[df.iloc[:, 0] == "Price"].iloc[0]
    st = (SRC / "stockanalysis" / "raw" / f"{sym}_statistics.html").read_text(encoding="utf-8")
    m = re.search(r'title:"Analyst Count",value:"(\d+)"', st)
    return {"pt_low": money(row["Low"]), "pt_average": money(row["Average"]), "pt_median": money(row["Median"]),
            "pt_high": money(row["High"]), "pt_analysts": int(m.group(1)) if m else None}


# ---------------------------------------------------------------------------------------------
# Yahoo Finance prices
# ---------------------------------------------------------------------------------------------
def yahoo(ticker: str) -> pd.DataFrame:
    f = SRC / "yahoo_finance" / (ticker.replace("^", "IDX_") + "_daily.csv")
    df = pd.read_csv(f, index_col=0, parse_dates=True)
    return df.sort_index()


# ---------------------------------------------------------------------------------------------
# 1) Peer inputs
# ---------------------------------------------------------------------------------------------
def last_n_quarters(df: pd.DataFrame, n: int = 4) -> list[str]:
    return list(df.columns)[-n:]


def company_row(sym: str, name: str, yticker: str, role: str, results_date: str, note: str) -> dict:
    q = screener_table(sym, "quarters")
    pl = screener_table(sym, "profit-loss")
    qcols = last_n_quarters(q)
    ttm_end = qcols[-1]                                   # e.g. 'Sep 2026'
    npq = schedule(sym, "quarters", "Net Profit")
    pe_profit = sum(num(npq.loc["Profit for PE", c]) for c in qcols)
    reported_profit = sum(num(q.loc["Net Profit", c]) for c in qcols)
    exceptional_at = sum(num(npq.loc["Exceptional items AT", c]) for c in qcols) \
        if "Exceptional items AT" in npq.index else 0.0

    # Balance sheet: Sep-2026 for companies that reported Q2 FY27 by 30-Oct-2026, else Mar-2026
    bs_col_screener = "Sep 2026" if ttm_end == "Sep 2026" else "Mar 2026"
    bs_text_sa = "Sep 30, 2026" if ttm_end == "Sep 2026" else "Mar 31, 2026"
    borr = schedule(sym, "balance-sheet", "Borrowings")
    borrowings = sum(num(borr.loc[i, bs_col_screener]) for i in borr.index
                     if not np.isnan(num(borr.loc[i, bs_col_screener])))
    leases = num(borr.loc["Lease Liabilities", bs_col_screener]) if "Lease Liabilities" in borr.index else 0.0
    oth = schedule(sym, "balance-sheet", "Other Liabilities")
    nci = num(oth.loc["Non controlling int", bs_col_screener]) if "Non controlling int" in oth.index else 0.0
    if np.isnan(nci):
        nci = 0.0

    sa_bs = sa_table(sym, "balance_annual", 0)
    sa_li = sa_table(sym, "balance_annual", 1)
    sa_eq = sa_table(sym, "balance_annual", 2)
    cash = sa_value(sa_bs, "Cash & Equivalents", bs_text_sa) / 10
    sti = np.nansum([sa_value(sa_bs, "Short-Term Investments", bs_text_sa),
                     sa_value(sa_bs, "Trading Asset Securities", bs_text_sa)]) / 10
    lti = sa_value(sa_bs, "Long-Term Investments", bs_text_sa) / 10
    lti = 0.0 if np.isnan(lti) else lti
    sa_debt = np.nansum([sa_value(sa_li, r, bs_text_sa) for r in
                         ("Short-Term Debt", "Current Portion of Long-Term Debt", "Current Portion of Leases",
                          "Long-Term Debt", "Long-Term Leases")]) / 10
    sa_mi = sa_value(sa_eq, "Minority Interest", bs_text_sa) / 10

    # Indigo Paints: no NCI line in equity; the 49% of Apple Chemie it does not own is carried as a
    # financial liability (consolidated non-current other financial liabilities Rs 62.22 cr vs Rs 0.51 cr
    # standalone, Q2 FY27 results p.6). Treated as the minority-interest equivalent.
    nci_note = ""
    if sym == "INDIGOPNTS":
        nci = round((6222.43 - 50.54) / 100, 2)
        nci_note = ("No NCI line in equity; Rs 61.72 cr liability for the 49% of Apple Chemie not owned "
                    "(consolidated minus standalone other financial liabilities, results p.6) used instead")

    # Prices
    px = yahoo(yticker)
    price = float(px.loc[PRICE_DATE, "Close"])
    win = px.loc[(px.index >= WEEK52_START) & (px.index <= PRICE_DATE)]
    hi52, lo52 = float(win["High"].max()), float(win["Low"].min())
    hi52_close, lo52_close = float(win["Close"].max()), float(win["Close"].min())

    shares = sa_shares(sym)
    est = sa_estimates(sym)
    eps27, eps28 = est.get("epsThis"), est.get("epsNext")
    split_note = ""
    if sym == "JSWDULUX":
        # S&P consensus EPS is still on the pre-split share count (1:10 split, record date 22-Oct-2026):
        # FY27E net income 403.65 cr / EPS 88.2 = 4.58 cr shares. Divide by 10 for the current share count.
        eps27, eps28 = eps27 / 10, eps28 / 10
        split_note = "Consensus EPS divided by 10 for the 1:10 split (S&P still shows pre-split EPS)"

    # Screener top ratios (ROCE, ROE)
    summ = json.loads((SRC / "screener" / "screener_summary.json").read_text(encoding="utf-8"))
    tr = summ[f"{sym}_consolidated"]["top_ratios"]

    # History for growth
    rev_fy23 = num(pl.loc["Sales", "Mar 2023"])
    rev_fy26 = num(pl.loc["Sales", "Mar 2026"])

    row = {
        "symbol": sym, "company": name, "role": role, "yahoo_ticker": yticker,
        "basis": "Consolidated",
        "price_rs": round(price, 2), "price_date": PRICE_DATE.date().isoformat(),
        "high_52w_rs": round(hi52, 2), "low_52w_rs": round(lo52, 2),
        "high_52w_close_rs": round(hi52_close, 2), "low_52w_close_rs": round(lo52_close, 2),
        "shares_crore": round(shares, 4),
        "ttm_end": ttm_end, "latest_results_date": results_date, "timing_note": note,
        "ttm_quarters": " + ".join(qcols),
        "ttm_revenue": sum(num(q.loc["Sales", c]) for c in qcols),
        "ttm_ebitda": sum(num(q.loc["Operating Profit", c]) for c in qcols),
        "ttm_depreciation": sum(num(q.loc["Depreciation", c]) for c in qcols),
        "ttm_other_income": sum(num(q.loc["Other Income", c]) for c in qcols),
        "ttm_pat_reported": reported_profit,
        "ttm_exceptional_after_tax": exceptional_at,
        "ttm_pat_for_pe": round(pe_profit, 2),
        "bs_date": "30-Sep-2026" if ttm_end == "Sep 2026" else "31-Mar-2026",
        "borrowings_incl_leases": round(borrowings, 2), "lease_liabilities": round(leases, 2),
        "minority_interest": round(nci, 2), "minority_note": nci_note,
        "cash_and_equivalents": round(cash, 2), "liquid_investments": round(sti, 2),
        "noncurrent_investments_memo": round(lti, 2),
        "check_sa_total_debt": round(sa_debt, 2), "check_sa_minority_interest": round(sa_mi, 2),
        "revenue_fy2023": rev_fy23, "revenue_fy2026": rev_fy26,
        "roce_fy2026_pct": tr.get("ROCE", {}).get("numbers", [np.nan])[0],
        "roe_fy2026_pct": tr.get("ROE", {}).get("numbers", [np.nan])[0],
        "screener_market_cap": tr.get("Market Cap", {}).get("numbers", [np.nan])[0],
        "screener_pe": tr.get("Stock P/E", {}).get("numbers", [np.nan])[0],
        "screener_high_52w": tr.get("High / Low", {}).get("numbers", [np.nan, np.nan])[0],
        "screener_low_52w": tr.get("High / Low", {}).get("numbers", [np.nan, np.nan])[1],
        "fy27e_revenue": round(est.get("revenueThis", np.nan) / 1e7, 1),
        "fy28e_revenue": round(est.get("revenueNext", np.nan) / 1e7, 1),
        "fy27e_eps_rs": round(eps27, 3), "fy28e_eps_rs": round(eps28, 3),
        "fy27e_net_income": round(est.get("fy27_netIncome", np.nan) / 1e7, 1),
        "fy27e_ebit": round(est.get("fy27_operatingIncome", np.nan) / 1e7, 1),
        "fy27e_analysts": est.get("fy27_analysts"),
        "consensus_note": split_note,
    }
    # Reconciliations
    log(f"[{sym}] TTM {row['ttm_quarters']}: revenue {row['ttm_revenue']:.0f}, EBITDA {row['ttm_ebitda']:.0f}, "
        f"PAT for P/E {pe_profit:.1f} (reported {reported_profit:.0f}, exceptional AT {exceptional_at:.0f})")
    log(f"[{sym}] debt incl. leases Screener {borrowings:.1f} vs S&P {sa_debt:.1f}; NCI {nci:.1f} (S&P {sa_mi:.1f}); "
        f"cash {cash:.1f}, liquid investments {sti:.1f}, non-current investments {lti:.1f} at {row['bs_date']}")
    mcap = price * shares
    log(f"[{sym}] price {price:.2f} x shares {shares:.4f} cr = market cap {mcap:,.0f} (Screener {row['screener_market_cap']:,.0f}, "
        f"diff {mcap / row['screener_market_cap'] - 1:+.2%}); P/E {mcap / pe_profit:.1f} (Screener {row['screener_pe']})")
    log(f"[{sym}] 52w high/low (intraday) {hi52:.1f}/{lo52:.1f}; closes {hi52_close:.1f}/{lo52_close:.1f}; "
        f"Screener {row['screener_high_52w']}/{row['screener_low_52w']}")
    # EPS-implied diluted share count from the latest quarter (rounding of EPS limits precision)
    last_q = qcols[-1]
    eps_q = num(q.loc["EPS in Rs", last_q])
    pfe = num(npq.loc["Profit for EPS", last_q])
    if eps_q and not np.isnan(eps_q):
        log(f"[{sym}] latest-quarter profit for EPS {pfe:.2f} / EPS {eps_q:.2f} = {pfe / eps_q:.3f} cr shares "
            f"(S&P count {shares:.3f} cr, diff {pfe / eps_q / shares - 1:+.2%})")
    return row


# ---------------------------------------------------------------------------------------------
# 2) Asian Paints history for the DCF
# ---------------------------------------------------------------------------------------------
def asian_paints_history() -> pd.DataFrame:
    sym = "ASIANPAINT"
    pl = screener_table(sym, "profit-loss")
    cf = screener_table(sym, "cash-flow")
    oa = schedule(sym, "balance-sheet", "Other Assets")
    ol = schedule(sym, "balance-sheet", "Other Liabilities")
    br = schedule(sym, "balance-sheet", "Borrowings")
    cfi = schedule(sym, "cash-flow", "Cash from Investing Activity")
    cfo_s = schedule(sym, "cash-flow", "Cash from Operating Activity")
    cff = schedule(sym, "cash-flow", "Cash from Financing Activity")
    years = ["Mar 2022", "Mar 2023", "Mar 2024", "Mar 2025", "Mar 2026"]
    rows = []
    for y in years:
        rows.append({
            "period": "FY" + y[-4:] + "A", "period_end": y,
            "revenue": num(pl.loc["Sales", y]),
            "ebitda": num(pl.loc["Operating Profit", y]),
            "depreciation": num(pl.loc["Depreciation", y]),
            "other_income": num(pl.loc["Other Income", y]),
            "interest": num(pl.loc["Interest", y]),
            "pbt": num(pl.loc["Profit before tax", y]),
            "tax_rate_pct": num(pl.loc["Tax %", y]),
            "net_profit": num(pl.loc["Net Profit", y]),
            "eps_rs": num(pl.loc["EPS in Rs", y]),
            "cfo": num(cf.loc["Cash from Operating Activity", y]),
            "capex": -num(cfi.loc["Fixed assets purchased", y]),
            "working_capital_change_cf": num(cfo_s.loc["Working capital changes", y]),
            "inventories": num(oa.loc["Inventories", y]),
            "trade_receivables": num(oa.loc["Trade receivables", y]),
            "trade_payables": num(ol.loc["Trade Payables", y]),
            "borrowings_incl_leases": float(np.nansum([num(br.loc[i, y]) for i in br.index])),
            "lease_liabilities": num(br.loc["Lease Liabilities", y]),
            # Screener financing schedule 'Financial liabilities' = principal portion of lease payments
            # (FY26 340 vs S&P 'Lease Payments' 339.8). Used as the proxy for new right-of-use additions.
            "lease_principal_repaid": -num(cff.loc["Financial liabilities", y]),
            "source": "Screener.in consolidated (annual P&L, cash flow, schedules)",
        })
    df = pd.DataFrame(rows)
    fil = pd.read_csv(DATA / "asian_paints_q2fy27_filing.csv")

    def f(item: str, period_start: str) -> float:
        m = fil[(fil["item"] == item) & (fil["period"].str.startswith(period_start))]
        return float(m["value_rs_crore"].iloc[0]) if len(m) else float("nan")

    # Replace FY2026 P&L with the audited company figures (Screener rounds to Rs 1 crore)
    i26 = df.index[df["period"] == "FY2026A"][0]
    for col, item in (("revenue", "revenue_from_operations"), ("ebitda", "ebitda_pbdit"),
                      ("depreciation", "depreciation_amortisation"), ("other_income", "other_income"),
                      ("interest", "finance_costs"), ("pbt", "profit_before_tax")):
        old = df.loc[i26, col]
        df.loc[i26, col] = f(item, "FY26")
        log(f"[AP FY2026] {col}: Screener {old:,.1f} -> company filing {df.loc[i26, col]:,.2f}")
    df.loc[i26, "tax_rate_pct"] = round(f("tax_expense", "FY26") / f("profit_before_tax", "FY26") * 100, 2)
    df.loc[i26, "source"] = "FY2026 P&L: company filing (audited, Q2 FY27 results p.12); rest Screener.in"
    # Half-year rows from the filing
    for label, start in (("H1 FY2026A", "H1 FY26"), ("H1 FY2027A", "H1 FY27")):
        df = pd.concat([df, pd.DataFrame([{
            "period": label, "period_end": "Sep " + ("2025" if "26" in start else "2026"),
            "revenue": f("revenue_from_operations", start), "ebitda": f("ebitda_pbdit", start),
            "depreciation": f("depreciation_amortisation", start), "cfo": f("cash_from_operations", start),
            "capex": f("capex_ppe_and_intangibles", start),
            "source": "Company filing: Q2 FY27 results (consolidated P&L p.12, cash flow p.14)"}])],
            ignore_index=True)
    # Reconcile H1 FY27 with Screener quarters (Jun-2026 + Sep-2026)
    q = screener_table(sym, "quarters")
    h1_screener = num(q.loc["Sales", "Jun 2026"]) + num(q.loc["Sales", "Sep 2026"])
    log(f"[AP H1 FY27] revenue filing {f('revenue_from_operations', 'H1 FY27'):,.2f} vs Screener Jun+Sep {h1_screener:,.0f}")
    ebitda_s = num(q.loc["Operating Profit", "Jun 2026"]) + num(q.loc["Operating Profit", "Sep 2026"])
    log(f"[AP H1 FY27] EBITDA filing {f('ebitda_pbdit', 'H1 FY27'):,.2f} vs Screener {ebitda_s:,.0f}")
    return df


# ---------------------------------------------------------------------------------------------
# 3) Betas: OLS of weekly returns vs NIFTY 50
# ---------------------------------------------------------------------------------------------
def ols(y: pd.Series, x: pd.Series) -> dict:
    d = pd.concat([y, x], axis=1).dropna()
    yy, xx = d.iloc[:, 0].values, d.iloc[:, 1].values
    xm, ym = xx.mean(), yy.mean()
    beta = ((xx - xm) * (yy - ym)).sum() / ((xx - xm) ** 2).sum()
    alpha = ym - beta * xm
    resid = yy - alpha - beta * xx
    n = len(yy)
    se = np.sqrt((resid ** 2).sum() / (n - 2) / ((xx - xm) ** 2).sum())
    r2 = 1 - (resid ** 2).sum() / ((yy - ym) ** 2).sum()
    return {"beta": beta, "alpha_per_period": alpha, "r_squared": r2, "std_error": se, "n_obs": n,
            "start": d.index.min().date().isoformat(), "end": d.index.max().date().isoformat()}


def betas() -> tuple[pd.DataFrame, pd.DataFrame]:
    nifty = yahoo("^NSEI")["Close"]
    weekly = {"NIFTY50": nifty.resample("W-FRI").last()}
    monthly = {"NIFTY50": nifty.resample("ME").last()}
    for sym, name, yt, *_ in COMPANIES:
        px = yahoo(yt)["Adj Close"]          # dividend- and split-adjusted (total return)
        weekly[sym] = px.resample("W-FRI").last()
        monthly[sym] = px.resample("ME").last()
    wk = pd.DataFrame(weekly).loc[:PRICE_DATE].pct_change()
    mo = pd.DataFrame(monthly).loc[:"2026-10-31"].pct_change()
    wk5 = wk.iloc[-260:]                         # 260 weekly returns = 5 years to 30-Oct-2026
    wk2 = wk.iloc[-104:]
    mo5 = mo.iloc[-60:]
    rows = []
    for sym, name, *_ in COMPANIES:
        for label, frame in (("5y weekly", wk5), ("2y weekly", wk2), ("5y monthly", mo5)):
            r = ols(frame[sym], frame["NIFTY50"])
            r.update({"symbol": sym, "company": name, "window": label,
                      "blume_adjusted_beta": 0.67 * r["beta"] + 0.33})
            rows.append(r)
            if label == "5y weekly":
                big = frame[sym][frame[sym] < -0.08]
                log(f"[beta {sym}] 5y weekly beta {r['beta']:.3f} (R2 {r['r_squared']:.3f}, n {r['n_obs']}); "
                    f"weekly moves below -8%: {[(d.date().isoformat(), round(v, 3)) for d, v in big.items()]}")
    summary = pd.DataFrame(rows)[["symbol", "company", "window", "beta", "blume_adjusted_beta", "r_squared",
                                  "std_error", "n_obs", "start", "end", "alpha_per_period"]]
    out = wk5.copy()
    out.index.name = "week_ending_friday"
    return summary, out


def main() -> None:
    peers = pd.DataFrame([company_row(*c) for c in COMPANIES])
    peers.to_csv(DATA / "peer_inputs.csv", index=False)
    hist = asian_paints_history()
    hist.to_csv(DATA / "asian_paints_history.csv", index=False)
    bsum, wk = betas()
    bsum.to_csv(DATA / "beta_summary.csv", index=False)
    wk.to_csv(DATA / "beta_weekly_returns.csv")
    pts = []
    for sym, name, *_ in COMPANIES:
        p = sa_price_targets(sym)
        if p:
            pts.append({"symbol": sym, "company": name, **p,
                        "source": f"https://stockanalysis.com/quote/nse/{sym}/forecast/ (S&P Global consensus)"})
    pd.DataFrame(pts).to_csv(DATA / "price_targets.csv", index=False)
    log(f"price targets: {pts}")
    (DATA / "prepare_log.txt").write_text("\n".join(LOG), encoding="utf-8")
    print("PREPARE DONE")


if __name__ == "__main__":
    main()
