"""Feature engineering utilities for ticker time-series data."""

from __future__ import annotations

import logging
from typing import Iterable

import numpy as np
import pandas as pd

from .config import FeatureConfig


def _ensure_close_column(df: pd.DataFrame) -> None:
    """
    Guard that a dataframe contains the `Close` column required for features.

    Args:
        df: DataFrame that should contain closing prices.

    Raises:
        ValueError: If `Close` is missing.
    """
    if "Close" not in df.columns:
        raise ValueError("Expected 'Close' column to compute engineered features.")


def _compute_daily_return(df: pd.DataFrame) -> pd.Series:
    """
    Compute simple daily percentage returns.

    Args:
        df: Price dataframe including a `Close` column.

    Returns:
        Series of pct-change values aligned to the dataframe index.
    """
    return df["Close"].pct_change()


def _compute_log_return(df: pd.DataFrame) -> pd.Series:
    """
    Compute log returns for the close price series.

    Args:
        df: Price dataframe including a `Close` column.

    Returns:
        Series of log-return values.
    """
    return np.log(df["Close"]).diff()


def _compute_sma(df: pd.DataFrame, window: int) -> pd.Series:
    """
    Compute a simple moving average over the closing price.

    Args:
        df: Price dataframe including `Close`.
        window: Window length in days.

    Returns:
        Series containing the SMA; leading values are NaN until the window is full.
    """
    return df["Close"].rolling(window=window, min_periods=window).mean()


def _compute_ema(df: pd.DataFrame, window: int) -> pd.Series:
    """
    Compute an exponential moving average over the closing price.

    Args:
        df: Price dataframe including `Close`.
        window: EMA span in days.

    Returns:
        EMA series aligned to the dataframe index.
    """
    return df["Close"].ewm(span=window, adjust=False).mean()


def _compute_volatility(df: pd.DataFrame, window: int) -> pd.Series:
    """
    Compute rolling volatility from daily returns.

    Args:
        df: Price dataframe containing `Daily_Return` or `Close`.
        window: Rolling standard deviation window length.

    Returns:
        Volatility series calculated from daily returns.
    """
    returns = df.get("Daily_Return")
    if returns is None:
        returns = _compute_daily_return(df)
    return returns.rolling(window=window, min_periods=window).std()


def _compute_high_low_range(df: pd.DataFrame) -> pd.Series:
    """Return the intraday trading range (high minus low)."""
    return df["High"] - df["Low"]


def _compute_true_range(df: pd.DataFrame) -> pd.Series:
    """Return the Wilder's True Range time series."""
    prev_close = df["Close"].shift(1)
    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - prev_close).abs()
    low_close = (df["Low"] - prev_close).abs()
    stacked = pd.concat([high_low, high_close, low_close], axis=1)
    return stacked.max(axis=1)


def _compute_atr(df: pd.DataFrame, window: int, true_range: pd.Series | None = None) -> pd.Series:
    """Return the Average True Range over the supplied window."""
    tr = true_range if true_range is not None else _compute_true_range(df)
    return tr.rolling(window=window, min_periods=window).mean()


