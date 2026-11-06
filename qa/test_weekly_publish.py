"""Unit tests for weekly publish path shaping helpers."""

from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

from evaluation.retrain_publish_weekly import _attach_target_anchored_display_path, _json_dumps


class WeeklyPublishPathTests(unittest.TestCase):
    def test_json_dumps_serializes_date_and_datetime_values(self) -> None:
        payload = {
            "run_date": date(2026, 3, 28),
            "generated_at": datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc),
        }

        encoded = _json_dumps(payload)

        self.assertIn('"run_date": "2026-03-28"', encoded)
        self.assertIn('"generated_at": "2026-03-28T12:00:00+00:00"', encoded)

    def test_target_anchored_display_path_preserves_raw_close_and_hits_target(self) -> None:
        rows = [
            {"forecast_date": "2026-03-23", "predicted_close": 101.0},
            {"forecast_date": "2026-03-24", "predicted_close": 102.0},
            {"forecast_date": "2026-03-25", "predicted_close": 103.0},
            {"forecast_date": "2026-03-26", "predicted_close": 104.0},
            {"forecast_date": "2026-03-27", "predicted_close": 105.0},
        ]

        shaped = _attach_target_anchored_display_path(
            rows,
            week_start_close=100.0,
            target_close=110.0,
        )

        self.assertEqual(len(shaped), 5)
        self.assertEqual(shaped[0]["raw_predicted_close"], 101.0)
        self.assertGreater(shaped[0]["display_close"], shaped[0]["predicted_close"])
        self.assertGreater(shaped[1]["display_close"], shaped[1]["predicted_close"])
        self.assertEqual(shaped[-1]["display_close"], 110.0)

    def test_target_anchored_display_path_falls_back_to_raw_without_anchor_inputs(self) -> None:
        rows = [
            {"forecast_date": "2026-03-23", "predicted_close": 98.0},
            {"forecast_date": "2026-03-24", "predicted_close": 97.5},
        ]

        shaped = _attach_target_anchored_display_path(
            rows,
            week_start_close=None,
            target_close=None,
        )

        self.assertEqual(shaped[0]["display_close"], 98.0)
        self.assertEqual(shaped[1]["display_close"], 97.5)
        self.assertEqual(shaped[1]["raw_predicted_close"], 97.5)


if __name__ == "__main__":
    unittest.main()
