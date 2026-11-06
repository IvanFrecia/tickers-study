"""Configuration models and loaders for the ticker forecasting pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import copy
import tomllib


class ConfigError(Exception):
    """Raised when pipeline configuration parsing or validation fails."""


@dataclass
class FeatureConfig:
    """Declarative description of raw and engineered feature columns."""

    raw: List[str] = field(default_factory=list)
    engineered: List[str] = field(default_factory=list)
    target: str = "Close"

    def all_features(self) -> List[str]:
        """
        Return the feature columns to materialise for modelling.

        The returned list preserves ordering from `raw` followed by `engineered`
        while removing duplicates to align downstream scaling/sequence building.

        Returns:
            Ordered feature names ready for dataframe selection.
        """
        ordered: List[str] = []
        for name in self.raw + self.engineered:
            if name not in ordered:
                ordered.append(name)
        return ordered

    def validate(self) -> None:
        """
        Ensure the feature configuration is internally consistent.

        Raises:
            ConfigError: When the declared target column is missing from the
                combined raw/engineered feature set.
        """
        if self.target not in self.raw and self.target not in self.engineered:
            raise ConfigError(f"Target column '{self.target}' must be part of the feature set.")


@dataclass
class ModelConfig:
    """Hyperparameter bundle for the sequence model."""

    type: str = "lstm"
    lstm_units: List[int] = field(default_factory=lambda: [128, 64])
    dropout: float = 0.2
    learning_rate: float = 0.001
    epochs: int = 50
    batch_size: int = 64
    early_stopping_patience: int = 10
    loss: str = "weighted_mse"
    metrics: List[str] = field(default_factory=lambda: ["mae"])

    def validate(self) -> None:
        """
        Validate the model configuration before training.

        Raises:
            ConfigError: If any numerical parameter is nonsensical or if the
                requested model type is unsupported.
        """
        allowed = {"lstm", "seq2seq", "seq2seq_lstm", "transformer", "attention"}
        if self.type.lower() not in allowed:
            raise ConfigError(
                f"Unsupported model type '{self.type}'. Supported types: {', '.join(sorted(allowed))}."
            )
        if not self.lstm_units:
            raise ConfigError("At least one LSTM layer must be specified.")
        if any(units <= 0 for units in self.lstm_units):
            raise ConfigError("LSTM units must be positive integers.")
        if self.epochs <= 0:
            raise ConfigError("Epochs must be a positive integer.")
        if self.batch_size <= 0:
            raise ConfigError("Batch size must be a positive integer.")


@dataclass
class BacktestConfig:
    """Parameters controlling walk-forward evaluation."""

    splits: int = 3
    step: int = 60
    val_ratio: float = 0.15
    test_ratio: float = 0.15
    min_train_points: int = 500

    def validate(self) -> None:
        """
        Validate walk-forward backtest settings before execution.

        Raises:
            ConfigError: If any ratio, split count, or step size is invalid,
                or if the dataset would be over-partitioned.
        """
        if self.splits <= 0:
            raise ConfigError("Backtest splits must be a positive integer.")
        if self.step <= 0:
            raise ConfigError("Backtest step must be a positive integer.")
        if not 0 < self.val_ratio < 1:
            raise ConfigError("Validation ratio must be in the interval (0, 1).")
        if not 0 < self.test_ratio < 1:
            raise ConfigError("Test ratio must be in the interval (0, 1).")
        if self.val_ratio + self.test_ratio >= 0.95:
            raise ConfigError("Validation and test ratios leave insufficient room for training data.")
        if self.min_train_points <= 0:
            raise ConfigError("Minimum train points must be a positive integer.")


@dataclass
class MacroSourceConfig:
    """Configuration for external macro/market features."""

    symbol: str
    feature_name: str
    transform: str = "log_return"

    def validate(self) -> None:
        """Validate the macro source definition."""

        if not self.symbol:
            raise ConfigError("Macro source symbol cannot be empty.")
        if not self.feature_name:
            raise ConfigError("Macro source feature_name cannot be empty.")
        if self.transform not in {"log_return", "pct_return", "level"}:
            raise ConfigError(
                "Macro source transform must be one of {'log_return', 'pct_return', 'level'}."
            )


@dataclass
class TickerConfig:
    """Ticker-specific overrides built by merging pipeline defaults."""

    symbol: str
    start_date: str
    end_date: Optional[str]
    window_size: int
    forecast_horizon: int
    features: FeatureConfig
    model: ModelConfig
    backtest: BacktestConfig
    output_dir: Path
    macro_sources: List[MacroSourceConfig] = field(default_factory=list)

    def validate(self) -> None:
        """
        Validate the ticker-specific configuration envelope.

        Raises:
            ConfigError: When required identifiers are missing or numerical
                parameters fall outside supported ranges.
        """
        if not self.symbol:
            raise ConfigError("Ticker symbol cannot be empty.")
        if self.window_size <= 0:
            raise ConfigError("Window size must be a positive integer.")
        if self.forecast_horizon <= 0:
            raise ConfigError("Forecast horizon must be a positive integer.")
        if self.window_size < 5:
            raise ConfigError("Window size is too small. Use at least 5 timesteps.")
        if self.forecast_horizon > 90:
            raise ConfigError("Forecast horizon is too large for the current pipeline (max 90).")
        self.features.validate()
        self.model.validate()
        self.backtest.validate()
        seen_macros = set()
        for source in self.macro_sources:
            source.validate()
            if source.feature_name in seen_macros:
                raise ConfigError(
                    f"Duplicate macro feature name '{source.feature_name}' for ticker {self.symbol}."
                )
            seen_macros.add(source.feature_name)


@dataclass
class PipelineConfig:
    """Top-level configuration for the multi-ticker pipeline."""

    seed: int
    data_source: str
    artifact_root: Path
    log_level: str
    tickers: List[TickerConfig]

    def validate(self) -> None:
        """
        Validate the overall pipeline configuration.

        Raises:
            ConfigError: If no tickers are defined or any ticker config fails
                its own validation.
        """
        if not self.tickers:
            raise ConfigError("At least one ticker must be configured.")
        for ticker in self.tickers:
            ticker.validate()


def deep_merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively merge two dictionaries without mutating the inputs.

    Args:
        base: Baseline configuration dictionary.
        override: Dictionary containing overrides that should replace or extend
            the base.

    Returns:
        A deep copy of `base` with values from `override` applied.
    """
    merged: Dict[str, Any] = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: Path | str) -> PipelineConfig:
    """
    Load and validate the pipeline configuration from a TOML file.

    Args:
        path: Filesystem path pointing to the TOML configuration.

    Returns:
        A fully validated `PipelineConfig` object ready for use.

    Raises:
        ConfigError: If the file is missing, badly formed, or fails validation.
    """
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"Configuration file '{config_path}' does not exist.")

    with config_path.open("rb") as fp:
        raw_config = tomllib.load(fp)

    return build_pipeline_config(raw_config, source=config_path)


