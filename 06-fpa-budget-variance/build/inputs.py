"""Fictional input data for Vriddhi Foods Pvt. Ltd. FY2027 FP&A model.

Vriddhi Foods is a fictional company. Every business number in this file is
invented for an educational FP&A exercise. Real-world facts used to shape the
storyline (festival dates, 2026 monsoon, edible-oil prices, RBI repo rate) are
listed in EXTERNAL_FACTS with their sources.

Fiscal year FY2027 = Apr-2026 to Mar-2027. Status date 31-Oct-2026:
April-September 2026 actuals are closed, October 2026 onward is forecast.
Units: volumes in tonnes (beverages: 1 kL counted as 1 tonne), prices and
costs in Rs per kg, P&L in Rs crore.
"""
from __future__ import annotations

import datetime as dt

COMPANY = "Vriddhi Foods Pvt. Ltd."
FY_LABEL = "FY2027"
STATUS_DATE = dt.date(2026, 10, 31)
MONTHS = [dt.date(2026, m, 1) for m in range(4, 13)] + [dt.date(2027, m, 1) for m in range(1, 4)]
N_ACT = 6  # months of closed actuals (Apr-Sep 2026)

LINES = [("NAM", "Namkeen & chips"), ("BIS", "Biscuits & cookies"), ("BEV", "Beverages (juices & RTD)")]
CHANNELS = [("GT", "General Trade"), ("MT", "Modern Trade"), ("EQC", "E-commerce & quick commerce")]
RMS = [("OIL", "Edible oil"), ("WHT", "Wheat flour"), ("SUG", "Sugar"), ("POT", "Potato"), ("FRP", "Fruit pulp blend")]
FUNCS = [("FAC", "Factory & supply chain"), ("SAL", "Sales & distribution"), ("COR", "Corporate")]

TAX_RATE = 0.2517  # 22% + 10% surcharge + 4% cess, s.115BAA
CONV = 0.0001      # tonnes x Rs/kg -> Rs crore (1,000 kg per tonne / 1e7 Rs per crore)

