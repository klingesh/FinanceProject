"""Regenerate every output and figure from the saved data (no internet needed).

Run from the project folder:
    python src/run_all.py

Steps: clean prices (src/data_cleaning.py) -> statistics, optimisation, frontier, Monte Carlo and
out-of-sample test (src/analysis.py, src/portfolio.py) -> CSVs in outputs/ -> PNGs in figures/
-> validation checks (exit code 1 if any check fails).
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib.pyplot as plt  # noqa: E402

from src import plotting  # noqa: E402
from src.analysis import (AnalysisResult, drawdown_table, frontier_points, growth_table,  # noqa: E402
                          run_analysis, write_outputs)
from src.config import FIG_DIR, OUT_DIR, PROCESSED_DIR, STOCK_LABELS  # noqa: E402
from src.data_cleaning import clean_prices  # noqa: E402


def make_figures(res: AnalysisResult, fig_dir: Path = FIG_DIR) -> list[Path]:
    """Create the seven README figures; returns their paths."""
    fig_dir.mkdir(parents=True, exist_ok=True)
    s_t = res.portfolio_stats.at["Max Sharpe", "sharpe"]
    jobs = {
        "cumulative_growth.png": lambda p: plotting.plot_cumulative_growth(growth_table(res), p),
        "correlation_heatmap.png": lambda p: plotting.plot_correlation_heatmap(res.corr, p),
        "risk_return.png": lambda p: plotting.plot_risk_return(res.stats, p),
        "efficient_frontier.png": lambda p: plotting.plot_efficient_frontier(
            res.frontier, res.mc, frontier_points(res), res.stats.loc[STOCK_LABELS], s_t, path=p),
        "optimal_weights.png": lambda p: plotting.plot_weights(res.weights, p),
        "drawdowns.png": lambda p: plotting.plot_drawdowns(drawdown_table(res), p),
        "out_of_sample_growth.png": lambda p: plotting.plot_oos_growth(res.oos_growth, p),
    }
    paths = []
    for name, job in jobs.items():
        fig = job(fig_dir / name)
        plt.close(fig)
        paths.append(fig_dir / name)
    return paths


def main() -> int:
    """Run the full pipeline and print the hygiene log, headline numbers and checks."""
    clean = clean_prices()
    print("\n".join(clean.log))
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    clean.prices.to_csv(PROCESSED_DIR / "prices_adjclose_clean.csv", float_format="%.6f")

    res = run_analysis(clean)
    out_paths = write_outputs(res, clean, OUT_DIR)
    fig_paths = make_figures(res)

    ps = res.portfolio_stats
    print("\nHEADLINE (Nov-2021 to Oct-2026, rf 5.93%)")
    for name in ps.index:
        r = ps.loc[name]
        print(f"  {name:24s} mean {r['ann_mean_return']:6.1%}  CAGR {r['cagr']:6.1%}  vol {r['ann_volatility']:5.1%}"
              f"  Sharpe {r['sharpe']:5.2f}  max DD {r['max_drawdown']:6.1%}")
    print("\nOutputs:", ", ".join(p.name for p in out_paths))
    print("Figures:", ", ".join(p.name for p in fig_paths))
    print("\nVALIDATION CHECKS")
    for _, r in res.checks.iterrows():
        print(f"  [{r['result']}] {r['check']} ({r['detail']})")
    n_fail = int((res.checks["result"] == "FAIL").sum()) + sum(not v for v in clean.checks.values())
    print(f"\n{'ALL CHECKS PASS' if n_fail == 0 else f'{n_fail} CHECK(S) FAILED'}")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
