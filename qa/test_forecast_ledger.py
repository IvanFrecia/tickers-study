"""Unit tests for immutable forecast-cycle ledger helpers."""

from __future__ import annotations

import unittest

from src.forecast_ledger import (
    build_origin_record,
    cycle_summary_row,
    forecast_cycle_id,
    forecast_origin_id,
    merge_origin_into_cycle,
    resolve_cycle,
)


class ForecastLedgerTests(unittest.TestCase):
    def test_cycle_and_origin_ids_are_stable(self) -> None:
        self.assertEqual(forecast_cycle_id("amzn", "2026-03-27"), "AMZN:2026-03-27")
        self.assertEqual(
            forecast_origin_id("amzn", "2026-03-23", "2026-03-27", "2026-03-22T02:00:00Z"),
            "AMZN:2026-03-23:2026-03-27:2026-03-22T02:00:00Z",
        )

    def test_first_forecast_remains_initial_when_revisions_arrive(self) -> None:
        first_origin = build_origin_record(
            ticker="AMZN",
            target_week_end_date="2026-03-27",
            last_observation_date="2026-03-23",
            issued_at="2026-03-23T22:00:00Z",
            final_forecast_date="2026-03-27",
            projection_selection="exact_market_close",
            week_start_close=200.0,
            predicted_target_close=210.0,
            predicted_target_return_pct=5.0,
            model_run_dir="artifacts/AMZN/20260323-220000",
            config_snapshot_path="configs/tickers.toml",
            forecast_rows=[{"date": "2026-03-27", "predicted_close": 210.0}],
            run_date="2026-03-23",
            summary_source_file=None,
            existing_cycle=None,
        )
        cycle = merge_origin_into_cycle(None, first_origin)
        self.assertEqual(cycle["initial_forecast"]["forecast_origin_id"], first_origin["forecast_origin_id"])
        self.assertEqual(cycle["latest_forecast"]["forecast_origin_id"], first_origin["forecast_origin_id"])

        revision = build_origin_record(
            ticker="AMZN",
            target_week_end_date="2026-03-27",
            last_observation_date="2026-03-24",
            issued_at="2026-03-24T22:00:00Z",
            final_forecast_date="2026-03-27",
            projection_selection="exact_market_close",
            week_start_close=202.0,
            predicted_target_close=208.0,
            predicted_target_return_pct=2.97,
            model_run_dir="artifacts/AMZN/20260324-220000",
            config_snapshot_path="configs/tickers.toml",
            forecast_rows=[{"date": "2026-03-27", "predicted_close": 208.0}],
            run_date="2026-03-24",
            summary_source_file=None,
            existing_cycle=cycle,
        )
        updated = merge_origin_into_cycle(cycle, revision)
        self.assertEqual(updated["initial_forecast"]["forecast_origin_id"], first_origin["forecast_origin_id"])
        self.assertEqual(updated["latest_forecast"]["forecast_origin_id"], revision["forecast_origin_id"])
        self.assertEqual(len(updated["revisions"]), 2)

    def test_resolve_cycle_computes_first_call_and_latest_kpis(self) -> None:
        first_origin = build_origin_record(
            ticker="GOOG",
            target_week_end_date="2026-03-27",
            last_observation_date="2026-03-23",
            issued_at="2026-03-23T22:00:00Z",
            final_forecast_date="2026-03-27",
            projection_selection="exact_market_close",
            week_start_close=100.0,
            predicted_target_close=105.0,
            predicted_target_return_pct=5.0,
            model_run_dir="artifacts/GOOG/20260323-220000",
            config_snapshot_path="configs/tickers.toml",
            forecast_rows=[{"date": "2026-03-27", "predicted_close": 105.0}],
            run_date="2026-03-23",
            summary_source_file=None,
            existing_cycle=None,
        )
        cycle = merge_origin_into_cycle(None, first_origin)
        revision = build_origin_record(
            ticker="GOOG",
            target_week_end_date="2026-03-27",
            last_observation_date="2026-03-24",
            issued_at="2026-03-24T22:00:00Z",
            final_forecast_date="2026-03-27",
            projection_selection="exact_market_close",
            week_start_close=101.0,
            predicted_target_close=103.0,
            predicted_target_return_pct=1.98,
            model_run_dir="artifacts/GOOG/20260324-220000",
            config_snapshot_path="configs/tickers.toml",
            forecast_rows=[{"date": "2026-03-27", "predicted_close": 103.0}],
            run_date="2026-03-24",
            summary_source_file=None,
            existing_cycle=cycle,
        )
        cycle = merge_origin_into_cycle(cycle, revision)
        resolved = resolve_cycle(
            cycle,
            actual_target_close=102.0,
            resolved_at="2026-03-28T14:15:00Z",
            source_run_date="2026-03-28",
        )
        kpis = resolved["kpis"]
        self.assertEqual(resolved["cycle_status"], "resolved")
        self.assertAlmostEqual(kpis["first_call_week_ahead"]["absolute_error"], 3.0)
        self.assertAlmostEqual(kpis["rolling_revision_accuracy"]["absolute_error"], 1.0)

        flattened = cycle_summary_row(resolved, source_run_date="2026-03-28", source_summary_file="summary.json")
        self.assertEqual(flattened["cycle_status"], "resolved")
        self.assertEqual(flattened["ticker"], "GOOG")


if __name__ == "__main__":
    unittest.main()