# ---------------------------------------------------------------------------
# BUDGET (set in Feb-2026, before the year started)
# ---------------------------------------------------------------------------
BUDGET = {
    "fy_volume": {"NAM": 14000, "BIS": 21000, "BEV": 24000},
    "fy_volume_reason": {
        "NAM": "FY2026 run-rate +9%, led by quick commerce; namkeen market about +10% a year (Technavio)",
        "BIS": "FY2026 run-rate +6%; listed biscuit makers grew 7-9% in FY2026 (Screener); new cookie line from Oct-26",
        "BEV": "FY2026 run-rate +8%; juice market about +8.5% a year (Grand View Research); summer-heavy portfolio",
    },
    # % of FY volume by month (Apr..Mar); festive load Oct-Nov (Navratri 11-Oct, Diwali 8-Nov-2026)
    "seasonality": {
        "NAM": [0.075, 0.075, 0.075, 0.078, 0.080, 0.084, 0.102, 0.096, 0.082, 0.080, 0.084, 0.089],
        "BIS": [0.076, 0.074, 0.078, 0.084, 0.086, 0.086, 0.096, 0.090, 0.082, 0.082, 0.080, 0.086],
        "BEV": [0.125, 0.140, 0.120, 0.080, 0.070, 0.065, 0.065, 0.055, 0.050, 0.050, 0.075, 0.105],
    },
    "seasonality_reason": {
        "NAM": "Festive pipeline fill in Oct-Nov (Diwali 8-Nov-2026)",
        "BIS": "Monsoon tea-time lift Jul-Sep, festive gifting Oct-Nov",
        "BEV": "Summer peak Apr-Jun, trough Nov-Jan",
    },
    "channel_mix": {  # share of line volume
        "NAM": {"GT": 0.64, "MT": 0.20, "EQC": 0.16},
        "BIS": {"GT": 0.70, "MT": 0.18, "EQC": 0.12},
        "BEV": {"GT": 0.58, "MT": 0.26, "EQC": 0.16},
    },
    "channel_mix_reason": {
        "NAM": "E-com & QC share up from about 13% in FY2026; QC order value +81% YoY in Q4 FY26 (Bernstein)",
        "BIS": "Biscuits remain kirana-led",
        "BEV": "MT strong for multi-packs and 1L juices",
    },
    "list_price": {"NAM": 238.0, "BIS": 138.0, "BEV": 76.0},  # Rs/kg to trade, ex-GST, flat all year
    "list_price_reason": {
        "NAM": "No price increase budgeted",
        "BIS": "No price increase budgeted",
        "BEV": "No price increase budgeted",
    },
    # trade spend % of gross sales by channel and month
    "trade_spend": {
        "GT": [0.080] * 6 + [0.090, 0.090] + [0.080] * 4,
        "MT": [0.140] * 12,
        "EQC": [0.180] * 12,
    },
    "trade_spend_reason": {
        "GT": "Base schemes 8%; festive schemes add 1 pp in Oct-Nov",
        "MT": "Listing fees and promotions",
        "EQC": "Platform margins and visibility fees; large brands pay 10-20% (ET), platforms quote 15-25%",
    },
    "rm_price": {  # Rs/kg by month
        "OIL": [110.0] * 12,
        "WHT": [32.0] * 12,
        "SUG": [42.0] * 12,
        "POT": [12.5, 13.0, 13.5, 14.0, 14.5, 15.0, 15.5, 16.0, 15.0, 12.0, 11.5, 12.0],
        "FRP": [65.0] * 12,
    },
    "rm_price_reason": {
        "OIL": "Palm/rice-bran blend at the Feb-2026 contract rate",
        "WHT": "Flat; MSP-linked procurement (wheat MSP Rs 2,585/quintal for 2026-27)",
        "SUG": "Ex-mill about Rs 38.5/kg in early 2026 (Indian Express) + freight + Rs 2 cushion",
        "POT": "Cold-store prices rise until the Jan-Mar new crop; large 2026 crop (TOI, Feb-2026)",
        "FRP": "Mango/guava pulp contracted in the Apr-Jun season (no public benchmark)",
    },
    # standard bill of materials: kg of input per kg of finished product (incl. process loss)
    "bom": {
        "NAM": {"OIL": 0.32, "WHT": 0.05, "SUG": 0.01, "POT": 1.40, "FRP": 0.00},
        "BIS": {"OIL": 0.16, "WHT": 0.62, "SUG": 0.25, "POT": 0.00, "FRP": 0.00},
        "BEV": {"OIL": 0.00, "WHT": 0.00, "SUG": 0.09, "POT": 0.00, "FRP": 0.22},
    },
    "other_ingr": {"NAM": 30.0, "BIS": 18.0, "BEV": 6.0},   # Rs/kg: spices, gram flour, milk solids, flavours
    "packaging": {"NAM": 20.0, "BIS": 12.0, "BEV": 14.0},   # Rs/kg
    "conversion": {"NAM": 16.0, "BIS": 10.0, "BEV": 7.0},   # Rs/kg: plant labour, power, fuel, consumables
    "freight_pct": 0.048,
    "freight_reason": "FY2026 actual 4.7% plus QC dark-store deliveries",
    "ap": [3.6, 3.8, 3.0, 2.8, 3.2, 3.8, 4.6, 4.2, 3.0, 2.8, 3.2, 3.6],  # Rs crore
    "ap_reason": "Summer beverage push Apr-May, festive campaigns Sep-Nov",
    "headcount": {
        "FAC": [820] * 6 + [845] * 6,
        "SAL": [380] * 3 + [390] * 9,
        "COR": [110] * 12,
    },
    "ctc": {"FAC": 2.8, "SAL": 5.0, "COR": 12.0},          # Rs lakh per head per year, before increment
    "increment": {"FAC": 0.08, "SAL": 0.10, "COR": 0.09},
    "increment_date": dt.date(2026, 7, 1),
    "increment_reason": "Annual increment cycle effective 1-Jul",
    "other_oh": [2.90] * 12,  # Rs crore: rent, IT, travel, insurance, professional fees
    "da": [1.75] * 6 + [1.95] * 6,  # new cookie line capitalised Oct-26
    "borrowings": [95, 95, 95, 105, 105, 105, 105, 105, 90, 90, 90, 90],  # average Rs crore
    "int_rate": [0.090] * 12,
}

