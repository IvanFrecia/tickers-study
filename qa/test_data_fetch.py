"""Regression tests for inclusive Yahoo date fetching."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from src.data import fetch_price_history, inclusive_to_yfinance_end
from src.macro import _download_series


class InclusiveYfinanceEndTests(unittest.TestCase):
    def test_inclusive_friday_requests_saturday_exclusive_end(self) -> None:
        self.assertEqual(inclusive_to_yfinance_end("2026-08-21"), "2026-08-22")

    def test_fetch_price_history_keeps_inclusive_friday_session(self) -> None:
        frame = pd.DataFrame(
            {"Close": [220.0, 221.0, 222.0, 223.0, 224.0]},
            index=pd.to_datetime(
                ["2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20", "2026-08-21"]
            ),
        )
        with patch("src.data.yf.download", return_value=frame.copy()) as download:
            data = fetch_price_history("AMZN", start_date="2026-08-17", end_date="2026-08-21")

        self.assertEqual(download.call_args.kwargs["end"], "2026-08-22")
        self.assertEqual(pd.Timestamp(data.index.max()).date().isoformat(), "2026-08-21")

    def test_macro_download_uses_exclusive_end_for_inclusive_friday(self) -> None:
        frame = pd.DataFrame(
            {"Close": [10.0, 11.0]},
            index=pd.to_datetime(["2026-08-20", "2026-08-21"]),
        )
        with patch("src.macro.yf.download", return_value=frame.copy()) as download:
            series = _download_series("^VIX", "2026-08-20", "2026-08-21")

        self.assertEqual(download.call_args.kwargs["end"], "2026-08-22")
        self.assertEqual(pd.Timestamp(series.index.max()).date().isoformat(), "2026-08-21")


if __name__ == "__main__":
    unittest.main()
