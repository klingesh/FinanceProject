# source_data: original downloads behind every number

All files were downloaded on 1-Nov-2026 (prices to the 30-Oct-2026 close; filings up to Asian Paints' Q2 FY27 results of 29-Oct-2026) by `build/fetch_screener.py`, `fetch_stockanalysis.py`, `fetch_xbrl.py`, `fetch_nse_filings.py`, `fetch_prices.py` and `fetch_news.py`. `build/export_source_xlsx.py` writes the `.xlsx` copies of the web tables (row 1 of every sheet gives the site, URL, download date and units). `build/trim_source_data.py` keeps this folder under 40 MB with no file over 20 MB: it image-compresses large PDFs (text layer unchanged, checked page by page), saves page extracts of very large documents and moves files that no number uses to a folder outside the repository (log: `build/_trim_log.txt`). The tidy inputs that the code reads are in `data/`; the code runs without any of the local-only files.

Companies (NSE symbol): Asian Paints (ASIANPAINT), Berger Paints (BERGEPAINT), Kansai Nerolac (KANSAINER), JSW Dulux (JSWDULUX, Akzo Nobel India until 11-Mar-2026, older filings under AKZOINDIA), Indigo Paints (INDIGOPNTS). Units: company filings and Screener in Rs crore (Indigo files in Rs lakh, JSW Dulux in Rs million); StockAnalysis statements in INR millions, its forecast page in INR billions ("B"); prices in Rs.

**Not in the GitHub copy.** The saved news articles in `news_and_macro/*.html` are copyrighted, so they stay on the author's PC and are left out of the public repository (see `.gitignore`). Each one is listed below with its full link and the fact taken from it. Company filings and press releases, the Competition Commission order, exchange data and data exports are included.

## company_filings/ (Asian Paints; NSE corporate announcements)

| File | What it contains | Source (name + full URL) | Date downloaded | Used for |
|---|---|---|---|---|
| `AsianPaints_Q2FY27_Results_and_Press_Release_29Oct2026.pdf` | Board-meeting outcome, 29-Oct-2026 (20 pages): Q2 and H1 FY27 standalone and consolidated results, segments, 30-Sep-2026 balance sheet, FY2026 comparatives, press release (pages 17-20). NSE carries the same file under two links; one copy kept, image-compressed (8.6 to 4.3 MB) | NSE: https://nsearchives.nseindia.com/corporate/ASIANPAINT_29102026140213_OutcomeofBM29102026signed.pdf (identical: https://nsearchives.nseindia.com/corporate/ASIANPAINT_29102026141409_OutcomeofBM29102026signed.pdf) | 01-Nov-2026 | Q2 and H1 FY27 results (`data/asianpaints_q2fy27_results.csv`, with page numbers), FY2026 cross-checks (`data/company_reported_checks.csv`), company profile |
| `AsianPaints_Q2FY27_Investor_Presentation_29Oct2026.pdf` | Q2 FY27 investor presentation (31 slides) | NSE: https://nsearchives.nseindia.com/corporate/ASIANPAINT_29102026164544_SEIntimation_Investor_Presentation_Q2FY26-27pdfsigned.pdf | 01-Nov-2026 | Gross margin (pp. 25-27), VAE plant (p. 14), new products (p. 18), home decor (pp. 19-20), dividend (p. 28), outlook (p. 29), ESG targets (p. 30) |
| `AsianPaints_Q2FY27_Call_Recording_Link_29Oct2026.pdf` | Filing with the link to the Q2 FY27 call recording | NSE: https://nsearchives.nseindia.com/corporate/ASIANPAINT_29102026211830_SE_intimation__Audio_Recording_Q2FY26-27signed.pdf | 01-Nov-2026 | Shows that no Q2 transcript was filed yet |
| `AsianPaints_Q4FY26_Results_and_Press_Release_29May2026.pdf` | FY2026 audited results (24 pages): auditor's reports, standalone and consolidated P&L, balance sheet, cash flow, segments, press release (pp. 21-24); image-compressed (10.8 to 5.0 MB) | NSE: https://nsearchives.nseindia.com/corporate/ASIANPAINT_29052026140521_SEIntimationoutcomeFY26.pdf | 01-Nov-2026 | FY2025-FY2026 cost of goods sold and exceptional items (consolidated P&L, p. 16; `data/company_reported_fy25_fy26.csv`) |
| `AsianPaints_Q4FY26_Earnings_Call_Transcript_29May2026.pdf` | Q4 FY26 earnings-call transcript (26 pages), filed 3-Jun-2026; image-compressed (3.7 to 1.5 MB) | NSE: https://nsearchives.nseindia.com/corporate/ASIANPAINT_03062026154629_Reg30_Transcript_Q4FY26.pdf | 01-Nov-2026 | Cost inflation of about 20% vs about 11% price increases, 18-20% margin band, 8-10% volume ambition, discounting (pp. 20-22) |
| `AsianPaints_Annual_Report_FY2025-26_extract.pdf` | Integrated Annual Report FY2025-26: pages 1, 5, 10, 18, 30, 44 and 165 of 294 (26.3 MB in full) | NSE annual reports: https://nsearchives.nseindia.com/annual_reports/AR_29385_ASIANPAINT_2025_2026_A_26278926_12062026160918.pdf | 01-Nov-2026 | Capacity 2,290,000 KL, 13 plants plus 30 outsourced centres, R&D, CSR Rs 114.6 cr, renewable electricity 56.5% (p. 44); 72,873 dealers (BRSR section, p. 165); 6,000 new retail touchpoints, 9.45 lakh painters trained (p. 18); international revenue Rs 3,354 cr (p. 30); auditor (p. 5) |

## company_filings/peers/ (FY2026 results of the four peers)

| File | What it contains | Source (name + full URL) | Date downloaded | Used for |
|---|---|---|---|---|
| `BergerPaints_Q4FY26_Financial_Results_12May2026.pdf` | FY2026 audited results (20 pages); image-compressed (2.1 to 1.8 MB) | NSE: https://nsearchives.nseindia.com/corporate/PAINTBERGE_12052026152354_ResultsFinal.pdf | 01-Nov-2026 | FY2025-FY2026 cost of goods sold and exceptional items (consolidated P&L, p. 14) |
| `JSWDulux_Q4FY26_Financial_Results_13May2026.pdf` | FY2026 audited results (25 pages; the consolidated P&L, p. 17, is a scan); image-compressed (2.8 to 1.9 MB) | NSE: https://nsearchives.nseindia.com/corporate/AKZOINDIA_13052026221122_JSWDuluxOutcomeofBoardMeeting13May26.pdf | 01-Nov-2026 | FY2025-FY2026 cost of goods sold; slump-sale gain (note 6, p. 15) and Rs 80.8 cr property gain (p. 17), both removed from adjusted ratios |
| `KansaiNerolac_Q4FY26_Results_extract.pdf` | FY2026 results and press release: pages 1, 2 and 14-19 of 19 (7.1 MB in full). Original page 14 = page 3 here, page 19 = page 8 | NSE: https://nsearchives.nseindia.com/corporate/KANSAINER_06052026164550_Outcome_BM_6that_may_2026signed.pdf | 01-Nov-2026 | FY2025-FY2026 cost of goods sold and exceptional items (original p. 14, note 5); industry size about Rs 77,500 cr (original p. 19) |
| `KansaiNerolac_Q4FY25_Results_extract.pdf` | FY2025 results: pages 1 and 14-16 of 20 (7.7 MB in full) | NSE: https://nsearchives.nseindia.com/corporate/KANSAINER_06052025205914_Outcome_Signed.pdf | 01-Nov-2026 | What the FY2024 exceptional gain was (Kavesar property sale, note 5) |
| `IndigoPaints_Q4FY26_Financial_Results_extract.pdf` | FY2026 results: pages 1 and 13-16 of 21 (19.1 MB in full, scanned pages). Original page 13 = page 2 here | NSE: https://nsearchives.nseindia.com/corporate/INDIGOPNTS_22052026201253_BM_Outcome_M26.pdf | 01-Nov-2026 | FY2025-FY2026 cost of goods sold and exceptional items (consolidated P&L, original p. 13) |

## nse/ (NSE public APIs, JSON as returned)

| File | What it contains | Source (name + full URL) | Date downloaded | Used for |
|---|---|---|---|---|
| `<SYMBOL>_announcements_2026.json` (5 files) | Corporate announcements in the date windows listed in `build/fetch_nse_filings.py` (subject, time, attachment link) | NSE API: https://www.nseindia.com/api/corporate-announcements?index=equities&symbol=ASIANPAINT&from_date=20-10-2026&to_date=01-11-2026 (symbol and dates vary) | 01-Nov-2026 | Finding the filings above and their filing times |
| `ASIANPAINT_annual-reports.json` | List of Asian Paints annual reports | NSE API: https://www.nseindia.com/api/annual-reports?index=equities&symbol=ASIANPAINT | 01-Nov-2026 | Link to the FY2025-26 annual report |
| `ASIANPAINT_corporate-share-holdings-master.json` | List of shareholding-pattern filings | NSE API: https://www.nseindia.com/api/corporate-share-holdings-master?index=equities&symbol=ASIANPAINT | 01-Nov-2026 | Cross-check of the Screener shareholding table |
| `xbrl/<SYMBOL>_FY<year>_<scope>.xml` (20 files) | Audited annual results in XBRL as filed with NSE, FY2021-FY2024 (Indigo standalone FY2021-FY2023); each file's link is in `data/xbrl_annual.csv` (column `xbrl_url`) | NSE XBRL archive, links listed by the API below | 01-Nov-2026 | Cost of materials, purchases of traded goods, inventory change and exceptional items, FY2021-FY2024 (`data/xbrl_annual.csv`) |
| `xbrl/<SYMBOL>_financial_results_annual.json` (6 files, incl. AKZOINDIA) | NSE list of annual results with XBRL links | NSE API: https://www.nseindia.com/api/corporates-financial-results?index=equities&symbol=ASIANPAINT&period=Annual (symbol varies) | 01-Nov-2026 | Choosing the latest audited filing for each year |

## screener/ (Screener.in, Rs crore)

| File | What it contains | Source (name + full URL) | Date downloaded | Used for |
|---|---|---|---|---|
| `<Company>_Screener_Consolidated.xlsx` (5 files) | 9 sheets: page summary (market cap, price, P/E, book value, dividend yield), quarters, profit and loss, balance sheet, cash flow, ratios, shareholding by quarter and by year, line-item schedules | Built by `build/export_source_xlsx.py` from the downloads below | 01-Nov-2026 | Easy viewing in Excel |
| `<Company>_Screener_Standalone.xlsx` (5 files) | The same for the standalone pages (schedules for Indigo Paints only) | Built from the downloads below | 01-Nov-2026 | Easy viewing in Excel |
| `raw/<SYMBOL>_consolidated.html` (5 files), `raw/INDIGOPNTS_standalone.html` | Company pages as downloaded | Screener.in: https://www.screener.in/company/ASIANPAINT/consolidated/ (standalone: https://www.screener.in/company/INDIGOPNTS/) | 01-Nov-2026 | Statements for the ratio workbook (`data/ratio_inputs.csv`); market cap, P/E, book value, dividend yield, shareholding; Indigo FY2021-FY2023 (standalone, no subsidiary then) |
| `schedules/<SYMBOL>_<scope>_<section>_<parent>.json` (102 files) | Line-item breakdowns (sales, expenses, borrowings, other assets and liabilities, investments, net profit) | Screener schedules API: https://www.screener.in/api/company/295/schedules/?parent=Borrowings&section=balance-sheet&consolidated=true (company id, parent and section vary; the URL is inside each file) | 01-Nov-2026 | Receivables, inventories, payables, cash, borrowings, leases, minority interest |

## stockanalysis/ (StockAnalysis.com, S&P Global Market Intelligence data)

| File | What it contains | Source (name + full URL) | Date downloaded | Used for |
|---|---|---|---|---|
| `<Company>_<Statement>_StockAnalysis.xlsx` (35 files) | Income statement, balance sheet, cash flow statement, ratios, statistics and valuation, forecast (analyst projections) and dividends for each company; one sheet per table on the page | Built by `build/export_source_xlsx.py` from the pages below | 01-Nov-2026 | Easy viewing in Excel |
| `raw/<SYMBOL>_income.html`, `raw/<SYMBOL>_balance.html` (10 files) | Annual income statement and balance sheet pages as downloaded (INR millions) | StockAnalysis: https://stockanalysis.com/quote/nse/ASIANPAINT/financials/ and https://stockanalysis.com/quote/nse/ASIANPAINT/financials/balance-sheet/ (symbol varies) | 01-Nov-2026 | Current assets and liabilities, cash and short-term investments (`data/ratio_inputs.csv`); cross-checks of COGS, net income, total assets and inventory (`outputs/data_crosscheck.csv`) |
| `raw/ASIANPAINT_forecast.html` | Analyst forecast page: price targets, ratings, FY2027 estimates (30 analysts) | StockAnalysis: https://stockanalysis.com/quote/nse/ASIANPAINT/forecast/ | 01-Nov-2026 | Consensus EPS Rs 53.94, revenue, price targets Rs 1,925 / 2,756 / 2,850 / 3,300, ratings |
| `raw/ASIANPAINT_dividend.html` | Dividend history | StockAnalysis: https://stockanalysis.com/quote/nse/ASIANPAINT/dividend/ | 01-Nov-2026 | Dividends per share (cross-check) |

## yahoo_finance/

| File | What it contains | Source (name + full URL) | Date downloaded | Used for |
|---|---|---|---|---|
| `ASIANPAINT.NS.csv`, `BERGEPAINT.NS.csv`, `KANSAINER.NS.csv`, `JSWDULUX.NS.csv`, `INDIGOPNTS.NS.csv`, `IDX_NSEI.csv` (NIFTY 50) | Daily open, high, low, close, adjusted close, dividends, splits and volume, 1-Oct-2021 to 30-Oct-2026 (closes restated for splits and bonus issues) | Yahoo Finance via yfinance (`auto_adjust=False`): https://finance.yahoo.com/quote/ASIANPAINT.NS/history/ (ticker varies; NIFTY 50 is ^NSEI) | 01-Nov-2026 | Price Rs 2,320, 52-week range, 1/3/5-year returns, price chart; daily P/E premium to peers (`build/relative_value.py`) |

## news_and_macro/ (news, industry and regulatory pages)

Saved by `build/fetch_news.py` with scripts and styles removed (article text kept). Files marked "local only" are copyrighted articles that are not in the GitHub copy.

| File | What it contains | Source (name + full URL) | Date downloaded | Used for |
|---|---|---|---|---|
| `2025-07-01_CCI_order_Grasim_v_AsianPaints.pdf` | Competition Commission of India order of 1-Jul-2025 (Section 26(1)) | CCI: https://www.cci.gov.in/images/antitrustorder/en/order1751442738.pdf | 01-Nov-2026 | Governance: investigation into alleged abuse of dominance |
| `2025-12-10_JSW_press_release_AkzoNobel_India.html` | JSW Group press release, 10-Dec-2025 | JSW: https://www.jsw.in/newsroom/press-releases/jsw-paints-completes-the-acquisition-process-of-akzo-nobel-india/ | 01-Nov-2026 | JSW Paints completed its 60.76% purchase of Akzo Nobel India |
| `Grasim_paints_business_page.html` | Grasim's paints (Birla Opus) business page | Grasim: https://www.grasim.com/about-us/our-businesses/paints | 01-Nov-2026 | Birla Opus capacity 1,332 million litres a year (about 24% of organised capacity) |
| `2026-08-13_NDTVProfit_BirlaOpus_Q1FY27.md` | Link and a one-line summary (the site blocked the download) | NDTV Profit, 13-Aug-2026: https://www.ndtvprofit.com/markets/birla-opus-strengthens-footing-in-paints-sector-can-it-affect-asian-paints-macquarie-morgan-stanley-weigh-in-11902907 | 01-Nov-2026 | Grasim paints revenue Rs 1,661 cr in Q1 FY27 (+64%) |
| `2024-03-07_ETBrandEquity_Pidilite_Haisha.html` (local only) | ET BrandEquity, 7-Mar-2024 | https://brandequity.economictimes.indiatimes.com/news/advertising/pidilite-bridges-crucial-gaps-in-the-decorative-paints-market-with-haisha-paints/108300157 | 01-Nov-2026 | Pidilite's entry with Haisha Paints |
| `2025-05-13_ETCFO_Birla_bet_rattles_AsianPaints.html` (local only) | ET CFO, 13-May-2025 | https://cfo.economictimes.indiatimes.com/news/news/birlas-big-paints-bet-rattles-asian-paints-india-reign/121139433 | 01-Nov-2026 | Asian Paints' share about 59% (Mar-2024) and about 52% (early 2025), industry estimates |
| `2025-10-14_ETBrandEquity_SC_AsianPaints_CCI.html` (local only) | ET BrandEquity, 14-Oct-2025 | https://brandequity.economictimes.indiatimes.com/news/business-of-brands/sc-refuses-to-entertain-plea-by-asian-paints-against-cci-probe/124543569 | 01-Nov-2026 | Supreme Court declined Asian Paints' plea against the CCI probe |
| `2026-03-13_ETBrandEquity_JSW_Dulux_rename.html` (local only) | ET BrandEquity, 13-Mar-2026 | https://brandequity.economictimes.indiatimes.com/news/business-of-brands/akzo-nobel-india-gets-regulatory-nod-to-change-name-to-jsw-dulux/129546141 | 01-Nov-2026 | Akzo Nobel India renamed JSW Dulux from 11-Mar-2026 |
| `2026-09-08_FinancialExpress_paint_shares.html` (local only) | Financial Express, 8-Sep-2026 | https://www.financialexpress.com/market/stock-insights/this-paint-stock-is-trading-at-a-50-discount-to-its-rivals-is-the-market-missing-something/4333892/ | 01-Nov-2026 | Second source for the 59% share estimate |
| `2026-09-30_TheHindu_monsoon_deficit.html` (local only) | The Hindu, 30-Sep-2026 | https://www.thehindu.com/sci-tech/energy-and-environment/southwest-monsoon-ends-with-12-deficit/article71529423.ece | 01-Nov-2026 | Monsoon at about 87% of the long-period average |
| `2026-10-25_ET_TiO2_antidumping_duty.html` (local only) | The Economic Times, 25-Oct-2026 | https://economictimes.indiatimes.com/industry/cons-products/paints/china-faces-fresh-indian-duties-on-titanium-dioxide-imports-anti-dumping-levy-of-460-681-per-tonne-reimposed-for-five-years/articleshow/135170362.cms | 01-Nov-2026 | Anti-dumping duty of USD 460-681 a tonne on Chinese titanium dioxide |
| `2026-10-27_Moneycontrol_paint_dealers_discounts.html` (local only) | Moneycontrol, 27-Oct-2026 | https://www.moneycontrol.com/news/business/paint-dealers-get-the-blues-as-companies-push-stocks-amid-sluggish-demand-14061151.html | 01-Nov-2026 | Dealer discounting since August 2026 |
| `2026-10-29_BusinessStandard_AsianPaints_Q2FY27_result.html` (local only) | Business Standard, 29-Oct-2026 | https://www.business-standard.com/companies/quarterly-results/asian-paints-q2fy27-result-profit-rises-7-5-to-1-068-cr-sales-grow-17-126102900944_1.html | 01-Nov-2026 | Cross-check of Q2 FY27 PAT (+7.5%) |
| `2026-10-30_ET_AsianPaints_broker_target_cuts.html` (local only) | The Economic Times, 30-Oct-2026 | https://economictimes.indiatimes.com/markets/stocks/news/asian-paints-shares-in-focus-as-jefferies-goldman-sachs-other-brokerages-cut-target-prices-after-q2-results-buy-sell-or-hold/articleshow/135342271.cms | 01-Nov-2026 | Broker ratings and target cuts after Q2 (Jefferies, Goldman Sachs, Systematix, Dolat) |
| `2026-10-30_Yahoo_GuruFocus_AsianPaints_Q2FY27_call_highlights.html` (local only) | GuruFocus via Yahoo Finance, 30-Oct-2026 | https://finance.yahoo.com/markets/stocks/articles/asian-paints-ltd-bom-500820-210832075.html | 01-Nov-2026 | Q2 call summary: H1 volume about 8%, price increases of about 7% (Q1) and 5% (Q2) |
| `2026-10-31_BusinessWorld_Grasim_BirlaOpus_share.html` (local only) | BusinessWorld, 31-Oct-2026 | https://www.businessworld.in/article/grasim-industries-targets-rs-2-lakh-cr-revenue-in-fy27-birla-620427 | 01-Nov-2026 | Birla Opus at about 10% of decorative revenue within two years |

## Downloaded but not kept in this folder

These files back no number in the project (or were replaced by the extracts above), so `build/trim_source_data.py` moved them to the author's PC to stay within the size limit:
- Asian Paints Q1 FY27 press release, 29-Jul-2026: https://nsearchives.nseindia.com/corporate/ASIANPAINT_29072026140548_SEintimationJune26.pdf
- Asian Paints Q1 FY27 investor presentation: https://nsearchives.nseindia.com/corporate/ASIANPAINT_29072026165710_Intimation_Investor_Presentation_Q1FY26-27finsigned.pdf
- Asian Paints Q4 FY26 investor presentation: https://nsearchives.nseindia.com/corporate/ASIANPAINT_29052026165558_SEintimationInvestorPresentation_Q4FY26finalfinal.pdf
- Asian Paints BRSR FY2025-26 (the same report is inside the annual report): https://nsearchives.nseindia.com/corporate/ASIANPAINT_12062026163131_SEIntimationBRSR202526signed.pdf
- JSW Dulux Q4 FY26 investor presentation: https://nsearchives.nseindia.com/corporate/AKZOINDIA_13052026230002_JSWDuluxInvestorCall14May26Presentation.pdf
- Indigo Paints Q2 FY27 investor presentation: https://nsearchives.nseindia.com/corporate/INDIGOPNTS_30102026184320_Indigo_Intimation_Presentation_of_Transcript_call-Signed.pdf
- The full annual report and the full Kansai Nerolac and Indigo Paints results (links in the tables above).
- StockAnalysis raw pages other than the income statements, balance sheets and Asian Paints' forecast and dividend pages, and the Screener standalone raw pages other than Indigo Paints. Their tables are in the `.xlsx` exports above and in `data/`.
