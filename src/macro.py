"""Utilities for ingesting macro and market context features."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Iterable, List

import pandas as pd
import yfinance as yf
import numpy as np

from .config import MacroSourceConfig
from .data import inclusive_to_yfinance_end


def _download_series(symbol: str, start_date: str, end_date: str | None) -> pd.Series:
    """Download adjusted close series for the supplied macro symbol."""

    resolved_end = end_date or date.today().strftime("%Y-%m-%d")
    yfinance_end = inclusive_to_yfinance_end(resolved_end)
    logging.info(
        "Downloading macro series %s (%s -> %s, yfinance exclusive end %s)",
        symbol,
        start_date,
        resolved_end,
        yfinance_end,
    )
    data = yf.download(
        tickers=symbol,
        start=start_date,
        end=yfinance_end,
        progress=False,
        auto_adjust=True,
        actions=False,
        threads=False,
    )
    if data.empty:
        raise ValueError(f"No macro data retrieved for {symbol} between {start_date} and {resolved_end}.")
    series = data["Close"].copy()
    if isinstance(series, pd.DataFrame):
        series = series.iloc[:, 0]
    series.index = pd.to_datetime(series.index)
    series = series.asfreq("B")
    series.ffill(inplace=True)
    return series


def _transform_series(series: pd.Series, transform: str) -> pd.Series:
    """Apply the requested transformation to the macro series."""

    transform = transform.lower()
    if transform == "level":
        return series
    if transform == "pct_return":
        return series.pct_change()
    if transform == "log_return":
        values = np.asarray(series).squeeze()
        values = np.clip(values, 1e-9, None)
        logged = pd.Series(np.log(values), index=series.index)
        return logged.diff()
    raise ValueError(f"Unsupported macro transform '{transform}'.")


def fetch_macro_features(
    sources: Iterable[MacroSourceConfig],
    start_date: str,
    end_date: str | None,
) -> pd.DataFrame:
    """Fetch and assemble macro features for the requested sources."""

    frames: List[pd.Series] = []
    for source in sources:
        raw_series = _download_series(source.symbol, start_date, end_date)
        transformed = _transform_series(raw_series, source.transform)
        if not isinstance(transformed, pd.Series):
            transformed = pd.Series(transformed, index=raw_series.index)
        transformed.name = source.feature_name
        frames.append(transformed)

    if not frames:
        return pd.DataFrame()

    features = pd.concat(frames, axis=1)
    features.sort_index(inplace=True)
    features = features.asfreq("B")
    features.ffill(inplace=True)
    return features
