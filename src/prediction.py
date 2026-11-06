"""Utilities for generating forecasts from trained models."""

from __future__ import annotations

import json
import gc
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

import joblib
import numpy as np
import pandas as pd
import tensorflow as tf

from .config import PipelineConfig, TickerConfig, load_config
from .data import fetch_price_history
from .features import build_feature_frame
from .market_calendar import (
    following_market_week_end,
    forecast_dates_after,
    latest_market_session_on_or_before,
    market_week_context,
)
from .models import weighted_mse


def _load_ticker_config(config_path: Path | str, ticker: str) -> tuple[PipelineConfig, TickerConfig]:
    pipeline_config = load_config(config_path)
    ticker_upper = ticker.upper()
    for ticker_cfg in pipeline_config.tickers:
        if ticker_cfg.symbol == ticker_upper:
            return pipeline_config, ticker_cfg
    raise ValueError(f"Ticker '{ticker}' not found in config '{config_path}'.")


def _prepare_input_sequence(
    feature_frame: pd.DataFrame,
    feature_columns: Sequence[str],
    scaler,
    window_size: int,
) -> tuple[np.ndarray, List[float], float]:
    scaled = scaler.transform(feature_frame[feature_columns])
    if len(scaled) < window_size:
        raise ValueError("Insufficient history to build inference window.")
    last_window = scaled[-window_size:]
    window_close = feature_frame["Close"].iloc[-window_size:].tolist()
    last_close = float(feature_frame["Close"].iloc[-1])
    return last_window, window_close, last_close


def _forecast_dates(last_date: pd.Timestamp, horizon: int) -> List[str]:
    return forecast_dates_after(last_date, horizon=horizon, exchange="NYSE")


def run_forecast(
    config_path: Path | str,
    ticker: str,
    model_path: Path | str,
    scaler_path: Path | str,
    output_path: Path | str,
    end_date: str | None = None,
    dump_json: bool = True,
    price_history_path: Path | None = None,
) -> Dict[str, object]:
    """
    Generate a multi-step forecast for a ticker using saved artefacts.

    Args:
        config_path: Path to the pipeline configuration file.
        ticker: Ticker symbol to forecast.
        model_path: Path to the saved Keras model.
        scaler_path: Path to the saved MinMax scaler (joblib).
        output_path: File path to store the forecast payload.
        end_date: Optional end date for fetching price history (defaults to today).
        dump_json: When True, serialize the payload to ``output_path``.

    Returns:
        Dictionary containing metadata and forecasted values.
    """
    pipeline_config, ticker_cfg = _load_ticker_config(Path(config_path), ticker)
    feature_columns = ticker_cfg.features.all_features()

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
        price_df = fetch_price_history(
            ticker_cfg.symbol,
            start_date=ticker_cfg.start_date,
            end_date=end_date,
        )
    if end_date:
        price_df = price_df.loc[:end_date]
    feature_frame = build_feature_frame(price_df, ticker_cfg.features)

    scaler = joblib.load(scaler_path)
    last_window, window_close, last_close = _prepare_input_sequence(
        feature_frame, feature_columns, scaler, ticker_cfg.window_size
    )

    model = None
    try:
        model = tf.keras.models.load_model(model_path, custom_objects={"weighted_mse": weighted_mse})
        predicted_returns = model.predict(last_window[np.newaxis, ...], verbose=0)[0]
    finally:
        del model
        tf.keras.backend.clear_session()
        gc.collect()

    predicted_prices = []
    running_price = last_close
    for ret in predicted_returns:
        running_price = running_price * (1.0 + ret)
        predicted_prices.append(float(running_price))

    last_obs_date = latest_market_session_on_or_before(feature_frame.index[-1])
    horizon = len(predicted_prices)
    forecast_dates = _forecast_dates(last_obs_date, horizon)
    target_week_end_date = following_market_week_end(last_obs_date)
    calendar_context = market_week_context(target_week_end_date)
    calendar_context["target_week_end_date"] = target_week_end_date.isoformat()

    payload = {
        "ticker": ticker_cfg.symbol,
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "config": {
            "config_path": str(Path(config_path).resolve()),
            "window_size": ticker_cfg.window_size,
            "forecast_horizon": horizon,
            "configured_forecast_horizon": ticker_cfg.forecast_horizon,
            "features": feature_columns,
            "target": ticker_cfg.features.target,
        },
        "model_path": str(Path(model_path).resolve()),
        "scaler_path": str(Path(scaler_path).resolve()),
        "last_observation_date": last_obs_date.isoformat(),
        "market_calendar": calendar_context,
        "context": {
            "window_close": window_close,
            "last_close": last_close,
            "target_week_end_date": target_week_end_date.isoformat(),
            "latest_market_session_date": calendar_context.get("latest_market_session_date"),
            "next_market_session_date": calendar_context.get("next_market_session_date"),
        },
        "forecast": [
            {
                "horizon": idx + 1,
                "forecast_date": f_date,
                "predicted_close": float(predicted_prices[idx]),
                "predicted_return": float(predicted_returns[idx]),
            }
            for idx, f_date in enumerate(forecast_dates)
        ],
    }

    if dump_json:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as fp:
            json.dump(payload, fp, indent=2)
        logging.info("Forecast saved to %s", output_path)

    return payload