# ---------------------------------------------------------------------------
# ACTUALS Apr-Sep 2026 (fictional ERP extract). Volumes are generated from a
# storyline (vs budget %) and channel mix, then rounded to 0.1 t like an ERP.
# ---------------------------------------------------------------------------
ACT_STORY = {
    # actual line volume vs budget, Apr..Sep
    "vol_vs_budget": {
        "NAM": [0.005, -0.005, 0.010, 0.005, -0.015, 0.025],
        "BIS": [0.000, -0.005, -0.010, -0.015, -0.025, -0.020],
        "BEV": [0.020, 0.040, 0.090, -0.220, -0.150, -0.060],
    },
    "mix": {  # GT, MT, EQC share of line volume, Apr..Sep
        "NAM": [(0.635, 0.198), (0.630, 0.197), (0.626, 0.196), (0.622, 0.195), (0.618, 0.194), (0.612, 0.193)],
        "BIS": [(0.696, 0.180), (0.692, 0.179), (0.688, 0.179), (0.684, 0.178), (0.680, 0.178), (0.676, 0.177)],
        "BEV": [(0.576, 0.260), (0.572, 0.260), (0.574, 0.254), (0.555, 0.265), (0.558, 0.260), (0.560, 0.255)],
    },
}

ACTUAL = {
    "list_price": {
        "NAM": [238.0, 238.0, 238.0, 238.0, 247.52, 247.52],  # +4% from 1-Aug-2026
        "BIS": [138.0] * 6,
        "BEV": [76.0] * 6,
    },
    "trade_spend": {
        "GT": [0.080, 0.080, 0.081, 0.082, 0.083, 0.086],
        "MT": [0.140, 0.140, 0.142, 0.152, 0.150, 0.143],
        "EQC": [0.183, 0.184, 0.185, 0.186, 0.187, 0.188],
    },
    "rm_price": {
        "OIL": [112.0, 115.0, 118.0, 122.0, 126.0, 128.0],
        "WHT": [32.0, 32.0, 32.0, 32.0, 32.5, 32.5],
        "SUG": [40.0, 40.0, 40.2, 42.5, 54.0, 55.0],  # 2026 spike: ex-mill Rs 41.5 early Jul, record Rs 67 mid-Aug, Rs 55 late Aug
        "POT": [12.0, 12.2, 12.5, 12.9, 13.4, 13.9],  # large 2026 crop kept cold-store potato below the budget path
        "FRP": [65.0, 65.0, 65.0, 65.5, 66.0, 66.0],
    },
    "other_ingr": {
        "NAM": [30.0, 30.0, 30.0, 30.2, 30.2, 30.2],
        "BIS": [18.0, 18.0, 18.0, 18.0, 18.2, 18.2],
        "BEV": [6.0] * 6,
    },
    "packaging": {
        "NAM": [20.0, 20.0, 20.0, 20.3, 20.3, 20.3],
        "BIS": [12.0, 12.0, 12.0, 12.1, 12.1, 12.1],
        "BEV": [14.0, 14.0, 14.0, 14.2, 14.2, 14.2],
    },
    "conversion": {
        "NAM": [16.0, 16.0, 15.9, 16.2, 16.1, 16.0],
        "BIS": [10.0, 10.0, 10.0, 10.2, 10.2, 10.1],
        "BEV": [7.0, 7.0, 6.9, 7.6, 7.4, 7.2],
    },
    "freight_pct": [0.048, 0.048, 0.048, 0.049, 0.049, 0.049],
    "freight_oneoff": [0.0, 0.0, 0.0, 0.85, 0.0, 0.0],  # July monsoon route-disruption surcharge (fictional)
    "ap": [3.5, 3.9, 3.1, 2.7, 4.3, 5.6],
    "headcount": {
        "FAC": [812, 815, 818, 820, 822, 825],
        "SAL": [372, 375, 378, 380, 384, 386],
        "COR": [108, 108, 109, 110, 110, 111],
    },
    "ctc": {"FAC": 2.8, "SAL": 5.0, "COR": 12.0},
    "increment_date": dt.date(2026, 10, 1),  # deferred from July to October
    "other_oh": [2.85, 2.92, 2.88, 2.95, 3.05, 2.98],
    "da": [1.75] * 6,
    "borrowings": [92, 94, 96, 108, 112, 115],
    "int_rate": [0.090] * 6,
}