def _compute_rsi(df: pd.DataFrame, window: int) -> pd.Series:
    """Compute the Relative Strength Index for closing prices."""
    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1 / window, min_periods=window).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def _compute_macd(df: pd.DataFrame, fast: int, slow: int, signal: int) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Compute MACD line, signal line, and histogram."""
    ema_fast = df["Close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["Close"].ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    histogram = macd - signal_line
    return macd, signal_line, histogram


def _compute_obv(df: pd.DataFrame) -> pd.Series:
    """Compute On-Balance Volume."""
    direction = np.sign(df["Close"].diff().fillna(0.0))
    return (direction * df["Volume"]).cumsum()


def _compute_volume_zscore(df: pd.DataFrame, window: int) -> pd.Series:
    """Compute rolling z-score of volume."""
    rolling_mean = df["Volume"].rolling(window=window, min_periods=window).mean()
    rolling_std = df["Volume"].rolling(window=window, min_periods=window).std()
    return (df["Volume"] - rolling_mean) / rolling_std.replace(0, np.nan)


def _compute_close_open_ratio(df: pd.DataFrame) -> pd.Series:
    """Compute the ratio of close to open price."""
    return df["Close"] / df["Open"]


def _compute_return(df: pd.DataFrame, window: int) -> pd.Series:
    """Compute percentage change over the specified window."""
    return df["Close"].pct_change(periods=window)


def apply_engineered_features(df: pd.DataFrame, features: Iterable[str]) -> pd.DataFrame:
    """
    Augment a dataframe with engineered feature columns.

    Args:
        df: Base price dataframe.
        features: Iterable of feature identifiers to create (e.g., "SMA_10").

    Returns:
        New dataframe containing the original data plus requested features.

    Raises:
        ValueError: If an unsupported feature name is provided.
    """
    enriched = df.copy()
    _ensure_close_column(enriched)

    true_range_cache: pd.Series | None = None
    macd_cache: dict[tuple[int, int, int], tuple[pd.Series, pd.Series, pd.Series]] = {}

    for name in features:
        if name in enriched.columns:
            # Column already exists (perhaps pre-computed); skip.
            continue
        if name == "Daily_Return":
            enriched[name] = _compute_daily_return(enriched)
        elif name == "Log_Return":
            enriched[name] = _compute_log_return(enriched)
        elif name == "High_Low_Range":
            enriched[name] = _compute_high_low_range(enriched)
        elif name == "True_Range":
            if true_range_cache is None:
                true_range_cache = _compute_true_range(enriched)
            enriched[name] = true_range_cache
        elif name.startswith("SMA_"):
            window = int(name.split("_", 1)[1])
            enriched[name] = _compute_sma(enriched, window)
        elif name.startswith("EMA_"):
            window = int(name.split("_", 1)[1])
            enriched[name] = _compute_ema(enriched, window)
        elif name.startswith("Volatility_"):
            window = int(name.split("_", 1)[1])
            if "Daily_Return" not in enriched.columns:
                logging.debug("Adding Daily_Return to support %s computation", name)
                enriched["Daily_Return"] = _compute_daily_return(enriched)
            enriched[name] = _compute_volatility(enriched, window)
        elif name.startswith("Vol_Regime_"):
            token = name.split("_", 2)
            window = int(token[2]) if len(token) > 2 else int(token[1])
            if "Daily_Return" not in enriched.columns:
                logging.debug("Adding Daily_Return to support %s computation", name)
                enriched["Daily_Return"] = _compute_daily_return(enriched)
            rolling_vol = _compute_volatility(enriched, window)
            median_vol = rolling_vol.rolling(window=252, min_periods=window).median()
            enriched[name] = (rolling_vol > median_vol).astype(float)
        elif name.startswith("ATR_"):
            window = int(name.split("_", 1)[1])
            if true_range_cache is None:
                true_range_cache = _compute_true_range(enriched)
            enriched[name] = _compute_atr(enriched, window, true_range=true_range_cache)
        elif name.startswith("RSI_"):
            window = int(name.split("_", 1)[1])
            enriched[name] = _compute_rsi(enriched, window)
        elif name.startswith("MACD_SIGNAL_"):
            params = name[len("MACD_SIGNAL_") :].split("_")
            if len(params) != 3:
                raise ValueError(f"MACD signal feature '{name}' must follow MACD_SIGNAL_fast_slow_signal format.")
            fast, slow, signal = map(int, params)
            key = (fast, slow, signal)
            if key not in macd_cache:
                macd_cache[key] = _compute_macd(enriched, fast, slow, signal)
            _, signal_line, _ = macd_cache[key]
            enriched[name] = signal_line
        elif name.startswith("MACD_HIST_"):
            params = name[len("MACD_HIST_") :].split("_")
            if len(params) != 3:
                raise ValueError(f"MACD histogram feature '{name}' must follow MACD_HIST_fast_slow_signal format.")
            fast, slow, signal = map(int, params)
            key = (fast, slow, signal)
            if key not in macd_cache:
                macd_cache[key] = _compute_macd(enriched, fast, slow, signal)
            _, _, histogram = macd_cache[key]
            enriched[name] = histogram
        elif name.startswith("MACD_"):
            params = name[len("MACD_") :].split("_")
            if len(params) != 3:
                raise ValueError(f"MACD feature '{name}' must follow MACD_fast_slow_signal format.")
            fast, slow, signal = map(int, params)
            key = (fast, slow, signal)
            if key not in macd_cache:
                macd_cache[key] = _compute_macd(enriched, fast, slow, signal)
            macd, _, _ = macd_cache[key]
            enriched[name] = macd
        elif name.startswith("Volume_Z_"):
            window = int(name.split("_", 2)[2])
            enriched[name] = _compute_volume_zscore(enriched, window)
        elif name == "OBV":
            enriched[name] = _compute_obv(enriched)
        elif name == "Close_Open_Ratio":
            enriched[name] = _compute_close_open_ratio(enriched)
        elif name.startswith("Return_"):
            window = int(name.split("_", 1)[1])
            enriched[name] = _compute_return(enriched, window)
        else:
            raise ValueError(f"Unsupported engineered feature '{name}'.")
    return enriched


def build_feature_frame(price_df: pd.DataFrame, config: FeatureConfig) -> pd.DataFrame:
    """
    Construct the model-ready feature dataframe for a ticker.

    Args:
        price_df: Clean price history indexed by date.
        config: Feature configuration describing required columns.

    Returns:
        Dataframe containing all requested features and the model target.

    Raises:
        ValueError: When required columns cannot be generated.
    """
    enriched = apply_engineered_features(price_df, config.engineered)

    if isinstance(enriched.columns, pd.MultiIndex):
        flattened = []
        for col in enriched.columns:
            if isinstance(col, tuple):
                first = str(col[0])
                second = str(col[1]) if len(col) > 1 else ""
                flattened.append(first if not second or second == 'nan' else first)
            else:
                flattened.append(str(col))
        enriched.columns = flattened

    required = config.all_features()
    missing = [col for col in required if col not in enriched.columns]
    if missing:
        raise ValueError(f"Missing required feature columns: {missing}")

    if config.target not in enriched.columns:
        raise ValueError(f"Target column '{config.target}' not present after feature engineering.")

    feature_frame = enriched[required + [config.target]].dropna()
    feature_frame = feature_frame.loc[:, ~feature_frame.columns.duplicated()]
    feature_frame = feature_frame.loc[~feature_frame.index.duplicated(keep="last")]
    return feature_frame
