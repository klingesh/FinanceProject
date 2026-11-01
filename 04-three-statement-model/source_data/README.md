# source_data: original downloads behind every number

All files were downloaded on 1-Nov-2026 (prices to the 30-Oct-2026 close; filings up to the Q2 FY2027 results of 19-Oct-2026). `build/01_fetch_data.py` and `build/02_fetch_filings.py` wrote them; `build/07_export_sources.py` built the `.xlsx` files from the raw pages so they open cleanly in Excel (row 1 of each sheet gives the site, URL, download date and units). The audited statements were typed from the company PDFs into `build/03_prepare_data.py`, which checks 60 subtotals against the filings and compares 35 lines with Screener (all within 1%).

Units: company filings and Screener in Rs crore; StockAnalysis in INR millions; Yahoo Finance in Rs per share.

**Not in the GitHub copy.** The saved news pages in `news_and_macro/*.html` are copyrighted articles, so they stay on the author's PC and are left out of the public repository. Each one is listed below with its full link and the fact taken from it. Company filings, exchange-quoted prices and data exports are included.

## company_filings/ (UltraTech Cement, consolidated)

Large PDFs are saved as page extracts (the pages used); the full document is at the link.

| File | What it contains | Source | Used for |
|---|---|---|---|
| `UltraTech_FY26_Audited_Consolidated_Results_extract.pdf` | FY2026 audited results, PDF pages 8-10 and 12 of 21: consolidated P&L, balance sheet and cash flow for FY2026 and FY2025 | [q4fy26-results.pdf](https://www.ultratechcement.com/content/dam/ultratechcementwebsite/pdf/financials/financial-results/fy26/q4/q4fy26-results.pdf) | Historical sheet: FY2026 and FY2025 |
| `UltraTech_FY24_Audited_Results.pdf` | FY2024 audited results (full, 11 pages) | [Q4FY24Results.pdf](https://www.ultratechcement.com/content/dam/ultratechcementwebsite/pdf/financials/financial-results/fy24/q4/Q4FY24Results.pdf) | Historical sheet: FY2024 |
| `UltraTech_FY23_Audited_Results.pdf` | FY2023 audited results (full, 10 pages), with FY2022 comparatives | [utcl-results-q4-fy-23-clean.pdf](https://www.ultratechcement.com/content/dam/ultratechcementwebsite/pdf/financials/financial-results/fy23/q4/utcl-results-q4-fy-23-clean.pdf) | Historical sheet: FY2023 and FY2022 |
| `UltraTech_Q2FY27_Consolidated_Results_19Oct2026_extract.pdf` | Q2 FY2027 consolidated results, pages 6-8 of 17 | [q2fy27-results.pdf](https://www.ultratechcement.com/content/dam/ultratechcementwebsite/pdf/financials/financial-results/fy27/q2/q2fy27-results.pdf) | H1 FY2027 reference points (volume, capex) |
| `UltraTech_Q2FY27_Investor_Presentation_19Oct2026_extract.pdf` | Q2 FY2027 presentation, pages 2, 9, 12-13, 19-20, 22, 30-33 of 40: capacity roadmap to 242.9 MTPA, volumes, costs per tonne | [q2fy27-investor-presentation.pdf](https://www.ultratechcement.com/content/dam/ultratechcementwebsite/pdf/financials/investor-update/q2fy27-investor-presentation.pdf) | Capacity additions, cost per tonne |
| `UltraTech_Q2FY27_Earnings_Call_Transcript_19Oct2026.pdf` | Q2 FY2027 earnings-call transcript (full) | [q2fy27-earnings-call-transcript.pdf](https://www.ultratechcement.com/content/dam/ultratechcementwebsite/pdf/financials/earnings-call/q2fy27-earnings-call-transcript.pdf) | FY2027 capex about Rs 10,000 crore; Rs 5,000 crore NCDs at 7.25% |
| `UltraTech_Q1FY27_Results_Presentation_extract.pdf` | Q1 FY2027 presentation, pages 8, 10, 13, 27-29 of 38 | [results-presentation-q1fy27.pdf](https://www.ultratechcement.com/content/dam/ultratechcementwebsite/pdf/financials/investor-update/results-presentation-q1fy27.pdf) | Q1 FY2027 volume and realisation |
| `UltraTech_Q4FY26_Investor_Presentation_27Apr2026_extract.pdf` | Q4 FY2026 presentation, pages 10, 14-15, 20-22, 32-37 of 47: net sales vs other operating income, volumes, capex | [q4fy26-investor-presentation.pdf](https://www.ultratechcement.com/content/dam/ultratechcementwebsite/pdf/financials/investor-update/q4fy26-investor-presentation.pdf) | FY2025-FY2026 operating data |
| `UltraTech_Q4FY26_Earnings_Call_Transcript_27Apr2026.pdf` | Q4 FY2026 earnings-call transcript (full) | [earnings-call-transcript-q4fy26.pdf](https://www.ultratechcement.com/content/dam/ultratechcementwebsite/pdf/financials/earnings-call/ultratech-cement-limited-earnings-call-transcript-q4fy26.pdf) | Volume growth guidance 7-8%; capex Rs 8,000-10,000 crore a year to FY2031; leverage below 1x |
| `UltraTech_Integrated_Report_FY2025-26_extract.pdf` | Integrated and Sustainability Report FY2025-26, 19 of 600 pages (incl. capex plan p.46-47, borrowings note 17 p.509-512) | [integrated-and-sustainability-report-2025-26-single-page.pdf](https://www.ultratechcement.com/content/dam/ultratechcementwebsite/pdf/financials/annual-reports/integrated-and-sustainability-report-2025-26-single-page.pdf) | Rs 16,000 crore for 37 MTPA (cost per MTPA); debt maturities |
| `UltraTech_Q4FY25_Results_Presentation_extract.pdf` | Q4 FY2025 presentation, pages 10, 13-14, 37-39, 41 of 46 | [UltraTech-Result-Presentation-Q4-FY25.pdf](https://www.ultratechcement.com/content/dam/ultratechcementwebsite/pdf/financials/investor-update/UltraTech-Result-Presentation-Q4-FY25.pdf) | FY2025 volumes and capacity |
| `UltraTech_Q4FY24_Results_Presentation_extract.pdf` | Q4 FY2024 presentation, pages 7, 9, 17, 36-37, 39 of 42 | [Result-Presentation-Q4-FY24 (2).pdf](https://www.ultratechcement.com/content/dam/ultratechcementwebsite/pdf/financials/investor-update/Result-Presentation-Q4-FY24%20%282%29.pdf) | FY2023-FY2024 net sales split, volumes |
| `UltraTech_Q4FY23_Results_Presentation_extract.pdf` | Q4 FY2023 presentation, pages 7-8, 19, 35-36, 38 of 39 | [ultratech-result-presentation-q4-fy-23.pdf](https://www.ultratechcement.com/content/dam/ultratechcementwebsite/pdf/financials/investor-update/ultratech-result-presentation-q4-fy-23.pdf) | FY2022-FY2023 operating data |
| `UltraTech_Q4FY22_Investor_Presentation_extract.pdf` | Q4 FY2022 presentation, pages 7 and 16 of 33 | [utcl-investor-presentation-q4-fy-22.pdf](https://www.ultratechcement.com/content/dam/ultratechcementwebsite/pdf/financials/investor-update/utcl-investor-presentation-q4-fy-22.pdf) | March 2022 capacity |

The FY2025 results PDF is a scan without text, so FY2025 comes from the FY2026 comparatives. The page lists for every extract are in `data/raw/filings_manifest.json`.

## screener/ (Screener.in, consolidated, Rs crore)

| File | What it contains | Source | Used for |
|---|---|---|---|
| `UltraTech_Screener_Consolidated.xlsx` | 10 sheets: summary box, quarters, profit and loss, balance sheet, cash flow, ratios and the line-item schedules | Built from the raw files below | Easy viewing in Excel |
| `raw/ULTRACEMCO_consolidated.html` | The company page as downloaded (prices to the 30-Oct-2026 close) | [screener.in/company/ULTRACEMCO/consolidated](https://www.screener.in/company/ULTRACEMCO/consolidated/) | Cross-check of the audited statements (`data/crosscheck_screener.csv`) |
| `raw/ULTRACEMCO_schedule_*.json` (16 files) | Line-item breakdowns: borrowings, fixed assets, investments, other assets and liabilities, expenses, other income, net profit, sales, cash-flow detail | Screener schedules API, e.g. [Borrowings](https://www.screener.in/api/company/3525/schedules/?parent=Borrowings&section=balance-sheet&consolidated=) (parent and section vary) | Cross-checks of cost and balance-sheet lines |

The tidy CSVs parsed from these pages are in `data/raw/screener/`.

## stockanalysis/ (StockAnalysis.com, S&P Global Market Intelligence data, INR millions)

| File | What it contains | Source | Used for |
|---|---|---|---|
| `UltraTech_Income_Statement_StockAnalysis.xlsx` | Annual and quarterly income statement | [financials](https://stockanalysis.com/quote/nse/ULTRACEMCO/financials/) | Second-source check |
| `UltraTech_Balance_Sheet_StockAnalysis.xlsx` | Annual and quarterly balance sheet | [balance sheet](https://stockanalysis.com/quote/nse/ULTRACEMCO/financials/balance-sheet/) | Second-source check |
| `UltraTech_Cash_Flow_Statement_StockAnalysis.xlsx` | Annual cash flow | [cash flow](https://stockanalysis.com/quote/nse/ULTRACEMCO/financials/cash-flow-statement/) | Second-source check |
| `UltraTech_Financials_Overview_StockAnalysis.xlsx` | Summary financials, annual and quarterly | [financials](https://stockanalysis.com/quote/nse/ULTRACEMCO/financials/) | Second-source check |
| `UltraTech_Ratios_StockAnalysis.xlsx` | Valuation and return ratios | [ratios](https://stockanalysis.com/quote/nse/ULTRACEMCO/financials/ratios/) | Context |
| `UltraTech_Statistics_Valuation_StockAnalysis.xlsx` | Key statistics (shares, valuation, margins) | [statistics](https://stockanalysis.com/quote/nse/ULTRACEMCO/statistics/) | Share count check |
| `UltraTech_Forecast_Analyst_Projections_StockAnalysis.xlsx` | Consensus revenue and EPS (FY2027 EPS average Rs 325.76, range 275.91-386.30), price targets | [forecast](https://stockanalysis.com/quote/nse/ULTRACEMCO/forecast/) | Comparison of the Base case with consensus |
| `raw/*.html` (10 pages) | The pages as downloaded: income (annual, quarterly), balance (annual, quarterly), cash flow, overview (annual, quarterly), ratios, statistics, forecast | Same pages | Audit trail; parsed tables in `data/raw/stockanalysis/` |

## yahoo_finance/

| File | What it contains | Source | Used for |
|---|---|---|---|
| `ULTRACEMCO_NS_daily.csv` | Daily prices (open, high, low, close, adjusted close, volume) | [Yahoo Finance ULTRACEMCO.NS](https://finance.yahoo.com/quote/ULTRACEMCO.NS/history/) via yfinance | Share price |
| `quote_30Oct2026.json` | Close of 30-Oct-2026: Rs 11,045 | Same | Cover sheet market data |
| `USDINR_INR=X_daily.csv` | USD/INR daily closes (95.15 on 30-Oct-2026) | [Yahoo Finance INR=X](https://finance.yahoo.com/quote/INR=X/history/) | Context for the US dollar loans and bonds |

## news_and_macro/ (local only: links below)

| Saved page (local only) | Fact used | Source | Used for |
|---|---|---|---|
| `ET_TBill_auction_28Oct2026.html` | 91-day T-bill cut-off yield 5.93% at the 28-Oct-2026 auction | [Economic Times](https://economictimes.indiatimes.com/markets/bonds/rbi-accepts-20-bps-higher-treasury-bill-cutoff-yields-than-last-auction/articleshow/135284706.cms) | Interest earned on cash and investments |
| `TheHindu_RBI_repo_hike_7Oct2026.html` | RBI raised the repo rate 25 bp to 5.50% on 7-Oct-2026 | [The Hindu](https://www.thehindu.com/business/Economy/rbi-hikes-repo-rate-by-25-basis-points-to-55/article71554369.ece) | Revolver rate (repo + 3.0%) |
| `Mint_RBI_repo_hike_7Oct2026.html` | Same decision (second source) | [Mint](https://www.livemint.com/market/stock-market-news/rbi-mpc-meeting-october-2026-repo-rate-hiked-by-25-bps-to-5-50-growth-inflation-forecast-other-key-takeaways-11791344804917.html) | Second source |
| `ETBFSI_Reuters_India_bonds_30Oct2026.html` | Benchmark 6.94% 2036 bond at 7.4139% on 30-Oct-2026 (Reuters) | [ETBFSI](https://bfsi.economictimes.indiatimes.com/articles/india-bonds-buckle-for-fourth-straight-month-on-oils-climb/135363689) | 10-year G-sec 7.41% (context for debt costs) |
| `TradingEconomics_India_10Y_yield.html` | India 10-year yield 7.40% on 30-Oct-2026 | [Trading Economics](https://tradingeconomics.com/india/government-bond-yield) | Second source for the G-sec yield |
| `ClearTax_section_115BAA.html` | 22% + 10% surcharge + 4% cess = 25.17% under s.115BAA | [ClearTax](https://cleartax.in/s/section-115-baa-tax-rate-domestic-companies) | Tax rate |
| `IncomeTaxIndia_domestic_company_rates.md` (published) | Link and note only: the site returned HTTP 403 | [Income Tax Department](https://www.incometaxindia.gov.in/domestic-company) | Official source for the tax rate |
| `TheHindu_StarCement_stake_27Dec2024.html` | UltraTech to buy 8.69% of Star Cement for up to Rs 851 crore (27-Dec-2024) | [The Hindu](https://www.thehindu.com/business/Industry/ultratech-to-acquire-minority-stake-in-star-cement-from-promoters-in-851-crore-deal/article69032907.ece) | Treated as an investment, not consolidated |
| `Moneycontrol_StarCement_stake_27Dec2024.html` | Same deal (second source): up to 3.7 crore shares at up to Rs 235 | [Moneycontrol](https://www.moneycontrol.com/news/business/markets/ultratech-cement-acquires-8-7-stake-in-star-cement-for-rs-851-crore-12898638.html) | Second source |

Size: 61 files and 14.5 MB on the author's PC (largest file 2.4 MB); the published copy leaves out the 8 news pages (0.9 MB).
