"""CLI entry point for running the unified pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .experiments import ExperimentRunner, load_experiment_plan
from .pipeline import load_pipeline


def parse_args() -> argparse.Namespace:
    """
    Parse command-line options for the pipeline runner.

    Returns:
        Populated argparse namespace.
    """
    parser = argparse.ArgumentParser(
        description="Unified ticker forecasting pipeline with backtesting."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/tickers.toml"),
        help="Path to the pipeline configuration file.",
    )
    parser.add_argument(
        "--tickers",
        nargs="*",
        help="Optional subset of tickers to process. Default: run all configured tickers.",
    )
    parser.add_argument(
        "--experiment-config",
        type=Path,
        help="Optional experiment definition file. When provided, the experiment runner executes instead of the base pipeline.",
    )
    parser.add_argument(
        "--experiment-names",
        nargs="*",
        help="Optional subset of experiments to run when using --experiment-config.",
    )
    parser.add_argument(
        "--dump-summary",
        action="store_true",
        help="Print aggregated metrics as JSON at the end of the run.",
    )
    return parser.parse_args()


def main() -> None:
    """Entrypoint that executes the pipeline based on CLI arguments."""
    args = parse_args()
    if args.experiment_config:
        base_config_path, artifact_root, specs = load_experiment_plan(args.experiment_config)
        runner = ExperimentRunner(base_config_path, artifact_root, specs)
        results = runner.run(args.experiment_names)
        if args.dump_summary:
            payload = {
                result.name: {
                    "aggregate_score": result.aggregate_score,
                    "ticker_metrics": result.ticker_metrics,
                }
                for result in results
            }
            print(json.dumps(payload, indent=2, default=str))
        return

    runner = load_pipeline(args.config)
    results = runner.run(args.tickers)

    if args.dump_summary:
        payload = {ticker: summary.aggregated_metrics for ticker, summary in results.items()}
        print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
