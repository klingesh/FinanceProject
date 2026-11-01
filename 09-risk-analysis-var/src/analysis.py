"""Analysis steps shared by run_all.py and var_analysis.ipynb.

Each step returns plain pandas / numpy objects, so the notebook can show intermediate results
and run_all.py can write them to outputs/ and figures/ with identical numbers.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from . import backtest as bt
from . import config as cfg
from . import data_prep as dp
from . import stress as st
from . import var_models as vm

V = cfg.PORTFOLIO_VALUE
ALPHAS = cfg.CONFIDENCE_LEVELS
CONVERGENCE_SIZES = [100, 200, 500, 1_000, 2_000, 5_000, 10_000, 20_000, 50_000, 100_000]
CONVERGENCE_REPS = 200

M_HS = "Historical (full window)"
M_HS250 = "Historical (last 250 days)"
M_NS = "Normal, sample covariance"
M_NE = "Normal, EWMA covariance"
M_CF = "Cornish-Fisher (modified)"
M_MCN = "Monte Carlo normal"
M_MCT = "Monte Carlo Student-t"


def inr(x: float) -> str:
    """Rupee amount with Indian digit grouping, rounded to the rupee: 1234567 -> '12,34,567'."""
    s = f"{abs(int(round(x)))}"
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return ("-" if x < 0 and round(x) != 0 else "") + s


@dataclass
class Inputs:
    prices: pd.DataFrame   # clean adjusted closes (all dates, columns = tickers)
    returns: pd.DataFrame  # simple daily returns inside the analysis window
    w: np.ndarray          # target weights
    port: pd.Series        # constant-weight portfolio simple returns
    labels: list[str]      # short ETF names
    holdings: pd.DataFrame # positions at the 30-Oct-2026 close


def load_inputs() -> Inputs:
    """Clean prices, window returns, weights and portfolio returns."""
    prices = dp.load_prices()
    returns = dp.window_returns(prices)
    w = dp.weights()
    port = dp.portfolio_returns(returns, w)
    labels = [cfg.HOLDINGS[t][0] for t in returns.columns]
    return Inputs(prices, returns, w, port, labels, dp.holdings_table(prices, w))


def _row(method: str, window: str, horizon: int, alpha: float, var: float, es: float, n: int,
         scaling: str, notes: str = "") -> dict:
    """One VaR/ES result at full precision (rounding happens only in `rounded_summary`)."""
    return {"method": method, "window": window, "horizon_days": horizon, "scaling": scaling,
            "confidence": alpha, "var_inr": var * V, "var_pct": 100 * var,
            "es_inr": es * V, "es_pct": 100 * es, "observations": n, "notes": notes}


def rounded_summary(summary: pd.DataFrame) -> pd.DataFrame:
    """VaR/ES table as written to outputs/var_summary.csv: rupees to Rs 1, percentages to 4 decimals."""
    return summary.round({"var_inr": 0, "es_inr": 0, "var_pct": 4, "es_pct": 4})


def pick(summary: pd.DataFrame, method: str, alpha: float, horizon: int = 1, scaling: str = "direct",
         col: str = "var_inr") -> float:
    """One value from the VaR/ES summary table."""
    s = summary[(summary["method"] == method) & (summary["confidence"] == alpha)
                & (summary["horizon_days"] == horizon) & (summary["scaling"] == scaling)]
    return float(s[col].iloc[0])


# ------------------------------------------------------------------ descriptive statistics
def asset_stats(inp: Inputs) -> pd.DataFrame:
    """Annualised return and volatility, skewness, kurtosis and extreme days per ETF and portfolio."""
    rets = inp.returns.copy()
    rets.columns = inp.labels
    rets["Portfolio"] = inp.port
    years = (rets.index[-1] - inp.prices.index[inp.prices.index < rets.index[0]][-1]).days / 365.25
    rows = []
    for c in rets.columns:
        x = rets[c]
        sk, ku = vm.sample_skew_kurt(x.to_numpy())
        rows.append({"series": c, "cagr_pct": round(100 * ((1 + x).prod() ** (1 / years) - 1), 2),
                     "ann_vol_pct": round(100 * x.std() * np.sqrt(cfg.TRADING_DAYS_PER_YEAR), 2),
                     "daily_mean_pct": round(100 * x.mean(), 4), "skew": round(sk, 3), "excess_kurtosis": round(ku, 2),
                     "worst_day_pct": round(100 * x.min(), 2), "worst_day": x.idxmin().date().isoformat(),
                     "best_day_pct": round(100 * x.max(), 2), "best_day": x.idxmax().date().isoformat()})
    return pd.DataFrame(rows)


def correlations(inp: Inputs) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Correlation of daily returns: full window and last 250 days."""
    r = inp.returns.copy()
    r.columns = inp.labels
    return r.corr(), r.iloc[-cfg.RECENT_WINDOW:].corr()


