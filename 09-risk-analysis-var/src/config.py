"""Project settings: paths, portfolio definition and model parameters.

Every script and the notebook read their settings from here, so a change made in
this file (for example a different weight or seed) flows through the whole project.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
FIGURES = ROOT / "figures"
OUTPUTS = ROOT / "outputs"
PRICES_FILE = DATA / "prices_adjclose.csv"
METADATA_FILE = DATA / "metadata.json"
NSE_FILE = RAW / "nse_bhavcopy_etf_closes.csv"

# ---------------------------------------------------------------- download settings
YF_START = "2021-10-01"
YF_END_EXCLUSIVE = "2026-10-31"  # yfinance treats `end` as exclusive -> last row 30-Oct-2026
CALENDAR_TICKER = "^NSEI"  # NIFTY 50 index rows define NSE trading days

# ---------------------------------------------------------------- portfolio
PORTFOLIO_VALUE = 10_000_000  # Rs 1 crore = Rs 1,00,00,000
VALUATION_DATE = "2026-10-30"
WINDOW_START = "2021-11-01"  # first daily return in the analysis window
WINDOW_END = "2026-10-30"

# ticker -> (label, fund name, asset class, target weight)
HOLDINGS: dict[str, tuple[str, str, str, float]] = {
    "NIFTYBEES.NS": ("NIFTYBEES", "Nippon India ETF Nifty 50 BeES", "Indian large-cap equity", 0.30),
    "JUNIORBEES.NS": ("JUNIORBEES", "Nippon India ETF Nifty Next 50 Junior BeES", "Indian large/mid-cap equity", 0.10),
    "BANKBEES.NS": ("BANKBEES", "Nippon India ETF Nifty Bank BeES", "Indian bank equity", 0.10),
    "MON100.NS": ("MON100", "Motilal Oswal Nasdaq 100 ETF", "US equity (INR, unhedged)", 0.10),
    "GOLDBEES.NS": ("GOLDBEES", "Nippon India ETF Gold BeES", "Gold", 0.15),
    "SETF10GILT.NS": ("SETF10GILT", "SBI Nifty 10 yr Benchmark G-Sec ETF", "Indian government bond (10-year)", 0.25),
}
TICKERS = list(HOLDINGS)
LABELS = [v[0] for v in HOLDINGS.values()]
WEIGHTS = [v[3] for v in HOLDINGS.values()]
EQUITY_TICKERS = ["NIFTYBEES.NS", "JUNIORBEES.NS", "BANKBEES.NS", "MON100.NS"]
# jump thresholds for the split / bad-print screen (absolute 1-day return)
JUMP_THRESHOLD = {t: (0.08 if t in EQUITY_TICKERS else 0.03) for t in TICKERS}

# Bond ETF candidates screened for the 25% bond sleeve: ticker -> (what it holds, requested?)
# The first five were requested; the last four are extra tickers tested for completeness
# (their fund names are taken from Yahoo Finance at download time, see metadata.json).
BOND_CANDIDATES: dict[str, tuple[str, bool]] = {
    "LTGILTBEES.NS": ("G-Secs, Nifty 8-13 yr G-Sec index", True),
    "SETF10GILT.NS": ("G-Secs, Nifty 10 yr Benchmark G-Sec index", True),
    "GILT5YBEES.NS": ("G-Secs, Nifty 5 yr Benchmark G-Sec index", True),
    "EBBETF0433.NS": ("AAA PSU bonds, target maturity Apr-2033", True),
    "EBBETF0430.NS": ("AAA PSU bonds, target maturity Apr-2030", True),
    "EBBETF0431.NS": ("AAA PSU bonds, target maturity Apr-2031", False),
    "LICNETFGSC.NS": ("G-Secs (long term)", False),
    "GSEC10IETF.NS": ("G-Secs, 10-year benchmark", False),
    "GSEC10ABSL.NS": ("G-Secs, 10-year", False),
}

# ---------------------------------------------------------------- model settings
CONFIDENCE_LEVELS = (0.95, 0.99)
EWMA_LAMBDA = 0.94  # RiskMetrics daily decay factor
RECENT_WINDOW = 250  # "last 250 days" historical simulation and backtest estimation window
N_SIMULATIONS = 100_000
SEED = 42
HORIZON_DAYS = 10
TRADING_DAYS_PER_YEAR = 250

# hypothetical stress shocks (simple returns applied to today's positions)
NASDAQ_SHOCK = -0.15
INR_APPRECIATION = 0.03  # USD/INR falls 3%, which lowers the rupee value of MON100
