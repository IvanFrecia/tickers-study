#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Batch helper to generate daily forecasts and evaluate realised closes.

Example:
    python evaluation/run_daily.py --tickers AAPL AMZN BA CVX
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Iterable, List

import pandas as pd
from pandas.tseries.offsets import BDay

# Ensure local imports resolve
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.prediction import run_forecast
from src.evaluation import evaluate_predictions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate forecasts and evaluations for the latest business day."
    )
    parser.add_argument(
        "--tickers",
        nargs="+",
        default=["AAPL", "AMZN", "BA", "CVX"],
        help="Ticker symbols to process.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/tickers.toml"),
        help="Pipeline configuration file.",
    )
    parser.add_argument(
        "--run-dirs",
        nargs="+",
        help="Optional explicit artefact directories (one per ticker, same order).",
    )
    parser.add_argument(
        "--anchor-date",
        type=str,
        help="Forecast end date (YYYY-MM-DD). Default: last business day.",
    )
    parser.add_argument(
        "--forecast-horizon",
        type=int,
        default=5,
        help="Number of future business days to forecast (default: 5).",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path("reports/risk_package/latest_week_summary.json"),
        help="Where to store aggregate summary.",
    )
    return parser.parse_args()


def resolve_run_dir(ticker: str, explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    base = Path("artifacts") / ticker
    candidates: List[Path] = sorted(
        [path for path in base.iterdir() if path.is_dir()],
        key=lambda path: path.name,
    ) if base.exists() else []
    if not candidates:
        raise FileNotFoundError(f"No artefacts found for {ticker} under {base}")
    return candidates[-1]


def main() -> None:
    args = parse_args()

    anchor = (
        pd.Timestamp(args.anchor_date)
        if args.anchor_date
        else pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=1)[0]
    )

    summary_payload = {
        "evaluation_anchor": anchor.strftime("%Y-%m-%d"),
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "evaluation": {},
        "forecasts": {},
    }

    run_dirs = args.run_dirs or [None] * len(args.tickers)
    if len(run_dirs) != len(args.tickers):
        raise ValueError("--run-dirs must contain one entry per ticker when provided.")

    for ticker, explicit_dir in zip(args.tickers, run_dirs):
        run_dir = resolve_run_dir(ticker, explicit_dir)
        model_path = run_dir / "models" / "best_model.keras"
        scaler_path = run_dir / "scalers" / "best_scaler.pkl"

        # Generate anchor forecast and evaluate if actuals exist
        forecast_path = Path("predictions") / ticker / f"{anchor.date()}_forecast.json"
        forecast_path.parent.mkdir(parents=True, exist_ok=True)
        payload = run_forecast(
            config_path=args.config,
            ticker=ticker,
            model_path=model_path,
            scaler_path=scaler_path,
            output_path=forecast_path,
            end_date=anchor.strftime("%Y-%m-%d"),
        )
        eval_path = Path("reports") / "daily" / ticker / f"{anchor.date()}_evaluation.json"
        eval_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            metrics = evaluate_predictions(
                forecast_path,
                metrics_output=eval_path,
            )
            summary_payload["evaluation"][ticker] = metrics
        except ValueError:
            summary_payload["evaluation"][ticker] = {"warning": "actual data not yet available"}
            eval_path.unlink(missing_ok=True)

        # Predict future horizon
        next_dates = [anchor + BDay(i) for i in range(1, args.forecast_horizon + 1)]
        future_payload = []
        current_date = anchor
        for target_date in next_dates:
            next_forecast = run_forecast(
                config_path=args.config,
                ticker=ticker,
                model_path=model_path,
                scaler_path=scaler_path,
                output_path=Path("predictions") / ticker / f"{target_date.date()}_preview.json",
                end_date=current_date.strftime("%Y-%m-%d"),
                dump_json=False,
            )
            step = next_forecast["forecast"][0]
            future_payload.append(step)
            current_date = target_date
        summary_payload["forecasts"][ticker] = future_payload

    args.summary.parent.mkdir(parents=True, exist_ok=True)
    with args.summary.open("w", encoding="utf-8") as fp:
        json.dump(summary_payload, fp, indent=2)
    print(f"Summary written to {args.summary}")


if __name__ == "__main__":
    main()
