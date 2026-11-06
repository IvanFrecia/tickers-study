#!/usr/bin/env python3
"""Replay and summarize resolved forecast-cycle KPI outcomes."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.forecast_ledger import ACTIVE_PROMOTED_COHORT, cycle_payload_from_summary_row  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay resolved forecast cycles and compute KPI summaries.")
    parser.add_argument("--ledger-local-root", type=Path, default=Path("reports/forecast_ledger"))
    parser.add_argument("--resolved-limit", type=int, default=6)
    parser.add_argument("--active-cohort-only", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("reports/forecast_ledger/replay_report.json"))
    return parser.parse_args()


def _load_from_local(args: argparse.Namespace) -> list[dict[str, Any]]:
    cycles_dir = args.ledger_local_root.expanduser().resolve(strict=False) / "cycles"
    rows: list[dict[str, Any]] = []
    if not cycles_dir.exists():
        return rows
    for path in sorted(cycles_dir.glob("*/*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    rows.sort(key=lambda item: (str(item.get("target_week_end_date", "")), str(item.get("updated_at", ""))), reverse=True)
    return rows


def main() -> None:
    args = parse_args()
    cycles = _load_from_local(args)

    if args.active_cohort_only:
        cycles = [cycle for cycle in cycles if str(cycle.get("ticker", "")).upper() in ACTIVE_PROMOTED_COHORT]

    resolved_cycles = [cycle for cycle in cycles if cycle.get("cycle_status") == "resolved"][: args.resolved_limit]

    first_call_errors: list[float] = []
    rolling_errors: list[float] = []
    exact_target_matches = 0
    revision_count = 0
    for cycle in resolved_cycles:
        kpis = cycle.get("kpis") if isinstance(cycle.get("kpis"), dict) else {}
        first_call = kpis.get("first_call_week_ahead") if isinstance(kpis.get("first_call_week_ahead"), dict) else {}
        rolling = (
            kpis.get("rolling_revision_accuracy") if isinstance(kpis.get("rolling_revision_accuracy"), dict) else {}
        )
        if isinstance(first_call.get("absolute_error"), (int, float)):
            first_call_errors.append(float(first_call["absolute_error"]))
        if isinstance(rolling.get("absolute_error"), (int, float)):
            rolling_errors.append(float(rolling["absolute_error"]))
        latest_forecast = cycle.get("latest_forecast") if isinstance(cycle.get("latest_forecast"), dict) else {}
        if latest_forecast.get("projection_selection") == "exact_market_close":
            exact_target_matches += 1
        revisions = cycle.get("revisions")
        if isinstance(revisions, list):
            revision_count += len(revisions)

    def _avg(values: list[float]) -> float | None:
        return (sum(values) / len(values)) if values else None

    report = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "resolved_cycle_count": len(resolved_cycles),
        "first_call_mae": _avg(first_call_errors),
        "rolling_revision_mae": _avg(rolling_errors),
        "exact_target_match_pct": (exact_target_matches / len(resolved_cycles) * 100.0) if resolved_cycles else None,
        "average_revisions_per_cycle": (revision_count / len(resolved_cycles)) if resolved_cycles else None,
        "cycles": resolved_cycles,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
