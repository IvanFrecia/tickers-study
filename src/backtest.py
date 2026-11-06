"""Walk-forward backtesting and evaluation helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler
from tensorflow.keras import callbacks

from .artifacts import ArtifactManager
from .config import TickerConfig
from .models import create_forecaster


@dataclass
class FoldResult:
    """Container capturing artefacts and metrics for a single fold."""

    fold_index: int
    metrics: Dict[str, float]
    model_metrics: Dict[str, float]
    history: Dict[str, List[float]]
    model_path: Path
    scaler_path: Path
    predictions_path: Path


@dataclass
class BacktestSummary:
    """Aggregate view across all folds for a ticker."""

    ticker: str
    fold_results: List[FoldResult]
    aggregated_metrics: Dict[str, float]
    best_fold: int


def _generate_backtest_windows(feature_df: pd.DataFrame, config: TickerConfig):
    """
    Split the feature dataframe into rolling train/val/test windows.

    Args:
        feature_df: Model-ready dataframe sorted by date.
        config: Ticker configuration controlling window parameters.

    Returns:
        List of tuples (fold_index, train_df, val_df, test_df).

    Raises:
        ValueError: If insufficient data exists to satisfy the configuration.
    """
    bt = config.backtest
    total = len(feature_df)
    if total < bt.min_train_points + config.window_size + config.forecast_horizon:
        raise ValueError(
            f"Not enough data for {config.symbol}. Require at least "
            f"{bt.min_train_points + config.window_size + config.forecast_horizon} rows, got {total}."
        )

    val_window = max(int(total * bt.val_ratio), config.window_size + config.forecast_horizon)
    test_window = max(int(total * bt.test_ratio), config.window_size + config.forecast_horizon)
    min_train = max(bt.min_train_points, config.window_size + config.forecast_horizon)

    windows: List[Tuple[int, pd.DataFrame, pd.DataFrame, pd.DataFrame]] = []
    fold = 0
    while fold < bt.splits:
        test_end = total - fold * bt.step
        test_start = test_end - test_window
        val_end = test_start
        val_start = val_end - val_window
        train_end = val_start
        train_start = train_end - min_train
        if train_start < 0 or test_start < 0:
            logging.info(
                "Stopping backtest window generation for %s at fold %d (insufficient history).",
                config.symbol,
                fold,
            )
            break
        train_df = feature_df.iloc[train_start:train_end]
        val_df = feature_df.iloc[val_start:val_end]
        test_df = feature_df.iloc[test_start:test_end]
        windows.append((fold, train_df, val_df, test_df))
        fold += 1

    if not windows:
        raise ValueError(f"Unable to build any backtest window for {config.symbol}.")
    return windows


def _build_sequences(
    feature_values: np.ndarray,
    target_returns: np.ndarray,
    close_values: np.ndarray,
    window_size: int,
    horizon: int,
):
    """
    Convert arrays into supervised learning sequences for return forecasting.

    Args:
        feature_values: 2D array of scaled feature values.
        target_returns: 1D array of returns to predict.
        close_values: 1D array of closing prices aligned with target_returns.
        window_size: Number of timesteps per input sequence.
        horizon: Forecast horizon length.

    Returns:
        Tuple (X, y_returns, base_prices, future_prices, indices).
    """
    length = len(target_returns)
    if length < window_size + horizon:
        empty_shape = (0, window_size, feature_values.shape[1])
        return np.empty(empty_shape), np.empty((0, horizon)), np.empty(0), np.empty((0, horizon)), []
    X, y, bases, futures, indices = [], [], [], [], []
    for idx in range(window_size, length - horizon + 1):
        start = idx - window_size
        X.append(feature_values[start:idx])
        y.append(target_returns[idx: idx + horizon])
        bases.append(close_values[idx - 1])
        futures.append(close_values[idx: idx + horizon])
        indices.append(idx)
    return np.asarray(X), np.asarray(y), np.asarray(bases), np.asarray(futures), indices


def _aggregate_metrics(results: List[FoldResult]) -> Dict[str, float]:
    """
    Compute mean metrics across folds for summary reporting.

    Args:
        results: List of per-fold results.

    Returns:
        Dictionary mapping metric name to averaged value.
    """
    if not results:
        return {}
    keys = results[0].metrics.keys()
    aggregated = {}
    for key in keys:
        aggregated[key] = float(np.mean([fold.metrics[key] for fold in results]))
    return aggregated


def run_backtest(
    feature_frame: pd.DataFrame,
    ticker_config: TickerConfig,
    artifacts: ArtifactManager,
    seed: int,
) -> BacktestSummary:
    """
    Execute a full walk-forward backtest for a ticker.

    Args:
        feature_frame: Model-ready dataframe (features + target).
        ticker_config: Configuration for the ticker under test.
        artifacts: Artefact manager handling persistence.
        seed: Random seed for reproducibility (currently unused but logged).

    Returns:
        BacktestSummary consolidating per-fold results.
    """
    feature_columns = ticker_config.features.all_features()
    target_column = ticker_config.features.target

    windows = _generate_backtest_windows(feature_frame, ticker_config)
    results: List[FoldResult] = []
    best_fold = None
    best_mae = float("inf")

    for fold_index, train_df, val_df, test_df in windows:
        logging.info(
            "Fold %d for %s: train=%d, val=%d, test=%d",
            fold_index,
            ticker_config.symbol,
            len(train_df),
            len(val_df),
            len(test_df),
        )

        scaler = StandardScaler()
        scaler.fit(train_df[feature_columns])

        train_features = scaler.transform(train_df[feature_columns])
        val_features = scaler.transform(val_df[feature_columns])
        test_features = scaler.transform(test_df[feature_columns])

        X_train, y_train, _, _, _ = _build_sequences(
            train_features,
            train_df[target_column].values,
            train_df["Close"].values,
            ticker_config.window_size,
            ticker_config.forecast_horizon,
        )
        X_val, y_val, _, _, _ = _build_sequences(
            val_features,
            val_df[target_column].values,
            val_df["Close"].values,
            ticker_config.window_size,
            ticker_config.forecast_horizon,
        )
        X_test, y_test, base_prices_test, future_prices_test, test_indices = _build_sequences(
            test_features,
            test_df[target_column].values,
            test_df["Close"].values,
            ticker_config.window_size,
            ticker_config.forecast_horizon,
        )

        if not len(X_train) or not len(X_val) or not len(X_test):
            logging.warning("Skipping fold %d for %s due to insufficient sequence data.", fold_index, ticker_config.symbol)
            continue

        forecaster = create_forecaster(ticker_config.model, ticker_config.forecast_horizon)
        early_stop = callbacks.EarlyStopping(
            monitor="val_loss",
            patience=ticker_config.model.early_stopping_patience,
            restore_best_weights=True,
        )
        reduce_lr = callbacks.ReduceLROnPlateau(
            monitor="val_loss",
            patience=max(2, ticker_config.model.early_stopping_patience // 2),
            factor=0.5,
            verbose=0,
        )

        history = forecaster.fit(
            X_train,
            y_train,
            X_val,
            y_val,
            cb=[early_stop, reduce_lr],
            verbose=0,
        )

        test_scores = forecaster.evaluate(X_test, y_test)
        model_metrics = dict(zip(forecaster.model.metrics_names, test_scores))
        val_scores = forecaster.model.evaluate(X_val, y_val, verbose=0)
        if isinstance(val_scores, (list, tuple)):
            model_metrics["val_loss"] = float(val_scores[0])
        else:
            model_metrics["val_loss"] = float(val_scores)

        pred_returns = forecaster.predict(X_test)

        preds_prices = []
        actual_prices = []
        for base_price, pred_seq, actual_seq, future_prices in zip(
            base_prices_test, pred_returns, y_test, future_prices_test
        ):
            price_pred = []
            running_price = base_price
            for ret in pred_seq:
                running_price = running_price * (1.0 + ret)
                price_pred.append(running_price)
            preds_prices.append(price_pred)
            actual_prices.append(future_prices)

        preds_prices = np.asarray(preds_prices)
        actual_prices = np.asarray(actual_prices)

        preds_flat = preds_prices.reshape(-1)
        actuals_flat = actual_prices.reshape(-1)

        rmse = float(np.sqrt(mean_squared_error(actuals_flat, preds_flat)))
        mae = float(mean_absolute_error(actuals_flat, preds_flat))
        mape = float(np.mean(np.abs((actuals_flat - preds_flat) / np.maximum(np.abs(actuals_flat), 1e-8))) * 100.0)
        r2 = float(r2_score(actuals_flat, preds_flat))

        metrics = {
            "RMSE": rmse,
            "MAE": mae,
            "MAPE": mape,
            "R2": r2,
        }

        predictions_records = []
        for seq_idx, target_start in enumerate(test_indices):
            forecast_dates = test_df.index[target_start: target_start + ticker_config.forecast_horizon]
            for horizon_step, forecast_date in enumerate(forecast_dates):
                predictions_records.append(
                    {
                        "fold": fold_index,
                        "horizon_step": horizon_step + 1,
                        "date": forecast_date.strftime("%Y-%m-%d"),
                        "actual_close": float(actual_prices[seq_idx, horizon_step]),
                        "predicted_close": float(preds_prices[seq_idx, horizon_step]),
                        "actual_return": float(y_test[seq_idx, horizon_step]),
                        "predicted_return": float(pred_returns[seq_idx, horizon_step]),
                    }
                )

        predictions_df = pd.DataFrame(predictions_records)
        predictions_path = artifacts.save_dataframe(predictions_df, f"predictions_fold_{fold_index}")

        forecaster.save(artifacts.model_checkpoint_path(fold_index))
        scaler_path = artifacts.scaler_checkpoint_path(fold_index)
        joblib.dump(scaler, scaler_path)

        fold_result = FoldResult(
            fold_index=fold_index,
            metrics=metrics,
            model_metrics=model_metrics,
            history=history.history,
            model_path=artifacts.model_checkpoint_path(fold_index),
            scaler_path=scaler_path,
            predictions_path=predictions_path,
        )
        results.append(fold_result)

        if mae <= best_mae:
            best_mae = mae
            best_fold = fold_index

        artifacts.save_json(
            {
                "metrics": metrics,
                "model_metrics": model_metrics,
                "history": history.history,
            },
            f"fold_{fold_index}",
        )

    if not results:
        raise ValueError(f"All folds skipped for {ticker_config.symbol}. Increase data availability or adjust config.")

    aggregated = _aggregate_metrics(results)
    summary = BacktestSummary(
        ticker=ticker_config.symbol,
        fold_results=results,
        aggregated_metrics=aggregated,
        best_fold=best_fold if best_fold is not None else results[0].fold_index,
    )

    return summary