# ------------------------------------------------------------------ 1-day VaR / ES
def one_day_var(inp: Inputs) -> dict:
    """1-day VaR and ES for every method at 95% and 99%, plus the fitted model inputs."""
    R = inp.returns.to_numpy()
    r = inp.port.to_numpy()
    n = len(r)
    w = inp.w
    cov = np.cov(R.T)  # sample covariance, ddof = 1
    sigma = vm.portfolio_sigma(cov, w)
    ewma_all = vm.ewma_covariance(R, cfg.EWMA_LAMBDA, np.cov(R[:cfg.RECENT_WINDOW].T))
    cov_ewma = ewma_all[-1]  # forecast for the next trading day (2-Nov-2026)
    sigma_ewma = vm.portfolio_sigma(cov_ewma, w)
    skew, kurt = vm.sample_skew_kurt(r)
    zstd = (r - r.mean()) / r.std(ddof=1)
    nu = vm.fit_t_df(zstd)
    nu_kurt = vm.t_df_from_kurtosis(kurt)
    nu_scipy = float(stats.t.fit(r)[0])
    sims_n = vm.simulate_normal(cov, cfg.N_SIMULATIONS, np.random.default_rng(cfg.SEED)) @ w
    sims_t = vm.simulate_student_t(cov, nu, cfg.N_SIMULATIONS, np.random.default_rng(cfg.SEED)) @ w
    rows = []
    for a in ALPHAS:
        rows.append(_row(M_HS, "full", 1, a, *vm.historical_var_es(r, a), n, "direct",
                         "empirical quantile of daily P&L"))
        rows.append(_row(M_HS250, "last 250", 1, a, *vm.historical_var_es(r[-cfg.RECENT_WINDOW:], a),
                         cfg.RECENT_WINDOW, "direct", "empirical quantile, most recent 250 days"))
        rows.append(_row(M_NS, "full", 1, a, *vm.normal_var_es(sigma, a), n, "direct",
                         f"z * sigma_p * V, sigma_p = {100 * sigma:.4f}% per day, zero mean"))
        rows.append(_row(M_NE, "full (EWMA)", 1, a, *vm.normal_var_es(sigma_ewma, a), n, "direct",
                         f"lambda = {cfg.EWMA_LAMBDA}, sigma_p = {100 * sigma_ewma:.4f}% per day, zero mean"))
        rows.append(_row(M_CF, "full", 1, a, *vm.cornish_fisher_var_es(sigma, a, skew, kurt), n, "direct",
                         f"skew = {skew:.3f}, excess kurtosis = {kurt:.3f}"))
        rows.append(_row(M_MCN, "full", 1, a, *vm.historical_var_es(sims_n, a), cfg.N_SIMULATIONS, "direct",
                         "Cholesky of sample covariance, seed 42"))
        rows.append(_row(M_MCT, "full", 1, a, *vm.historical_var_es(sims_t, a), cfg.N_SIMULATIONS, "direct",
                         f"multivariate t, nu = {nu:.2f} (MLE), covariance = sample, seed 42"))
    return {"summary": pd.DataFrame(rows), "cov": cov, "cov_ewma": cov_ewma, "ewma_all": ewma_all,
            "sigma": sigma, "sigma_ewma": sigma_ewma, "mean": float(r.mean()), "skew": skew, "kurt": kurt,
            "nu": nu, "nu_kurt": nu_kurt, "nu_scipy": nu_scipy, "sims_n": sims_n, "sims_t": sims_t}


