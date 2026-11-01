# source_data: original files behind every number

Two sets of files are kept here.

- **The author's Screener downloads of 15-Oct-2026** (`screener/exports/`): the four "Export to Excel" files the workbook's `Raw_Data` sheet was typed from. They are unchanged; only the file names were made consistent.
- **Copies saved on 1-Nov-2026** by `build/fetch_sources.py`: the same four Screener company pages as HTML (with the tables parsed to CSV), the Bajaj Auto press release, and page extracts of two Bajaj Auto annual reports.

Units: Screener and annual reports in ₹ crore. All figures are consolidated, for fiscal years ending 31 March.

**Not in the GitHub copy.** The saved news articles in `news_and_macro/*.html` are copyrighted, so they stay on the author's PC and are left out of the public repository. Each one is listed below with its link. Company documents and data exports are included.

## screener/exports/ (the workbook's inputs)

| File | What it contains | Source | Used for |
|---|---|---|---|
| `HEROMOTOCO_Screener_DataSheet_export_15Oct2026.xlsx` | Screener's standard export: Data Sheet with FY2017-FY2026 profit and loss, balance sheet, cash flow, 10 quarters, prices | [screener.in/company/HEROMOTOCO/consolidated](https://www.screener.in/company/HEROMOTOCO/consolidated/) | `Raw_Data` columns D-I (Hero FY2021-FY2026) |
| `BAJAJ-AUTO_Screener_DataSheet_export_15Oct2026.xlsx` | same layout | [screener.in/company/BAJAJ-AUTO/consolidated](https://www.screener.in/company/BAJAJ-AUTO/consolidated/) | `Raw_Data` columns J-O |
| `TVSMOTOR_Screener_DataSheet_export_15Oct2026.xlsx` | same layout | [screener.in/company/TVSMOTOR/consolidated](https://www.screener.in/company/TVSMOTOR/consolidated/) | `Raw_Data` columns P-U |
| `EICHERMOT_Screener_DataSheet_export_15Oct2026.xlsx` | same layout | [screener.in/company/EICHERMOT/consolidated](https://www.screener.in/company/EICHERMOT/consolidated/) | `Raw_Data` columns V-AA |

`build/check_workbook.py` confirms that all 504 inputs checked (21 lines x 6 years x 4 companies) equal these files. The exports' "Net profit" is profit attributable to owners; Screener's web page shows profit including minority interests.

## screener/ (the company pages saved on 1-Nov-2026)

| File | What it contains | Source | Used for |
|---|---|---|---|
| `raw/<SYMBOL>_consolidated.html` (4 files) | The company page as served, with annual profit and loss, balance sheet, cash flow and ratios | the four Screener links above | Second check of the inputs: 384 of 384 values agree to the whole crore |
| `<SYMBOL>_profit-loss.csv`, `_balance-sheet.csv`, `_cash-flow.csv`, `_ratios.csv` (16 files) | Tables parsed from those pages (₹ crore; ratios in %) | built by `build/fetch_sources.py` | The comparison above, and Screener's own ROCE % |
| `screener_pages_summary.json` | Table shapes and Screener company ids | built by the script | Audit trail |

## company_filings/ (Bajaj Auto)

Annual reports are saved as page extracts (the pages used); the full document is at the link.

| File | What it contains | Source | Used for |
|---|---|---|---|
| `BajajAuto_Annual_Report_FY2025-26_extract.pdf` | 19th Annual Report 2025-26, 13 of 364 pages: consolidated balance sheet and P&L (printed p.247-248), borrowings (p.300-301), financial-instrument tables with total borrowings of ₹21,980.59 crore (FY2026), ₹9,236.52 crore (FY2025) and ₹1,785.90 crore (FY2024) (p.318-322), and Note 46 on the KTM business combination (p.352-356): acquisition on 18-Nov-2025, ₹953.10 crore remeasurement gain, ₹645.71 crore currency reserve moved to profit | [bajajauto.com, Annual Report 2025-26](https://www.bajajauto.com/-/media/images/bajajauto/media-kit/press-release/new-annual-reports/fy2025-26/bajaj-auto-annual-report-2025-26.pdf) | `Raw_Data` rows 51-52 (one-off gains); the borrowings comparison in the Summary |
| `BajajAuto_Annual_Report_FY2024-25_extract.pdf` | 18th Annual Report 2024-25, 16 of 300 pages: Directors' Report results table (p.36-37), standalone and consolidated P&L (p.144-145, 232-233), tax notes (p.193-194, 267-268), auditors' key audit matter on KTM (p.222-223), consolidated cash flow with operating cash flow of -₹1,405.57 crore (p.236-237), Note 42 on the associate: ₹915.48 crore net loss = ₹314.55 crore share of loss + ₹600.93 crore impairment (p.290-291) | [investors.bajajauto.com, Annual Report 2025](https://investors.bajajauto.com/ar25/wp-content/uploads/2025/07/BAL_Annual_Report_2025.pdf) | Context for Bajaj's FY2025 ROE dip and the ₹211.26 crore exceptional deferred tax |
| `BajajAuto_press_release_KTM_control_21May2025.html` | "Bajaj Auto makes decisive move to take charge of rebuilding KTM" | [bajajauto.com press release](https://www.bajajauto.com/corporate/media-centre/press-releases/bajaj-auto-makes-decisive-move-to-take-charge-of-rebuilding-ktm) | KTM timeline |
| `annual_report_extracts.json` | The PDF page numbers kept in each extract and the phrases used to find them | built by `build/fetch_sources.py` | Audit trail |

The FY2023-24 (17th) annual report cited in `notes/bajaj_auto_ktm_research_report.md` was not downloaded: [BAL_Annual_Report_2024.pdf](https://investors.bajajauto.com/ar24/wp-content/uploads/2024/06/BAL_Annual_Report_2024.pdf).

## news_and_macro/ (local only, not in the GitHub copy)

| File | What it contains | Source | Used for |
|---|---|---|---|
| `ET_Bajaj_KTM_EUR566m_loan_18May2025.html` | Bajaj signs a €566 million loan before KTM's funding deadline | [economictimes.indiatimes.com](https://economictimes.indiatimes.com/industry/auto/auto-news/ktm-co-owner-bajaj-auto-signs-566m-loan-before-funding-deadline/articleshow/121245454.cms) | KTM funding timeline (research notes) |
| `Livemint_KTM_operating_profit_28Aug2026.html` | KTM's first operating profit under Bajaj | [livemint.com](https://www.livemint.com/news/ktm-bajaj-auto-bajaj-mobility-ktm-insolvency-motorcycle-sales-premium-motorcycles-11787886342479.html) | What to monitor (research notes) |

## Downloads that were blocked

| URL | Note |
|---|---|
| https://ackodrive.com/news/bajaj-auto-raises-5-399-crore-loan-for-ktm-buyout/ | ACKO Drive article on the KTM loan (cited in the research notes): HTTP 403 on 1-Nov-2026 |

`download_log.csv` lists every download with its URL, HTTP status, size, SHA-256 hash and a phrase check (the number or word that must appear in the file). Every saved file passed its check.

Folder size: 6.8 MB in 32 files plus this index; the published part is 6.3 MB in 30 files and the local-only pages are 0.5 MB in 2 files. Largest file: `company_filings/BajajAuto_Annual_Report_FY2024-25_extract.pdf` (3.0 MB).
