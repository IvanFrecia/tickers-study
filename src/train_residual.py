"""Train a residual learner to correct base model forecasts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error

from .config import load_config
from .macro import fetch_macro_features


def _load_prediction_files(predictions_dir: Path) -> List[pd.DataFrame]:
    """Load all prediction CSVs from a pipeline artefact directory."""

    frames: List[pd.DataFrame] = []
    for csv_path in sorted(predictions_dir.glob("predictions_fold_*.csv")):
        df = pd.read_csv(csv_path)
        if not df.empty:
            df["fold"] = df.get("fold", 0)
            frames.append(df)
    if not frames:
        raise FileNotFoundError(f"No prediction CSVs found under {predictions_dir}.")
    return frames


def _attach_macro_features(
    df: pd.DataFrame,
    config_path: Path,
    ticker: str,
) -> Tuple[pd.DataFrame, List[str]]:
    pipeline_config = load_config(config_path)
    ticker_cfg = next((t for t in pipeline_config.tickers if t.symbol == ticker.upper()), None)
    if ticker_cfg is None:
        raise ValueError(f"Ticker '{ticker}' not found in configuration {config_path}.")
    if not ticker_cfg.macro_sources:
        return df, []

    macro_df = fetch_macro_features(
        ticker_cfg.macro_sources,
        start_date=ticker_cfg.start_date,
        end_date=ticker_cfg.end_date,
    )
    macro_df = macro_df.ffill().bfill().fillna(0.0)
    macro_df.index.name = "date"

    df["date_dt"] = pd.to_datetime(df["date"])
    macro_cols = [src.feature_name for src in ticker_cfg.macro_sources]

    merged = df[["date_dt"]].join(macro_df, on="date_dt", how="left")
    merged[macro_cols] = merged[macro_cols].ffill().bfill().fillna(0.0)

    for col in macro_cols:
        df[col] = merged[col].values
    return df, macro_cols


def _prepare_training_data(
    df: pd.DataFrame,
    feature_columns: List[str],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Construct feature and target arrays for residual modelling."""

    df = df.copy()
    df.dropna(subset=["predicted_close", "actual_close"], inplace=True)

    features = df[feature_columns].astype(float)
    X = features.values
    y = (df["actual_close"] - df["predicted_close"]).values

    return X, y, df["predicted_close"].values, df["actual_close"].values


def train_residual_ensemble(
    predictions_dir: Path,
    output_path: Path,
    config_path: Path,
    ticker: str,
) -> Dict[str, float]:
    """Fit a gradient boosting residual model and persist artefacts."""

    frames = _load_prediction_files(predictions_dir)
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])

    base_feature_columns = ["predicted_close", "predicted_return", "horizon_step"]
    df, macro_cols = _attach_macro_features(df, config_path, ticker)
    feature_columns = base_feature_columns + macro_cols

    X, y, base_preds, actuals = _prepare_training_data(df, feature_columns)

    model = GradientBoostingRegressor(random_state=42)
    model.fit(X, y)

    residuals = model.predict(X)
    corrected = base_preds + residuals
    mae = mean_absolute_error(actuals, corrected)
    base_mae = mean_absolute_error(actuals, base_preds)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "feature_columns": feature_columns}, output_path)

    metrics = {
        "base_mae": float(base_mae),
        "corrected_mae": float(mae),
        "macro_features": macro_cols,
    }

    metrics_path = output_path.with_suffix(".json")
    metrics_path.write_text(json.dumps(metrics, indent=2))
    return metrics


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(description="Train residual ensemble on pipeline predictions.")
    parser.add_argument("predictions_dir", type=Path, help="Directory containing predictions_fold_*.csv files.")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Destination path for the residual model (defaults to <predictions_dir>/residual_model.pkl).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/tickers.toml"),
        help="Pipeline configuration used to resolve macro sources.",
    )
    parser.add_argument("--ticker", required=True, help="Ticker symbol corresponding to the predictions.")
    return parser.parse_args()


def main() -> None:
    """Entry point for residual training CLI."""

    args = parse_args()
    output_path = args.output or args.predictions_dir / "residual_model.pkl"
    metrics = train_residual_ensemble(args.predictions_dir, output_path, args.config, args.ticker)
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
