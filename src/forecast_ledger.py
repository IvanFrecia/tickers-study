"""Forecast cycle ledger helpers for immutable week-end prediction tracking."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


ACTIVE_PROMOTED_COHORT = frozenset({"AMZN", "BA", "GOOG", "NVDA"})


LEDGER_TABLE_SCHEMAS: dict[str, list[tuple[str, str]]] = {
    "forecast_origin_ledger": [
        ("forecast_cycle_id", "STRING"),
        ("forecast_origin_id", "STRING"),
        ("ticker", "STRING"),
        ("target_week_end_date", "DATE"),
        ("last_observation_date", "DATE"),
        ("issued_at", "TIMESTAMP"),
        ("origin_kind", "STRING"),
        ("revision_index", "INTEGER"),
        ("sessions_to_target", "INTEGER"),
        ("model_run_dir", "STRING"),
        ("model_version", "STRING"),
        ("config_snapshot_path", "STRING"),
        ("predicted_target_close", "FLOAT"),
        ("predicted_target_return_pct", "FLOAT"),
        ("final_forecast_date", "DATE"),
        ("projection_selection", "STRING"),
        ("target_matched", "BOOL"),
        ("week_start_close", "FLOAT"),
        ("forecast_json", "STRING"),
        ("published_summary_file", "STRING"),
        ("run_date", "DATE"),
        ("generated_at", "TIMESTAMP"),
    ],
    "forecast_cycle_summary": [
        ("forecast_cycle_id", "STRING"),
        ("ticker", "STRING"),
        ("target_week_end_date", "DATE"),
        ("cycle_status", "STRING"),
        ("initial_origin_id", "STRING"),
        ("latest_origin_id", "STRING"),
        ("latest_last_observation_date", "DATE"),
        ("latest_forecast_date", "DATE"),
        ("initial_predicted_target_close", "FLOAT"),
        ("latest_predicted_target_close", "FLOAT"),
        ("latest_predicted_target_return_pct", "FLOAT"),
        ("resolved_actual_close", "FLOAT"),
        ("first_call_absolute_error", "FLOAT"),
        ("latest_absolute_error", "FLOAT"),
        ("first_call_error_pct", "FLOAT"),
        ("latest_error_pct", "FLOAT"),
        ("first_call_direction_match", "BOOL"),
        ("latest_direction_match", "BOOL"),
        ("initial_forecast_json", "STRING"),
        ("latest_forecast_json", "STRING"),
        ("revisions_json", "STRING"),
        ("resolved_actual_json", "STRING"),
        ("kpis_json", "STRING"),
        ("source_run_date", "DATE"),
        ("source_summary_file", "STRING"),
        ("updated_at", "TIMESTAMP"),
    ],
    "forecast_resolution_events": [
        ("forecast_cycle_id", "STRING"),
        ("ticker", "STRING"),
        ("target_week_end_date", "DATE"),
        ("resolved_at", "TIMESTAMP"),
        ("actual_target_close", "FLOAT"),
        ("first_call_origin_id", "STRING"),
        ("latest_origin_id", "STRING"),
        ("first_call_absolute_error", "FLOAT"),
        ("latest_absolute_error", "FLOAT"),
        ("first_call_error_pct", "FLOAT"),
        ("latest_error_pct", "FLOAT"),
        ("first_call_direction_match", "BOOL"),
        ("latest_direction_match", "BOOL"),
        ("source_run_date", "DATE"),
    ],
    "model_candidate_runs": [
        ("candidate_run_id", "STRING"),
        ("ticker", "STRING"),
        ("target_week_end_date", "DATE"),
        ("candidate_kind", "STRING"),
        ("model_run_dir", "STRING"),
        ("model_version", "STRING"),
        ("metrics_json", "STRING"),
        ("runtime_config_json", "STRING"),
        ("created_at", "TIMESTAMP"),
    ],
    "model_selection_decisions": [
        ("decision_id", "STRING"),
        ("ticker", "STRING"),
        ("target_week_end_date", "DATE"),
        ("selected_model_run_dir", "STRING"),
        ("selected_model_version", "STRING"),
        ("reason", "STRING"),
        ("decision_json", "STRING"),
        ("created_at", "TIMESTAMP"),
    ],
    "weekly_predictions_v1_shadow": [
        ("run_date", "DATE"),
        ("week_start", "DATE"),
        ("week_end", "DATE"),
        ("ticker", "STRING"),
        ("status", "STRING"),
        ("last_observation", "DATE"),
        ("target_week_end_date", "DATE"),
        ("final_forecast_date", "DATE"),
        ("last_close", "FLOAT"),
        ("expected_week_close", "FLOAT"),
        ("expected_week_return_pct", "FLOAT"),
        ("mae", "FLOAT"),
        ("rmse", "FLOAT"),
        ("mape", "FLOAT"),
        ("r2", "FLOAT"),
        ("source_file", "STRING"),
        ("projection_selection", "STRING"),
        ("note", "STRING"),
        ("generated_at", "TIMESTAMP"),
    ],
}


def _utc_now() -> str:
    """Return current UTC timestamp in ISO-8601 Z format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def schema_string(table_name: str) -> str:
    """Return a bq CLI schema string for a known ledger table."""
    return ",".join(f"{name}:{kind}" for name, kind in LEDGER_TABLE_SCHEMAS[table_name])


