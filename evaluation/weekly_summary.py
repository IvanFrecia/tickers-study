#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aggregate MAE/MAPE/RMSE over a date window.

Example:
    python evaluation/weekly_summary.py --start 2025-09-12 --end 2025-09-30 --tickers AAPL AMZN BA CVX
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarise evaluation metrics over a business-day window."
    )
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD).")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD).")
    parser.add_argument(
        "--tickers",
        nargs="+",
        default=["AAPL", "AMZN", "BA", "CVX"],
        help="Ticker symbols to include.",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=Path("reports/risk_package/paper_trading_metrics.json"),
        help="JSON file where summary should be appended/updated.",
    )
    return parser.parse_args()


def load_metrics(ticker: str, dates: List[pd.Timestamp]) -> pd.DataFrame:
    rows = []
    for date in dates:
        path = Path("reports") / "daily" / ticker / f"{date.date()}_evaluation.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text())
        metrics = payload.get("metrics")
        if not metrics:
            continue
        rows.append(
            {
                "date": date,
                "mae": metrics["mae"],
                "rmse": metrics["rmse"],
                "mape": metrics["mape"],
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    args = parse_args()
    start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end)
    dates = pd.bdate_range(start=start, end=end)

    summary: Dict[str, Dict[str, float]] = {}
    for ticker in args.tickers:
        df = load_metrics(ticker, list(dates))
        if df.empty:
            summary[ticker] = {"records": 0}
            continue
        summary[ticker] = {
            "records": len(df),
            "mae_mean": df["mae"].mean(),
            "mae_std": df["mae"].std(),
            "mape_mean": df["mape"].mean(),
            "mape_std": df["mape"].std(),
            "rmse_mean": df["rmse"].mean(),
            "latest_mae": df.sort_values("date").iloc[-1]["mae"],
        }

    args.target.parent.mkdir(parents=True, exist_ok=True)
    if args.target.exists():
        payload = json.loads(args.target.read_text())
    else:
        payload = {}

    key = f"{start.date()}__{end.date()}"
    payload[key] = summary

    args.target.write_text(json.dumps(payload, indent=2))
    print(f"Updated {args.target} with window {key}")


if __name__ == "__main__":
    main()
