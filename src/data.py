"""Data access helpers for downloading and loading historical prices."""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from pathlib import Path
from typing import IO, Optional, Union

import pandas as pd
import yfinance as yf


def inclusive_to_yfinance_end(inclusive_end: str) -> str:
    """Convert an inclusive YYYY-MM-DD cutoff into yfinance's exclusive `end`.

    yfinance treats `end` as exclusive. Passing the inclusive session date
    (for example Friday after the close) silently drops that session, which
    blocks Saturday rollover from observing Friday's close.
    """
    return (date.fromisoformat(inclusive_end) + timedelta(days=1)).isoformat()


def fetch_price_history(
    symbol: str,
    start_date: str,
    end_date: Optional[str] = None,
    show_progress: bool = False,
) -> pd.DataFrame:
    """
    Download daily OHLCV history for a given ticker.

    Call this when you need fresh price data from Yahoo Finance. The function
    normalises the index to business days and forward/back fills gaps so later
    preprocessing steps receive a contiguous series.

    Args:
        symbol: Market ticker symbol (e.g., "AAPL").
        start_date: First trading day to request in ISO format.
        end_date: Optional inclusive end date in ISO format; defaults to today.
        show_progress: When True, display yfinance's download progress bar.

    Returns:
        DataFrame indexed by date with columns returned by yfinance.

    Raises:
        ValueError: If yfinance returns an empty dataset.
    """
    resolved_end = end_date or date.today().strftime("%Y-%m-%d")
    yfinance_end = inclusive_to_yfinance_end(resolved_end)
    logging.info(
        "Downloading %s data from %s to %s (yfinance exclusive end %s)",
        symbol,
        start_date,
        resolved_end,
        yfinance_end,
    )
    attempts = 3
    backoff = 5.0
    last_error: ValueError | None = None
    for attempt in range(1, attempts + 1):
        data = yf.download(
            tickers=symbol,
            start=start_date,
            end=yfinance_end,
            progress=show_progress,
            auto_adjust=False,
            actions=True,
            threads=False,
        )
        if not data.empty:
            break
        last_error = ValueError(f"No price data retrieved for {symbol} between {start_date} and {resolved_end}.")
        if attempt < attempts:
            logging.warning(
                "Download returned no rows for %s (attempt %d/%d). Retrying in %.0f seconds.",
                symbol,
                attempt,
                attempts,
                backoff,
            )
            time.sleep(backoff)
            backoff *= 2
    else:
        assert last_error is not None
        raise last_error

    data.index = pd.to_datetime(data.index)
    data.sort_index(inplace=True)
    data = data[~data.index.duplicated(keep="last")]
    data = data.asfreq("B")
    data.ffill(inplace=True)
    data.bfill(inplace=True)
    logging.info("Retrieved %d rows for %s", len(data), symbol)
    return data


def load_price_history_from_csv(path: Union[str, Path, IO[str]]) -> pd.DataFrame:
    """
    Load a CSV export of price history that uses a `Date` column index.

    Args:
        path: Filesystem path or file-like object pointing to the CSV file.

    Returns:
        Price history dataframe sorted chronologically.
    """
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    df.sort_index(inplace=True)
    return df