def forecast_cycle_id(ticker: str, target_week_end_date: str) -> str:
    """Build the immutable cycle identifier."""
    return f"{ticker.upper()}:{target_week_end_date}"


def forecast_origin_id(
    ticker: str,
    last_observation_date: str | None,
    target_week_end_date: str,
    issued_at: str,
) -> str:
    """Build the immutable origin identifier."""
    observation = (last_observation_date or "unknown").strip() or "unknown"
    return f"{ticker.upper()}:{observation}:{target_week_end_date}:{issued_at}"


def canonical_cycle_path(root: Path, ticker: str, target_week_end_date: str) -> Path:
    """Return the canonical local cycle snapshot path."""
    return root.expanduser().resolve(strict=False) / "cycles" / ticker.upper() / f"{target_week_end_date}.json"


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime,)):
        return value.isoformat()
    return str(value)


def json_dumps(value: Any) -> str:
    """Serialize compact JSON for BQ string fields."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=_json_default)


def parse_json_field(value: Any) -> Any:
    """Parse JSON string fields coming back from local snapshots."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def load_local_cycle(root: Path, ticker: str, target_week_end_date: str) -> dict[str, Any] | None:
    """Load a local cycle snapshot when available."""
    path = canonical_cycle_path(root, ticker, target_week_end_date)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def save_local_cycle(root: Path, cycle: dict[str, Any]) -> Path:
    """Persist the latest cycle snapshot locally."""
    ticker = str(cycle.get("ticker", "")).upper()
    target_week_end_date = str(cycle.get("target_week_end_date", ""))
    path = canonical_cycle_path(root, ticker, target_week_end_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cycle, indent=2, default=_json_default), encoding="utf-8")
    return path


