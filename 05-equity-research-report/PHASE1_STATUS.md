# How phase 1 and phase 2 fit

The report was built in two phases because its valuation comes from Project 3 (comps and DCF on Asian Paints), which was being finished at the same time.

| Phase | When | What it produced |
|---|---|---|
| 1 | 1-Nov-2026, before Project 3 was final | Ratio workbook (70 of 70 checks PASS), research facts, Q2 FY27 results, risks and ESG, and a 9-page draft report in which every Project 3 value was a yellow `{{P3:key}}` tag held in one dict (`P3` in `build/build_report.py`) |
| 2 | After Project 3's `outputs/READY.txt` (1-Nov-2026 16:15, 22 of 22 checks PASS) | `load_p3()` fills the `P3` dict from Project 3's output files, `build/relative_value.py` adds the premium-adjusted P/E, `valuation()` blends the three values with weights fixed before the result, and the unchanged rating rule gives SELL (target ₹1,707, -26.4%). Final report: `report/AsianPaints_Initiation_Report.pdf`, 9 pages; the draft files were deleted |

## Which report sections use which phase

| Report section | Phase 1 inputs | Phase 2 inputs |
|---|---|---|
| Page 1 summary | Price, market cap, ratios, Q2 results, consensus | Rating, target, upside, FY27E-FY28E forecasts, FY28E consensus EPS |
| 1. Investment thesis | Three pillars | "What the price already assumes, and our rating" |
| 2-4. Company, financial analysis, recent results | All | None |
| 5. Forecasts | FY26A column, FY27E consensus | FY27E-FY29E forecasts, free cash flow, FY28E consensus, comparison with consensus |
| 6. Valuation | Analyst targets, 52-week range | DCF, comps, premium-adjusted P/E, target, sensitivity, football field |
| 7-8. Risks, ESG | All | The risks paragraph refers to the rating |

## If Project 3 changes
Re-run `python build/build_report.py --p3-dir <Project 3 folder>`. The script refreshes `data/p3/`, re-checks the copies against Project 3's workbook and rebuilds everything. The narrative was written for a SELL (`THESIS_WRITTEN_FOR` in `build_report.py`): if new inputs give a different rating, the PDF check fails until the text is revised. Without the Project 3 folder the script uses the copies in `data/p3/`.
