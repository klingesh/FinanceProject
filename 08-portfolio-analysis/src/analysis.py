"""End-to-end analysis pipeline used by ``run_all.py`` (the notebook walks through the same steps)."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src import portfolio as pf
from src.config import (ANALYSIS_END, ANALYSIS_START, BENCHMARK, IS_END, N_FRONTIER, N_FRONTIER_LOWER,
                        N_MONTE_CARLO, NAMES, OOS_START, RF_ARITH, RF_DAILY, RF_WEEKLY, SECTORS, SEED,
                        STOCK_LABELS, TRADING_DAYS, WEIGHT_CAP)
from src.data_cleaning import CleanResult

PORTFOLIO_NAMES = {
    "equal_weight": "Equal weight",
    "min_variance": "Min variance",
    "max_sharpe": "Max Sharpe",
    "min_variance_cap20": "Min variance (20% cap)",
    "max_sharpe_cap20": "Max Sharpe (20% cap)",
}


@dataclass
class AnalysisResult:
    """Everything the outputs, figures and README are built from."""

    returns: pd.DataFrame                # daily returns in the window, stocks + NIFTY50
    base_date: pd.Timestamp
    weekly: pd.DataFrame
    stats: pd.DataFrame                  # per-stock statistics (+ NIFTY50)
    corr: pd.DataFrame
    mu: pd.Series                        # annualised arithmetic means (stocks)
    cov: pd.DataFrame                    # annualised covariance (stocks)
    weights: pd.DataFrame                # stocks x portfolios
    portfolio_stats: pd.DataFrame
    port_returns: pd.DataFrame           # daily returns of portfolios + NIFTY50
    frontier: pd.DataFrame               # both frontiers, long format
    mc: pd.DataFrame
    mc_weights: np.ndarray
    kkt: pd.DataFrame
    oos_weights: pd.DataFrame
    oos_table: pd.DataFrame
    oos_growth: pd.DataFrame
    oos_base_date: pd.Timestamp
    tr_gap: dict
    checks: pd.DataFrame = field(default_factory=pd.DataFrame)


def estimate_inputs(returns: pd.DataFrame) -> tuple[pd.Series, pd.DataFrame]:
    """Annualised mean vector (x252) and covariance matrix (x252) of daily returns."""
    return pf.annualised_mean(returns), returns.cov() * TRADING_DAYS


def optimise_set(mu: pd.Series, cov: pd.DataFrame, rf: float = RF_ARITH, cap: float = WEIGHT_CAP) -> pd.DataFrame:
    """Equal weight, min variance and max Sharpe, unconstrained (long-only) and with a per-stock cap."""
    m, c = mu.to_numpy(), cov.to_numpy()
    n = len(m)
    w = {
        "equal_weight": np.full(n, 1.0 / n),
        "min_variance": pf.min_variance(m, c),
        "max_sharpe": pf.max_sharpe(m, c, rf),
        "min_variance_cap20": pf.min_variance(m, c, cap=cap),
        "max_sharpe_cap20": pf.max_sharpe(m, c, rf, cap=cap),
    }
    return pd.DataFrame(w, index=mu.index)


def summarise_portfolios(port_returns: pd.DataFrame, weights: pd.DataFrame, mu: pd.Series, cov: pd.DataFrame,
                         bench: pd.Series, base_date: pd.Timestamp) -> pd.DataFrame:
    """Performance table for each portfolio and NIFTY 50."""
    rows = {}
    for key in port_returns.columns:
        s = pf.performance_summary(port_returns[key], bench, base_date)
        if key in weights:
            w = weights[key].to_numpy()
            s.update({"effective_n": pf.effective_n(w), "max_weight": float(w.max()),
                      "n_holdings": int((w > 1e-6).sum())})
        rows[PORTFOLIO_NAMES.get(key, "NIFTY 50" if key == BENCHMARK else key)] = s
    return pd.DataFrame(rows).T


def tr_gap_estimate(tr_proxy: pd.Series, bench_prices: pd.Series, bench_returns: pd.Series,
                    base_date: pd.Timestamp, end: pd.Timestamp) -> dict:
    """Size the dividends left out of the NIFTY 50 price index, using the NIFTYBEES ETF.

    NIFTYBEES keeps the index dividends inside its NAV, so its price growth approximates the
    total-return index (less a small expense ratio). It has a few stale or missing days, so only
    its end-to-end growth is used. The approximate total-return Sharpe adds the CAGR gap to the
    price index's arithmetic mean and keeps the price index's volatility.
    """
    years = (end - base_date).days / 365.25
    px = float(bench_prices.loc[end] / bench_prices.loc[base_date])
    tr = float(tr_proxy.loc[end] / tr_proxy.loc[base_date])
    gap = tr ** (1 / years) - px ** (1 / years)
    mean, vol = float(pf.annualised_mean(bench_returns)), float(pf.annualised_vol(bench_returns))
    return {"nifty_price_cagr": px ** (1 / years) - 1, "niftybees_cagr": tr ** (1 / years) - 1, "gap_pp": gap,
            "nifty_sharpe_price": (mean - RF_ARITH) / vol, "nifty_sharpe_tr_approx": (mean + gap - RF_ARITH) / vol}


def out_of_sample(prices: pd.DataFrame, cap: float = WEIGHT_CAP) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame,
                                                                         pd.Timestamp]:
    """Estimate weights on Nov-2021..Oct-2024, hold them Nov-2024..Oct-2026, compare with EW and NIFTY.

    Returns (weights estimated in-sample, statistics table, OOS growth of Rs 100, OOS base date).
    """
    is_r, is_base = pf.window_returns(prices, ANALYSIS_START, IS_END)
    oos_r, oos_base = pf.window_returns(prices, OOS_START, ANALYSIS_END)
    mu_is, cov_is = estimate_inputs(is_r[STOCK_LABELS])
    m, c = mu_is.to_numpy(), cov_is.to_numpy()
    n = len(m)
    w_is = pd.DataFrame({
        "equal_weight": np.full(n, 1.0 / n),
        "min_variance": pf.min_variance(m, c),
        "max_sharpe": pf.max_sharpe(m, c, RF_ARITH),
        "max_sharpe_cap20": pf.max_sharpe(m, c, RF_ARITH, cap=cap),
    }, index=STOCK_LABELS)
    rows, growth = [], {}
    for period, r, base in (("in-sample (Nov-2021 to Oct-2024)", is_r, is_base),
                            ("out-of-sample (Nov-2024 to Oct-2026)", oos_r, oos_base)):
        # In-sample, only the constant-weight version matches what the optimiser assumed.
        rebalancing = ("daily",) if period.startswith("in") else ("daily", "buy-and-hold")
        for key in w_is.columns:
            for reb in rebalancing:
                rp = (pf.portfolio_returns(r[STOCK_LABELS], w_is[key]) if reb == "daily"
                      else pf.buy_and_hold_returns(r[STOCK_LABELS], w_is[key]))
                s = pf.performance_summary(rp, r[BENCHMARK], base)
                rows.append({"portfolio": PORTFOLIO_NAMES[key], "period": period, "rebalancing": reb, **s})
                if period.startswith("out") and reb == "daily":
                    growth[PORTFOLIO_NAMES[key]] = pf.wealth_index(rp, base)
        s = pf.performance_summary(r[BENCHMARK], r[BENCHMARK], base)
        rows.append({"portfolio": "NIFTY 50", "period": period, "rebalancing": "index", **s})
        if period.startswith("out"):
            growth["NIFTY 50"] = pf.wealth_index(r[BENCHMARK], base)
    table = pd.DataFrame(rows)
    keep = ["portfolio", "period", "rebalancing", "cagr", "ann_mean_return", "ann_volatility", "sharpe",
            "sortino", "beta", "max_drawdown", "total_return"]
    return w_is, table[keep], pd.DataFrame(growth), oos_base


def run_analysis(clean: CleanResult) -> AnalysisResult:
    """Compute every statistic, portfolio, frontier and check used in the project."""
    prices = clean.prices
    rets, base = pf.window_returns(prices, ANALYSIS_START, ANALYSIS_END)
    weekly = pf.weekly_returns(prices, ANALYSIS_START, ANALYSIS_END)
    stats = pf.asset_statistics(rets, weekly, BENCHMARK, base, RF_DAILY, RF_WEEKLY)
    stats.insert(0, "sector", [SECTORS.get(i, "Index") for i in stats.index])
    stats.insert(0, "name", [NAMES[i] for i in stats.index])
    corr = rets.corr()

    R = rets[STOCK_LABELS]
    mu, cov = estimate_inputs(R)
    weights = optimise_set(mu, cov)
    port_returns = pd.DataFrame({k: pf.portfolio_returns(R, weights[k]) for k in weights})
    port_returns[BENCHMARK] = rets[BENCHMARK]
    pstats = summarise_portfolios(port_returns, weights, mu, cov, rets[BENCHMARK], base)

    m, c = mu.to_numpy(), cov.to_numpy()
    fr = pf.efficient_frontier(m, c, RF_ARITH, 1.0, N_FRONTIER, N_FRONTIER_LOWER, STOCK_LABELS)
    fr_cap = pf.efficient_frontier(m, c, RF_ARITH, WEIGHT_CAP, N_FRONTIER, N_FRONTIER_LOWER, STOCK_LABELS)
    frontier = pd.concat([fr.assign(frontier="long-only"), fr_cap.assign(frontier="long-only, 20% cap")],
                         ignore_index=True)
    frontier = frontier[["frontier", "branch", "target_return", "return", "volatility", "sharpe"] + STOCK_LABELS]

    mc, mc_w = pf.random_portfolios(m, c, RF_ARITH, N_MONTE_CARLO, SEED)
    kkt = pf.tangency_kkt_table(weights["max_sharpe"].to_numpy(), m, c, RF_ARITH, STOCK_LABELS)
    w_is, oos_table, oos_growth, oos_base = out_of_sample(prices)
    tr = tr_gap_estimate(clean.tr_proxy, prices[BENCHMARK], rets[BENCHMARK], base, ANALYSIS_END)

    res = AnalysisResult(returns=rets, base_date=base, weekly=weekly, stats=stats, corr=corr, mu=mu, cov=cov,
                         weights=weights, portfolio_stats=pstats, port_returns=port_returns, frontier=frontier,
                         mc=mc, mc_weights=mc_w, kkt=kkt, oos_weights=w_is, oos_table=oos_table,
                         oos_growth=oos_growth, oos_base_date=oos_base, tr_gap=tr)
    res.checks = validation_checks(res)
    return res


def growth_table(res: AnalysisResult) -> pd.DataFrame:
    """Growth of Rs 100 from the base date for every stock and NIFTY 50."""
    return pf.wealth_index(res.returns, res.base_date)


def frontier_points(res: AnalysisResult) -> dict[str, tuple[float, float]]:
    """(volatility, return) of each optimised portfolio and NIFTY 50, for the frontier chart."""
    m, c = res.mu.to_numpy(), res.cov.to_numpy()
    pts = {PORTFOLIO_NAMES[k]: pf.portfolio_point(res.weights[k].to_numpy(), m, c)[1::-1] for k in res.weights}
    pts["NIFTY 50"] = (float(res.stats.at[BENCHMARK, "ann_volatility"]), float(res.stats.at[BENCHMARK, "ann_mean_return"]))
    return pts


def drawdown_table(res: AnalysisResult, keys: tuple[str, ...] = ("max_sharpe", "equal_weight")) -> pd.DataFrame:
    """Drawdown series of selected portfolios and NIFTY 50 (weights from the full sample)."""
    dd = {PORTFOLIO_NAMES[k]: pf.drawdown_series(res.port_returns[k], res.base_date) for k in keys}
    dd["NIFTY 50"] = pf.drawdown_series(res.port_returns[BENCHMARK], res.base_date)
    return pd.DataFrame(dd)


def write_outputs(res: AnalysisResult, clean: CleanResult, out_dir) -> list:
    """Write the CSV outputs; returns the list of paths written."""
    from pathlib import Path

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []

    def save(df: pd.DataFrame, name: str, index: bool = True) -> None:
        p = out_dir / name
        df.to_csv(p, index=index, float_format="%.6f")
        paths.append(p)

    stats = res.stats.copy()
    stats.index.name = "ticker"
    save(stats, "stock_statistics.csv")
    w = res.weights.copy()
    w_is = res.oos_weights.drop(columns="equal_weight").add_suffix("_fit_2021_2024")
    w = w.join(w_is)
    w.index.name = "ticker"
    save(w, "portfolio_weights.csv")
    ps = res.portfolio_stats.copy()
    ps.index.name = "portfolio"
    save(ps, "portfolio_statistics.csv")
    save(res.frontier, "efficient_frontier.csv", index=False)
    save(res.oos_table, "out_of_sample.csv", index=False)
    save(res.kkt.rename_axis("ticker"), "tangency_optimality.csv")
    save(clean.demergers, "demerger_adjustments.csv", index=False)
    moves = pd.concat([clean.large_moves.assign(direction="drop below -8%"),
                       clean.large_gains.assign(direction="gain above +8%")], ignore_index=True)
    save(moves, "large_moves_review.csv", index=False)
    hyg = pd.DataFrame([{"check": k, "result": "PASS" if v else "FAIL", "detail": "data hygiene"}
                        for k, v in clean.checks.items()])
    save(pd.concat([hyg, res.checks], ignore_index=True), "validation_checks.csv", index=False)
    return paths


def validation_checks(res: AnalysisResult, tol: float = 1e-8) -> pd.DataFrame:
    """PASS/FAIL checks on weights, frontier shape, tangency optimality and annualisation."""
    m, c = res.mu.to_numpy(), res.cov.to_numpy()
    checks = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "result": "PASS" if ok else "FAIL", "detail": detail})

    W = res.weights
    add("Weights sum to 1 (all portfolios)", bool(np.allclose(W.sum(), 1, atol=tol)),
        f"max |sum-1| = {abs(W.sum() - 1).max():.1e}")
    add("Weights >= 0 (long-only)", bool((W.to_numpy() >= -tol).all()), f"min weight = {W.to_numpy().min():.1e}")
    capped = W[["min_variance_cap20", "max_sharpe_cap20"]]
    add("Capped weights <= 20%", bool((capped.to_numpy() <= WEIGHT_CAP + tol).all()),
        f"max capped weight = {capped.to_numpy().max():.4f}")
    fw = res.frontier[STOCK_LABELS].to_numpy()
    add("Frontier weights sum to 1 and >= 0",
        bool(np.allclose(fw.sum(axis=1), 1, atol=tol) and (fw >= -tol).all()), f"{len(fw)} frontier portfolios")
    add("Monte Carlo weights sum to 1 and >= 0",
        bool(np.allclose(res.mc_weights.sum(axis=1), 1, atol=1e-12) and (res.mc_weights >= 0).all()),
        f"{len(res.mc_weights):,} portfolios")
    for name, fr in res.frontier.groupby("frontier"):
        eff = fr[fr["branch"] == "efficient"].sort_values("return")
        dv = np.diff(eff["volatility"].to_numpy())
        add(f"Frontier volatility non-decreasing above min variance ({name})", bool((dv >= -1e-9).all()),
            f"smallest step = {dv.min():.2e}")
        add(f"No frontier point below the min-variance volatility ({name})",
            bool(fr["volatility"].min() >= eff["volatility"].iloc[0] - 1e-9),
            f"min vol {fr['volatility'].min():.4%} vs GMV {eff['volatility'].iloc[0]:.4%}")
    s_t = pf.portfolio_point(W["max_sharpe"].to_numpy(), m, c)[2]
    s_tc = pf.portfolio_point(W["max_sharpe_cap20"].to_numpy(), m, c)[2]
    add("Tangency Sharpe >= every Monte Carlo Sharpe", bool(s_t >= res.mc["sharpe"].max() - 1e-9),
        f"tangency {s_t:.4f} vs best random {res.mc['sharpe'].max():.4f}")
    fr_u = res.frontier[res.frontier["frontier"] == "long-only"]
    fr_c = res.frontier[res.frontier["frontier"] != "long-only"]
    add("Tangency Sharpe >= every frontier point", bool(s_t >= fr_u["sharpe"].max() - 1e-9),
        f"tangency {s_t:.4f} vs best frontier point {fr_u['sharpe'].max():.4f}")
    add("Capped tangency Sharpe >= capped frontier points and <= uncapped tangency",
        bool(s_tc >= fr_c["sharpe"].max() - 1e-9 and s_tc <= s_t + 1e-9), f"capped {s_tc:.4f}")
    w_cvx = pf.max_sharpe_convex(m, c, RF_ARITH)
    w_cvx_cap = pf.max_sharpe_convex(m, c, RF_ARITH, WEIGHT_CAP)
    d1 = np.abs(w_cvx - W["max_sharpe"].to_numpy()).max()
    d2 = np.abs(w_cvx_cap - W["max_sharpe_cap20"].to_numpy()).max()
    add("Tangency weights match the convex reformulation", bool(d1 < 1e-4 and d2 < 1e-4),
        f"max weight difference {max(d1, d2):.1e}")
    k = res.kkt
    held = k["weight"] > 1e-6
    rel = (k.loc[held, "shortfall"].abs() / k.loc[held, "excess_return"].abs()).max()
    add("Tangency optimality (KKT): held stocks on the line, excluded stocks below",
        bool(rel < 1e-3 and (k.loc[~held, "shortfall"] <= 1e-6).all()), f"max relative gap {rel:.1e}")
    gmv_vol = pf.portfolio_point(W["min_variance"].to_numpy(), m, c)[1]
    add("Min-variance vol <= every Monte Carlo vol", bool(gmv_vol <= res.mc["volatility"].min() + 1e-9),
        f"GMV {gmv_vol:.4%} vs lowest random {res.mc['volatility'].min():.4%}")
    pr = res.port_returns
    d_mean = max(abs(pr[k].mean() * TRADING_DAYS - W[k] @ res.mu) for k in W)
    d_vol = max(abs(pr[k].std(ddof=1) * np.sqrt(TRADING_DAYS) - np.sqrt(W[k] @ res.cov @ W[k])) for k in W)
    add("Annualisation: w'mu = 252 x mean(daily portfolio return)", bool(d_mean < 1e-12), f"max diff {d_mean:.1e}")
    add("Annualisation: sqrt(w'Cov w) = sqrt(252) x std(daily portfolio return)", bool(d_vol < 1e-12),
        f"max diff {d_vol:.1e}")
    st = res.stats.loc[STOCK_LABELS]
    d_sr = np.abs((st["ann_mean_return"] - RF_ARITH) / st["ann_volatility"] - st["sharpe"]).max()
    add("Annualisation: Sharpe = (mean x 252 - rf x 252) / (std x sqrt 252)", bool(d_sr < 1e-12),
        f"max diff {d_sr:.1e}")
    logm = np.log1p(res.returns[STOCK_LABELS]).mean() * TRADING_DAYS
    approx = st["ann_mean_return"] - st["ann_volatility"] ** 2 / 2
    d_drag = (logm - approx).abs().max()
    add("Volatility drag: mean log return ~ mean - sigma^2/2 (within 1 pp)", bool(d_drag < 0.01),
        f"max gap {d_drag:.2%}")
    wv = res.weekly[STOCK_LABELS].std() * np.sqrt(52)
    ratio = (wv / st["ann_volatility"])
    add("Weekly and daily annualised volatility agree within 25%", bool(ratio.between(0.75, 1.25).all()),
        f"weekly/daily ratio {ratio.min():.2f} to {ratio.max():.2f}")
    return pd.DataFrame(checks)