def build_origin_record(
    *,
    ticker: str,
    target_week_end_date: str,
    last_observation_date: str | None,
    issued_at: str,
    final_forecast_date: str | None,
    projection_selection: str,
    week_start_close: float | None,
    predicted_target_close: float | None,
    predicted_target_return_pct: float | None,
    model_run_dir: str | None,
    config_snapshot_path: str | None,
    forecast_rows: list[dict[str, Any]],
    run_date: str,
    summary_source_file: str | None,
    existing_cycle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one immutable origin record for the current cycle."""
    existing_revisions = existing_cycle.get("revisions", []) if isinstance(existing_cycle, dict) else []
    revision_index = len(existing_revisions)
    origin_kind = "initial_weekly" if revision_index == 0 else "daily_revision"
    target_matched = (
        bool(final_forecast_date)
        and final_forecast_date == target_week_end_date
        and projection_selection == "exact_market_close"
    )
    sessions_to_target = max(0, len(forecast_rows) - 1) if forecast_rows else 0
    origin_id = forecast_origin_id(ticker, last_observation_date, target_week_end_date, issued_at)
    model_version = None
    if model_run_dir:
        model_version = str(Path(model_run_dir).name)

    return {
        "forecast_cycle_id": forecast_cycle_id(ticker, target_week_end_date),
        "forecast_origin_id": origin_id,
        "ticker": ticker.upper(),
        "target_week_end_date": target_week_end_date,
        "last_observation_date": last_observation_date,
        "issued_at": issued_at,
        "origin_kind": origin_kind,
        "revision_index": revision_index,
        "sessions_to_target": sessions_to_target,
        "model_run_dir": model_run_dir,
        "model_version": model_version,
        "config_snapshot_path": config_snapshot_path,
        "predicted_target_close": predicted_target_close,
        "predicted_target_return_pct": predicted_target_return_pct,
        "final_forecast_date": final_forecast_date,
        "projection_selection": projection_selection,
        "target_matched": target_matched,
        "week_start_close": week_start_close,
        "forecast": forecast_rows,
        "published_summary_file": summary_source_file,
        "run_date": run_date,
        "generated_at": issued_at,
    }


def merge_origin_into_cycle(existing_cycle: dict[str, Any] | None, origin: dict[str, Any]) -> dict[str, Any]:
    """Merge one origin into the latest cycle snapshot without overwriting first call."""
    revisions: list[dict[str, Any]] = []
    if isinstance(existing_cycle, dict):
        existing_revisions = existing_cycle.get("revisions")
        if isinstance(existing_revisions, list):
            revisions = [item for item in existing_revisions if isinstance(item, dict)]

    if any(item.get("forecast_origin_id") == origin.get("forecast_origin_id") for item in revisions):
        latest_origin = next(
            item for item in revisions if item.get("forecast_origin_id") == origin.get("forecast_origin_id")
        )
        initial_forecast = revisions[0] if revisions else latest_origin
        return {
            "forecast_cycle_id": origin["forecast_cycle_id"],
            "ticker": origin["ticker"],
            "target_week_end_date": origin["target_week_end_date"],
            "cycle_status": "resolved" if isinstance(existing_cycle, dict) and existing_cycle.get("resolved_actual") else "open",
            "initial_forecast": initial_forecast,
            "latest_forecast": latest_origin,
            "revisions": revisions,
            "resolved_actual": existing_cycle.get("resolved_actual") if isinstance(existing_cycle, dict) else None,
            "kpis": existing_cycle.get("kpis") if isinstance(existing_cycle, dict) else {},
            "updated_at": _utc_now(),
        }

    revisions.append(origin)
    revisions.sort(key=lambda item: (_safe_int(item.get("revision_index")) or 0, str(item.get("issued_at") or "")))
    initial_forecast = revisions[0]
    latest_forecast = revisions[-1]
    resolved_actual = existing_cycle.get("resolved_actual") if isinstance(existing_cycle, dict) else None
    cycle_status = "resolved" if isinstance(resolved_actual, dict) else "open"
    return {
        "forecast_cycle_id": origin["forecast_cycle_id"],
        "ticker": origin["ticker"],
        "target_week_end_date": origin["target_week_end_date"],
        "cycle_status": cycle_status,
        "initial_forecast": initial_forecast,
        "latest_forecast": latest_forecast,
        "revisions": revisions,
        "resolved_actual": resolved_actual,
        "kpis": existing_cycle.get("kpis") if isinstance(existing_cycle, dict) else {},
        "updated_at": _utc_now(),
    }


def resolve_cycle(
    cycle: dict[str, Any],
    *,
    actual_target_close: float,
    resolved_at: str,
    source_run_date: str,
) -> dict[str, Any]:
    """Mark a cycle resolved and compute first-call / latest-call KPI summaries."""
    revisions = [item for item in cycle.get("revisions", []) if isinstance(item, dict)]
    if not revisions:
        return cycle

    initial_forecast = revisions[0]
    latest_forecast = revisions[-1]

    def _error_block(origin: dict[str, Any]) -> dict[str, Any]:
        predicted_close = _safe_float(origin.get("predicted_target_close"))
        week_start_close = _safe_float(origin.get("week_start_close"))
        predicted_return_pct = _safe_float(origin.get("predicted_target_return_pct"))
        absolute_error = None
        error_pct = None
        if predicted_close is not None:
            absolute_error = abs(actual_target_close - predicted_close)
            if predicted_close != 0:
                error_pct = (actual_target_close - predicted_close) / predicted_close * 100.0
        realized_return_pct = None
        if week_start_close not in (None, 0.0):
            realized_return_pct = (actual_target_close - week_start_close) / week_start_close * 100.0
        direction_match = None
        if predicted_return_pct is not None and realized_return_pct is not None:
            if predicted_return_pct == 0 and realized_return_pct == 0:
                direction_match = True
            elif predicted_return_pct == 0 or realized_return_pct == 0:
                direction_match = False
            else:
                direction_match = (predicted_return_pct > 0) == (realized_return_pct > 0)
        return {
            "forecast_origin_id": origin.get("forecast_origin_id"),
            "predicted_target_close": predicted_close,
            "actual_target_close": actual_target_close,
            "absolute_error": absolute_error,
            "error_pct": error_pct,
            "predicted_target_return_pct": predicted_return_pct,
            "realized_return_pct": realized_return_pct,
            "direction_match": direction_match,
        }

    first_call = _error_block(initial_forecast)
    latest_call = _error_block(latest_forecast)
    cycle["cycle_status"] = "resolved"
    cycle["resolved_actual"] = {
        "actual_target_close": actual_target_close,
        "resolved_at": resolved_at,
        "source_run_date": source_run_date,
    }
    cycle["kpis"] = {
        "first_call_week_ahead": first_call,
        "rolling_revision_accuracy": latest_call,
    }
    cycle["updated_at"] = resolved_at
    return cycle


def cycle_summary_row(cycle: dict[str, Any], *, source_run_date: str, source_summary_file: str | None) -> dict[str, Any]:
    """Flatten a cycle snapshot into an append-only summary row."""
    initial_forecast = cycle.get("initial_forecast") if isinstance(cycle.get("initial_forecast"), dict) else {}
    latest_forecast = cycle.get("latest_forecast") if isinstance(cycle.get("latest_forecast"), dict) else {}
    resolved_actual = cycle.get("resolved_actual") if isinstance(cycle.get("resolved_actual"), dict) else None
    kpis = cycle.get("kpis") if isinstance(cycle.get("kpis"), dict) else {}
    first_call = kpis.get("first_call_week_ahead") if isinstance(kpis.get("first_call_week_ahead"), dict) else {}
    latest_call = (
        kpis.get("rolling_revision_accuracy") if isinstance(kpis.get("rolling_revision_accuracy"), dict) else {}
    )

    return {
        "forecast_cycle_id": cycle.get("forecast_cycle_id"),
        "ticker": cycle.get("ticker"),
        "target_week_end_date": cycle.get("target_week_end_date"),
        "cycle_status": cycle.get("cycle_status", "open"),
        "initial_origin_id": initial_forecast.get("forecast_origin_id"),
        "latest_origin_id": latest_forecast.get("forecast_origin_id"),
        "latest_last_observation_date": latest_forecast.get("last_observation_date"),
        "latest_forecast_date": latest_forecast.get("final_forecast_date"),
        "initial_predicted_target_close": _safe_float(initial_forecast.get("predicted_target_close")),
        "latest_predicted_target_close": _safe_float(latest_forecast.get("predicted_target_close")),
        "latest_predicted_target_return_pct": _safe_float(latest_forecast.get("predicted_target_return_pct")),
        "resolved_actual_close": _safe_float(resolved_actual.get("actual_target_close")) if resolved_actual else None,
        "first_call_absolute_error": _safe_float(first_call.get("absolute_error")),
        "latest_absolute_error": _safe_float(latest_call.get("absolute_error")),
        "first_call_error_pct": _safe_float(first_call.get("error_pct")),
        "latest_error_pct": _safe_float(latest_call.get("error_pct")),
        "first_call_direction_match": _safe_bool(first_call.get("direction_match")),
        "latest_direction_match": _safe_bool(latest_call.get("direction_match")),
        "initial_forecast_json": json_dumps(initial_forecast),
        "latest_forecast_json": json_dumps(latest_forecast),
        "revisions_json": json_dumps(cycle.get("revisions", [])),
        "resolved_actual_json": json_dumps(resolved_actual) if resolved_actual is not None else None,
        "kpis_json": json_dumps(kpis),
        "source_run_date": source_run_date,
        "source_summary_file": source_summary_file,
        "updated_at": cycle.get("updated_at") or _utc_now(),
    }


def resolution_event_row(cycle: dict[str, Any], *, source_run_date: str) -> dict[str, Any] | None:
    """Build a resolution-event row when the cycle has resolved actuals."""
    resolved_actual = cycle.get("resolved_actual")
    if not isinstance(resolved_actual, dict):
        return None
    kpis = cycle.get("kpis") if isinstance(cycle.get("kpis"), dict) else {}
    first_call = kpis.get("first_call_week_ahead") if isinstance(kpis.get("first_call_week_ahead"), dict) else {}
    latest_call = (
        kpis.get("rolling_revision_accuracy") if isinstance(kpis.get("rolling_revision_accuracy"), dict) else {}
    )
    return {
        "forecast_cycle_id": cycle.get("forecast_cycle_id"),
        "ticker": cycle.get("ticker"),
        "target_week_end_date": cycle.get("target_week_end_date"),
        "resolved_at": resolved_actual.get("resolved_at"),
        "actual_target_close": _safe_float(resolved_actual.get("actual_target_close")),
        "first_call_origin_id": first_call.get("forecast_origin_id"),
        "latest_origin_id": latest_call.get("forecast_origin_id"),
        "first_call_absolute_error": _safe_float(first_call.get("absolute_error")),
        "latest_absolute_error": _safe_float(latest_call.get("absolute_error")),
        "first_call_error_pct": _safe_float(first_call.get("error_pct")),
        "latest_error_pct": _safe_float(latest_call.get("error_pct")),
        "first_call_direction_match": _safe_bool(first_call.get("direction_match")),
        "latest_direction_match": _safe_bool(latest_call.get("direction_match")),
        "source_run_date": source_run_date,
    }


def model_candidate_row(
    *,
    ticker: str,
    target_week_end_date: str,
    model_run_dir: str | None,
    metrics: dict[str, Any],
    runtime_config: dict[str, Any],
    candidate_kind: str = "selected_run",
) -> dict[str, Any]:
    """Record the current trained artifact as a candidate run."""
    model_version = str(Path(model_run_dir).name) if model_run_dir else None
    candidate_run_id = f"{ticker.upper()}:{target_week_end_date}:{model_version or 'unknown'}:{candidate_kind}"
    return {
        "candidate_run_id": candidate_run_id,
        "ticker": ticker.upper(),
        "target_week_end_date": target_week_end_date,
        "candidate_kind": candidate_kind,
        "model_run_dir": model_run_dir,
        "model_version": model_version,
        "metrics_json": json_dumps(metrics),
        "runtime_config_json": json_dumps(runtime_config),
        "created_at": _utc_now(),
    }


def model_selection_row(
    *,
    ticker: str,
    target_week_end_date: str,
    model_run_dir: str | None,
    reason: str,
    decision: dict[str, Any],
) -> dict[str, Any]:
    """Record the current selected model for the cycle."""
    model_version = str(Path(model_run_dir).name) if model_run_dir else None
    decision_id = f"{ticker.upper()}:{target_week_end_date}:{model_version or 'unknown'}"
    return {
        "decision_id": decision_id,
        "ticker": ticker.upper(),
        "target_week_end_date": target_week_end_date,
        "selected_model_run_dir": model_run_dir,
        "selected_model_version": model_version,
        "reason": reason,
        "decision_json": json_dumps(decision),
        "created_at": _utc_now(),
    }


def cycle_payload_from_summary_row(row: dict[str, Any]) -> dict[str, Any]:
    """Expand a cycle summary row back into the API-facing cycle payload."""
    initial_forecast = parse_json_field(row.get("initial_forecast_json")) or {}
    latest_forecast = parse_json_field(row.get("latest_forecast_json")) or {}
    revisions = parse_json_field(row.get("revisions_json")) or []
    resolved_actual = parse_json_field(row.get("resolved_actual_json"))
    kpis = parse_json_field(row.get("kpis_json")) or {}
    return {
        "forecast_cycle_id": row.get("forecast_cycle_id"),
        "ticker": row.get("ticker"),
        "target_week_end_date": row.get("target_week_end_date"),
        "cycle_status": row.get("cycle_status"),
        "initial_forecast": initial_forecast,
        "latest_forecast": latest_forecast,
        "revisions": revisions,
        "resolved_actual": resolved_actual,
        "kpis": kpis,
        "updated_at": row.get("updated_at"),
    }
