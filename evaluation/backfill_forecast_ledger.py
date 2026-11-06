#!/usr/bin/env python3
"""Backfill immutable forecast-cycle ledger rows from historical weekly summaries."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.forecast_ledger import (  # noqa: E402
    ACTIVE_PROMOTED_COHORT,
    build_origin_record,
    cycle_summary_row,
    merge_origin_into_cycle,
    model_candidate_row,
    model_selection_row,
    resolution_event_row,
    resolve_cycle,
    save_local_cycle,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill forecast-cycle ledger rows from weekly summary history.")
    parser.add_argument(
        "--local-risk-package-dir",
        type=Path,
        default=Path("reports/risk_package"),
        help="Local directory containing weekly summary JSON files.",
    )
    parser.add_argument(
        "--ledger-local-root",
        type=Path,
        default=Path("reports/forecast_ledger"),
        help="Local ledger root for cycle snapshots and backfill rows.",
    )
    parser.add_argument(
        "--active-cohort-only",
        action="store_true",
        help="Restrict backfill to AMZN, BA, GOOG, NVDA.",
    )
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _summary_candidates(args: argparse.Namespace) -> list[Path]:
    from evaluation.retrain_publish_weekly import _canonical

    local_dir = _canonical(args.local_risk_package_dir)
    candidates = sorted(local_dir.glob("weekly_forecast_summary_simple_*.json"))
    unique = {str(_canonical(path)): _canonical(path) for path in candidates if path.exists()}
    return sorted(unique.values(), key=lambda path: path.name)


def _write_ndjson(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def main() -> None:
    args = parse_args()
    from evaluation.retrain_publish_weekly import _canonical  # noqa: WPS433

    ledger_root = _canonical(args.ledger_local_root)
    ledger_root.mkdir(parents=True, exist_ok=True)

    summaries = []
    for source in _summary_candidates(args):
        payload = _load_json(source)
        generated_at = payload.get("generated_at")
        tickers = payload.get("tickers")
        if not isinstance(generated_at, str) or not isinstance(tickers, dict):
            continue
        summaries.append((generated_at, source, payload))
    summaries.sort(key=lambda item: item[0])

    cycle_snapshots: dict[tuple[str, str], dict[str, Any]] = {}
    revisions_seen: dict[tuple[str, str], int] = defaultdict(int)
    origin_rows: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []
    selection_rows: list[dict[str, Any]] = []
    resolution_rows: list[dict[str, Any]] = []

    for generated_at, source, payload in summaries:
        tickers = payload.get("tickers", {})
        run_date = generated_at[:10]
        for symbol, info in tickers.items():
            if not isinstance(info, dict):
                continue
            symbol = str(symbol).upper()
            if args.active_cohort_only and symbol not in ACTIVE_PROMOTED_COHORT:
                continue
            target_week_end_date = info.get("target_week_end_date")
            if not isinstance(target_week_end_date, str) or not target_week_end_date:
                continue

            cycle_key = (symbol, target_week_end_date)
            origin = build_origin_record(
                ticker=symbol,
                target_week_end_date=target_week_end_date,
                last_observation_date=info.get("last_observation") if isinstance(info.get("last_observation"), str) else None,
                issued_at=generated_at,
                final_forecast_date=info.get("final_forecast_date") if isinstance(info.get("final_forecast_date"), str) else None,
                projection_selection=str(info.get("projection_selection") or "none"),
                week_start_close=float(info["last_close"]) if isinstance(info.get("last_close"), (int, float)) else None,
                predicted_target_close=float(info["expected_week_close"]) if isinstance(info.get("expected_week_close"), (int, float)) else None,
                predicted_target_return_pct=(
                    float(info["expected_week_return_pct"])
                    if isinstance(info.get("expected_week_return_pct"), (int, float))
                    else None
                ),
                model_run_dir=str(info.get("artifact_run_dir")) if info.get("artifact_run_dir") else None,
                config_snapshot_path=str(ROOT / "configs" / "tickers.toml"),
                forecast_rows=info.get("daily") if isinstance(info.get("daily"), list) else [],
                run_date=run_date,
                summary_source_file=str(source),
                existing_cycle=cycle_snapshots.get(cycle_key),
            )
            cycle_snapshots[cycle_key] = merge_origin_into_cycle(cycle_snapshots.get(cycle_key), origin)
            save_local_cycle(ledger_root, cycle_snapshots[cycle_key])
            origin_rows.append(
                {**{key: value for key, value in origin.items() if key != "forecast"}, "forecast_json": json.dumps(origin["forecast"])}
            )
            candidate_rows.append(
                model_candidate_row(
                    ticker=symbol,
                    target_week_end_date=target_week_end_date,
                    model_run_dir=str(info.get("artifact_run_dir")) if info.get("artifact_run_dir") else None,
                    metrics=info.get("model_metrics") if isinstance(info.get("model_metrics"), dict) else {},
                    runtime_config={"source": str(source), "backfill": True},
                )
            )
            selection_rows.append(
                model_selection_row(
                    ticker=symbol,
                    target_week_end_date=target_week_end_date,
                    model_run_dir=str(info.get("artifact_run_dir")) if info.get("artifact_run_dir") else None,
                    reason="backfilled from historical weekly summary",
                    decision={"source": str(source), "generated_at": generated_at},
                )
            )
            revisions_seen[cycle_key] += 1

            previous_week = info.get("previous_week_comparison")
            if (
                isinstance(previous_week, dict)
                and previous_week.get("status") == "resolved"
                and isinstance(previous_week.get("target_week_end_date"), str)
                and isinstance(previous_week.get("actual_close"), (int, float))
            ):
                previous_key = (symbol, str(previous_week["target_week_end_date"]))
                existing_cycle = cycle_snapshots.get(previous_key)
                if existing_cycle is None:
                    continue
                resolved_cycle = resolve_cycle(
                    existing_cycle,
                    actual_target_close=float(previous_week["actual_close"]),
                    resolved_at=generated_at,
                    source_run_date=run_date,
                )
                cycle_snapshots[previous_key] = resolved_cycle
                save_local_cycle(ledger_root, resolved_cycle)
                event = resolution_event_row(resolved_cycle, source_run_date=run_date)
                if event is not None:
                    resolution_rows.append(event)

    cycle_rows = [
        cycle_summary_row(cycle, source_run_date=str(cycle.get("updated_at", ""))[:10], source_summary_file="backfill")
        for cycle in cycle_snapshots.values()
    ]

    rows_dir = _canonical(ledger_root / "backfill_rows")
    origin_path = rows_dir / "forecast_origin_ledger_backfill.ndjson"
    cycle_path = rows_dir / "forecast_cycle_summary_backfill.ndjson"
    resolution_path = rows_dir / "forecast_resolution_events_backfill.ndjson"
    candidate_path = rows_dir / "model_candidate_runs_backfill.ndjson"
    selection_path = rows_dir / "model_selection_decisions_backfill.ndjson"
    _write_ndjson(origin_path, origin_rows)
    _write_ndjson(cycle_path, cycle_rows)
    _write_ndjson(resolution_path, resolution_rows)
    _write_ndjson(candidate_path, candidate_rows)
    _write_ndjson(selection_path, selection_rows)

    report = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summary_count": len(summaries),
        "cycle_count": len(cycle_snapshots),
        "origin_count": len(origin_rows),
        "resolution_event_count": len(resolution_rows),
        "local_rows_dir": str(rows_dir),
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
