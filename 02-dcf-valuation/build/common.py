"""Shared paths for the Project 2 scripts. The scripts only READ the author's workbook; they never write to it."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "TCS_DCF_Model.xlsx"
REPORT_PDF = ROOT / "TCS_DCF_Report.pdf"
OUTPUTS = ROOT / "outputs"
FIGURES = ROOT / "figures"
SOURCE = ROOT / "source_data"
SA = SOURCE / "stockanalysis" / "exports"
FILINGS = SOURCE / "company_filings"

HIST_COLS = {2022: "B", 2023: "C", 2024: "D", 2025: "E", 2026: "F"}  # Historical sheet
DCF_COLS = {2026: "B", 2027: "C", 2028: "D", 2029: "E", 2030: "F", 2031: "G"}  # DCF sheet (FY2026A, FY2027E-31E)
