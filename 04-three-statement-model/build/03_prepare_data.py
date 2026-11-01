"""Tidy historical data for the UltraTech three-statement model (offline step, no network).

The audited consolidated statements (FY2022-FY2026) were transcribed from the company's results PDFs
(page extracts are in source_data/company_filings/). The script checks every transcribed block against the
subtotals printed in the same filing, cross-checks against Screener, and writes:

  data/hist_income_statement.csv   P&L line items, Rs crore
  data/hist_balance_sheet.csv      statement of assets and liabilities, Rs crore, with the model line each item maps to
  data/hist_cash_flow.csv          cash-flow lines used by the model, Rs crore
  data/operating_kpis.csv          sales volume, capacity, net sales split (investor presentations)
  data/debt_maturities.csv         scheduled repayments of borrowings outstanding at 31-Mar-2026 (AR FY26 Note 17)
  data/market_inputs.json          share price, share count, macro inputs with sources
  data/crosscheck_screener.csv     company figures vs Screener consolidated
  data/prepare_log.txt             PASS/FAIL log of all the checks

Run:  python build/03_prepare_data.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
YEARS = ["FY2022", "FY2023", "FY2024", "FY2025", "FY2026"]

SRC_FY26 = "FY26 audited consolidated results (27-Apr-2026), PDF p.8-10"
SRC_FY24 = "FY24 audited consolidated results (29-Apr-2024), PDF p.1-3"
SRC_FY23 = "FY23 audited consolidated results (28-Apr-2023), PDF p.1-3"
# column source per year: FY25 uses the comparative column of the FY26 filing (the FY25 PDF is an image scan)
YEAR_SRC = {"FY2022": SRC_FY23, "FY2023": SRC_FY23, "FY2024": SRC_FY24, "FY2025": SRC_FY26, "FY2026": SRC_FY26}

# ---------------------------------------------------------------- income statement (Rs crore)
IS = [  # (line, model group, FY22..FY26)
    ("Revenue from operations", "revenue", [52598.83, 63239.98, 70908.14, 75955.13, 88511.53]),
    ("Other income", "other_income", [507.81, 503.08, 616.95, 744.17, 577.51]),
    ("Cost of materials consumed", "raw_material", [7096.49, 8933.49, 10252.41, 11821.72, 14568.44]),
    ("Purchases of stock-in-trade", "raw_material", [1251.66, 1299.68, 1733.86, 1869.74, 2516.57]),
    ("Changes in inventories of FG, WIP and stock-in-trade", "raw_material", [-383.16, -518.21, -83.35, 12.27, 103.35]),
    ("Employee benefits expense", "employee", [2534.68, 2738.97, 3037.58, 3604.59, 4162.44]),
    ("Finance costs", "finance_costs", [944.71, 822.72, 968.00, 1650.54, 1871.71]),
    ("Depreciation and amortisation", "da", [2714.75, 2887.99, 3145.30, 4014.95, 4644.46]),
    ("Power and fuel", "power_fuel", [12137.26, 18491.32, 18283.32, 18419.15, 19597.16]),
    ("Freight and forwarding", "freight", [11712.33, 14009.16, 15880.67, 17459.83, 19169.13]),
    ("Other expenses", "other_exp", [6735.22, 7665.72, 8835.09, 10210.38, 11374.21]),
    ("Exceptional items (charge)", "exceptional", [0.0, 0.0, 72.00, 97.43, 138.55]),
    ("Share in profit/(loss) of associates and JV", "jv", [1.70, 4.03, 22.01, -10.57, -15.83]),
    ("Current tax", "tax", [1211.22, 2070.77, 2218.48, 828.29, 2313.62]),
    ("Deferred tax", "tax", [-21.16, 272.08, 199.78, 660.20, 425.22]),
    ("Profit from discontinued operations (net)", "discontinued", [159.92, 0.0, 0.0, 0.0, 0.0]),
    ("Profit attributable to non-controlling interest", "nci", [-10.05, 9.44, -1.04, 0.53, 22.71]),
]
IS_REPORTED = {  # subtotals printed in the filings, used for checks
    "Total expenses": [44743.94, 56330.84, 62052.88, 69063.17, 78007.47],
    "Profit before tax": [8364.40, 7416.25, 9422.22, 7528.13, 10927.19],
    "Net profit (incl. discontinued)": [7334.26, 5073.40, 7003.96, 6039.64, 8188.35],
    "Profit attributable to owners": [7344.31, 5063.96, 7005.00, 6039.11, 8165.64],
    "Basic EPS (Rs)": [254.64, 175.63, 243.05, 205.30, 277.62],
}

# ---------------------------------------------------------------- balance sheet (Rs crore, 31 March)
BS = [  # (line, section, model line, Mar-22..Mar-26)
    ("Property, plant and equipment", "NCA", "Net fixed assets", [42592.19, 46480.28, 50126.09, 76015.19, 80283.38]),
    ("Right-of-use assets", "NCA", "Net fixed assets", [1178.60, 1190.36, 916.27, 835.73, 714.34]),
    ("Goodwill", "NCA", "Net fixed assets", [6250.21, 6329.26, 6345.49, 7681.78, 7909.05]),
    ("Other intangible assets", "NCA", "Net fixed assets", [5466.57, 5579.10, 5489.76, 10031.52, 9886.78]),
    ("Intangible assets under development", "NCA", "Net fixed assets", [7.42, 5.48, 28.41, 45.92, 466.40]),
    ("Capital work-in-progress", "NCA", "Capital work-in-progress", [4777.25, 4034.91, 6782.77, 6188.27, 8275.87]),
    ("Investments accounted using equity method", "NCA", "Investments", [30.17, 876.01, 968.94, 300.12, 319.41]),
    ("Investments (non-current)", "NCA", "Investments", [1342.26, 584.34, 1795.21, 1997.28, 2684.48]),
    ("Loans (non-current)", "NCA", "Other assets", [9.59, 9.22, 8.31, 16.21, 17.21]),
    ("Other financial assets (non-current)", "NCA", "Other assets", [1109.98, 1881.11, 1457.23, 2933.16, 3063.39]),
    ("Income tax assets (non-current)", "NCA", "Other assets", [479.46, 401.94, 456.03, 857.91, 266.26]),
    ("Deferred tax assets (net)", "NCA", "Other assets", [16.35, 6.56, 4.90, 65.09, 60.95]),
    ("Other non-current assets", "NCA", "Other assets", [3078.27, 3265.49, 3264.23, 2991.77, 2181.09]),
    ("Inventories", "CA", "Inventories", [5595.58, 6611.83, 8329.74, 9562.98, 9694.28]),
    ("Investments (current)", "CA", "Investments", [4963.34, 5836.60, 5484.80, 2859.07, 3735.62]),
    ("Trade receivables", "CA", "Trade receivables", [3071.61, 3867.02, 4278.16, 5890.25, 6028.75]),
    ("Cash and cash equivalents", "CA", "Cash and cash equivalents", [120.54, 370.37, 553.58, 467.21, 354.48]),
    ("Bank balances other than cash", "CA", "Other bank balances", [238.64, 779.22, 229.63, 1206.11, 1029.87]),
    ("Loans (current)", "CA", "Other assets", [6.86, 7.67, 8.91, 10.00, 13.37]),
    ("Other financial assets (current)", "CA", "Other assets", [1871.95, 1433.82, 2310.35, 1298.68, 1535.87]),
    ("Income tax assets (current)", "CA", "Other assets", [0.09, 0.07, 0.07, 58.00, 64.45]),
    ("Other current assets", "CA", "Other assets", [1611.33, 1818.28, 1948.23, 2247.21, 2645.06]),
    ("Assets held for sale", "HFS", "Other assets", [9.53, 18.02, 14.90, 137.69, 145.69]),
    ("Equity share capital", "EQ", "Equity share capital", [288.67, 288.69, 288.69, 294.68, 294.68]),
    ("Other equity", "EQ", "Other equity", [50146.60, 54035.85, 59938.78, 70411.53, 76328.86]),
    ("Share application money pending allotment", "EQ", "Other equity", [0.0, 0.0, 0.01, 0.56, 0.0]),
    ("Non-controlling interest", "EQ", "Non-controlling interest", [-3.06, 55.63, 55.94, 3186.59, 4088.90]),
    ("Borrowings (non-current)", "NCL", "Borrowings", [5303.00, 5356.41, 5307.78, 15780.77, 15018.82]),
    ("Lease liabilities (non-current)", "NCL", "Lease liabilities", [978.20, 1010.65, 942.11, 868.21, 751.72]),
    ("Other financial liabilities (non-current)", "NCL", "Other liabilities", [303.48, 319.84, 240.86, 287.82, 236.35]),
    ("Provisions (non-current)", "NCL", "Other liabilities", [617.84, 624.21, 670.57, 892.09, 934.96]),
    ("Deferred tax liabilities (net)", "NCL", "Deferred tax liabilities", [6033.24, 6260.11, 6447.78, 9579.44, 9890.06]),
    ("Other non-current liabilities", "NCL", "Other liabilities", [4.63, 3.78, 3.53, 30.49, 0.0]),
    ("Borrowings (current)", "CL", "Borrowings", [4899.84, 4544.37, 4990.61, 7250.22, 7761.84]),
    ("Lease liabilities (current)", "CL", "Lease liabilities", [117.76, 146.31, 162.45, 202.98, 222.71]),
    ("Trade payables - micro and small enterprises", "CL", "Trade payables", [124.47, 183.40, 254.19, 272.52, 518.62]),
    ("Trade payables - others", "CL", "Trade payables", [5738.36, 7025.90, 8224.14, 9054.96, 9718.09]),
    ("Other financial liabilities (current)", "CL", "Other liabilities", [3608.55, 4783.56, 5326.92, 6552.32, 6510.58]),
    ("Other current liabilities", "CL", "Other liabilities", [4890.94, 5177.40, 5706.68, 6692.18, 6311.87]),
    ("Provisions (current)", "CL", "Other liabilities", [247.98, 204.43, 257.50, 350.21, 354.84]),
    ("Current tax liabilities (net)", "CL", "Other liabilities", [527.29, 1366.42, 1983.47, 1989.58, 2433.15]),
]
BS_REPORTED = {
    "NCA": [66338.32, 70644.06, 77643.64, 109959.95, 116128.61],
    "CA": [17479.94, 20724.88, 23143.47, 23599.51, 25101.75],
    "NCL": [13240.39, 13575.00, 13612.63, 27438.82, 26831.91],
    "CL": [20155.19, 23431.79, 26905.96, 32364.97, 33831.70],
    "Total assets": [83827.79, 91386.96, 100802.01, 133697.15, 141376.05],
    "Total equity and liabilities": [83827.79, 91386.96, 100802.01, 133697.15, 141376.05],
}
BS_SRC = {"FY2022": "FY23 results PDF p.2 (comparative)", "FY2023": "FY24 results PDF p.2 (comparative)",
          "FY2024": "FY24 results PDF p.2", "FY2025": "FY26 results PDF p.9 (comparative)",
          "FY2026": "FY26 results PDF p.9"}

# ---------------------------------------------------------------- cash flow (Rs crore)
CF = [  # (line, FY22..FY26)
    ("Net cash from operating activities", [9283.24, 9068.51, 10897.54, 10673.43, 15315.86]),
    ("Purchase of property, plant and equipment", [-5613.41, -6200.11, -9005.59, -9129.33, -9677.77]),
    ("Net cash from investing activities", [2257.01, -7187.07, -8788.12, -16504.45, -9480.08]),
    ("Net proceeds from/(repayment of) borrowings", [-10171.10, 452.94, 329.91, 8859.26, -1465.89]),
    ("Interest paid (excl. lease interest)", [-960.94, -701.56, -853.46, -1478.99, -1868.69]),
    ("Dividends paid", [-1065.00, -1091.27, -1094.43, -2011.65, -2273.36]),
    ("Net cash from financing activities", [-12497.93, -1631.00, -1925.65, 5075.76, -5953.57]),
    ("Cash and cash equivalents at beginning of year", [177.21, 120.54, 370.37, 553.58, 467.21]),
    ("Cash acquired/transferred (acquisitions, discontinued ops) and FX", [901.01, -0.61, -0.56, 668.89, 5.06]),
    ("Cash and cash equivalents at end of year", [120.54, 370.37, 553.58, 467.21, 354.48]),
]
CF_NOTE = {
    "Net proceeds from/(repayment of) borrowings": "non-current proceeds less repayments plus current borrowings (net)",
    "Cash acquired/transferred (acquisitions, discontinued ops) and FX":
        "FY22: 901.48 from discontinued ops less 0.47 FX; FY25: 1.89 RAK + 76.76 Kesoram + 586.45 India Cements + 3.79 FX",
}
CF_SRC = {"FY2022": "FY23 results PDF p.3 (comparative)", "FY2023": "FY24 results PDF p.3 (comparative)",
          "FY2024": "FY24 results PDF p.3", "FY2025": "FY26 results PDF p.10 (comparative)",
          "FY2026": "FY26 results PDF p.10"}

# ---------------------------------------------------------------- operating KPIs
KPI = [  # (kpi, unit, FY22..FY26, source)
    ("Sales volume (consolidated)", "MnT", [93.99, 105.70, 119.04, 135.83, 154.25],
     "Q4FY22 pres p.7; Q4FY23 pres p.35; Q4FY24 pres p.36; Q4FY25 pres p.37; Q4FY26 pres p.32"),
    ("Grey cement capacity at year end (incl. 5.4 MTPA overseas)", "MTPA", [119.95, 132.35, 146.20, 188.80, 196.80],
     "Mar-22 = 126.95 - 12.4 commissioned in FY23 + 5.4 overseas (Q4FY23 pres p.7-8); Mar-23 = 126.95 + 5.4; "
     "Mar-24 to Mar-26: Q2FY27 investor presentation p.12"),
    ("Net sales", "Rs crore", [51708.0, 62338.0, 69810.0, 74936.0, 87384.0],
     "Consolidated P&L slide: Q4FY23 pres p.35 (FY22), Q4FY24 pres p.36 (FY23, FY24), Q4FY26 pres p.32 (FY25, FY26)"),
    ("Capex reported by the company (accrual basis)", "Rs crore", [None, None, 9187.0, 9428.0, 10064.0],
     "Q4FY26 investor presentation p.36"),
]
FORWARD = [  # forward-looking company facts used to set drivers
    ("Capacity Sep-2026", "MTPA", 210.1, "Q2FY27 investor presentation p.2 and p.12 (domestic 204.7 + 5.4 overseas)"),
    ("Capacity plan Mar-2027 (FY27E)", "MTPA", 213.1, "Q2FY27 investor presentation p.12"),
    ("Capacity plan Mar-2028 (FY28E)", "MTPA", 242.9, "Q2FY27 investor presentation p.12"),
    ("Committed capex for 37 MTPA to 242.5 MTPA by FY28", "Rs crore", 16000.0, "Integrated Report FY2025-26 p.46-47"),
    ("Implied cost per MTPA (16,000 / 37)", "Rs crore per MTPA", round(16000 / 37, 1), "derived"),
    ("FY27 capex guidance", "Rs crore", 10000.0, "Q2FY27 earnings call (19-Oct-2026) p.7: 'Plus minus INR10,000 crores'"),
    ("H1FY27 capex and investments", "Rs crore", 5882.0, "Q2FY27 investor presentation p.30; Q2FY27 call p.7"),
    ("Annual capex FY26-FY31", "Rs crore per year", 9000.0,
     "Q4FY26 earnings call (27-Apr-2026) p.5-6: 'INR8,000 crores to INR10,000 crores every year' (midpoint)"),
    ("Sustainable volume growth guidance", "% p.a.", 7.5, "Q4FY26 earnings call p.5: '7% to 8% per annum' (midpoint)"),
    ("Net debt / EBITDA Mar-2026 (company definition)", "x", 0.94, "Q4FY26 earnings call p.5"),
    ("Net debt / EBITDA Sep-2026 (company definition)", "x", 1.26, "Q2FY27 earnings call p.7"),
    ("FY26 dividend per share (paid Jul-2026)", "Rs", 240.0, "Q4FY26 earnings call p.5; Yahoo dividend 30-Jul-2026"),
    ("NCDs raised in Q2FY27 at 7.25%", "Rs crore", 5000.0, "Q2FY27 earnings call p.7"),
    ("H1FY27 sales volume (Q1 41.31 + Q2 38.22)", "MnT", 79.53, "Q1FY27 results pres p.8; Q2FY27 investor pres p.2"),
    ("H1FY27 revenue from operations (Q1 24,648 + Q2 23,295)", "Rs crore", 47943.0, "Q2FY27 consolidated results p.6"),
    ("H1FY27 operating EBITDA (Q1 5,015 + Q2 3,719)", "Rs crore", 8734.0, "Screener quarterly results (consolidated)"),
]

# ---------------------------------------------------------------- debt maturities (Rs crore, AR FY26 Note 17)
DEBT = [  # (fiscal year of repayment, amount, instruments)
    ("FY2027", 1173.42, "current maturities at 31-Mar-2026: 7.53% NCD 500 (Aug-26), SBI Gift City USD loan 474.17 "
                        "(Sep-26), term loans 162.18, deferment loans 37.06"),
    ("FY2028", 7978.86, "USD 500m sustainability-linked loan 4,741.74 (Aug/Oct-27), SMBC 237.12 (Jun-27), "
                        "SBI INR term loan 2,000 (Nov-27), 7.34% NCD 1,000 (Mar-28)"),
    ("FY2029", 0.0, "no large maturity (small amortising loans assumed rolled over)"),
    ("FY2030", 1000.0, "7.34% NCD (5-Mar-2030)"),
    ("FY2031", 3793.40, "2.80% USD 400m sustainability-linked bond (16-Feb-2031)"),
]


def check(log: list[str], name: str, a: float, b: float, tol: float = 0.6) -> bool:
    ok = abs(a - b) <= tol
    log.append(f"{'PASS' if ok else 'FAIL'} | {name}: computed {a:,.2f} vs reported {b:,.2f}")
    return ok


def main() -> None:
    log: list[str] = []
    DATA.mkdir(exist_ok=True)
    # ---- income statement
    is_df = pd.DataFrame([{"line": l, "group": g, **dict(zip(YEARS, v))} for l, g, v in IS])
    is_df["source"] = "; ".join(f"{y}: {YEAR_SRC[y]}" for y in ("FY2022", "FY2024", "FY2026"))
    is_df.to_csv(DATA / "hist_income_statement.csv", index=False)
    g = is_df.groupby("group")[YEARS].sum()
    for i, y in enumerate(YEARS):
        tot_exp = sum(g.loc[k, y] for k in ("raw_material", "employee", "finance_costs", "da", "power_fuel",
                                             "freight", "other_exp"))
        check(log, f"IS {y} total expenses", tot_exp, IS_REPORTED["Total expenses"][i])
        pbt = g.loc["revenue", y] + g.loc["other_income", y] - tot_exp - g.loc["exceptional", y] + g.loc["jv", y]
        check(log, f"IS {y} profit before tax", pbt, IS_REPORTED["Profit before tax"][i])
        pat = pbt - g.loc["tax", y] + g.loc["discontinued", y]
        check(log, f"IS {y} net profit", pat, IS_REPORTED["Net profit (incl. discontinued)"][i])
        check(log, f"IS {y} profit to owners", pat - g.loc["nci", y], IS_REPORTED["Profit attributable to owners"][i])
    # ---- balance sheet
    bs_df = pd.DataFrame([{"line": l, "section": s, "model_line": m, **dict(zip(YEARS, v))} for l, s, m, v in BS])
    bs_df["source"] = "; ".join(f"{y}: {BS_SRC[y]}" for y in YEARS)
    bs_df.to_csv(DATA / "hist_balance_sheet.csv", index=False)
    sec = bs_df.groupby("section")[YEARS].sum()
    for i, y in enumerate(YEARS):
        for s in ("NCA", "CA", "NCL", "CL"):
            check(log, f"BS {y} subtotal {s}", sec.loc[s, y], BS_REPORTED[s][i])
        ta = sec.loc[["NCA", "CA", "HFS"], y].sum()
        tel = sec.loc[["EQ", "NCL", "CL"], y].sum()
        check(log, f"BS {y} total assets", ta, BS_REPORTED["Total assets"][i])
        check(log, f"BS {y} total equity and liabilities", tel, BS_REPORTED["Total equity and liabilities"][i])
    # ---- cash flow
    cf_df = pd.DataFrame([{"line": l, **dict(zip(YEARS, v)), "note": CF_NOTE.get(l, "")} for l, v in CF])
    cf_df["source"] = "; ".join(f"{y}: {CF_SRC[y]}" for y in YEARS)
    cf_df.to_csv(DATA / "hist_cash_flow.csv", index=False)
    cf = cf_df.set_index("line")[YEARS]
    cash_bs = bs_df.set_index("line").loc["Cash and cash equivalents", YEARS]
    for y in YEARS:
        net = cf.loc[["Net cash from operating activities", "Net cash from investing activities",
                      "Net cash from financing activities"], y].sum()
        close = net + cf.loc["Cash and cash equivalents at beginning of year", y] + \
            cf.loc["Cash acquired/transferred (acquisitions, discontinued ops) and FX", y]
        check(log, f"CF {y} closing cash", close, cf.loc["Cash and cash equivalents at end of year", y])
        check(log, f"CF {y} closing cash = BS cash", cf.loc["Cash and cash equivalents at end of year", y], cash_bs[y])
    # ---- KPIs, forward facts, debt maturities
    kpi_df = pd.DataFrame([{"kpi": k, "unit": u, **dict(zip(YEARS, v)), "source": s} for k, u, v, s in KPI])
    kpi_df.to_csv(DATA / "operating_kpis.csv", index=False)
    pd.DataFrame(FORWARD, columns=["fact", "unit", "value", "source"]).to_csv(DATA / "company_guidance.csv", index=False)
    pd.DataFrame(DEBT, columns=["fiscal_year", "repayment_rs_crore", "instruments"]).assign(
        source="Integrated Report FY2025-26, Note 17 Non-current borrowings, PDF p.509-512").to_csv(
        DATA / "debt_maturities.csv", index=False)
    ns = kpi_df.set_index("kpi").loc["Net sales", YEARS]
    rev = is_df.set_index("line").loc["Revenue from operations", YEARS]
    for y in YEARS:
        ooi = rev[y] - ns[y]
        log.append(f"INFO | {y} other operating income (revenue - net sales) = {ooi:,.2f} ({ooi / ns[y]:.2%} of net sales)")
    # ---- market inputs
    quote = json.loads((ROOT / "source_data" / "yahoo_finance" / "quote_30Oct2026.json").read_text(encoding="utf-8"))
    eq_cap = bs_df.set_index("line").loc["Equity share capital", "FY2026"]
    owners = IS_REPORTED["Profit attributable to owners"][4]
    eps = IS_REPORTED["Basic EPS (Rs)"][4]
    market = {
        "valuation_date": "2026-10-30",
        "share_price_rs": quote["close"],
        "share_price_source": "Yahoo Finance ULTRACEMCO.NS close 30-Oct-2026 (source_data/yahoo_finance/quote_30Oct2026.json)",
        "shares_issued_crore": round(eq_cap / 10, 4),
        "shares_for_eps_crore": round(owners / eps, 2),
        "shares_note": "issued = equity capital / Rs 10 face value; EPS share count = FY26 profit to owners / basic EPS "
                       "(net of treasury shares held by the employee trust)",
        "macro": {
            "repo_rate": [0.055, "RBI hike of 7-Oct-2026 (The Hindu, Mint)", "news_and_macro/TheHindu_RBI_repo_hike_7Oct2026.html"],
            "tbill_91d": [0.0593, "RBI auction 28-Oct-2026 (Economic Times)", "news_and_macro/ET_TBill_auction_28Oct2026.html"],
            "gsec_10y": [0.0741, "30-Oct-2026 close: Reuters via ETBFSI 7.4139%, Trading Economics 7.40%",
                         "news_and_macro/ETBFSI_Reuters_India_bonds_30Oct2026.html"],
            "tax_rate": [0.2517, "s.115BAA: 22% + 10% surcharge + 4% cess", "news_and_macro/ClearTax_section_115BAA.html"],
            "usd_inr": [95.15, "Yahoo INR=X close 30-Oct-2026", "yahoo_finance/USDINR_INR=X_daily.csv"],
        },
    }
    (DATA / "market_inputs.json").write_text(json.dumps(market, indent=2), encoding="utf-8")
    # ---- cross-check against Screener (consolidated)
    scr_pl = pd.read_csv(RAW / "screener" / "ULTRACEMCO_profit-loss.csv").set_index("item")
    scr_bs = pd.read_csv(RAW / "screener" / "ULTRACEMCO_balance-sheet.csv").set_index("item")
    scr_cf = pd.read_csv(RAW / "screener" / "ULTRACEMCO_cash-flow.csv").set_index("item")
    rows = []
    for y in YEARS:
        col = f"Mar {y[2:]}"
        pairs = [
            ("Revenue from operations", rev[y], scr_pl.loc["Sales", col]),
            ("Depreciation", g.loc["da", y], scr_pl.loc["Depreciation", col]),
            ("Finance costs", g.loc["finance_costs", y], scr_pl.loc["Interest", col]),
            ("Net profit", IS_REPORTED["Net profit (incl. discontinued)"][YEARS.index(y)], scr_pl.loc["Net Profit", col]),
            ("Total assets", BS_REPORTED["Total assets"][YEARS.index(y)], scr_bs.loc["Total Assets", col]),
            ("Borrowings incl. leases", bs_df[bs_df.model_line.isin(["Borrowings", "Lease liabilities"])][y].sum(),
             scr_bs.loc["Borrowings", col]),
            ("Cash from operations", cf.loc["Net cash from operating activities", y], scr_cf.loc["Cash from Operating Activity", col]),
        ]
        for name, comp, scr in pairs:
            rows.append({"year": y, "item": name, "company_filing": round(comp, 2), "screener": scr,
                         "difference": round(comp - scr, 2), "pct_diff": round((comp - scr) / scr * 100, 2)})
    xc = pd.DataFrame(rows)
    xc.to_csv(DATA / "crosscheck_screener.csv", index=False)
    big = xc[xc.pct_diff.abs() > 1.0]
    log.append(f"INFO | Screener cross-check: {len(xc)} comparisons, {len(big)} differ by more than 1%")
    for _, r in big.iterrows():
        log.append(f"INFO |   {r.year} {r['item']}: filing {r.company_filing:,.0f} vs Screener {r.screener:,.0f}")
    n_fail = sum(1 for l in log if l.startswith("FAIL"))
    log.insert(0, f"prepare_data: {sum(1 for l in log if l.startswith('PASS'))} PASS, {n_fail} FAIL")
    (DATA / "prepare_log.txt").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log[:1]))
    print("EXIT_OK" if n_fail == 0 else "EXIT_FAIL")


if __name__ == "__main__":
    main()
