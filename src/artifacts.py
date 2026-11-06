"""Artefact management utilities for the forecasting pipeline."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from .config import PipelineConfig, TickerConfig


class ArtifactManager:
    """Utility class responsible for organising run artefacts on disk."""

    SUBDIRS = ("data", "models", "scalers", "plots", "metrics", "reports")

    def __init__(self, root: Path, ticker: str, run_name: Optional[str] = None) -> None:
        """
        Create a new artefact manager for a ticker run.

        Args:
            root: Root directory that stores all ticker artefacts.
            ticker: Uppercase ticker symbol.
            run_name: Optional human-readable identifier; defaults to timestamp.
        """
        timestamp = run_name or datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        self.run_dir = Path(root) / ticker / timestamp
        for subdir in self.SUBDIRS:
            (self.run_dir / subdir).mkdir(parents=True, exist_ok=True)

    @property
    def data_dir(self) -> Path:
        """Return the directory where data CSVs are stored."""
        return self.run_dir / "data"

    @property
    def model_dir(self) -> Path:
        """Return the directory containing trained model artefacts."""
        return self.run_dir / "models"

    @property
    def scaler_dir(self) -> Path:
        """Return the directory containing fitted scalers."""
        return self.run_dir / "scalers"

    @property
    def metrics_dir(self) -> Path:
        """Return the metrics directory (per-fold and summary JSON)."""
        return self.run_dir / "metrics"

    @property
    def plots_dir(self) -> Path:
        """Return the directory reserved for generated plots."""
        return self.run_dir / "plots"

    @property
    def reports_dir(self) -> Path:
        """Return the directory containing configuration snapshots."""
        return self.run_dir / "reports"

    def save_config(self, pipeline_cfg: PipelineConfig, ticker_cfg: TickerConfig) -> None:
        """
        Persist the current pipeline/ticker configuration for reproducibility.

        Args:
            pipeline_cfg: Validated pipeline configuration.
            ticker_cfg: Ticker-specific configuration bundle.
        """
        payload: Dict[str, Any] = {
            "pipeline": {
                "seed": pipeline_cfg.seed,
                "data_source": pipeline_cfg.data_source,
                "artifact_root": str(pipeline_cfg.artifact_root),
                "log_level": pipeline_cfg.log_level,
            },
            "ticker": {
                **asdict(ticker_cfg),
                "output_dir": str(ticker_cfg.output_dir),
            },
        }
        path = self.reports_dir / "config.json"
        with path.open("w", encoding="utf-8") as fp:
            json.dump(payload, fp, indent=2)

    def save_dataframe(self, df: pd.DataFrame, name: str) -> Path:
        """
        Write a dataframe artefact to the run directory.

        Args:
            df: DataFrame to persist.
            name: Logical name used as the filename stem.

        Returns:
            Path to the created CSV file.
        """
        path = self.data_dir / f"{name}.csv"
        df.to_csv(path, index=True)
        return path

    def save_json(self, payload: Dict[str, Any], name: str) -> Path:
        """
        Write a JSON artefact (typically metrics or reports).

        Args:
            payload: JSON-serialisable dictionary.
            name: Filename stem for the JSON artefact.

        Returns:
            Path to the generated JSON file.
        """
        path = self.metrics_dir / f"{name}.json"
        with path.open("w", encoding="utf-8") as fp:
            json.dump(payload, fp, indent=2)
        return path

    def model_checkpoint_path(self, fold_index: int) -> Path:
        """
        Return the prospective path for a fold-specific trained model.

        Args:
            fold_index: Backtest fold identifier.
        """
        return self.model_dir / f"fold_{fold_index}_model.keras"

    def scaler_checkpoint_path(self, fold_index: int) -> Path:
        """
        Return the prospective path for a fold-specific scaler pickle.

        Args:
            fold_index: Backtest fold identifier.
        """
        return self.scaler_dir / f"fold_{fold_index}_scaler.pkl"

    def best_model_path(self) -> Path:
        """Return the canonical path for the selected best model."""
        return self.model_dir / "best_model.keras"

    def best_scaler_path(self) -> Path:
        """Return the canonical path for the scaler paired with the best model."""
        return self.scaler_dir / "best_scaler.pkl"