# ---------------------------------------------------------------------------
# REFORECAST Oct-2026 to Mar-2027 (6+6), base case
# ---------------------------------------------------------------------------
FORECAST = {
    "vol_adj": {  # vs budget line volume, Oct..Mar
        "NAM": [0.03, 0.05, 0.01, 0.01, 0.01, 0.01],
        "BIS": [0.00, 0.01, -0.03, -0.03, -0.03, -0.03],
        "BEV": [-0.06, -0.05, -0.04, -0.04, -0.03, -0.03],
    },
    "vol_adj_reason": {
        "NAM": "Festive gifting packs and QC; Diwali 8-Nov loads Oct-Nov",
        "BIS": "Festive lift, then weak rural demand (ICRA, NIQ) and about 1 pp lost to the Oct price rise",
        "BEV": "H1 trend persists; distributor stocks still high",
    },
    "mix": {  # H2 channel mix: GT, MT, EQC
        "NAM": {"GT": 0.61, "MT": 0.19, "EQC": 0.20},
        "BIS": {"GT": 0.67, "MT": 0.175, "EQC": 0.155},
        "BEV": {"GT": 0.56, "MT": 0.25, "EQC": 0.19},
    },
    "mix_reason": {
        "NAM": "Sep-26 exit mix carried forward, QC rising",
        "BIS": "Sep-26 exit mix carried forward",
        "BEV": "Sep-26 exit mix carried forward",
    },
    "price_chg": {"NAM": 0.04, "BIS": 0.03, "BEV": 0.0},
    "price_chg_reason": {
        "NAM": "4% increase taken 1-Aug-2026 stays in place",
        "BIS": "3% increase from 1-Oct-2026 (grammage cut) to recover sugar and oil inflation",
        "BEV": "No increase assumed",
    },
    "ts_adj": {"GT": 0.003, "MT": 0.003, "EQC": 0.010},  # pp added to budget trade spend %
    "ts_adj_reason": {
        "GT": "H1 run-rate 0.2-0.6 pp above budget",
        "MT": "Beverage promotions continue at a lower level",
        "EQC": "QC visibility fees at H1 exit rate",
    },
    "rm_price": {
        "OIL": [125.0, 123.0, 121.0, 120.0, 120.0, 120.0],
        "WHT": [33.0] * 6,
        "SUG": [53.5, 53.0, 51.0, 50.0, 49.5, 49.5],
        "POT": [14.4, 14.8, 14.0, 11.5, 11.0, 11.5],
        "FRP": [66.0] * 6,
    },
    "rm_price_reason": {
        "OIL": "Duty cut of 24-Sep-2026 (effective duty 16.5% to 11%) eases landed cost from the Sep peak of Rs 128",
        "WHT": "Firm wheat: FCI auction bids above Rs 3,100/quintal on 28-Oct-2026 (BusinessLine)",
        "SUG": "Ex-mill Rs 50.4-55.5/kg on 31-Oct-2026 (ChiniMandi); eases as the new crushing season starts",
        "POT": "Budget path less Rs 0.5-1.2/kg: wholesale potato about Rs 11.7/kg in mid-Oct-2026",
        "FRP": "Sep-26 exit rate",
    },
    "other_ingr": {"NAM": 30.2, "BIS": 18.2, "BEV": 6.0},
    "packaging": {"NAM": 20.3, "BIS": 12.1, "BEV": 14.2},
    "conversion": {"NAM": 16.0, "BIS": 10.0, "BEV": 7.0},
    "freight_pct": 0.049,
    "ap": [4.6, 4.2, 2.6, 2.4, 2.8, 3.2],
    "ap_reason": "Festive plan kept; Dec-Mar cut Rs 0.4 cr/month to recover part of H1 overspend",
    "increment_date": dt.date(2026, 10, 1),
    "borrowings": [118, 115, 100, 95, 92, 90],
    "int_rate": [0.090, 0.0925, 0.0925, 0.0925, 0.0925, 0.0925],
    "int_rate_reason": "RBI repo +25 bp on 7-Oct-2026; floating loans reset from Nov",
}

