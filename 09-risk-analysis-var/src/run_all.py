"""Regenerate every output table and figure offline from data/.

Usage:
    python src/run_all.py            # rebuilds the clean price file from data/raw, then runs everything
    python src/run_all.py --no-build # uses data/prices_adjclose.csv as it is

Writes outputs/*.csv and figures/*.png and prints the headline numbers and validation checks.
Exits with code 1 if any validation check fails. Runtime: about one to two minutes.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import analysis as an  # noqa: E402
from src import backtest as bt  # noqa: E402
from src import config as cfg  # noqa: E402
from src import data_prep as dp  # noqa: E402
from src import plots  # noqa: E402


def main(build: bool = True) -> dict:
    cfg.OUTPUTS.mkdir(parents=True, exist_ok=True)
    cfg.FIGURES.mkdir(parents=True, exist_ok=True)
    if build:
        dp.build_dataset()
    inp = an.load_inputs()
    inp.holdings.to_csv(cfg.OUTPUTS / "holdings.csv", index=False)
    stats_tab = an.asset_stats(inp)
    stats_tab.to_csv(cfg.OUTPUTS / "asset_stats.csv", index=False)
    corr_full, corr_recent = an.correlations(inp)
    corr_full.round(4).to_csv(cfg.OUTPUTS / "correlation_full_window.csv")
    corr_recent.round(4).to_csv(cfg.OUTPUTS / "correlation_last250.csv")

    od = an.one_day_var(inp)
    td = an.ten_day_var(inp, od)
    summary = pd.concat([od["summary"], td], ignore_index=True)
    an.rounded_summary(summary).to_csv(cfg.OUTPUTS / "var_summary.csv", index=False)
    es_est = an.es_estimators(inp)
    es_est.to_csv(cfg.OUTPUTS / "es_estimators.csv", index=False)
    ten = an.ten_day_comparison(summary)
    ten.to_csv(cfg.OUTPUTS / "ten_day_comparison.csv", index=False)
    vr10, eff10 = an.ten_day_diagnostics(inp)
    vr10.to_csv(cfg.OUTPUTS / "ten_day_variance_ratios.csv", index=False)
    eff10.to_csv(cfg.OUTPUTS / "ten_day_effects.csv", index=False)
    sens = an.index_sensitivity(inp)
    sens.to_csv(cfg.OUTPUTS / "sensitivity_nifty_index.csv", index=False)

    dec = an.decomposition(inp, od)
    dec.round(6).to_csv(cfg.OUTPUTS / "component_var.csv")
    div = an.diversification(dec, od)
    div.to_csv(cfg.OUTPUTS / "diversification.csv", index=False)

    fc, bts = an.run_backtest(inp)
    fc.to_csv(cfg.OUTPUTS / "backtest_daily.csv")
    bts.to_csv(cfg.OUTPUTS / "backtest_summary.csv", index=False)
    resid = pd.DataFrame([bt.residual_diagnostics(fc)])
    resid.to_csv(cfg.OUTPUTS / "backtest_residuals.csv", index=False)
    nxt = bt.next_day_forecasts(inp.port, inp.returns, inp.w, cfg.RECENT_WINDOW, cfg.CONFIDENCE_LEVELS,
                                cfg.EWMA_LAMBDA, cfg.PORTFOLIO_VALUE)
    nxt.to_csv(cfg.OUTPUTS / "next_day_var.csv", index=False)

    worst, hyp = an.run_stress(inp, od)
    stress = an.stress_table(worst, hyp)
    stress.to_csv(cfg.OUTPUTS / "stress_tests.csv", index=False)

    conv = an.convergence(inp, od)
    conv["table"].to_csv(cfg.OUTPUTS / "mc_convergence.csv", index=False)

    checks = an.validation_checks(inp, od, summary, dec, fc, eff10)
    checks.to_csv(cfg.OUTPUTS / "validation_checks.csv", index=False)

    # figures
    s1 = summary[summary["horizon_days"] == 1]
    lines_99 = {m: (s1[(s1["method"] == m) & (s1["confidence"] == 0.99)]["var_pct"].iloc[0] / 100,
                    s1[(s1["method"] == m) & (s1["confidence"] == 0.99)]["es_pct"].iloc[0] / 100)
                for m in dict.fromkeys(s1["method"])}
    sigma_ewma = bt.ewma_sigma_forecasts(inp.returns, inp.w, cfg.EWMA_LAMBDA, cfg.RECENT_WINDOW)
    figs = {
        "growth.png": plots.plot_growth(inp.prices, inp.port),
        "rolling_volatility.png": plots.plot_rolling_vol(inp.returns, inp.port, sigma_ewma.iloc[cfg.RECENT_WINDOW:]),
        "correlation_heatmap.png": plots.plot_correlation(
            corr_full, corr_recent,
            (f"Full window ({inp.returns.index[0]:%d-%b-%Y} to {inp.returns.index[-1]:%d-%b-%Y})",
             f"Last 250 trading days ({inp.returns.index[-cfg.RECENT_WINDOW]:%d-%b-%Y} to "
             f"{inp.returns.index[-1]:%d-%b-%Y})")),
        "return_histogram.png": plots.plot_return_histogram(inp.port, cfg.PORTFOLIO_VALUE, lines_99),
        "var_es_comparison.png": plots.plot_var_comparison(summary),
        "mc_convergence.png": plots.plot_mc_convergence(conv["nested"], conv["bands"], conv["analytic"],
                                                        cfg.PORTFOLIO_VALUE),
        "component_var.png": plots.plot_component_var(dec, float(div.loc[0, "portfolio_var_inr"])),
        "backtest.png": plots.plot_backtest(fc, cfg.PORTFOLIO_VALUE,
                                            {k: bt.MODELS[k] for k in ["hs", "n_ewma", "fhs"]}),
    }
    for name, fig in figs.items():
        fig.savefig(cfg.FIGURES / name, dpi=150, bbox_inches="tight")
        plt.close(fig)

    pd.set_option("display.width", 200)
    print(inp.holdings.to_string(index=False))
    print(stats_tab.to_string(index=False))
    print(an.rounded_summary(summary)[["method", "horizon_days", "scaling", "confidence", "var_inr", "var_pct",
                                       "es_inr"]].to_string())
    print(es_est.to_string(index=False))
    print(ten.to_string(index=False))
    print(vr10.to_string(index=False))
    print(eff10.to_string(index=False))
    print(sens.to_string(index=False), sens.attrs)
    print(dec.round(4).to_string())
    print(div.to_string(index=False))
    print(bts.to_string(index=False))
    print(resid.to_string(index=False))
    print(nxt.to_string(index=False), nxt.attrs)
    print(stress.to_string(index=False))
    print(conv["table"].to_string(index=False))
    print(f"nu MLE {od['nu']:.3f}, nu kurtosis {od['nu_kurt']:.3f}, nu scipy {od['nu_scipy']:.3f}, "
          f"skew {od['skew']:.3f}, kurt {od['kurt']:.3f}, mean {od['mean']:.6f}")
    print(checks.to_string(index=False))
    n_fail = int((checks["result"] == "FAIL").sum())
    print(f"VALIDATION: {len(checks) - n_fail} PASS, {n_fail} FAIL")
    return {"inputs": inp, "one_day": od, "summary": summary, "decomposition": dec, "backtest": (fc, bts),
            "stress": stress, "convergence": conv, "checks": checks}


if __name__ == "__main__":
    result = main(build="--no-build" not in sys.argv)
    sys.exit(1 if (result["checks"]["result"] == "FAIL").any() else 0)
