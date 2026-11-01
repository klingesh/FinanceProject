# source_data: original files behind every input

Two sets of files are kept here.

- **The author's downloads of 23-Oct-2026**, the files the model was built from: five StockAnalysis.com Excel exports (`stockanalysis/exports/`) and four TCS documents (`company_filings/`). They are unchanged; only the PDF file names were made descriptive.
- **Copies saved on 1-Nov-2026** by `build/fetch_sources.py`: the same StockAnalysis pages as HTML, Yahoo Finance prices, and the macro and news pages cited in the model.

Units: StockAnalysis in ₹ million (the model divides by 10 to get ₹ crore); TCS documents in ₹ crore or ₹ million as labelled; Yahoo Finance in ₹ per share.

**Not in the GitHub copy.** The saved news and macro pages in `news_and_macro/*.html` are copyrighted third-party pages, so they stay on the author's PC and are left out of the public repository. Each one is listed below with its full link and the fact taken from it. Company documents, data exports and exchange prices are included.

## stockanalysis/exports/ (the model's inputs; S&P Global Market Intelligence data via StockAnalysis.com)

| File | What it contains | Source | Used for |
|---|---|---|---|
| `TCS_Income_Statement_StockAnalysis.xlsx` | Annual income statement FY2022-FY2026 and TTM to Sep-2026, plus additional metrics (D&A for EBITDA, EBITDA, margins) | [stockanalysis.com/quote/nse/TCS/financials](https://stockanalysis.com/quote/nse/TCS/financials/) | `Historical` rows 5-9 and 16 (revenue, EBIT, pre-tax income, tax, D&A excluding leases, interest) |
| `TCS_Cash_Flow_Statement_StockAnalysis.xlsx` | Annual cash flow statement FY2022-FY2026 and TTM to Jun-2026 | [.../financials/cash-flow-statement](https://stockanalysis.com/quote/nse/TCS/financials/cash-flow-statement/) | `Historical` rows 10-15 (D&A, capex, intangibles, working capital, acquisitions, operating cash flow) |
| `TCS_Balance_Sheet_StockAnalysis.xlsx` | Annual balance sheet FY2022-FY2026 and the 30-Sep-2026 quarter | [.../financials/balance-sheet](https://stockanalysis.com/quote/nse/TCS/financials/balance-sheet/) | `Historical` rows 17-18 (leases, cash); `Assumptions` cash ₹51,024 crore and lease debt ₹11,808 crore at 30-Sep-2026 |
| `TCS_Statistics_Valuation_StockAnalysis.xlsx` | Valuation, share and risk statistics (observed 22-Oct-2026): beta, shares, EV/EBITDA, price | [.../statistics](https://stockanalysis.com/quote/nse/TCS/statistics/) | Beta 0.18, 361.8 crore shares. The model's price (₹2,459.10) and EV/EBITDA (11.4x) were read from the same page on 19-Oct-2026; this export was taken later and shows ₹2,529 and 11.72x |
| `TCS_Forecast_Analyst_Projections_StockAnalysis.xlsx` | Consensus revenue and EPS forecasts, price targets, ratings (23-Oct-2026) | [.../forecast](https://stockanalysis.com/quote/nse/TCS/forecast/) | FY2027 growth 9.0% (range 7.1-11.1%); average target ₹2,390.26 |

`build/check_model.py` confirms that all 70 Historical inputs (14 lines x 5 years) equal these exports divided by 10, within ₹0.5 crore.

## stockanalysis/raw/ (the same pages as HTML, 1-Nov-2026)

| File | Source | Note |
|---|---|---|
| `TCS_income_statement_annual.html` | [stockanalysis.com/quote/nse/TCS/financials](https://stockanalysis.com/quote/nse/TCS/financials/) | Contains FY2026 revenue 2,670,210 (₹ million) |
| `TCS_balance_sheet_annual.html` | [.../financials/balance-sheet](https://stockanalysis.com/quote/nse/TCS/financials/balance-sheet/) | |
| `TCS_cash_flow_statement_annual.html` | [.../financials/cash-flow-statement](https://stockanalysis.com/quote/nse/TCS/financials/cash-flow-statement/) | Contains FY2026 capex -42,240 (₹ million) |
| `TCS_statistics.html` | [.../statistics](https://stockanalysis.com/quote/nse/TCS/statistics/) | Prices as of 1-Nov-2026 |
| `TCS_forecast.html` | [.../forecast](https://stockanalysis.com/quote/nse/TCS/forecast/) | |

## company_filings/ (TCS documents, downloaded by the author on 23-Oct-2026)

| File | What it contains | Source | Used for |
|---|---|---|---|
| `TCS_Q2FY27_Fact_Sheet_8Oct2026.pdf` | Q2 FY2027 fact sheet (24 pages): revenue ₹731,880 million, operating margin 24.0%, net margin 19.0%, cash from operations 102.2% of net profit, order book US$9.6 billion | [tcs.com, Q2 2026-27 Fact Sheet](https://www.tcs.com/content/dam/tcs/investor-relations/financial-statements/2026-27/q2/Presentations/Q2%202026-27%20Fact%20Sheet.pdf) | FY2027 growth and margin assumptions |
| `TCS_Q1FY27_Press_Release_INR_9Jul2026.pdf` | Q1 FY2027 press release (11 pages): revenue ₹72,275 crore, +13.9% year on year | [tcs.com, Q1 Press Release - INR](https://www.tcs.com/content/dam/tcs/investor-relations/financial-statements/2026-27/q1/IND%20AS/Press%20Release%20-%20INR.pdf) | H1 FY2027 revenue ₹1,45,463 crore = 72,275 + 73,188 |
| `TCS_Q1FY27_Earnings_Call_Transcript_9Jul2026.pdf` | Q1 FY2027 earnings-call transcript (24 pages) | [tcs.com, transcript](https://www.tcs.com/content/dam/tcs/investor-relations/financial-statements/2026-27/q1/Management%20Commentary/Transcript%20of%20the%20Q1%202026-27%20Earnings%20Conference%20Call%20held%20on%20Jul%209,%202026.pdf) | Background on demand, margins and AI deals |
| `TCS_Q2FY27_Integrated_Filing_IndAS_Consolidated.pdf` | Q2 FY2027 consolidated results in the stock-exchange "Integrated Filing" (XBRL) format (16 pages), saved from the exchange viewer as PDF; board meeting 8-Oct-2026 | Filed by TCS with BSE (532540) and NSE (TCS); the exact page link was not recorded | Cross-check of the quarter's results |

tcs.com refused automated downloads on 1-Nov-2026 (HTTP 403), so the copies could not be compared byte for byte with the links. The links for the fact sheet and the press release are the ones in the PDF report's source table; the transcript link was found by web search and its title matches the PDF.

## yahoo_finance/

| File | What it contains | Source | Used for |
|---|---|---|---|
| `TCS_NS_daily_2026-09-01_to_2026-10-30.csv` | Daily open, high, low, close, adjusted close and volume for TCS.NS | Yahoo Finance via yfinance, 1-Nov-2026 | Confirms the model's price: on 19-Oct-2026 TCS traded between ₹2,432.10 and ₹2,497.00 and closed at ₹2,460.90. The 30-Oct-2026 close was ₹2,502.60 |

## news_and_macro/ (local only, not in the GitHub copy)

| File | What it contains | Source | Used for |
|---|---|---|---|
| `TradingEconomics_India_10Y_yield_news_28Sep2026.html` | India 10-year bond yield about 7.17% on 28-Sep-2026 | [tradingeconomics.com](https://tradingeconomics.com/india/government-bond-yield/news/587153) | Risk-free rate 7.15% |
| `Damodaran_country_risk_premiums_Jan2026.html` | Country risk premiums, January 2026: India total ERP 7.08%, country risk premium 2.85% | [pages.stern.nyu.edu/~adamodar](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ctryprem.html) | Reference for the 6.0% ERP |
| `FreePressJournal_TCS_Q2FY27_8Oct2026.html` | Q2 FY2027 results: revenue ₹73,188 crore, net profit ₹13,884 crore, AI revenue above US$3.1 billion | [freepressjournal.in](https://www.freepressjournal.in/business/tcs-net-profit-up-025-to-13884-crore-in-q2-fy27-revenue-rises-to-73188-crore) | Narrative only |
| `BusinessToday_TCS_Q2FY27_8Oct2026.html` | Q2 FY2027 results, ₹12 dividend | [businesstoday.in](https://www.businesstoday.in/markets/stocks/story/tcs-q2-fy27-results-net-profit-rises-15-to-rs-13934-crore-declares-rs-12-dividend-560435-2026-10-08) | Narrative only (dividend; the price is ex-dividend) |
| `FreePressJournal_TCS_Q1FY27_9Jul2026.html` | Q1 FY2027 results: revenue growth and the legal-settlement charge | [freepressjournal.in](https://www.freepressjournal.in/business/tcs-reports-14-revenue-growth-in-q1-fy27-net-profit-rises-47-to-13420-crore-despite-legal-settlement-charge) | Background for the FY2027 growth assumption |
| `AngelOne_TCS_Q2FY27_H1_total.html` | H1 FY2027 totals | [angelone.in](https://www.angelone.in/news/stocks/tcs-share-price-in-focus-after-q2-fy27-earnings-results-total-income-up-11-8-yoy) | H1 revenue cross-check |
| `Upstox_TCS_Q2FY27_TCV_8Oct2026.html` | Q2 FY2027 deal wins (TCV US$9.6 billion) and AI revenue | [upstox.com](https://upstox.com/news/market-news/earnings/tcs-q2-results-net-profit-rises-15-to-13-884-crore-revenue-jumps-11-yo-y-tcv-rises-to-9-6-billion/article-201534/) | Narrative only |

## Downloads that were blocked

| URL | Note |
|---|---|
| https://www.tcs.com/investor-relations/financial-statements | TCS investor-relations page: HTTP 403 to automated requests on 1-Nov-2026 |
| https://bvresources.com/articles/bvwire/damodaran-posts-his-first-data-update-for-2026 | BVWire note on Damodaran's January 2026 update (mature-market ERP 4.23%): HTTP 403 |

`download_log.csv` lists every download with its URL, HTTP status, size, SHA-256 hash and the phrase checked.

Folder size: 5.0 MB in 23 files plus this index; the published part is 3.2 MB in 16 files and the local-only pages are 1.8 MB in 7 files. Largest file: `company_filings/TCS_Q2FY27_Integrated_Filing_IndAS_Consolidated.pdf` (0.58 MB).