def build_pipeline_config(raw_config: Dict[str, Any], *, source: Path | None = None) -> PipelineConfig:
    """
    Construct a validated `PipelineConfig` from a raw dictionary.

    Args:
        raw_config: Dictionary loaded from TOML or another source.
        source: Optional path reference used for error reporting.

    Returns:
        Validated pipeline configuration.

    Raises:
        ConfigError: If the provided dictionary is incomplete or invalid.
    """

    pipeline_section: Dict[str, Any] = raw_config.get("pipeline", {})
    defaults_section: Dict[str, Any] = raw_config.get("defaults", {})
    tickers_section: Dict[str, Any] = raw_config.get("tickers", {})

    if not tickers_section:
        raise ConfigError("No tickers specified under [tickers].")

    seed = int(pipeline_section.get("seed", 42))
    artifact_root = Path(pipeline_section.get("artifact_root", "artifacts"))
    data_source = pipeline_section.get("data_source", "yfinance")
    log_level = pipeline_section.get("log_level", "INFO")

    tickers: List[TickerConfig] = []
    for symbol, override in tickers_section.items():
        combined = deep_merge_dicts(defaults_section, override or {})

        if "start_date" not in combined:
            raise ConfigError(f"Ticker '{symbol}' must specify a start_date (directly or via defaults).")

        feature_section = combined.get("features", {}) or {}
        model_section = combined.get("model", {}) or {}
        backtest_section = combined.get("backtest", {}) or {}
        macro_section = combined.get("macro_sources", []) or []

        features = FeatureConfig(
            raw=list(feature_section.get("raw", [])),
            engineered=list(feature_section.get("engineered", [])),
            target=feature_section.get("target", "Close"),
        )

        model = ModelConfig(
            type=model_section.get("type", "lstm"),
            lstm_units=list(model_section.get("lstm_units", [128, 64])),
            dropout=float(model_section.get("dropout", 0.2)),
            learning_rate=float(model_section.get("learning_rate", 0.001)),
            epochs=int(model_section.get("epochs", 50)),
            batch_size=int(model_section.get("batch_size", 64)),
            early_stopping_patience=int(model_section.get("early_stopping_patience", 10)),
            loss=model_section.get("loss", "weighted_mse"),
            metrics=list(model_section.get("metrics", ["mae"])),
        )

        backtest = BacktestConfig(
            splits=int(backtest_section.get("splits", 3)),
            step=int(backtest_section.get("step", 60)),
            val_ratio=float(backtest_section.get("val_ratio", 0.15)),
            test_ratio=float(backtest_section.get("test_ratio", 0.15)),
            min_train_points=int(backtest_section.get("min_train_points", 500)),
        )

        macro_sources = [
            MacroSourceConfig(
                symbol=str(entry.get("symbol", "")),
                feature_name=str(entry.get("feature_name", "")),
                transform=str(entry.get("transform", "log_return")).lower(),
            )
            for entry in macro_section
        ]

        output_dir = Path(combined.get("output_dir", artifact_root))

        ticker_config = TickerConfig(
            symbol=symbol.upper(),
            start_date=combined.get("start_date"),
            end_date=combined.get("end_date") or None,
            window_size=int(combined.get("window_size", 60)),
            forecast_horizon=int(combined.get("forecast_horizon", 5)),
            features=features,
            model=model,
            backtest=backtest,
            output_dir=output_dir,
            macro_sources=macro_sources,
        )
        tickers.append(ticker_config)

    pipeline_config = PipelineConfig(
        seed=seed,
        data_source=data_source,
        artifact_root=artifact_root,
        log_level=log_level,
        tickers=tickers,
    )
    pipeline_config.validate()
    return pipeline_config
