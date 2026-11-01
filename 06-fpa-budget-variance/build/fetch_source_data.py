"""Download the real-world benchmarks behind the fictional Vriddhi Foods assumptions into source_data/.

Vriddhi Foods is fictional, so its "sources" are the public facts used to set and test the assumptions:
festive dates, the 2026 monsoon, FMCG demand data, edible-oil / sugar / wheat / potato prices, GST rates,
quick-commerce growth and trade terms, salary increments, the RBI repo rate, the corporate tax rate, and
the margins of listed Indian packaged-food companies (Screener.in).

Run once with internet access:   python build/fetch_source_data.py
The workbook build does NOT depend on this script. build/peer_benchmarks.py turns the saved Screener
CSVs into data/peer_benchmarks.csv, which the build reads.

Outputs (downloaded files are saved byte-for-byte, untouched):
  source_data/screener/raw/<SYMBOL>_<view>.html and <SYMBOL>_expenses_schedule.json
  source_data/screener/csv/<SYMBOL>_<section>.csv
  source_data/screener/<Name>_Screener_<View>.xlsx   (one sheet per section; row 1 = source line)
  source_data/news_and_macro/*.html|*.pdf            (a .md note with the URL instead, if a site blocks us)
  source_data/government/*.html|*.pdf
  source_data/download_log.csv                       (URL, HTTP status, bytes, SHA-256, phrase check)
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import os
import re
import time

import pandas as pd
import requests
from bs4 import BeautifulSoup
from openpyxl import Workbook
from openpyxl.styles import Font

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SD = os.path.join(ROOT, "source_data")
UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/130.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
}
TODAY = dt.date.today().strftime("%d-%b-%Y")
LOG_ROWS: list[dict] = []

# ---------------------------------------------------------------------------------------------
# Listed peers on Screener.in (Rs crore). view = preferred view; falls back to the other view if empty.
# ---------------------------------------------------------------------------------------------
PEERS = [
    ("BRITANNIA", "Britannia", "Britannia Industries", "consolidated", "Biscuits & cookies (market leader)"),
    ("BECTORFOOD", "MrsBectors", "Mrs Bectors Food Specialities", "consolidated", "Biscuits (Cremica) and bakery"),
    ("BIKAJI", "Bikaji", "Bikaji Foods International", "consolidated", "Namkeen and ethnic snacks"),
    ("GOPAL", "GopalSnacks", "Gopal Snacks", "standalone", "Namkeen, gathiya and wafers"),
    # standalone: the consolidated view has no FY2024-FY2025 columns, so growth cannot be computed from it
    ("DIAMONDYD", "PrataapSnacks", "Prataap Snacks", "standalone", "Potato chips and extruded snacks (Yellow Diamond)"),
    ("TATACONSUM", "TataConsumer", "Tata Consumer Products", "consolidated", "Branded foods and beverages incl. RTD"),
    ("DFMFOODS", "DFMFoods", "DFM Foods (delisted)", "standalone", "Corn puffs and chips (Crax); delisted, last full year FY2022"),
]
SECTIONS = ["quarters", "profit-loss", "balance-sheet", "cash-flow", "ratios"]

# ---------------------------------------------------------------------------------------------
# Web pages: (folder, file stem, url, title, publisher, published, used for, phrases that must appear)
# ---------------------------------------------------------------------------------------------
PAGES = [
    # festive calendar
    ("news_and_macro", "festive_navratri_2026_timesofindia",
     "https://timesofindia.indiatimes.com/religion/festivals/navratri-2026-start-end-date-is-ghatasthapana-on-october-10-or-11-check-the-full-tithi-schedule/articleshow/134767429.cms",
     "Navratri 2026 start and end date", "Times of India", "Oct-2026",
     "Festive seasonality: Navratri 11-Oct, Dussehra 20-Oct-2026", ["11 October", "20 October"]),
    ("news_and_macro", "festive_navratri_2026_economictimes",
     "https://economictimes.indiatimes.com/news/new-updates/navratri-2026-date-and-time-check-all-dates-9-colours-forms-of-goddess-durga-puja-muhurat/articleshow/134849399.cms",
     "Navratri 2026 date and time", "Economic Times", "Oct-2026",
     "Second source for the Navratri and Dussehra dates", ["October 11", "October 20"]),
    ("news_and_macro", "festive_diwali_2026_drikpanchang",
     "https://www.drikpanchang.com/festivals/lakshmipuja/festivals-lakshmipuja-timings.html?year=2026",
     "Lakshmi Puja (Diwali) 2026 timings", "Drik Panchang", "2026",
     "Festive seasonality: Diwali (Lakshmi Puja) on Sunday 8-Nov-2026", ["November 8, 2026"]),
    ("news_and_macro", "festive_diwali_2026_economictimes",
     "https://economictimes.indiatimes.com/astrology/others/diwali-2026-date-when-is-diwali-check-lakshmi-puja-muhurat-significance-and-5-day-festival-calendar/articleshow/135254249.cms",
     "Diwali 2026 date", "Economic Times", "Oct-2026", "Second source for the Diwali date", ["November 8"]),
    # monsoon and demand
    ("news_and_macro", "monsoon_rural_demand_icra_2026-09-01",
     "https://www.icra.in/Research/ViewResearchReport/deficient-rainfall-inflation-risks-and-weak-crop-output-prospects-cloud-outlook-for-rural-demand-in-h2-fy2027/7096",
     "Deficient rainfall, inflation risks and weak crop output prospects cloud outlook for rural demand in H2 FY2027",
     "ICRA", "01-Sep-2026", "Monsoon by month (June -40%, July 103%, August 84% of LPA); weak rural demand in H2",
     ["40% below LPA", "103% of LPA", "84% of LPA"]),
    ("news_and_macro", "fmcg_volumes_aprjun2026_niq_economictimes",
     "https://economictimes.indiatimes.com/industry/cons-products/fmcg/68-of-fmcg-categories-lose-volume-as-a-triple-shock-squeezes-indias-basket-in-april-june/articleshow/134520579.cms",
     "Triple shock rattles India's FMCG basket as 68% of categories lose volume", "Economic Times (NIQ data)",
     "Sep-2026", "FMCG volumes -2% YoY in Apr-Jun 2026, rural -5%; MT and e-commerce growing", ["68%"]),
    ("news_and_macro", "fmcg_volumes_aprjun2026_niq_moneycontrol",
     "https://www.moneycontrol.com/news/business/macro-headwinds-rising-input-costs-impact-fmcg-volumes-in-june-quarter-niq-14039279.html",
     "Macro headwinds, rising input costs impact FMCG volumes in June quarter", "Moneycontrol (NIQ data)",
     "Sep-2026", "Rural value -2.9%, volume -5%; urban value +3%, volume flat (Apr-Jun 2026)", ["rural"]),
    ("news_and_macro", "fmcg_gst2_niq_newscenter_2026",
     "https://nielseniq.com/global/en/news-center/2026/niq-gst-2-0-transition-reshapes-indias-fmcg-growth-landscape/",
     "NIQ: GST 2.0 transition reshapes India's FMCG growth landscape", "NielsenIQ", "2026",
     "GST 2.0 demand effect expected from Jan-Mar 2026 (context for the Feb-2026 budget)", ["GST 2.0"]),
    ("news_and_macro", "britannia_q1fy27_results_economictimes",
     "https://economictimes.indiatimes.com/markets/stocks/earnings/britannia-q1-results-profit-rises-14-to-rs-591-crore-misses-estimates-as-iran-war-pushes-costs-higher/articleshow/133007596.cms",
     "Britannia Q1 results: profit rises 14%", "Economic Times", "06-Aug-2026",
     "Biscuit category demand in Apr-Jun 2026 (volume and price growth at the leader)", ["Britannia"]),
    # industry growth
    ("news_and_macro", "industry_snacks_market_imarc",
     "https://www.imarcgroup.com/india-snacks-market", "India snacks market size and growth", "IMARC Group",
     "2026", "Snacks market growth (8.28% CAGR 2026-2034) for the namkeen volume budget", ["8.28%"]),
    ("news_and_macro", "industry_namkeen_market_technavio",
     "https://www.technavio.com/report/namkeen-market-industry-in-india-analysis", "India namkeen market analysis",
     "Technavio", "Jan-2026", "Namkeen market growth (10.2% CAGR 2025-2030)", ["10.2%"]),
    ("news_and_macro", "industry_juice_market_grandviewresearch",
     "https://www.grandviewresearch.com/horizon/outlook/fruit-and-vegetable-juice-market/india",
     "India fruit and vegetable juice market outlook", "Grand View Research", "2026",
     "Juice market growth (8.52% CAGR 2026-2033) for the beverages volume budget", ["8.52%"]),
    # edible oil
    ("news_and_macro", "edible_oil_duty_cut_livemint_2026-09",
     "https://www.livemint.com/economy/centre-cuts-import-duty-on-edible-oils-to-curb-price-rise-11790184261562.html",
     "Centre cuts import duty on edible oils to curb price rise", "Mint", "Sep-2026",
     "Retail palm oil Rs 153.89/kg on 23-Sep-2026 (+16.3% YoY); duty cut from 24-Sep-2026", ["153.89"]),
    ("news_and_macro", "edible_oil_duty_cut_thehindu_2026-09-24",
     "https://www.thehindu.com/business/Industry/ahead-of-festivals-centre-cuts-import-duty-on-edible-oils/article71504736.ece",
     "Ahead of festivals, Centre cuts import duty on edible oils", "The Hindu", "24-Sep-2026",
     "Basic customs duty on crude palm and soybean oil 10% -> 5% (24-Sep-2026)", ["Basic Customs Duty"]),
    ("news_and_macro", "edible_oil_effective_duty_financialexpress_2026-09",
     "https://www.financialexpress.com/policy/economy-edible-oil-duty-cut-may-put-8-retail-price-hikes-on-hold-4346955/",
     "Edible oil duty cut may put 8% retail price hikes on hold", "Financial Express", "Sep-2026",
     "Effective duty on crude palm oil 16.5% -> 11%: size of the forecast oil price easing", ["16.5"]),
    ("news_and_macro", "edible_oil_retail_prices_ndtv_2026-09",
     "https://www.ndtv.com/india-news/india-cuts-edible-oil-import-duty-but-how-much-can-it-change-prices-12131246",
     "India cuts edible oil import duty: how much can it change prices", "NDTV", "Sep-2026",
     "Retail palm oil Rs 131.65 -> Rs 153.60/kg (+14.3%) over a year", ["153.60"]),
    # sugar
    ("news_and_macro", "sugar_exmill_apr2026_indianexpress",
     "https://indianexpress.com/article/business/commodities/sugar-supply-situation-stable-despite-stocks-at-nine-year-low-says-cooperative-federation-chief-10624476/",
     "Sugar supply situation stable despite stocks at nine-year low", "Indian Express", "07-Apr-2026",
     "All-India ex-mill sugar about Rs 3,850/quintal in early 2026 (budget anchor)", ["3,850"]),
    ("news_and_macro", "sugar_imports_moneycontrol_2026-08",
     "https://www.moneycontrol.com/news/india/sugar-shock-in-india-why-the-world-s-biggest-producer-is-turning-importer-14012525.html",
     "Sugar shock in India: why the world's biggest producer is turning importer", "Moneycontrol", "Aug-2026",
     "Ex-mill Rs 38.5/kg early June -> Rs 41.5 early July -> Rs 54-55.6 by mid-August 2026", ["38.5", "41.5"]),
    ("news_and_macro", "sugar_record_high_timesofindia_2026-08",
     "https://timesofindia.indiatimes.com/business/india-business/sugar-prices-cool-18-after-hitting-record-high-ex-mill-rates-fall-to-rs-55-per-kg/articleshow/133504686.cms",
     "Sugar prices cool 18% after hitting record high, ex-mill rates fall to Rs 55 per kg", "Times of India",
     "Aug-2026", "Record Rs 67/kg in mid-August, Rs 55/kg after imports and stock limits", ["67", "55"]),
    ("news_and_macro", "sugar_daily_market_chinimandi_2026-10-31",
     "https://www.chinimandi.com/daily-sugar-market-update-by-vizzie-31-10-2026/",
     "Daily sugar market update, 31-Oct-2026", "ChiniMandi", "31-Oct-2026",
     "Ex-mill S-grade Rs 50.4-51.0/kg, M-grade Rs 54.5-55.5/kg at the status date (forecast anchor)", ["5,040"]),
    # wheat
    ("news_and_macro", "wheat_fci_auction_businessline_2026-10-28",
     "https://www.thehindubusinessline.com/economy/agri-business/indian-millers-bid-higher-rates-to-get-fcis-wheat-offtake-100-in-many-states/article71645756.ece",
     "Indian millers bid higher rates to get FCI's wheat", "BusinessLine", "28-Oct-2026",
     "All-India average wholesale wheat Rs 2,910/quintal; millers paying over Rs 3,100", ["2,910"]),
    ("news_and_macro", "food_prices_wheat_atta_livemint_2026-09",
     "https://www.livemint.com/economy/food-prices-stable-sugar-pulses-rice-retail-prices-india-11789896950548.html",
     "Food prices stable as pulses, cereals output rises; sugar rates ease", "Mint", "Sep-2026",
     "Retail wheat Rs 31.77/kg and atta Rs 37.39/kg (wheat flour broadly stable)", ["37.39"]),
    ("news_and_macro", "wheat_msp_2026-27_timesofindia",
     "https://timesofindia.indiatimes.com/city/agra/47-centres-msp-fixed-at-rs-2585/quintal-as-agra-gears-up-for-wheat-procurement/articleshow/129886182.cms",
     "MSP fixed at Rs 2,585/quintal for wheat procurement", "Times of India", "Mar-2026",
     "Wheat MSP for the 2026-27 marketing season (budget anchor for wheat flour)", ["2,585"]),
    # potato
    ("news_and_macro", "potato_bumper_harvest_timesofindia_2026-02",
     "https://timesofindia.indiatimes.com/city/kolkata/bumper-potato-harvest-sparks-distress-sales-fears-no-sign-of-farm-retail-gap-narrowing/articleshow/128434204.cms",
     "Bumper potato harvest sparks distress sales fears", "Times of India", "Feb-2026",
     "Bumper 2026 potato crop: farm-gate Rs 6/kg (why chip-grade potato ran below budget)", ["Rs 6"]),
    ("news_and_macro", "potato_mandi_prices_khetivyapar_2026-10-28",
     "https://www.khetivyapar.com/en/potato-mandi-prices-today-delhi-rates-hit-indian-rupee2000-per-quintal-10809",
     "Potato mandi prices today (28-Oct-2026)", "Khetivyapar", "28-Oct-2026",
     "Potato wholesale prices at the status date", ["Azadpur"]),
    ("news_and_macro", "potato_prices_indianpotato_2026-10",
     "https://indianpotato.com/", "IndianPotato.com price tracker", "IndianPotato.com", "Oct-2026",
     "All-India wholesale potato about Rs 11.7/kg (16-Oct-2026)", ["11.7"]),
    # quick commerce
    ("news_and_macro", "quick_commerce_growth_bernstein_businessworld_2026",
     "https://www.businessworld.in/article/india-s-quick-commerce-growth-enters-a-more-rational-phase-bernstein-615248",
     "India's quick-commerce growth enters a more rational phase: Bernstein", "BusinessWorld", "Oct-2026",
     "QC order value about USD 2.9 bn in Q4 FY26, growth slowing from 116% to 81% YoY", ["81 per cent"]),
    ("news_and_macro", "quick_commerce_share_of_online_economictimes_2026",
     "https://economictimes.indiatimes.com/industry/cons-products/fmcg/for-a-match-made-in-retail-heaven-friction-on-earth-can-be-real/articleshow/131406916.cms",
     "For a match made in retail heaven, friction on earth can be real", "Economic Times", "May-2026",
     "Quick commerce 60-75% of FMCG online sales in FY2026 (e-com & QC channel budget)", ["quick commerce"]),
    ("news_and_macro", "quick_commerce_commissions_economictimes_2024",
     "https://economictimes.indiatimes.com/articleshow/109380031.cms",
     "D2C brands cough up 30-45% commission for a spot on quick-commerce platforms", "Economic Times",
     "Apr-2024", "Large FMCG companies pay 10-20% to QC platforms (trade-spend rate for e-com & QC)", ["10-20%"]),
    ("news_and_macro", "quick_commerce_costs_startuptalky_2026",
     "https://startuptalky.com/quick-commerce-real-cost-d2c-brands/",
     "What quick commerce actually costs brands", "StartupTalky", "2026",
     "QC platforms quote 15-25% commission on selling price", ["15-25%"]),
    # payroll
    ("news_and_macro", "salary_increase_aon_2026-02-24",
     "https://www.aon.com/apac/in-the-press/asia-newsroom/2026/aon-survey-projects-slight-uptick-in-salaries-in-india-2026",
     "Aon survey projects slight uptick in salaries in India in 2026", "Aon", "24-Feb-2026",
     "Average salary increase 9.1% in 2026 (budget increment 8-10%)", ["9.1"]),
    ("news_and_macro", "salary_increase_fmcg_moneycontrol_2026",
     "https://www.moneycontrol.com/news/business/looking-forward-to-that-increment-why-your-next-appraisal-just-got-harder-to-crack-13881323.html",
     "Looking forward to that increment?", "Moneycontrol", "Apr-2026",
     "FMCG increments 8.6% and consumer products 8.7% projected for 2026", ["8.6"]),
    # interest rate
    ("news_and_macro", "rbi_repo_hike_thehindu_2026-10-07",
     "https://www.thehindu.com/business/Economy/rbi-hikes-repo-rate-by-25-basis-points-to-55/article71554369.ece",
     "RBI raises repo rate by 25 basis points to 5.50%", "The Hindu", "07-Oct-2026",
     "Repo +25 bp to 5.50% on 7-Oct-2026 (forecast interest rate +25 bp from November)", ["5.50"]),
    ("news_and_macro", "rbi_repo_hike_livemint_2026-10-07",
     "https://www.livemint.com/market/stock-market-news/rbi-mpc-meeting-october-2026-repo-rate-hiked-by-25-bps-to-5-50-growth-inflation-forecast-other-key-takeaways-11791344804917.html",
     "RBI MPC meeting October 2026: repo rate hiked by 25 bps to 5.50%", "Mint", "07-Oct-2026",
     "Second source for the repo-rate change", ["5.50"]),
    # GST and tax (government / professional sources)
    ("government", "gst_56th_council_press_release_2025-09-03",
     "https://bcasonline.org/wp-content/uploads/2025/09/03_Sep-_025_GST_Council_Recommendations.pdf",
     "Recommendations of the 56th GST Council meeting (PIB press release, copy hosted by BCAS)",
     "Press Information Bureau", "03-Sep-2025",
     "GST on namkeen, biscuits and fruit-juice drinks cut to 5% from 22-Sep-2025 (prices in the model are ex-GST)",
     ["Namkeen", "Biscuits"]),
    ("government", "gst_food_rate_cuts_economictimes_2025-09",
     "https://economictimes.indiatimes.com/articleshow/123705935.cms",
     "Food companies upbeat, expect consumer choice to shift to branded products", "Economic Times",
     "04-Sep-2025", "GST on namkeens, bhujia and mixtures cut from 12% to 5%", ["namkeen"]),
    ("government", "corporate_tax_115BAA_section200_eztax",
     "https://eztax.in/section-115baa-tax-rate-explained",
     "Section 200 (Section 115BAA) tax rate for companies explained", "EZTax", "2026",
     "22% + 10% surcharge + 4% cess = 25.168% (s.115BAA, now s.200 of the Income-tax Act 2025)", ["25.168"]),
    ("government", "corporate_tax_domestic_company_incometaxindia",
     "https://www.incometaxindia.gov.in/domestic-company", "Tax rates for a domestic company",
     "Income Tax Department", "2026", "Official surcharge rule: 10% for companies under s.115BAA", ["115BAA"]),
]


def log_row(**kw):
    LOG_ROWS.append(kw)


def fetch(url: str, timeout: int = 45) -> requests.Response | None:
    for attempt in range(3):
        try:
            return requests.get(url, headers=UA, timeout=timeout, allow_redirects=True)
        except requests.RequestException:
            time.sleep(2 + 2 * attempt)
    return None


def save_page(folder, stem, url, title, publisher, published, used_for, phrases):
    out_dir = os.path.join(SD, folder)
    os.makedirs(out_dir, exist_ok=True)
    r = fetch(url)
    status = r.status_code if r is not None else "error"
    ctype = (r.headers.get("content-type", "") if r is not None else "").lower()
    body = r.content if r is not None else b""
    blocked = r is None or r.status_code != 200 or len(body) < 3000
    if not blocked:
        is_pdf = "pdf" in ctype or body[:4] == b"%PDF"
        ext = ".pdf" if is_pdf else ".html"
        path = os.path.join(out_dir, stem + ext)
        with open(path, "wb") as fh:
            fh.write(body)
        if is_pdf:
            text = ""
            try:
                import fitz  # PyMuPDF
                with fitz.open(path) as doc:
                    text = " ".join(p.get_text() for p in doc)
            except Exception:  # noqa: BLE001
                pass
        else:
            text = BeautifulSoup(body, "lxml").get_text(" ")
        text = " ".join(text.split())
        found = [p for p in phrases if p.lower() in text.lower()]
        missing = [p for p in phrases if p not in found]
        note = "" if not missing else "phrase not found: " + "; ".join(missing)
    else:
        ext = ".md"
        path = os.path.join(out_dir, stem + ext)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"# {title}\n\n- Publisher: {publisher}\n- Published: {published}\n- URL: {url}\n"
                     f"- Attempted download: {TODAY}; HTTP status {status}. The site blocked the automated "
                     f"download, so only the link and the fact used are recorded here.\n- Fact used in the model: "
                     f"{used_for}\n")
        found, note = [], f"blocked (HTTP {status}); link recorded"
    log_row(folder=folder, file=os.path.basename(path), url=url, title=title, publisher=publisher,
            published=published, used_for=used_for, http_status=status, bytes=len(body) if not blocked else 0,
            sha256=hashlib.sha256(body).hexdigest() if not blocked else "", downloaded=TODAY,
            phrase_check="ok" if (not blocked and not note) else note)
    print(f"{folder}/{os.path.basename(path)}: status {status}, {len(body):,} bytes {note}")
    time.sleep(1.2)


# ---------------------------------------------------------------------------------------------
# Screener
# ---------------------------------------------------------------------------------------------
def to_number(x):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    s = str(x).replace(",", "").replace("%", "").strip()
    if s in ("", "-", "--"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_section(soup, sec_id):
    sec = soup.find("section", id=sec_id)
    if sec is None:
        return None
    table = sec.find("table", class_=re.compile("data-table"))
    if table is None:
        return None
    df = pd.read_html(io.StringIO(str(table)))[0]
    df = df.rename(columns={df.columns[0]: "item"})
    df["item"] = df["item"].astype(str).str.replace(r"\s*\+\s*$", "", regex=True).str.replace("\xa0", " ").str.strip()
    df = df[df["item"].str.lower() != "raw pdf"]
    for c in df.columns[1:]:
        df[c] = df[c].map(to_number)
    return df


def sales_points(df):
    if df is None:
        return 0
    row = df[df["item"].str.match(r"^(Sales|Revenue)", na=False)]
    return int(row.iloc[0, 1:].notna().sum()) if len(row) else 0


def write_xlsx(path, url, view, frames: dict):
    wb = Workbook()
    wb.remove(wb.active)
    for name, df in frames.items():
        ws = wb.create_sheet(name[:31])
        units = ("% of sales" if name == "expenses_breakdown" else
                 "Rs crore (rows ending in % are percentages; EPS in Rs)")
        ws.append([f"Source: Screener.in ({view}) | {url} | downloaded {TODAY} | {units}"])
        ws["A1"].font = Font(bold=True)
        ws.append([str(c) for c in df.columns])
        for c in ws[2]:
            c.font = Font(bold=True)
        for rec in df.itertuples(index=False):
            ws.append([None if (isinstance(v, float) and pd.isna(v)) else v for v in rec])
        ws.column_dimensions["A"].width = 34
        ws.freeze_panes = "B3"
    wb.save(path)


def fetch_screener():
    base = os.path.join(SD, "screener")
    raw, csvd = os.path.join(base, "raw"), os.path.join(base, "csv")
    os.makedirs(raw, exist_ok=True)
    os.makedirs(csvd, exist_ok=True)
    summary = {}
    for sym, short, name, pref, segment in PEERS:
        chosen = None
        for view in (pref, "standalone" if pref == "consolidated" else "consolidated"):
            url = f"https://www.screener.in/company/{sym}/" + ("consolidated/" if view == "consolidated" else "")
            r = fetch(url)
            if r is None or r.status_code != 200:
                print(f"screener {sym} {view}: HTTP {getattr(r, 'status_code', 'error')}")
                continue
            soup = BeautifulSoup(r.text, "lxml")
            pl = parse_section(soup, "profit-loss")
            if sales_points(pl) >= 3:
                chosen = (view, url, r, soup)
                break
            time.sleep(1.2)
        if chosen is None:
            print(f"screener {sym}: no usable page")
            log_row(folder="screener", file="", url=f"https://www.screener.in/company/{sym}/", title=name,
                    publisher="Screener.in", published="", used_for="Peer margins", http_status="no data",
                    bytes=0, sha256="", downloaded=TODAY, phrase_check="no usable page")
            continue
        view, url, r, soup = chosen
        html_path = os.path.join(raw, f"{sym}_{view}.html")
        with open(html_path, "wb") as fh:
            fh.write(r.content)
        log_row(folder="screener/raw", file=os.path.basename(html_path), url=url, title=f"{name} ({view})",
                publisher="Screener.in", published="live page", used_for="Peer revenue growth and margins",
                http_status=r.status_code, bytes=len(r.content), sha256=hashlib.sha256(r.content).hexdigest(),
                downloaded=TODAY, phrase_check="ok")
        frames = {}
        for sec in SECTIONS:
            df = parse_section(soup, sec)
            if df is not None:
                df.to_csv(os.path.join(csvd, f"{sym}_{sec}.csv"), index=False)
                frames[sec] = df
        m = re.search(r'data-company-id="(\d+)"', r.text)
        cid = m.group(1) if m else None
        if cid:
            api = (f"https://www.screener.in/api/company/{cid}/schedules/?parent=Expenses&section=profit-loss"
                   f"&consolidated={'true' if view == 'consolidated' else ''}")
            a = fetch(api)
            if a is not None and a.status_code == 200:
                with open(os.path.join(raw, f"{sym}_expenses_schedule.json"), "wb") as fh:
                    fh.write(a.content)
                try:
                    js = a.json()
                except ValueError:
                    js = {}
                if isinstance(js, dict) and js:
                    rows = []
                    for item, vals in js.items():
                        rec = {"item": item}
                        rec.update({k: to_number(v) for k, v in vals.items() if k != "isExpandable"})
                        rows.append(rec)
                    edf = pd.DataFrame(rows)
                    edf.to_csv(os.path.join(csvd, f"{sym}_expenses_breakdown.csv"), index=False)
                    frames["expenses_breakdown"] = edf
                log_row(folder="screener/raw", file=f"{sym}_expenses_schedule.json", url=api,
                        title=f"{name} expense schedule", publisher="Screener.in", published="live API",
                        used_for="Material and employee cost % of sales", http_status=a.status_code,
                        bytes=len(a.content), sha256=hashlib.sha256(a.content).hexdigest(), downloaded=TODAY,
                        phrase_check="ok" if js else "empty schedule")
        xlsx = os.path.join(base, f"{short}_Screener_{view.capitalize()}.xlsx")
        write_xlsx(xlsx, url, view, frames)
        summary[sym] = {"name": name, "short": short, "segment": segment, "view": view, "url": url,
                        "company_id": cid, "sections": list(frames), "xlsx": os.path.basename(xlsx)}
        print(f"screener {sym}: {view}, sections {list(frames)}")
        time.sleep(1.5)
    with open(os.path.join(base, "screener_summary.json"), "w", encoding="utf-8") as fh:
        json.dump({"downloaded": TODAY, "peers": summary}, fh, indent=2)


def main(parts: list[str]):
    """parts: any of 'screener', 'pages' (default both). A partial run keeps the other rows of the log."""
    os.makedirs(SD, exist_ok=True)
    if "screener" in parts:
        fetch_screener()
    if "pages" in parts:
        for p in PAGES:
            save_page(*p)
    fields = ["folder", "file", "url", "title", "publisher", "published", "used_for", "http_status", "bytes",
              "sha256", "downloaded", "phrase_check"]
    log_path = os.path.join(SD, "download_log.csv")
    keep = []
    if os.path.exists(log_path) and set(parts) != {"screener", "pages"}:
        with open(log_path, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                is_scr = row["folder"].startswith("screener")
                if (is_scr and "screener" not in parts) or (not is_scr and "pages" not in parts):
                    keep.append(row)
    with open(log_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        rows = [r for r in LOG_ROWS if r["folder"].startswith("screener")] + \
               [r for r in keep if r["folder"].startswith("screener")] + \
               [r for r in keep if not r["folder"].startswith("screener")] + \
               [r for r in LOG_ROWS if not r["folder"].startswith("screener")]
        w.writerows(rows)
    total = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(SD) for f in fs)
    print(f"source_data total size: {total / 1e6:.1f} MB")


if __name__ == "__main__":
    import sys
    main(sys.argv[1:] or ["screener", "pages"])
