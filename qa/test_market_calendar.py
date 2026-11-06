"""Regression tests for market-calendar rollover helpers."""

from __future__ import annotations

from datetime import date, datetime, timezone
import unittest
from unittest.mock import patch

from src.market_calendar import following_market_week_end, latest_market_session_on_or_before, market_week_context


def _fake_market_schedule(start_date: date, end_date: date, exchange: str = "NYSE") -> list[date]:
    """Return deterministic trading sessions for the covered regression windows."""
    del exchange
    sessions = {
        date(2026, 3, 23),
        date(2026, 3, 24),
        date(2026, 3, 25),
        date(2026, 3, 26),
        date(2026, 3, 27),
        date(2026, 3, 30),
        date(2026, 3, 31),
        date(2026, 4, 1),
        date(2026, 4, 2),
        date(2026, 4, 6),
        date(2026, 4, 7),
        date(2026, 4, 8),
        date(2026, 4, 9),
        date(2026, 4, 10),
    }
    return [session for session in sorted(sessions) if start_date <= session <= end_date]


class MarketCalendarTests(unittest.TestCase):
    def test_following_market_week_end_advances_after_holiday_shortened_week_end(self) -> None:
        with patch("src.market_calendar._market_schedule", side_effect=_fake_market_schedule):
            target = following_market_week_end("2026-04-02")

        self.assertEqual(target, date(2026, 4, 10))

    def test_following_market_week_end_keeps_current_week_for_midweek_observation(self) -> None:
        with patch("src.market_calendar._market_schedule", side_effect=_fake_market_schedule):
            target = following_market_week_end("2026-03-24")

        self.assertEqual(target, date(2026, 3, 27))

    def test_latest_market_session_on_or_before_skips_holiday_fill_dates(self) -> None:
        with patch("src.market_calendar._market_schedule", side_effect=_fake_market_schedule):
            latest = latest_market_session_on_or_before("2026-04-03")

        self.assertEqual(latest, date(2026, 4, 2))

    def test_market_week_context_names_2026_juneteenth_friday_closure(self) -> None:
        context = market_week_context(datetime(2026, 6, 18, 22, 30, tzinfo=timezone.utc))

        self.assertEqual(context["current_week_end_date"], "2026-06-18")
        self.assertEqual(context["next_market_session_date"], "2026-06-22")
        self.assertIn("2026-06-19", context["week_sessions"] + [item["date"] for item in context["week_closures"]])
        self.assertEqual(context["week_closures"][0]["date"], "2026-06-19")
        self.assertEqual(context["week_closures"][0]["name"], "Juneteenth National Independence Day")

    def test_market_week_context_date_anchor_represents_market_close(self) -> None:
        context = market_week_context(date(2026, 6, 18))

        self.assertEqual(context["market_time"], "2026-06-18T16:00:00-04:00")
        self.assertFalse(context["is_market_open_now"])
        self.assertEqual(context["current_week_end_date"], "2026-06-18")
        self.assertEqual(context["week_closures"][0]["date"], "2026-06-19")

    def test_market_week_context_names_2027_observed_juneteenth_friday_closure(self) -> None:
        context = market_week_context(datetime(2027, 6, 18, 14, 0, tzinfo=timezone.utc))

        self.assertEqual(context["current_week_end_date"], "2027-06-17")
        self.assertEqual(context["week_closures"][0]["date"], "2027-06-18")
        self.assertEqual(context["week_closures"][0]["name"], "Juneteenth National Independence Day")

    def test_market_week_context_names_2028_monday_juneteenth_closure(self) -> None:
        context = market_week_context(datetime(2028, 6, 20, 14, 0, tzinfo=timezone.utc))

        self.assertEqual(context["current_week_end_date"], "2028-06-23")
        self.assertEqual(context["week_closures"][0]["date"], "2028-06-19")
        self.assertEqual(context["week_closures"][0]["name"], "Juneteenth National Independence Day")


if __name__ == "__main__":
    unittest.main()