# ------------------------------------------------------------------ 10-day VaR / ES
def ten_day_var(inp: Inputs, od: dict) -> pd.DataFrame:
    """10-day VaR/ES: square-root-of-time scaling of every 1-day figure, and direct estimates.

    Direct historical: overlapping 10-day returns of each ETF, positions held fixed over the
    10 days (P&L = V * sum_i w_i R_i,10d). Direct Monte Carlo: 10 iid daily draws per path,
    compounded per ETF.
    """
    h = cfg.HORIZON_DAYS
    rows = []
    one = od["summary"]
    for _, x in one.iterrows():
        rows.append(_row(x["method"], x["window"], h, x["confidence"], np.sqrt(h) * x["var_pct"] / 100,
                         np.sqrt(h) * x["es_pct"] / 100, x["observations"], "sqrt-time",
                         "1-day figure x sqrt(10)"))
    r10 = vm.overlapping_horizon_returns(_window_prices(inp), h) @ inp.w
    paths_n = vm.simulate_horizon_returns(od["cov"], cfg.N_SIMULATIONS, h, np.random.default_rng(cfg.SEED)) @ inp.w
    paths_t = vm.simulate_horizon_returns(od["cov"], cfg.N_SIMULATIONS, h, np.random.default_rng(cfg.SEED),
                                          nu=od["nu"]) @ inp.w
    for a in ALPHAS:
        rows.append(_row(M_HS, "full", h, a, *vm.historical_var_es(r10.to_numpy(), a), len(r10), "direct",
                         f"{len(r10)} overlapping 10-day windows (about {len(r10) // h} independent)"))
        rows.append(_row(M_MCN, "full", h, a, *vm.historical_var_es(paths_n, a), cfg.N_SIMULATIONS, "direct",
                         "10 iid normal days compounded, seed 42"))
        rows.append(_row(M_MCT, "full", h, a, *vm.historical_var_es(paths_t, a), cfg.N_SIMULATIONS, "direct",
                         f"10 iid Student-t days (nu = {od['nu']:.2f}) compounded, seed 42"))
    return pd.DataFrame(rows)


def _window_prices(inp: Inputs) -> pd.DataFrame:
    """Prices from the base date (last close before the window) to the end of the window."""
    base = inp.prices.index[inp.prices.index < inp.returns.index[0]][-1]
    return inp.prices.loc[base:inp.returns.index[-1]]


