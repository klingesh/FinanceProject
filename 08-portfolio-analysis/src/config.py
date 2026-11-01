"""Project-wide constants: universe, dates, risk-free rate and folder paths."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

# ----------------------------------------------------------------------------- paths
PROJECT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
FIG_DIR = PROJECT_DIR / "figures"
OUT_DIR = PROJECT_DIR / "outputs"

# ----------------------------------------------------------------------------- universe
# Yahoo Finance ticker -> (short label used in tables and charts, company name, sector)
STOCKS: dict[str, tuple[str, str, str]] = {
    "RELIANCE.NS": ("RELIANCE", "Reliance Industries", "Energy / conglomerate"),
    "HDFCBANK.NS": ("HDFCBANK", "HDFC Bank", "Private bank"),
    "ICICIBANK.NS": ("ICICIBANK", "ICICI Bank", "Private bank"),
    "INFY.NS": ("INFY", "Infosys", "IT services"),
    "BHARTIARTL.NS": ("BHARTIARTL", "Bharti Airtel", "Telecom"),
    "ITC.NS": ("ITC", "ITC", "FMCG / tobacco"),
    "LT.NS": ("LT", "Larsen & Toubro", "Engineering & construction"),
    "SUNPHARMA.NS": ("SUNPHARMA", "Sun Pharmaceutical", "Pharma"),
    "MARUTI.NS": ("MARUTI", "Maruti Suzuki", "Automobiles"),
    "TITAN.NS": ("TITAN", "Titan Company", "Consumer discretionary"),
}
BENCHMARK_TICKER = "^NSEI"
BENCHMARK = "NIFTY50"  # short label
# Reference only (not part of the optimisation): an ETF whose adjusted price tracks the
# NIFTY 50 total-return index, used to size the dividend gap of the ^NSEI price index.
TR_PROXY_TICKER = "NIFTYBEES.NS"
TR_PROXY = "NIFTYBEES"

ALL_TICKERS = list(STOCKS) + [BENCHMARK_TICKER, TR_PROXY_TICKER]
LABELS: dict[str, str] = {t: v[0] for t, v in STOCKS.items()}
LABELS[BENCHMARK_TICKER] = BENCHMARK
LABELS[TR_PROXY_TICKER] = TR_PROXY
STOCK_LABELS = [v[0] for v in STOCKS.values()]
NAMES: dict[str, str] = {v[0]: v[1] for v in STOCKS.values()}
NAMES[BENCHMARK] = "NIFTY 50 (price index)"
NAMES[TR_PROXY] = "Nippon India ETF Nifty 50 BeES"
SECTORS: dict[str, str] = {v[0]: v[2] for v in STOCKS.values()}

# ----------------------------------------------------------------------------- dates
DOWNLOAD_START = "2021-10-01"
DOWNLOAD_END = "2026-10-31"          # exclusive in yfinance, so the last bar is 30-Oct-2026
ANALYSIS_START = pd.Timestamp("2021-11-01")
ANALYSIS_END = pd.Timestamp("2026-10-30")
# Out-of-sample split: estimate on Nov-2021..Oct-2024, hold Nov-2024..Oct-2026
IS_END = pd.Timestamp("2024-10-31")
OOS_START = pd.Timestamp("2024-11-01")

# ----------------------------------------------------------------------------- conventions
TRADING_DAYS = 252
WEEKS_PER_YEAR = 52
RF_ANNUAL = 0.0593  # 91-day T-bill cut-off yield, RBI auction of 28-Oct-2026
RF_DAILY = (1 + RF_ANNUAL) ** (1 / TRADING_DAYS) - 1
RF_WEEKLY = (1 + RF_ANNUAL) ** (1 / WEEKS_PER_YEAR) - 1
RF_ARITH = RF_DAILY * TRADING_DAYS  # rf on the same arithmetic x252 basis as the mean returns
WEIGHT_CAP = 0.20                   # per-stock cap for the constrained frontier
N_FRONTIER = 60                     # target returns on the efficient branch
N_FRONTIER_LOWER = 20               # extra points on the inefficient (lower) branch, for the plot
N_MONTE_CARLO = 20_000
SEED = 42
LARGE_DROP_THRESHOLD = -0.08        # one-day return that triggers a corporate-action review

SOURCE_NOTE = ("Source: Yahoo Finance via yfinance (daily adjusted close), 1-Nov-2021 to 30-Oct-2026; "
               "author's calculations")
