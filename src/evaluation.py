"""Evaluation utilities for daily forecast monitoring."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd

from .data import fetch_price_history


def _load_predictions(path: Path | str) -> Dict[str, object]:
    with Path(path).open("r", encoding="utf-8") as fp:
        return json.load(fp)


def _actuals_for_dates(ticker: str, dates: Iterable[str], price_history_path: Path | None = None) -> pd.Series:
    parsed_dates = sorted({pd.Timestamp(d) for d in dates})
    if not parsed_dates:
        return pd.Series(dtype=float)
    start = parsed_dates[0] - pd.Timedelta(days=5)
    end = parsed_dates[-1] + pd.Timedelta(days=5)
    if price_history_path:
        raw = pd.read_csv(price_history_path)
        first_col = raw.columns[0]
        mask = raw[first_col].isin(["Ticker", "Date"])
        cleaned = raw.loc[~mask].copy()
        cleaned.rename(columns={first_col: "Date"}, inplace=True)
        cleaned["Date"] = pd.to_datetime(cleaned["Date"])
        cleaned.set_index("Date", inplace=True)
        cleaned = cleaned.apply(pd.to_numeric, errors="coerce")
        price_df = cleaned
    else:
        price_df = fetch_price_history(ticker, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
    return price_df["Close"]


def evaluate_predictions(
    predictions_path: Path | str,
    metrics_output: Path | str | None = None,
    price_history_path: Path | None = None,
) -> Dict[str, object]:
    """
    Compare stored predictions against realised close prices.

    Args:
        predictions_path: JSON file created by ``run_forecast``.
        metrics_output: Optional path to store evaluation results.

    Returns:
        Dictionary containing metrics and per-date breakdown.
    """
    payload = _load_predictions(predictions_path)
    ticker = payload["ticker"]
    forecast_entries = payload["forecast"]
    forecast_dates = [entry["forecast_date"] for entry in forecast_entries]
    predicted = np.array([entry["predicted_close"] for entry in forecast_entries], dtype=float)

    actual_series = _actuals_for_dates(ticker, forecast_dates, price_history_path=price_history_path)
    actual_values: List[float] = []
    matched_indices: List[int] = []
    for idx, forecast_date in enumerate(forecast_dates):
        ts = pd.Timestamp(forecast_date)
        if ts in actual_series.index:
            actual_values.append(float(actual_series.loc[ts]))
            matched_indices.append(idx)

    if not matched_indices:
        raise ValueError("Actual data not yet available for any forecast dates.")

    actual = np.array(actual_values, dtype=float)
    predicted_subset = predicted[matched_indices]

    errors = predicted_subset - actual
    mae = float(np.mean(np.abs(errors)))
    rmse = float(np.sqrt(np.mean(errors**2)))
    mape = float(np.mean(np.abs(errors / np.maximum(actual, 1e-8))) * 100.0)

    per_date = []
    for dest_idx, src_idx in enumerate(matched_indices):
        per_date.append(
            {
                "forecast_date": forecast_dates[src_idx],
                "predicted_close": float(predicted_subset[dest_idx]),
                "actual_close": float(actual[dest_idx]),
                "error": float(errors[dest_idx]),
                "absolute_error": float(abs(errors[dest_idx])),
                "percent_error": float((errors[dest_idx] / max(actual[dest_idx], 1e-8)) * 100.0),
            }
        )

    results = {
        "ticker": ticker,
        "prediction_file": str(Path(predictions_path).resolve()),
        "evaluated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "metrics": {
            "count": len(actual),
            "mae": mae,
            "rmse": rmse,
            "mape": mape,
        },
        "per_date": per_date,
    }

    if metrics_output:
        metrics_output = Path(metrics_output)
        metrics_output.parent.mkdir(parents=True, exist_ok=True)
        with metrics_output.open("w", encoding="utf-8") as fp:
            json.dump(results, fp, indent=2)

    return results
