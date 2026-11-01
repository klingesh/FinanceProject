# source_data: original downloads behind every number

Files as downloaded (31-Oct-2026 to 1-Nov-2026), organised by source. Nothing here is edited except: the three annual reports are saved as page extracts (financial statements and notes only, to keep the folder small; full links below), and the `.xlsx` files are exports of the raw Screener / StockAnalysis tables made by `build/export_source_tables.py` (row 1 of each sheet gives site, URL, download date and units). Market data are as of the Friday 30-Oct-2026 close. Total size about 25 MB; largest file 6.0 MB.

**Not in the GitHub copy:** some files are copyrighted copies of third-party content: the news pages in `news_and_macro/` (`.html`), the Kotak Securities broker note, and the law-firm and consultancy commentary in `regulation/` (Cyril Amarchand Mangaldas, Khaitan & Co, KPMG, KS&K, Economic Times). These stay on the author's PC and are left out of the public repository; the tables below give the link to each one. Company filings, deal press releases, SEBI regulations and the market-data files are included.

The model reads `data/` (curated from these files) and `screener/CASTROLIND_profit-loss.csv` (cross-check). Units: Castrol India filings and Screener in Rs crore; StockAnalysis in INR millions; Yahoo Finance in Rs per share.

## company_filings/

| File | What it contains | Source | Downloaded | Used for |
|---|---|---|---|---|
| `Castrol_India_AR2025_financial_statements_extract.pdf` | Annual Report 2025, original PDF pages 82-108 of 115 (two printed pages per PDF page): balance sheet and profit and loss (printed pp. 160-161, extract p.1), cash flow (pp. 162-163, extract p.2), notes (extract pp. 3-27; royalty in note 21 on extract p.16 = PDF p.97; related parties extract pp. 22-23; ratios extract p.26 = PDF p.107) | Castrol India, [cil-annual-report-2025.pdf](https://www.castrol.com/content/dam/castrol/country-sites-new/en_in/india/home/documents/investors/cil-annual-report-2025.pdf) (19.3 MB full) | 31-Oct-2026 | CY2024-CY2025 history, royalty, lease and cash balances |
| `Castrol_India_AR2023_financial_statements_extract.pdf` | Annual Report 2023, PDF pages 152-193 of 216 (printed pp. 150-191): balance sheet p.150, profit and loss p.151, cash flow pp. 152-153, notes incl. royalty (printed p.179) | Castrol India, [castrol-india-limited-annual-report-2023.pdf](https://www.castrol.com/content/dam/castrol/country-sites-new/en_in/india/home/documents/investors/castrol-india-limited-annual-report-2023.pdf) (8.0 MB full) | 1-Nov-2026 | CY2022-CY2023 history |
| `Castrol_India_AR2022_financial_statements_extract.pdf` | Annual Report 2022, PDF pages 124-165 of 188 (printed pp. 122-163): balance sheet p.122, profit and loss p.123, cash flow pp. 124-125, notes incl. royalty (printed p.152) | Castrol India, [castrol_india_limited_annual_report_2022.pdf](https://www.castrol.com/content/dam/castrol/country-sites-new/en_in/india/home/documents/investors/castrol_india_limited_annual_report_2022.pdf) (9.2 MB full) | 1-Nov-2026 | CY2021 history |
| `Castrol_India_Q3CY2026_results_and_press_release_24Oct2026.pdf` | Board-meeting outcome: auditor's limited review, results for the quarter and nine months to 30-Sep-2026, press release | Castrol India, [outcome-of-bm-24-oct-2026.pdf](https://www.castrol.com/content/dam/castrol/country-sites-new/en_in/india/home/documents/investors/outcome-of-bm-24-oct-2026.pdf) | 1-Nov-2026 | 9M and Q3 CY2026, LTM, CY2026E base |
| `Castrol_India_H1CY2026_results_and_press_release_4Aug2026.pdf` | Board-meeting outcome: results to 30-Jun-2026 with balance sheet and H1 cash flow, interim dividend Rs 6.25 | Castrol India, [Outcome-of-BM-Signed.pdf](https://www.castrol.com/content/dam/castrol/country-sites-new/en_in/india/home/documents/investors/Outcome-of-BM-Signed.pdf) | 1-Nov-2026 | 30-Jun-2026 cash, working capital, leases, investment; cash-at-close bridge |
| `Castrol_India_Q3CY2026_earnings_call_transcript_26Oct2026.pdf` | Official transcript of the 26-Oct-2026 post-earnings call (filed 29-Oct-2026) | Castrol India, [clse-intimation-analyst-call-26-oct-2026-transcriptsigned.pdf](https://www.castrol.com/content/dam/castrol/country-sites-new/en_in/india/home/documents/investors/clse-intimation-analyst-call-26-oct-2026-transcriptsigned.pdf) | 1-Nov-2026 | Calendar-year reporting, 21%-24% EBITDA frame, volume ambition, capex, deal status |

## deal_documents/

| File | What it contains | Source | Downloaded | Used for |
|---|---|---|---|---|
| `bp_press_release_Castrol_sale_to_Stonepeak_24Dec2025.pdf` | bp: sale of 65% of Castrol to Stonepeak, EV US$10.1bn, about 8.6x LTM EBITDA, equity US$8.0bn, proceeds about US$6bn | bp, [PDF](http://bp.com/api/files/6cqieuqhq4no/master/4F4krNIzOL2e0opQdSGB1W/2766915e59b4094d9349ce9cac8e53ff/bp-agrees-to-sell-a-65-per-cent-shareholding-in-castrol-to-stonepeak-at-an-enterprise-value-of-10-billion.pdf) | 31-Oct-2026 | Real_Deal_Context sheet |
| `bp_press_release_page_24Dec2025.html` | Same release, web page | bp, [press release page](https://www.bp.com/press-and-publications/press-releases/bp-agrees-to-sell-a-65-per-cent-shareholding-in-castrol-to-stonepeak-at-an-enterprise-value-of-10-billion) (URL checked 1-Nov-2026: `bp.com/...` redirects here and the page loads) | 1-Nov-2026 | Link check |
| `CPP_Investments_release_Castrol_24Dec2025.pdf` | CPP Investments: US$1.05bn for a minority stake alongside Stonepeak | CPP Investments, [PDF](https://www.cppinvestments.com/wp-content/uploads/attachments/News-Release-CPP-Investments-to-Acquire-Minority-Stake-in-Castrol-EN.pdf) | 31-Oct-2026 | Real_Deal_Context |
| `Open_offer_public_announcement_Castrol_India_24Dec2025.pdf` | SEBI SAST public announcement by Motion JVCo (manager UBS Securities India): Rs 194.04 x 25,71,71,820 shares = Rs 4,990.16 crore; promoter 50,44,52,416 shares (51.00%); 98,91,22,384 fully diluted shares | Castrol India, [stock-exchange-intimation-public-announcement.pdf](https://www.castrol.com/content/dam/castrol/country-sites-new/en_in/india/home/documents/investors/stock-exchange-intimation-public-announcement.pdf); identical file (same MD5) on the [BSE filing mirror](https://bsmedia.business-standard.com/_media/bs/data/announcements/bse/24122025/ccedebac-a5e1-448a-aaf9-f4ec30d0f085.pdf) | 1-Nov-2026 | Shares, open-offer price floor, Real_Deal_Context |
| `Castrol_India_Reg30A_disclosure_of_SPA_24Dec2025.pdf` | Disclosure of the 23-Dec-2025 sale and purchase agreement between bp and Motion JVCo | Castrol India, [PDF](https://www.castrol.com/content/dam/castrol/country-sites-new/en_in/india/home/documents/investors/disclosure-under-regulation-30a-of-sebi-lodr.pdf) | 31-Oct-2026 | SPA date (start of the 10% a year price enhancement) |
| `Castrol_India_intimation_bp_strategic_review_26Feb2025.pdf` | Stock-exchange intimation of bp's strategic review of Castrol | Castrol India, [PDF](https://www.castrol.com/content/dam/castrol/country-sites-new/en_in/india/home/documents/about-castrol/SE-intimation-strategic-review-of-castrol-26Feb2025.pdf) | 1-Nov-2026 | Background |
| `Botswana_CCA_merger_decision_19_2026_Motion_JVCo_Castrol.pdf` | Competition authority decision describing the deal structure (Motion JVCo; bp to hold 35%) | Competition and Consumer Authority of Botswana, [PDF](https://cca.co.bw/index.php/sites/default/files/Merger-Decision-No-19-2026-Motion-JVCo-and-Castrol-Group-Holdings.pdf) | 31-Oct-2026 | Ownership after completion (65/35) |
| `Latham_Watkins_Stonepeak_Castrol_financing_Jul2026.html` | Financing: US$1.0bn notes + US$2.75bn term loans at holdco, US$1.3bn revolver of which US$0.3bn for the India tender offer | Latham & Watkins, [web page](https://www.lw.com/en/news/2026/07/latham-advises-on-financing-for-stonepeak-acquisition-of-castrol-from-bp) | 1-Nov-2026 | Real_Deal_Context |

## regulation/

| File | What it contains | Source | Downloaded | Used for |
|---|---|---|---|---|
| `SEBI_SAST_Regulations_2011_consolidated_Aug2026.pdf` | Takeover Regulations: Reg 3(1), 4, 5(1) (indirect acquisition), 7(1) (26% minimum), 8(12) (10% a year enhancement), 5A and 7(5) | SEBI, [PDF](https://www.sebi.gov.in/sebi_data/attachdocs/aug-2026/1785911192198.pdf) | 31-Oct-2026 | India execution notes; enhanced offer price |
| `SEBI_Delisting_Regulations_2021_consolidated_Aug2026.pdf` | Delisting Regulations: Reg 21(a) 90% threshold, Reg 22(4) counter-offer | SEBI, [PDF](https://www.sebi.gov.in/sebi_data/attachdocs/aug-2026/1786948319926.pdf) | 31-Oct-2026 | India execution notes |
| `Cyril_Amarchand_Mangaldas_delisting_amendments_1Jul2024.pdf` | Law-firm note on the 2024 delisting amendments (fixed-price route, counter-offer) | Cyril Amarchand Mangaldas, [PDF](https://www.cyrilshroff.com/wp-content/uploads/2024/07/Client-Update-Delisting-Regulations-amendment_0107.pdf) | 31-Oct-2026 | India execution notes |
| `Khaitan_ERGO_RBI_draft_acquisition_finance_directions_6Nov2025.pdf` | Law-firm note on RBI's draft acquisition-finance directions | Khaitan & Co, [PDF](https://www.khaitanco.com/sites/default/files/2025-11/ERGO%20-%20RBI%20-%20Draft%20Directions%20-%206%20November%202025.pdf) | 31-Oct-2026 | Background to the 2026 framework |
| `KPMG_India_RBI_acquisition_finance_Mar2026.html` | Banks may fund up to 75% of acquisition value; Rs 500 crore net worth and 3-year profit record; ECB still barred for buying securities | KPMG India, [blog](https://kpmg.com/in/en/blogs/2026/03/rbis-power-play-to-fire-up-m-as.html) | 1-Nov-2026 | Acquisition-debt note |
| `KSandK_sponsor_side_leveraged_finance_in_India.html` | Sponsor-side LBO finance in India: RBI framework announced 13-Feb-2026, eligibility (incl. 3:1 debt-to-equity), ECB end-use limits, Companies Act s.67, private credit and NCDs | King Stubb & Kasiva, [article, 12-Mar-2026](https://ksandk.com/banking/sponsor-side-leveraged-finance-in-india/) | 1-Nov-2026 | Acquisition-debt and financial-assistance notes |
| `ET_RBI_opens_bank_lending_for_acquisitions_2026.html` | Commentary: 75% cap, debt-equity ceiling; sponsor-backed deals still need private credit | The Economic Times, [ET Commentary, 1-Jul-2026](https://economictimes.indiatimes.com/opinion/et-commentary/rbi-opens-bank-lending-for-acquisitions-under-new-framework/articleshow/132100398.cms) | 1-Nov-2026 | Acquisition-debt note |

## news_and_macro/

| File | What it contains | Source | Downloaded | Used for |
|---|---|---|---|---|
| `ETBFSI_India_10y_bond_close_30Oct2026.html` | Benchmark 6.94% 2036 bond closed at 7.4139% on 30-Oct-2026 (Reuters) | ETBFSI, [article](https://bfsi.economictimes.indiatimes.com/articles/india-bonds-buckle-for-fourth-straight-month-on-oils-climb/135363689) | 1-Nov-2026 | 10-year G-sec 7.41% (debt pricing) |
| `TradingEconomics_India_10y_government_bond_yield.html` | India 10-year yield 7.40% on 30-Oct-2026 | Trading Economics, [page](https://tradingeconomics.com/india/government-bond-yield) | 1-Nov-2026 | Second source for the G-sec yield |
| `ET_10y_gsec_7.39pct_Oct2026.html` | 10-year yield at 7.39% earlier in the week | The Economic Times, [article](https://m.economictimes.com/markets/bonds/g-sec-10-year-yields-come-down-5-bps-to-7-39-on-fed-signals/amp_articleshow/135335834.cms) | 1-Nov-2026 | Context for the G-sec yield |
| `TheHindu_RBI_repo_rate_5.50pct_7Oct2026.html` | RBI raised the repo rate 25 bp to 5.50% on 7-Oct-2026 | The Hindu, [article](https://www.thehindu.com/business/Economy/rbi-hikes-repo-rate-by-25-basis-points-to-55/article71554369.ece) | 1-Nov-2026 | Repo rate (reference) |
| `Mint_RBI_MPC_repo_rate_5.50pct_7Oct2026.html` | Same decision | Mint, [article](https://www.livemint.com/market/stock-market-news/rbi-mpc-meeting-october-2026-repo-rate-hiked-by-25-bps-to-5-50-growth-inflation-forecast-other-key-takeaways-11791344804917.html) | 1-Nov-2026 | Repo rate (second source) |
| `ET_91day_tbill_cutoff_28Oct2026.html` | 91-day T-bill cut-off yield 5.93% at the 28-Oct-2026 auction | The Economic Times, [article](https://economictimes.indiatimes.com/markets/bonds/rbi-accepts-20-bps-higher-treasury-bill-cutoff-yields-than-last-auction/articleshow/135284706.cms) | 1-Nov-2026 | Interest earned on cash |
| `AJBell_AllianceNews_bp_3Q2026_results_30Oct2026.html` | bp 3Q 2026 results: Castrol closing "imminent", about US$6bn of proceeds expected in 2026 | Alliance News via AJ Bell, [article](https://www.ajbell.co.uk/news/articles/bp-hits-debt-target-year-ahead-schedule-profit-beats-forecast) | 1-Nov-2026 | Deal status at 30-Oct-2026 |
| `Kotak_Securities_Castrol_India_Q2CY26_result_update_6Aug2026.pdf` | Broker result update: long-term cautious on volumes given the EV transition; stock range-bound near the Rs 194 open offer | Kotak Securities, [PDF](https://www.kotakneo.com/uploads/Castrol_One_Pager_Result_Update_Q2_CY_26_6_Aug2026_0c6b28aa63.pdf) | 31-Oct-2026 | EV-transition risk |
| `Investing_Castrol_India_Q3CY2026_call_summary_26Oct2026.md` | Link and note only: the site returned HTTP 403; replaced by the official transcript | Investing.com, [article](https://in.investing.com/news/stock-market-news/earnings-call-transcript-castrol-india-q3-2026-profit-falls-as-margins-narrow-93CH-5653381) | tried 1-Nov-2026 | Secondary source for call facts |

## screener/ (Screener.in, standalone, Rs crore)

| File | What it contains | Source | Downloaded | Used for |
|---|---|---|---|---|
| `Castrol_India_Screener_Standalone.xlsx` | Export of the five tables below plus all schedules, one sheet each, source line in row 1 | Built from the files below | 1-Nov-2026 | Easy viewing in Excel |
| `CASTROLIND_standalone.html` | Raw company page (standalone figures; prices to the 30-Oct-2026 close) | [Screener.in](https://www.screener.in/company/CASTROLIND/) | 31-Oct-2026 | Audit trail |
| `CASTROLIND_profit-loss.csv`, `_quarters.csv`, `_balance-sheet.csv`, `_cash-flow.csv`, `_ratios.csv` | The page's annual P&L (CY2014-CY2025 + TTM), quarterly results, balance sheet, cash flow and ratios | Same page | 31-Oct-2026 | Revenue and EBITDA cross-checks (Historical sheet, checks 16-17) |
| `CASTROLIND_schedule_*.json` (16 files) | Line-item breakdowns (expenses, other income, borrowings, other assets and liabilities, cash-flow detail) from the schedules API | [Screener schedules API](https://www.screener.in/api/company/589/schedules/?parent=Expenses&section=profit-loss) (parent and section vary) | 31-Oct-2026 | Cross-checks of cost and balance-sheet lines |
| `screener_summary.json` | Top ratios (market cap, price, 52-week range), company id, fetch time | Same page | 31-Oct-2026 | Price cross-check (Rs 188) |

## stockanalysis/ (StockAnalysis.com, S&P Global data, INR millions)

| File | What it contains | Source | Downloaded | Used for |
|---|---|---|---|---|
| `Castrol_India_Income_Statement_Annual_StockAnalysis.xlsx` + `income_annual.html` + `income_annual_table0-6.csv` | Annual income statement summary (CY2021-CY2025 and TTM Sep-2026), revenue by region | [financials](https://stockanalysis.com/quote/nse/CASTROLIND/financials/) | 31-Oct-2026 | Second-source check of revenue and profit |
| `Castrol_India_Income_Statement_Quarterly_StockAnalysis.xlsx` + `income_quarterly.html` + `income_quarterly_table0-4.csv` | Quarterly income statement to Q3 2026 | [financials, quarterly](https://stockanalysis.com/quote/nse/CASTROLIND/financials/?p=quarterly) | 31-Oct-2026 | Quarterly check |
| `Castrol_India_Balance_Sheet_Annual_StockAnalysis.xlsx` + `balance_annual.html` + `balance_annual_table0-3.csv` | Annual balance sheet | [balance sheet](https://stockanalysis.com/quote/nse/CASTROLIND/financials/balance-sheet/) | 31-Oct-2026 | Cash and debt check |
| `Castrol_India_Balance_Sheet_Quarterly_StockAnalysis.xlsx` + `balance_quarterly.html` + `balance_quarterly_table0-3.csv` | Quarterly balance sheet | [balance sheet, quarterly](https://stockanalysis.com/quote/nse/CASTROLIND/financials/balance-sheet/?p=quarterly) | 31-Oct-2026 | Cash and debt check |
| `Castrol_India_Cash_Flow_Statement_Annual_StockAnalysis.xlsx` + `cashflow_annual.html` + `cashflow_annual_table0-5.csv` | Annual cash flow | [cash flow](https://stockanalysis.com/quote/nse/CASTROLIND/financials/cash-flow-statement/) | 31-Oct-2026 | CFO and capex check |
| `Castrol_India_Ratios_Annual_StockAnalysis.xlsx` + `ratios_annual.html` + `ratios_annual_table0-4.csv` | Valuation and return ratios | [ratios](https://stockanalysis.com/quote/nse/CASTROLIND/financials/ratios/) | 31-Oct-2026 | Market multiple context |
| `Castrol_India_Statistics_StockAnalysis.xlsx` + `statistics.html` + `statistics_table0-18.csv` | Key statistics (shares, valuation, margins) | [statistics](https://stockanalysis.com/quote/nse/CASTROLIND/statistics/) | 31-Oct-2026 | Shares and valuation check |
| `Castrol_India_Forecast_StockAnalysis.xlsx` + `forecast.html` + `forecast_table0-6.csv` | Analyst price targets and ratings | [forecast](https://stockanalysis.com/quote/nse/CASTROLIND/forecast/) | 31-Oct-2026 | Context only |
| `fetch_market_data.log` | Log of the download run (status, table shapes, Yahoo summary) | `build/fetch_market_data.py` | 31-Oct-2026 | Audit trail |

## yahoo_finance/

| File | What it contains | Source | Downloaded | Used for |
|---|---|---|---|---|
| `CASTROLIND_NS_daily.csv` | Daily open, high, low, close, adjusted close, volume and dividends | Yahoo Finance via yfinance, [CASTROLIND.NS](https://finance.yahoo.com/quote/CASTROLIND.NS/history/) | 31-Oct-2026 | 52-week high Rs 203.40, 60-day VWAP Rs 193.14 |
| `quote_30Oct2026.json` | Close on 30-Oct-2026 (Rs 188.00) and 52-week range | Same | 31-Oct-2026 | Share price input |
| `USDINR_daily.csv` | USD/INR daily closes | Yahoo Finance via yfinance, [INR=X](https://finance.yahoo.com/quote/INR=X/history/) | 31-Oct-2026 | 95.1524 (30-Oct-2026), 89.6039 (23-Dec-2025) |
| `deal_dates_fx_prices.json` | FX and CASTROLIND closes around the 23/24-Dec-2025 announcement | Same | 31-Oct-2026 | Real_Deal_Context |

## Not saved here (links only)

| Document | Why not saved | Link |
|---|---|---|
| Full annual reports 2022, 2023, 2025 | 9.2 MB, 8.0 MB and 19.3 MB; only the financial-statement pages are kept | See the company_filings table |
| Q3 CY2026 results statement on its own | Same pages are inside the 24-Oct-2026 board-meeting file | [financial-result-third-quarter.pdf](https://www.castrol.com/content/dam/castrol/country-sites-new/en_in/india/home/documents/investors/financial-result-third-quarter.pdf) |
| Investor presentation, August 2026 (latest; none was published for Q3 CY2026 by 30-Oct-2026) | 4.9 MB and no number in the model comes from it | [cil-2q26-investor-presentation-21-aug.pdf](https://www.castrol.com/content/dam/castrol/country-sites-new/en_in/india/home/documents/investors/cil-2q26-investor-presentation-21-aug.pdf) |
| Castrol India's stock-exchange copy of the bp press release | Duplicate of the bp PDF with a cover letter | [press-release-from-bp-plc.pdf](https://www.castrol.com/content/dam/castrol/country-sites-new/en_in/india/home/documents/investors/press-release-from-bp-plc.pdf) |