# Forecast case overlays (Oct-Mar only). Selected on the Cover sheet.
CASES = ["Base", "Downside", "Upside"]
CASE_OVERLAYS = [
    # key, label, unit, base, downside, upside, applies from
    ("oil", "Edible oil price change", "Rs/kg", 0.0, 8.0, -5.0, dt.date(2026, 10, 1)),
    ("gtvol", "General Trade volume change (all lines)", "%", 0.0, -0.03, 0.0, dt.date(2026, 12, 1)),
    ("bisprice", "Biscuits list price change", "%", 0.0, 0.0, 0.02, dt.date(2027, 1, 1)),
]

# (fact, value, source, url, date, saved copy under source_data/)
EXTERNAL_FACTS = [
    ("Sharad Navratri 2026", "11-Oct to 19-Oct-2026; Dussehra 20-Oct-2026", "Times of India",
     "https://timesofindia.indiatimes.com/religion/festivals/navratri-2026-start-end-date-is-ghatasthapana-on-october-10-or-11-check-the-full-tithi-schedule/articleshow/134767429.cms",
     "08-Oct-2026", "news_and_macro/festive_navratri_2026_timesofindia.html"),
    ("Diwali 2026", "Lakshmi Puja on Sunday 8-Nov-2026", "Drik Panchang",
     "https://www.drikpanchang.com/festivals/lakshmipuja/festivals-lakshmipuja-timings.html?year=2026",
     "accessed 01-Nov-2026", "news_and_macro/festive_diwali_2026_drikpanchang.html"),
    ("2026 monsoon", "June 40% below the long-period average (LPA), July 103% of LPA, August 84% of LPA; rural "
     "demand outlook weak for H2 FY2027", "ICRA thematic report",
     "https://www.icra.in/Research/ViewResearchReport/deficient-rainfall-inflation-risks-and-weak-crop-output-prospects-cloud-outlook-for-rural-demand-in-h2-fy2027/7096",
     "01-Sep-2026", "news_and_macro/monsoon_rural_demand_icra_2026-09-01.html"),
    ("FMCG demand, Apr-Jun 2026", "Volume -2% YoY, value +0.8%; rural volume -5%; e-commerce volume +34.8%, modern "
     "trade +17.5% (NIQ quarterly snapshot)", "Moneycontrol",
     "https://www.moneycontrol.com/news/business/macro-headwinds-rising-input-costs-impact-fmcg-volumes-in-june-quarter-niq-14039279.html",
     "27-Sep-2026", "news_and_macro/fmcg_volumes_aprjun2026_niq_moneycontrol.html"),
    ("Category growth", "Snacks market Rs 50,590 crore in 2025, 8.28% CAGR 2026-2034 (IMARC); namkeen 10.2% CAGR "
     "2025-2030 (Technavio); fruit and vegetable juice 8.52% CAGR 2026-2033 (Grand View Research)",
     "Market research summaries", "https://www.imarcgroup.com/india-snacks-market", "2026",
     "news_and_macro/industry_*.html"),
    ("Edible oil", "Retail palm oil Rs 153.89/kg on 23-Sep-2026, up 16.3% YoY; customs duty on crude palm and soybean "
     "oil cut from 10% to 5% from 24-Sep-2026 (effective duty 16.5% to 11%)", "Mint; Financial Express",
     "https://www.livemint.com/economy/centre-cuts-import-duty-on-edible-oils-to-curb-price-rise-11790184261562.html",
     "Sep-2026", "news_and_macro/edible_oil_*.html"),
    ("Sugar", "Ex-mill about Rs 38.5/kg in early 2026 and early June, Rs 41.5 by early July, record Rs 67/kg in "
     "mid-August, Rs 55/kg after imports and stock limits; Rs 50.4-55.5/kg on 31-Oct-2026",
     "Indian Express; Moneycontrol; Times of India; ChiniMandi",
     "https://timesofindia.indiatimes.com/business/india-business/sugar-prices-cool-18-after-hitting-record-high-ex-mill-rates-fall-to-rs-55-per-kg/articleshow/133504686.cms",
     "Apr-Oct 2026", "news_and_macro/sugar_*.html"),
    ("Wheat", "MSP Rs 2,585/quintal for 2026-27; retail atta Rs 37.39/kg (Sep-2026); all-India wholesale wheat "
     "Rs 2,910/quintal with millers bidding above Rs 3,100 on 28-Oct-2026", "Times of India; Mint; BusinessLine",
     "https://www.thehindubusinessline.com/economy/agri-business/indian-millers-bid-higher-rates-to-get-fcis-wheat-offtake-100-in-many-states/article71645756.ece",
     "Mar-Oct 2026", "news_and_macro/wheat_*.html, food_prices_wheat_atta_livemint_2026-09.html"),
    ("Potato", "Large 2026 crop: farm-gate Rs 6/kg in Feb-2026; all-India wholesale about Rs 11.7/kg on 16-Oct-2026",
     "Times of India; IndianPotato.com",
     "https://timesofindia.indiatimes.com/city/kolkata/bumper-potato-harvest-sparks-distress-sales-fears-no-sign-of-farm-retail-gap-narrowing/articleshow/128434204.cms",
     "Feb-Oct 2026", "news_and_macro/potato_*.html"),
    ("GST on the product range", "Namkeen/bhujia 12% to 5%, biscuits 18% to 5%, fruit juices and fruit-juice based "
     "drinks to 5% from 22-Sep-2025; model prices are ex-GST", "PIB press release on the 56th GST Council; Economic Times",
     "https://bcasonline.org/wp-content/uploads/2025/09/03_Sep-_025_GST_Council_Recommendations.pdf",
     "03-Sep-2025", "government/gst_56th_council_press_release_2025-09-03.pdf"),
    ("Quick commerce", "Combined order value about USD 2.9 bn in Q4 FY26, growth slowing to 81% YoY (Bernstein); 60-75% "
     "of large FMCG companies' online sales in FY2026; large brands pay 10-20% commission, platforms quote 15-25%",
     "BusinessWorld; Economic Times; StartupTalky",
     "https://www.businessworld.in/article/india-s-quick-commerce-growth-enters-a-more-rational-phase-bernstein-615248",
     "2024-2026", "news_and_macro/quick_commerce_*.html"),
    ("Salary increments", "India average 9.1% projected for 2026 (Aon); FMCG 8.6%, consumer products 8.7%",
     "Aon; Moneycontrol",
     "https://www.aon.com/apac/in-the-press/asia-newsroom/2026/aon-survey-projects-slight-uptick-in-salaries-in-india-2026",
     "24-Feb-2026", "news_and_macro/salary_increase_*.html"),
    ("RBI repo rate", "Raised 25 bp to 5.50% on 7-Oct-2026; stance changed to calibrated tightening", "The Hindu; Mint",
     "https://www.thehindu.com/business/Economy/rbi-hikes-repo-rate-by-25-basis-points-to-55/article71554369.ece",
     "07-Oct-2026", "news_and_macro/rbi_repo_hike_*.html"),
    ("Corporate tax", "25.168% = 22% + 10% surcharge + 4% cess (s.115BAA; s.200 of the Income-tax Act 2025)",
     "EZTax summary; Income Tax Department page (link only)", "https://eztax.in/section-115baa-tax-rate-explained",
     "2026", "government/corporate_tax_*.html|.md"),
    ("Listed peers", "FY2026 median of six listed packaged-food companies: material cost 56% of sales, employee cost "
     "7%, operating margin 13.5%, revenue growth 7.9%", "Screener.in",
     "https://www.screener.in/company/BIKAJI/consolidated/", "downloaded 01-Nov-2026",
     "screener/*.xlsx (summary in data/peer_benchmarks.csv)"),
]


def actual_volumes() -> dict:
    """Return actual Apr-Sep volumes by (line, channel) in tonnes, rounded to 0.1 t."""
    out = {}
    for lk, _ in LINES:
        fy = BUDGET["fy_volume"][lk]
        for m in range(N_ACT):
            budget_vol = fy * BUDGET["seasonality"][lk][m]
            line_vol = budget_vol * (1 + ACT_STORY["vol_vs_budget"][lk][m])
            gt, mt = ACT_STORY["mix"][lk][m]
            eqc = 1 - gt - mt
            for ck, share in (("GT", gt), ("MT", mt), ("EQC", eqc)):
                out.setdefault((lk, ck), []).append(round(line_vol * share, 1))
    return out
