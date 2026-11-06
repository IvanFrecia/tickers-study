"""CLI for generating forecasts from archived models."""

from __future__ import annotations

import argparse
from pathlib import Path

from .prediction import run_forecast


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate multi-step forecasts for a ticker.")
    parser.add_argument("--config", type=Path, default=Path("configs/tickers.toml"), help="Pipeline configuration file.")
    parser.add_argument("--ticker", required=True, help="Ticker symbol to forecast.")
    parser.add_argument("--model-path", type=Path, required=True, help="Path to the saved Keras model (.keras).")
    parser.add_argument("--scaler-path", type=Path, required=True, help="Path to the saved MinMax scaler (.pkl).")
    parser.add_argument("--output", type=Path, required=True, help="Destination file for forecast JSON.")
    parser.add_argument("--end-date", type=str, default=None, help="Optional end date (YYYY-MM-DD) for price data.")
    parser.add_argument(
        "--price-history",
        type=Path,
        help="Optional CSV containing historical prices (useful to avoid repeated downloads).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = run_forecast(
        config_path=args.config,
        ticker=args.ticker,
        model_path=args.model_path,
        scaler_path=args.scaler_path,
        output_path=args.output,
        end_date=args.end_date,
        price_history_path=args.price_history,
    )
    # Print basic summary for operator feedback.
    horizon = len(payload["forecast"])
    print(f"Generated {horizon} predictions for {payload['ticker']} (last close {payload['context']['last_close']:.2f}).")


if __name__ == "__main__":
    main()
