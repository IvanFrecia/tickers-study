"""Regression tests for forecast generation."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from src.config import BacktestConfig, FeatureConfig, ModelConfig, PipelineConfig, TickerConfig
from src.prediction import run_forecast


class PredictionTests(unittest.TestCase):
    def test_run_forecast_uses_model_output_horizon_for_dates(self) -> None:
        ticker_cfg = TickerConfig(
            symbol="GOOG",
            start_date="2010-01-01",
            end_date=None,
            window_size=5,
            forecast_horizon=3,
            features=FeatureConfig(raw=["Close"], engineered=[], target="Close"),
            model=ModelConfig(),
            backtest=BacktestConfig(),
            output_dir=Path("artifacts"),
        )
        pipeline_cfg = PipelineConfig(
            seed=42,
            data_source="yfinance",
            artifact_root=Path("artifacts"),
            log_level="INFO",
            tickers=[ticker_cfg],
        )

        feature_frame = pd.DataFrame({"Close": [100.0]}, index=pd.to_datetime(["2026-03-20"]))
        model = MagicMock()
        model.predict.return_value = np.array([[0.01, 0.02, 0.03, 0.04, 0.05]], dtype=float)

        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "forecast.json"
            with (
                patch("src.prediction._load_ticker_config", return_value=(pipeline_cfg, ticker_cfg)),
                patch("src.prediction.fetch_price_history", return_value=feature_frame),
                patch("src.prediction.build_feature_frame", return_value=feature_frame),
                patch(
                    "src.prediction._prepare_input_sequence",
                    return_value=(np.zeros((5, 1), dtype=float), [99.0, 100.0], 100.0),
                ),
                patch("src.prediction.joblib.load", return_value=MagicMock()),
                patch("src.prediction.tf.keras.models.load_model", return_value=model),
                patch("src.prediction.tf.keras.backend.clear_session"),
                patch("src.prediction.gc.collect"),
            ):
                payload = run_forecast(
                    config_path="configs/tickers.toml",
                    ticker="GOOG",
                    model_path=Path(tmpdir) / "best_model.keras",
                    scaler_path=Path(tmpdir) / "best_scaler.pkl",
                    output_path=output_path,
                    dump_json=False,
                )

        forecast = payload["forecast"]
        self.assertEqual(len(forecast), 5)
        self.assertEqual([row["forecast_date"] for row in forecast], [
            "2026-03-23",
            "2026-03-24",
            "2026-03-25",
            "2026-03-26",
            "2026-03-27",
        ])
        self.assertEqual(payload["config"]["forecast_horizon"], 5)
        self.assertEqual(payload["config"]["configured_forecast_horizon"], 3)
        self.assertEqual(payload["context"]["target_week_end_date"], "2026-03-27")
        self.assertEqual(payload["market_calendar"]["target_week_end_date"], "2026-03-27")


if __name__ == "__main__":
    unittest.main()
