"""High-level orchestration for multi-ticker training and backtesting."""

from __future__ import annotations

import json
import gc
import logging
import random
import shutil
from pathlib import Path
from typing import Dict, Iterable, Optional

import numpy as np
import pandas as pd
import tensorflow as tf

from .artifacts import ArtifactManager
from .backtest import BacktestSummary, run_backtest
from .config import PipelineConfig, TickerConfig, load_config
from .data import fetch_price_history
from .features import build_feature_frame
from .macro import fetch_macro_features


def release_ml_memory() -> None:
    """Drop TensorFlow graph state between ticker runs in long-lived processes."""
    tf.keras.backend.clear_session()
    gc.collect()


def set_global_seed(seed: int) -> None:
    """
    Synchronise RNG state across supported libraries.

    Args:
        seed: Deterministic seed value.
    """
    random.seed(seed)
    np.random.seed(seed)
    tf.random.set_seed(seed)


def configure_logging(level: str) -> None:
    """
    Configure root logging for pipeline execution.

    Args:
        level: Logging level name (e.g., "INFO", "DEBUG").
    """
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )


class PipelineRunner:
    """Coordinate end-to-end execution for each configured ticker."""

    def __init__(self, config: PipelineConfig):
        """
        Initialise a runner from a validated configuration.

        Args:
            config: Loaded `PipelineConfig` instance.
        """
        self.config = config

    def _iter_tickers(self, selected: Optional[Iterable[str]]) -> Iterable[TickerConfig]:
        """
        Yield tickers that should be processed for this run.

        Args:
            selected: Optional iterable of ticker symbols to restrict work.

        Returns:
            Generator over the chosen `TickerConfig` objects.
        """
        if not selected:
            yield from self.config.tickers
            return
        selected_upper = {sym.upper() for sym in selected}
        for ticker_cfg in self.config.tickers:
            if ticker_cfg.symbol in selected_upper:
                yield ticker_cfg

    def run(self, tickers: Optional[Iterable[str]] = None) -> Dict[str, BacktestSummary]:
        """
        Execute the pipeline for each chosen ticker.

        Args:
            tickers: Optional subset of ticker symbols.

        Returns:
            Mapping of ticker symbol to backtest summary.
        """
        set_global_seed(self.config.seed)
        results: Dict[str, BacktestSummary] = {}
        for ticker_cfg in self._iter_tickers(tickers):
            try:
                logging.info("Starting pipeline for %s", ticker_cfg.symbol)
                ticker_cfg.output_dir.mkdir(parents=True, exist_ok=True)
                artifacts = ArtifactManager(ticker_cfg.output_dir, ticker_cfg.symbol)
                artifacts.save_config(self.config, ticker_cfg)

                price_df = fetch_price_history(
                    ticker_cfg.symbol,
                    start_date=ticker_cfg.start_date,
                    end_date=ticker_cfg.end_date,
                )
                if isinstance(price_df.columns, pd.MultiIndex):
                    price_df.columns = [col[0] if isinstance(col, tuple) else col for col in price_df.columns]
                if ticker_cfg.macro_sources:
                    macro_df = fetch_macro_features(
                        ticker_cfg.macro_sources,
                        start_date=ticker_cfg.start_date,
                        end_date=ticker_cfg.end_date,
                    )
                    price_df = pd.concat([price_df, macro_df], axis=1)
                    price_df.ffill(inplace=True)
                artifacts.save_dataframe(price_df, "price_history")

                feature_frame = build_feature_frame(price_df, ticker_cfg.features)
                artifacts.save_dataframe(feature_frame, "feature_frame")

                summary = run_backtest(feature_frame, ticker_cfg, artifacts, seed=self.config.seed)
                results[ticker_cfg.symbol] = summary

                summary_payload = {
                    "ticker": summary.ticker,
                    "aggregated_metrics": summary.aggregated_metrics,
                    "best_fold": summary.best_fold,
                    "folds": [
                        {
                            "fold_index": fold.fold_index,
                            "metrics": fold.metrics,
                            "model_metrics": fold.model_metrics,
                            "history": fold.history,
                            "model_path": str(fold.model_path),
                            "scaler_path": str(fold.scaler_path),
                            "predictions_path": str(fold.predictions_path),
                        }
                        for fold in summary.fold_results
                    ],
                }
                artifacts.save_json(summary_payload, "summary")

                best_result = next(
                    (fold for fold in summary.fold_results if fold.fold_index == summary.best_fold),
                    summary.fold_results[0],
                )
                shutil.copy2(best_result.model_path, artifacts.best_model_path())
                shutil.copy2(best_result.scaler_path, artifacts.best_scaler_path())

                logging.info(
                    "Completed pipeline for %s. Best fold: %d (MAE %.4f)",
                    ticker_cfg.symbol,
                    summary.best_fold,
                    best_result.metrics["MAE"],
                )
            finally:
                release_ml_memory()

        return results


def load_pipeline(config_path: Path | str) -> PipelineRunner:
    """
    Load configuration from disk and prepare a `PipelineRunner`.

    Args:
        config_path: Filesystem path to the TOML configuration.

    Returns:
        Ready-to-run `PipelineRunner` instance.
    """
    config = load_config(config_path)
    configure_logging(config.log_level)
    return PipelineRunner(config)