def ten_day_diagnostics(inp: Inputs) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Why direct 10-day VaR differs from sqrt(10) scaling.

    Returns (variance ratios, effects table):
    * VR(10) = Var(10-day return) / (10 Var(1-day return)); 1 under iid returns, below 1 with
      mean reversion (for example bid-ask bounce), above 1 with momentum.
    * Effects: direct historical 10-day 99% VaR with and without the sample drift, sqrt(10) x the
      1-day figure, and the spread of non-overlapping estimates (10 possible start offsets).
    """
    px = _window_prices(inp)
    rows = []
    for t, lab in zip(inp.returns.columns, inp.labels):
        r10 = (px[t] / px[t].shift(cfg.HORIZON_DAYS) - 1).dropna()
        rows.append({"series": lab, "vr10": round(r10.var() / (cfg.HORIZON_DAYS * inp.returns[t].var()), 3),
                     "lag1_autocorr": round(inp.returns[t].autocorr(1), 3)})
    r10p = vm.overlapping_horizon_returns(px, cfg.HORIZON_DAYS) @ inp.w
    rows.append({"series": "Portfolio", "vr10": round(r10p.var() / (cfg.HORIZON_DAYS * inp.port.var()), 3),
                 "lag1_autocorr": round(inp.port.autocorr(1), 3)})
    vr = pd.DataFrame(rows)

    demeaned = inp.returns - inp.returns.mean()
    growth = pd.concat([pd.DataFrame([np.ones(len(inp.w))], index=[px.index[0]], columns=inp.returns.columns),
                        (1 + demeaned).cumprod()])
    r10d = vm.overlapping_horizon_returns(growth, cfg.HORIZON_DAYS) @ inp.w
    eff = []
    for a in ALPHAS:
        direct = vm.historical_var_es(r10p.to_numpy(), a)[0]
        direct_dm = vm.historical_var_es(r10d.to_numpy(), a)[0]
        one = vm.historical_var_es(inp.port.to_numpy(), a)[0]
        one_dm = vm.historical_var_es((inp.port - inp.port.mean()).to_numpy(), a)[0]
        nonover = [vm.historical_var_es(r10p.to_numpy()[k::cfg.HORIZON_DAYS], a)[0] for k in range(cfg.HORIZON_DAYS)]
        eff.append({"confidence": a, "sqrt10_x_1day_inr": round(np.sqrt(10) * one * V),
                    "sqrt10_x_1day_demeaned_inr": round(np.sqrt(10) * one_dm * V),
                    "direct_overlapping_inr": round(direct * V), "direct_demeaned_inr": round(direct_dm * V),
                    "drift_10d_inr": round(cfg.HORIZON_DAYS * inp.port.mean() * V),
                    "nonoverlap_min_inr": round(min(nonover) * V), "nonoverlap_max_inr": round(max(nonover) * V),
                    "nonoverlap_obs": len(r10p.to_numpy()[0::cfg.HORIZON_DAYS])})
    return vr, pd.DataFrame(eff)


def index_sensitivity(inp: Inputs) -> pd.DataFrame:
    """Historical VaR/ES when the NIFTYBEES leg uses NIFTY 50 index returns instead of ETF prices.

    The ETF's closing price can sit above or below its NAV on volatile days (on 4-Jun-2024 NIFTYBEES
    fell 2.97% while the index fell 5.93%). Swapping in the index (^NSEI, a price index) shows how
    much this smoothing lowers the measured tail risk. The five special sessions that Yahoo's
    index series lacks keep the ETF return.
    """
    nsei = dp.read_yahoo(cfg.CALENDAR_TICKER)["Close"]
    idx_ret = (nsei / nsei.shift(1) - 1).dropna()
    swapped = inp.returns.copy()
    common = swapped.index.intersection(idx_ret.index)
    swapped.loc[common, "NIFTYBEES.NS"] = idx_ret.loc[common]
    port_idx = swapped.to_numpy() @ inp.w
    rows = []
    for a in ALPHAS:
        v0, e0 = vm.historical_var_es(inp.port.to_numpy(), a)
        v1, e1 = vm.historical_var_es(port_idx, a)
        rows.append({"confidence": a, "var_etf_inr": round(v0 * V), "var_index_inr": round(v1 * V),
                     "es_etf_inr": round(e0 * V), "es_index_inr": round(e1 * V),
                     "days_swapped": len(common)})
    out = pd.DataFrame(rows)
    track = (inp.returns["NIFTYBEES.NS"] - idx_ret).loc[common]
    out.attrs.update({"tracking_sd_daily_pct": 100 * track.std(), "tracking_autocorr": track.autocorr(1),
                      "corr": float(np.corrcoef(inp.returns.loc[common, "NIFTYBEES.NS"], idx_ret.loc[common])[0, 1]),
                      "worst_day_index_version": pd.Series(port_idx, index=inp.returns.index).nsmallest(3)})
    return out


def es_estimators(inp: Inputs) -> pd.DataFrame:
    """Historical ES with the tail-mean estimator used throughout and the Acerbi-Tasche alternative."""
    r = inp.port.to_numpy()
    rows = []
    for label, x in [("full window", r), ("last 250 days", r[-cfg.RECENT_WINDOW:])]:
        for a in ALPHAS:
            var, es = vm.historical_var_es(x, a)
            at = vm.acerbi_tasche_es(x, a)
            rows.append({"window": label, "confidence": a, "observations": len(x),
                         "n_times_p": round(len(x) * (1 - a), 2), "tail_days_averaged": int((x <= -var).sum()),
                         "var_inr": round(var * V), "es_tail_mean_inr": round(es * V),
                         "es_acerbi_tasche_inr": round(at * V), "difference_pct": round(100 * (at / es - 1), 2)})
    return pd.DataFrame(rows)


def ten_day_comparison(summary: pd.DataFrame) -> pd.DataFrame:
    """Side-by-side 10-day VaR: sqrt-time scaling vs direct estimate, for methods that have both."""
    s = summary[summary["horizon_days"] == cfg.HORIZON_DAYS]
    out = []
    for m in [M_HS, M_MCN, M_MCT]:
        for a in ALPHAS:
            sq = s[(s["method"] == m) & (s["confidence"] == a) & (s["scaling"] == "sqrt-time")].iloc[0]
            di = s[(s["method"] == m) & (s["confidence"] == a) & (s["scaling"] == "direct")].iloc[0]
            out.append({"method": m, "confidence": a, "sqrt_time_var_inr": round(sq["var_inr"]),
                        "direct_var_inr": round(di["var_inr"]),
                        "direct_over_sqrt_time": round(di["var_inr"] / sq["var_inr"], 3),
                        "sqrt_time_es_inr": round(sq["es_inr"]), "direct_es_inr": round(di["es_inr"])})
    return pd.DataFrame(out)


# ------------------------------------------------------------------ decomposition
def decomposition(inp: Inputs, od: dict, alpha: float = 0.99) -> pd.DataFrame:
    """Euler decomposition of the parametric-normal VaR with the sample and the EWMA covariance."""
    a = vm.var_decomposition(od["cov"], inp.w, V, alpha, inp.labels)
    b = vm.var_decomposition(od["cov_ewma"], inp.w, V, alpha, inp.labels)
    a.columns = [f"{c}" for c in a.columns]
    b = b[["standalone_var_inr", "marginal_var_per_inr", "component_var_inr", "contribution_pct"]]
    b.columns = [f"{c}_ewma" for c in b.columns]
    out = pd.concat([a, b], axis=1)
    out.index.name = "etf"
    return out


def diversification(dec: pd.DataFrame, od: dict, alpha: float = 0.99) -> pd.DataFrame:
    """Undiversified VaR (sum of standalone VaRs) vs portfolio VaR, sample and EWMA covariance."""
    z = stats.norm.ppf(alpha)
    rows = []
    for name, sig, col in [("sample covariance", od["sigma"], "standalone_var_inr"),
                           ("EWMA covariance", od["sigma_ewma"], "standalone_var_inr_ewma")]:
        undiv = dec[col].sum()
        port = z * sig * V
        rows.append({"covariance": name, "undiversified_var_inr": round(undiv, 0), "portfolio_var_inr": round(port, 0),
                     "diversification_benefit_inr": round(undiv - port, 0),
                     "benefit_pct_of_undiversified": round(100 * (undiv - port) / undiv, 1)})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ backtest, stress, convergence
def run_backtest(inp: Inputs) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rolling 250-day one-day-ahead VaR forecasts and the test summary."""
    fc = bt.rolling_forecasts(inp.port, inp.returns, inp.w, cfg.RECENT_WINDOW, ALPHAS, cfg.EWMA_LAMBDA)
    return fc, bt.backtest_summary(fc, ALPHAS, last_n=cfg.RECENT_WINDOW)


