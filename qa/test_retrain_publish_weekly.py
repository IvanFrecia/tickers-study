"""Regression tests for weekly retrain/publish defaults."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import patch

from datetime import date

from evaluation.retrain_publish_weekly import (
    _attach_target_anchored_display_path,
    _catch_up_observation_dates,
    _resolve_anchor_date,
    parse_args,
)


class WeeklyRetrainPublishArgTests(unittest.TestCase):
    def test_constant_loss_defaults_to_target_close_weighting(self) -> None:
        with patch.object(sys, "argv", ["retrain_publish_weekly.py"]):
            args = parse_args()

        self.assertEqual(args.constant_loss, "weighted_mse")

    def test_target_anchored_display_path_preserves_raw_close_and_lands_on_target(self) -> None:
        rows = [
            {"forecast_date": "2026-03-24", "predicted_close": 102.0},
            {"forecast_date": "2026-03-25", "predicted_close": 104.0},
            {"forecast_date": "2026-03-27", "predicted_close": 105.0},
        ]

        enriched = _attach_target_anchored_display_path(
            rows,
            week_start_close=100.0,
            target_close=110.0,
        )

        self.assertEqual(len(enriched), 3)
        self.assertEqual(enriched[-1]["display_close"], 110.0)
        self.assertEqual(enriched[0]["raw_predicted_close"], 102.0)
        self.assertGreater(enriched[0]["display_close"], enriched[0]["predicted_close"])
        self.assertIn("target_bridge_close", enriched[1])

    def test_catch_up_observation_dates_walk_from_last_target_week_end(self) -> None:
        with patch(
            "evaluation.retrain_publish_weekly.following_market_week_end",
            side_effect=[
                date(2026, 4, 10),
                date(2026, 4, 17),
                date(2026, 4, 24),
                date(2026, 5, 1),
                date(2026, 5, 8),
            ],
        ):
            dates = _catch_up_observation_dates("2026-04-02", date(2026, 5, 1))

        self.assertEqual(
            dates,
            ["2026-04-02", "2026-04-10", "2026-04-17", "2026-04-24", "2026-05-01"],
        )

    def test_resolve_anchor_date_defaults_to_live_market_session(self) -> None:
        with patch(
            "evaluation.retrain_publish_weekly.market_week_context",
            return_value={
                "market_date": "2026-06-18",
                "latest_market_session_date": "2026-06-18",
            },
        ):
            anchor = _resolve_anchor_date(None)

        self.assertEqual(anchor, date(2026, 6, 18))


if __name__ == "__main__":
    unittest.main()