def run_stress(inp: Inputs, od: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Five worst historical days and the hypothetical shock scenarios."""
    s = od["summary"]
    var99 = s[(s["method"] == M_HS) & (s["confidence"] == 0.99)]["var_inr"].iloc[0]
    worst = st.worst_days(inp.port, inp.returns, V, k=5)
    worst["multiple_of_1d_var99"] = (-worst["pnl_inr"] / var99).round(2)
    worst["event"] = [st.EVENTS.get(str(d), "") for d in worst.index]
    hyp = st.hypothetical_stress(inp.w, V, var99)
    return worst, hyp


def stress_table(worst: pd.DataFrame, hyp: pd.DataFrame) -> pd.DataFrame:
    """One tidy table with the historical worst days and the hypothetical scenarios."""
    rows = []
    for d, x in worst.iterrows():
        row = {"type": "historical", "scenario": f"Worst day {d}", "date": str(d)}
        for lab in [cfg.HOLDINGS[t][0] for t in cfg.TICKERS]:
            row[f"{lab}_move_pct"] = x[f"{lab}_ret_pct"]
        row.update({"total_pnl_inr": x["pnl_inr"], "total_pnl_pct": x["portfolio_ret_pct"],
                    "multiple_of_1d_var99": x["multiple_of_1d_var99"], "description": x["event"]})
        rows.append(row)
    for _, x in hyp.iterrows():
        row = {"type": "hypothetical", "scenario": x["scenario"], "date": ""}
        for t in cfg.TICKERS:
            lab = cfg.HOLDINGS[t][0]
            row[f"{lab}_move_pct"] = x[f"{lab}_shock_pct"]
        row.update({"total_pnl_inr": x["total_pnl_inr"], "total_pnl_pct": x["total_pnl_pct"],
                    "multiple_of_1d_var99": x["multiple_of_1d_var99"],
                    "description": "instantaneous shock to the 30-Oct-2026 positions"})
        rows.append(row)
    return pd.DataFrame(rows)


def convergence(inp: Inputs, od: dict, alpha: float = 0.99) -> dict:
    """Nested-sample and replicated Monte Carlo VaR estimates for the convergence chart."""
    nested = {"Normal": vm.nested_convergence(od["sims_n"], alpha, CONVERGENCE_SIZES),
              "Student-t": vm.nested_convergence(od["sims_t"], alpha, CONVERGENCE_SIZES)}
    bands = {"Normal": vm.replicated_convergence(od["cov"], inp.w, alpha, CONVERGENCE_SIZES, CONVERGENCE_REPS,
                                                 cfg.SEED),
             "Student-t": vm.replicated_convergence(od["cov"], inp.w, alpha, CONVERGENCE_SIZES, CONVERGENCE_REPS,
                                                    cfg.SEED, nu=od["nu"])}
    analytic = {"Normal": vm.normal_var_es(od["sigma"], alpha)[0],
                "Student-t": vm.student_t_var_es(od["sigma"], alpha, od["nu"])[0]}
    table = pd.DataFrame({"n_sims": CONVERGENCE_SIZES,
                          "normal_nested_var_inr": (nested["Normal"].to_numpy() * V).round(0),
                          "normal_p2_5_inr": (bands["Normal"]["p2_5"].to_numpy() * V).round(0),
                          "normal_p97_5_inr": (bands["Normal"]["p97_5"].to_numpy() * V).round(0),
                          "t_nested_var_inr": (nested["Student-t"].to_numpy() * V).round(0),
                          "t_p2_5_inr": (bands["Student-t"]["p2_5"].to_numpy() * V).round(0),
                          "t_p97_5_inr": (bands["Student-t"]["p97_5"].to_numpy() * V).round(0)})
    return {"nested": nested, "bands": bands, "analytic": analytic, "table": table}


# ------------------------------------------------------------------ validation
def validation_checks(inp: Inputs, od: dict, summary: pd.DataFrame, dec: pd.DataFrame,
                      fc: pd.DataFrame, eff10: pd.DataFrame | None = None) -> pd.DataFrame:
    """PASS/FAIL checks that confirm the implementation is internally consistent.

    Groups: data and weights; historical quantiles; Monte Carlo against closed forms (VaR within 2%,
    ES within 3 Monte Carlo standard errors); ES definitions; decomposition; matrices; backtest
    statistics (textbook Kupiec regions, conditional-coverage identity, Basel zones, no look-ahead).
    """
    r = inp.port.to_numpy()
    checks = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "result": "PASS" if ok else "FAIL", "detail": detail})

    add("Weights sum to 1", abs(inp.w.sum() - 1) < 1e-12, f"sum = {inp.w.sum():.12f}")
    add("No missing returns in the window", not inp.returns.isna().any().any(),
        f"{len(inp.returns)} days x {inp.returns.shape[1]} ETFs")

    # data: cleaned prices against the official NSE closes, jump screen, bond ETF choice
    raw = dp.load_raw(list(dict.fromkeys(cfg.TICKERS + list(cfg.BOND_CANDIDATES) + [cfg.CALENDAR_TICKER])))
    nse = dp.read_nse_closes()
    cross = dp.nse_crosscheck(raw, inp.prices, nse)
    add("Cleaned closes equal every NSE bhavcopy close fetched", bool(cross["clean_match"].all()
                                                                      and cross["prev_match"].all()),
        f"{len(cross)} ETF-days on {cross['date'].nunique()} dates; Yahoo as downloaded matched "
        f"{int(cross['yahoo_match'].sum())}")
    calendar, _ = dp.trading_calendar(raw, dp.read_nse_requests())
    jumps = dp.jump_screen(raw, inp.prices, nse, calendar)
    genuine = int(jumps["status"].str.startswith("genuine").sum())
    artefact = int(jumps["status"].str.startswith("artefact").sum())
    add("Every large one-day move is confirmed by NSE or removed by a data fix", genuine + artefact == len(jumps),
        f"{len(jumps)} moves screened: {genuine} genuine, {artefact} artefacts of bad prints or missing sessions")
    yahoo_calendar, _ = dp.trading_calendar(raw)
    screen = dp.bond_screen(raw, yahoo_calendar)
    chosen = screen.loc[screen["selected"], "ticker"].tolist()
    add("Bond ETF screen selects the gilt ETF held in the portfolio", chosen == ["SETF10GILT.NS"],
        f"selected {chosen}; {int(screen['eligible'].sum())} of {len(screen)} candidates eligible")
    for a in ALPHAS:
        for label, x in [("full window", r), ("last 250 days", r[-cfg.RECENT_WINDOW:])]:
            own = vm.historical_var_es(x, a)[0]
            npq = -np.quantile(x, 1 - a)
            pdq = -pd.Series(x).quantile(1 - a)
            add(f"Historical VaR {a:.0%} ({label}) equals the empirical quantile",
                abs(own - npq) < 1e-12 and abs(own - pdq) < 1e-12,
                f"own {own * V:,.2f} vs numpy {npq * V:,.2f} vs pandas {pdq * V:,.2f} Rs")
    s1 = summary[summary["horizon_days"] == 1]
    for a in ALPHAS:
        p = s1[(s1["method"] == M_NS) & (s1["confidence"] == a)]["var_inr"].iloc[0]
        m = s1[(s1["method"] == M_MCN) & (s1["confidence"] == a)]["var_inr"].iloc[0]
        add(f"MC normal VaR {a:.0%} within 2% of parametric normal VaR", abs(m / p - 1) < 0.02,
            f"MC {m:,.0f} vs parametric {p:,.0f} Rs ({100 * (m / p - 1):+.2f}%)")
        ta = vm.student_t_var_es(od["sigma"], a, od["nu"])[0] * V
        mt = s1[(s1["method"] == M_MCT) & (s1["confidence"] == a)]["var_inr"].iloc[0]
        add(f"MC Student-t VaR {a:.0%} within 2% of analytic t VaR", abs(mt / ta - 1) < 0.02,
            f"MC {mt:,.0f} vs analytic {ta:,.0f} Rs ({100 * (mt / ta - 1):+.2f}%)")
    bad = summary[summary["es_inr"] < summary["var_inr"]]
    add("ES >= VaR for every method, confidence and horizon", bad.empty,
        f"{len(summary)} rows checked, {len(bad)} violations")
    for a in ALPHAS:
        for name, sims, closed in [("normal", od["sims_n"], vm.normal_var_es(od["sigma"], a)[1]),
                                   ("Student-t", od["sims_t"], vm.student_t_var_es(od["sigma"], a, od["nu"])[1])]:
            mc = vm.historical_var_es(sims, a)[1]
            se = vm.es_standard_error(sims, a)
            add(f"MC {name} ES {a:.0%} within 3 standard errors of the closed-form ES", abs(mc - closed) < 3 * se,
                f"MC {mc * V:,.0f} vs closed form {closed * V:,.0f} Rs ({100 * (mc / closed - 1):+.2f}%, "
                f"{abs(mc - closed) / se:.1f} SE; SE = Rs {se * V:,.0f})")
    for a in ALPHAS:
        te = vm.student_t_var_es(od["sigma"], a, od["nu"])[1]
        ten = vm.student_t_es_numeric(od["sigma"], a, od["nu"])
        add(f"Student-t ES {a:.0%}: closed form equals numerical integral", abs(te / ten - 1) < 1e-6,
            f"{te * V:,.2f} vs {ten * V:,.2f} Rs")
    h = cfg.HORIZON_DAYS
    worst_gap = max(abs(pick(summary, m, a, h, "sqrt-time") - np.sqrt(h) * pick(summary, m, a))
                    for m in dict.fromkeys(summary["method"]) for a in ALPHAS
                    if not summary[(summary["method"] == m) & (summary["scaling"] == "sqrt-time")].empty)
    detail = f"largest gap Rs {worst_gap:.2e}"
    ok = worst_gap < 1e-6
    if eff10 is not None:
        e99 = float(eff10.loc[eff10["confidence"] == 0.99, "sqrt10_x_1day_inr"].iloc[0])
        s99 = round(pick(summary, M_HS, 0.99, h, "sqrt-time"))
        ok = ok and abs(e99 - s99) < 0.5
        detail += f"; historical 99%: Rs {s99:,.0f} in var_summary, Rs {e99:,.0f} in ten_day_effects"
    add("10-day square-root-of-time rows equal sqrt(10) x the 1-day figures", ok, detail)
    for a in ALPHAS:
        z = stats.norm.ppf(a)
        for cov, tag in [(od["cov"], "sample"), (od["cov_ewma"], "EWMA")]:
            d = vm.var_decomposition(cov, inp.w, V, a, inp.labels)
            tot = z * vm.portfolio_sigma(cov, inp.w) * V
            add(f"Component VaRs sum to portfolio VaR ({tag}, {a:.0%})",
                abs(d["component_var_inr"].sum() - tot) < 1e-6,
                f"sum {d['component_var_inr'].sum():,.4f} vs total {tot:,.4f} Rs")
    for a in ALPHAS:
        cf = vm.cornish_fisher_var_es(od["sigma"], a, od["skew"], od["kurt"])[1]
        cfn = vm.cornish_fisher_es_numeric(od["sigma"], a, od["skew"], od["kurt"])
        add(f"Cornish-Fisher ES {a:.0%}: closed form equals numerical integral", abs(cf / cfn - 1) < 1e-6,
            f"{cf * V:,.2f} vs {cfn * V:,.2f} Rs")
    add("Cornish-Fisher quantile is monotone on z in [-5, 0]",
        vm.cornish_fisher_is_monotone(od["skew"], od["kurt"]),
        f"skew {od['skew']:.3f}, excess kurtosis {od['kurt']:.3f}")
    chol = np.linalg.cholesky(od["cov"])
    add("Cholesky factor reproduces the covariance matrix", np.allclose(chol @ chol.T, od["cov"], atol=1e-15),
        f"max abs error {np.abs(chol @ chol.T - od['cov']).max():.2e}")
    add("EWMA covariance is positive definite", bool(np.all(np.linalg.eigvalsh(od["cov_ewma"]) > 0)),
        f"smallest eigenvalue {np.linalg.eigvalsh(od['cov_ewma']).min():.3e}")
    for name, sims in [("normal", od["sims_n"]), ("Student-t", od["sims_t"])]:
        ratio = sims.std(ddof=1) / od["sigma"]
        add(f"MC {name}: simulated portfolio sigma within 2% of sample sigma", abs(ratio - 1) < 0.02,
            f"ratio {ratio:.4f}")
    add("Backtest covers every day after the first 250", len(fc) == len(r) - cfg.RECENT_WINDOW,
        f"{len(fc)} out-of-sample days")

    # backtest statistics
    regions = {}
    for a, expected in [(0.99, (5, 16)), (0.95, (38, 64))]:
        acc = [x for x in range(0, 120)
               if bt.kupiec_pof(np.r_[np.ones(x), np.zeros(1000 - x)], 1 - a)["p_pof"] >= 0.05]
        regions[a] = (min(acc), max(acc))
        add(f"Kupiec test reproduces the textbook acceptance region (T = 1000, {a:.0%})",
            regions[a] == expected, f"accepts {regions[a][0]} to {regions[a][1]} exceptions; "
                                    f"published region {expected[0]} to {expected[1]}")
    gaps = []
    for key in bt.MODELS:
        for a in ALPHAS:
            exc = (fc["ret"] < -fc[f"{key}_{int(round(a * 100))}"]).to_numpy()
            cc = bt.conditional_coverage(exc, 1 - a)["lr_cc"]
            parts = bt.kupiec_pof(exc[1:], 1 - a)["lr_pof"] + bt.christoffersen_ind(exc)["lr_ind"]
            gaps.append(abs(cc - parts))
    add("Conditional coverage LR = Kupiec LR (days 2..n) + independence LR", max(gaps) < 1e-9,
        f"{len(gaps)} model-level pairs, largest gap {max(gaps):.1e}")
    bounds = bt.basel_zone_bounds(cfg.RECENT_WINDOW, 0.01)
    zones_ok = (bounds == (4, 10) and bt.traffic_light(bounds[0]) == "green"
                and bt.traffic_light(bounds[0] + 1) == "yellow" and bt.traffic_light(bounds[1]) == "red"
                and bt.traffic_light(bounds[1] - 1) == "yellow")
    add("Basel traffic-light zones match the binomial rule (250 days, 99%)", zones_ok,
        f"green up to {bounds[0]} exceptions, red from {bounds[1]}")
    # no look-ahead: drop every day after t_chk and multiply day t_chk's own returns by 5;
    # the forecasts made for day t_chk must not change
    t_chk = 700
    pert_ret = inp.returns.iloc[:t_chk + 1].copy()
    pert_ret.iloc[-1] = 5 * pert_ret.iloc[-1]
    pert_port = pd.Series(pert_ret.to_numpy() @ inp.w, index=pert_ret.index)
    sub = bt.rolling_forecasts(pert_port, pert_ret, inp.w, cfg.RECENT_WINDOW, ALPHAS, cfg.EWMA_LAMBDA)
    day = inp.port.index[t_chk]
    cols = [c for c in fc.columns if c != "ret"]
    diff = float(np.max(np.abs(sub.loc[day, cols].to_numpy(float) - fc.loc[day, cols].to_numpy(float))))
    add("Backtest forecasts use only past data (no look-ahead)", diff < 1e-9,
        f"forecasts for {day:%d-%b-%Y} recomputed after deleting later days and changing that day's "
        f"returns; largest difference {diff:.1e}")
    return pd.DataFrame(checks)
