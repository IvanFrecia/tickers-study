#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Retrain configured tickers and publish market week-end predictions.

This orchestration script standardizes training settings for a weekly run,
generates per-ticker forecasts, extracts next market week-end close estimates,
and writes outputs to local files.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import logging
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any

# Ensure local imports resolve
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import PipelineConfig, TickerConfig, load_config
from src.forecast_ledger import (
    ACTIVE_PROMOTED_COHORT,
    LEDGER_TABLE_SCHEMAS,
    build_origin_record,
    cycle_payload_from_summary_row,
    cycle_summary_row,
    load_local_cycle,
    merge_origin_into_cycle,
    model_candidate_row,
    model_selection_row,
    resolution_event_row,
    resolve_cycle,
    save_local_cycle,
    schema_string,
)
from src.market_calendar import (
    following_market_week_end,
    latest_market_session_on_or_before,
    market_week_context,
    market_week_end,
)
from src.pipeline import PipelineRunner, configure_logging
from src.prediction import run_forecast


TARGET_CLOSE_ANCHOR_BLEND = 0.65


def _canonical(path: Path) -> Path:
    """Return canonical absolute path without requiring filesystem existence."""
    return path.expanduser().resolve(strict=False)


def _run_utc() -> str:
    """Return UTC timestamp for metadata payloads."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso_today() -> str:
    """Return today's date in ISO format."""
    return date.today().isoformat()


def _latest_run_dir(artifact_root: Path, ticker: str) -> Path:
    """Resolve the newest run directory for a ticker."""
    base = _canonical(artifact_root / ticker.upper())
    if not base.exists():
        raise FileNotFoundError(f"No artifacts root found for {ticker}: {base}")
    candidates = sorted([path for path in base.iterdir() if path.is_dir()], key=lambda path: path.name)
    if not candidates:
        raise FileNotFoundError(f"No artifact runs found for {ticker} under {base}")
    return candidates[-1]


def _load_json(path: Path) -> dict[str, Any]:
    """Load JSON from disk with dictionary fallback."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_json(path: Path, payload: dict[str, Any]) -> Path:
    """Write pretty JSON to disk and return canonical destination path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json_dumps(payload, indent=2), encoding="utf-8")
    return _canonical(path)


def _json_default(value: Any) -> str:
    """Serialize date-like values emitted by ledger rows."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")


def _json_dumps(value: Any, *, indent: int | None = None) -> str:
    """Serialize JSON payloads with support for date and datetime values."""
    return json.dumps(value, indent=indent, default=_json_default)


def _latest_matching_file(directory: Path, pattern: str) -> Path | None:
    """Return newest matching file inside a directory."""
    folder = _canonical(directory)
    if not folder.exists():
        return None
    matches = [item for item in folder.glob(pattern) if item.is_file()]
    if not matches:
        return None
    return max(matches, key=lambda item: item.stat().st_mtime)


def _load_previous_weekly_summary(
    *,
    local_risk_package_dir: Path,
    local_seed_path: Path,
    prefer_local: bool = False,
) -> tuple[dict[str, Any], str | None]:
    """Load the newest local weekly summary, then the local seed file."""
    del prefer_local
    local_summary = _latest_matching_file(local_risk_package_dir, "weekly_forecast_summary_simple_*.json")
    if local_summary is not None:
        payload = _load_json(local_summary)
        if payload:
            return payload, str(_canonical(local_summary))
    seed_path = _canonical(local_seed_path)
    if seed_path.exists():
        payload = _load_json(seed_path)
        if payload:
            return payload, str(seed_path)
    return {}, None


def _load_recent_weekly_summaries(
    *,
    local_risk_package_dir: Path,
    local_seed_path: Path,
    history_limit: int = 6,
    prefer_local: bool = False,
) -> list[tuple[dict[str, Any], str | None]]:
    """Load the newest local weekly summary for prior-week comparisons."""
    del history_limit, prefer_local
    payload, source = _load_previous_weekly_summary(
        local_risk_package_dir=local_risk_package_dir,
        local_seed_path=local_seed_path,
    )
    if payload:
        return [(payload, source)]
    return []


def _select_prior_ticker_payload(

    *,
    symbol: str,
    current_last_observation: str | None,
    summary_candidates: list[tuple[dict[str, Any], str | None]],
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Pick best prior summary ticker payload for comparison against current close."""
    latest_fallback: tuple[dict[str, Any] | None, str | None, str | None] = (None, None, None)
    for payload, source in summary_candidates:
        tickers = payload.get("tickers", {})
        if not isinstance(tickers, dict):
            continue
        ticker_payload = tickers.get(symbol)
        if not isinstance(ticker_payload, dict):
            continue
        generated_at = str(payload.get("generated_at")) if isinstance(payload.get("generated_at"), str) else None
        if latest_fallback[0] is None:
            latest_fallback = (ticker_payload, generated_at, source)
        if current_last_observation and ticker_payload.get("target_week_end_date") == current_last_observation:
            return ticker_payload, generated_at, source
    return latest_fallback


def _previous_week_comparison(
    *,
    previous_ticker_payload: dict[str, Any] | None,
    previous_generated_at: str | None,
    previous_summary_source: str | None,
    current_last_observation: str | None,
    current_last_close: float | None,
) -> dict[str, Any]:
    """Build prior-week predicted-vs-actual comparison block for one ticker."""
    if not previous_ticker_payload:
        return {
            "status": "no_prior_forecast",
            "prior_generated_at": previous_generated_at,
            "prior_summary_source": previous_summary_source,
            "target_week_end_date": None,
            "predicted_close": None,
            "actual_close": None,
            "absolute_error": None,
            "error_pct": None,
            "predicted_return_pct": None,
            "realized_return_pct": None,
            "direction_match": None,
            "prior_week_start_close": None,
        }

    target_week_end_date = previous_ticker_payload.get("target_week_end_date")
    predicted_close_raw = previous_ticker_payload.get("expected_week_close")
    predicted_close = float(predicted_close_raw) if isinstance(predicted_close_raw, (int, float)) else None
    predicted_return_raw = previous_ticker_payload.get("expected_week_return_pct")
    predicted_return_pct = float(predicted_return_raw) if isinstance(predicted_return_raw, (int, float)) else None
    prior_week_start_raw = previous_ticker_payload.get("last_close")
    prior_week_start_close = float(prior_week_start_raw) if isinstance(prior_week_start_raw, (int, float)) else None

    actual_close = None
    if (
        isinstance(target_week_end_date, str)
        and current_last_observation == target_week_end_date
        and isinstance(current_last_close, (int, float))
    ):
        actual_close = float(current_last_close)

    absolute_error = None
    error_pct = None
    if actual_close is not None and predicted_close is not None:
        absolute_error = abs(actual_close - predicted_close)
        if predicted_close != 0:
            error_pct = (actual_close - predicted_close) / predicted_close * 100.0

    realized_return_pct = None
    if (
        actual_close is not None
        and isinstance(prior_week_start_close, (int, float))
        and prior_week_start_close not in (0.0,)
    ):
        realized_return_pct = (actual_close - prior_week_start_close) / prior_week_start_close * 100.0

    direction_match = None
    if isinstance(predicted_return_pct, (int, float)) and isinstance(realized_return_pct, (int, float)):
        if predicted_return_pct == 0 and realized_return_pct == 0:
            direction_match = True
        elif predicted_return_pct == 0 or realized_return_pct == 0:
            direction_match = False
        else:
            direction_match = (predicted_return_pct > 0) == (realized_return_pct > 0)

    status = "pending_actual"
    if predicted_close is None or not isinstance(target_week_end_date, str):
        status = "insufficient_prior_data"
    elif actual_close is not None:
        status = "resolved"

    return {
        "status": status,
        "prior_generated_at": previous_generated_at,
        "prior_summary_source": previous_summary_source,
        "target_week_end_date": target_week_end_date if isinstance(target_week_end_date, str) else None,
        "predicted_close": predicted_close,
        "actual_close": actual_close,
        "absolute_error": absolute_error,
        "error_pct": error_pct,
        "predicted_return_pct": predicted_return_pct,
        "realized_return_pct": realized_return_pct,
        "direction_match": direction_match,
        "prior_week_start_close": prior_week_start_close,
    }


def _load_state(path: Path) -> dict[str, Any]:
    """Load adaptive retry state for self-tuning sleep intervals."""
    state = _load_json(path)
    if "tickers" not in state or not isinstance(state["tickers"], dict):
        state["tickers"] = {}
    return state


def _save_state(path: Path, state: dict[str, Any]) -> None:
    """Persist adaptive retry state."""
    _save_json(path, state)
def _status_for_metrics(metrics: dict[str, float], mae_threshold: float, r2_threshold: float) -> str:
    """Map aggregate metrics to portfolio status classification."""
    mae = metrics.get("MAE")
    r2 = metrics.get("R2")
    if isinstance(mae, (int, float)) and isinstance(r2, (int, float)):
        if float(mae) <= mae_threshold and float(r2) >= r2_threshold:
            return "active"
    return "under_review"


def _tone_for_return(expected_week_return_pct: float | None) -> str:
    """Translate expected weekly return into qualitative direction."""
    if expected_week_return_pct is None:
        return "Unknown"
    if expected_week_return_pct > 0:
        return "Upside bias"
    if expected_week_return_pct < 0:
        return "Downside bias"
    return "Sideways bias"


def _forecast_risk(
    *,
    expected_week_return_pct: float | None,
) -> dict[str, Any]:
    """Classify projected week-end move without suppressing publication."""
    abs_expected_week_return_pct = abs(float(expected_week_return_pct)) if isinstance(expected_week_return_pct, (int, float)) else None
    elevated_threshold_pct = 15.0
    extreme_threshold_pct = 25.0
    state = "normal"
    severity = "good"
    label = "Normal forecast band"
    message = "Projected move is within the current publish warning band."
    threshold_pct = None
    note = None

    if abs_expected_week_return_pct is None:
        state = "unknown"
        severity = "info"
        label = "Forecast band unavailable"
        message = "Projected move band could not be evaluated for this run."
    elif abs_expected_week_return_pct >= extreme_threshold_pct:
        state = "extreme_move"
        severity = "warning"
        label = "Extreme move"
        threshold_pct = extreme_threshold_pct
        message = (
            f"Projected week-end move of {expected_week_return_pct:+.2f}% is far outside a normal one-week band "
            "and should be treated as experimental."
        )
        note = f"Extreme move: projected week return {expected_week_return_pct:+.2f}%."
    elif abs_expected_week_return_pct >= elevated_threshold_pct:
        state = "elevated_move"
        severity = "info"
        label = "Elevated move"
        threshold_pct = elevated_threshold_pct
        message = (
            f"Projected week-end move of {expected_week_return_pct:+.2f}% is unusually large for one week "
            "and should be watched closely."
        )
        note = f"Elevated move: projected week return {expected_week_return_pct:+.2f}%."

    return {
        "state": state,
        "severity": severity,
        "label": label,
        "message": message,
        "expected_week_return_pct": float(expected_week_return_pct) if isinstance(expected_week_return_pct, (int, float)) else None,
        "abs_expected_week_return_pct": abs_expected_week_return_pct,
        "elevated_threshold_pct": elevated_threshold_pct,
        "extreme_threshold_pct": extreme_threshold_pct,
        "threshold_pct": threshold_pct,
        "note": note,
    }


def _select_week_end_projection(
    forecast_rows: list[dict[str, Any]],
    target_week_end_iso: str,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str]:
    """Select market week-end projection and rows up to that target date."""
    daily: list[dict[str, Any]] = []
    target_row = None
    ordered = sorted(
        (row for row in forecast_rows if isinstance(row, dict) and row.get("forecast_date")),
        key=lambda row: str(row.get("forecast_date")),
    )
    for row in ordered:
        forecast_date = str(row.get("forecast_date", ""))
        if forecast_date <= target_week_end_iso:
            daily.append(row)
        if forecast_date == target_week_end_iso:
            target_row = row
    if target_row is not None:
        return target_row, daily, "exact_market_close"
    if daily:
        return daily[-1], daily, "nearest_prior_session"
    if ordered:
        return ordered[-1], ordered, "latest_available"
    return None, [], "none"


def _target_market_week_end(last_observation_iso: str | None, anchor: date) -> str:
    """Resolve next market week-end close date for a ticker."""
    if last_observation_iso:
        try:
            return following_market_week_end(date.fromisoformat(last_observation_iso)).isoformat()
        except ValueError:
            pass
    return market_week_end(anchor).isoformat()


def _parse_iso_date(value: str | None, *, field_name: str) -> date | None:
    """Parse one optional ISO date argument."""
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be YYYY-MM-DD, got {value!r}.") from exc


def _live_market_anchor_date() -> date:
    """Return the latest market session for the current New York market clock."""
    context = market_week_context()
    latest = context.get("latest_market_session_date")
    if isinstance(latest, str):
        try:
            return date.fromisoformat(latest)
        except ValueError:
            pass
    market_date = context.get("market_date")
    if isinstance(market_date, str):
        try:
            return latest_market_session_on_or_before(date.fromisoformat(market_date))
        except ValueError:
            pass
    return latest_market_session_on_or_before(datetime.now(timezone.utc))


def _resolve_anchor_date(value: str | None) -> date:
    """Resolve the effective anchor date for one run."""
    parsed = _parse_iso_date(value, field_name="--as-of-date")
    if parsed is not None:
        return latest_market_session_on_or_before(parsed)
    return _live_market_anchor_date()


def _catch_up_observation_dates(start_target_week_end: str, latest_available_observation: date) -> list[str]:
    """Return the ordered list of weekly catch-up observation dates to execute."""
    observation = date.fromisoformat(start_target_week_end)
    sequence: list[str] = []
    while observation <= latest_available_observation:
        sequence.append(observation.isoformat())
        next_observation = following_market_week_end(observation)
        if next_observation <= observation:
            raise ValueError(
                "Catch-up observation sequence did not advance; "
                f"observation={observation.isoformat()} next={next_observation.isoformat()}"
            )
        observation = next_observation
    return sequence


def _bridge_close_to_target(start_close: float, target_close: float, progress: float) -> float:
    """Interpolate from the current actual close toward the selected target close."""
    progress = min(max(progress, 0.0), 1.0)
    if start_close > 0.0 and target_close > 0.0:
        return float(start_close * ((target_close / start_close) ** progress))
    return float(start_close + (target_close - start_close) * progress)


def _attach_target_anchored_display_path(
    daily_rows: list[dict[str, Any]],
    *,
    week_start_close: float | None,
    target_close: float | None,
) -> list[dict[str, Any]]:
    """Add a display-oriented close path that stays visibly anchored to the week-end target.

    The raw model close remains untouched under ``predicted_close``. ``display_close`` is the
    dashboard-facing path: it blends the raw day-by-day sequence with a smooth bridge from the
    current actual close to the selected target close so the week is read as one target-date call.
    """
    if not daily_rows:
        return []

    enriched_rows: list[dict[str, Any]] = []
    total = len(daily_rows)
    for idx, row in enumerate(daily_rows, start=1):
        item = dict(row)
        raw_close = row.get("predicted_close")
        predicted_close = float(raw_close) if isinstance(raw_close, (int, float)) else None
        item["raw_predicted_close"] = predicted_close
        item["display_close"] = predicted_close
        if (
            predicted_close is not None
            and isinstance(week_start_close, (int, float))
            and isinstance(target_close, (int, float))
        ):
            progress = idx / total
            bridge_close = _bridge_close_to_target(float(week_start_close), float(target_close), progress)
            display_close = (
                predicted_close * (1.0 - TARGET_CLOSE_ANCHOR_BLEND)
                + bridge_close * TARGET_CLOSE_ANCHOR_BLEND
            )
            if idx == total:
                display_close = float(target_close)
            item["target_bridge_close"] = bridge_close
            item["display_close"] = float(display_close)
        enriched_rows.append(item)
    return enriched_rows


def _select_display_day_label(day_iso: str) -> str:
    """Short weekday label for dashboard rows."""
    try:
        return datetime.strptime(day_iso, "%Y-%m-%d").strftime("%a")
    except ValueError:
        return day_iso


def _apply_constant_overrides(
    pipeline_cfg: PipelineConfig,
    selected: set[str],
    *,
    constant_loss: str,
    horizon: int,
    epochs: int,
    splits: int,
    end_date: str | None,
) -> None:
    """Mutate selected ticker configs with standardized weekly run settings."""
    for ticker_cfg in pipeline_cfg.tickers:
        if ticker_cfg.symbol not in selected:
            continue
        ticker_cfg.model.loss = constant_loss
        ticker_cfg.forecast_horizon = horizon
        ticker_cfg.model.epochs = epochs
        ticker_cfg.backtest.splits = splits
        ticker_cfg.end_date = end_date


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for weekly retrain/publish orchestration."""
    parser = argparse.ArgumentParser(
        description=(
            "Retrain selected tickers with a unified loss override, forecast next market week-end close, "
            "and write a local weekly summary."
        )
    )
    parser.add_argument("--config", type=Path, default=Path("configs/tickers.toml"), help="Base pipeline config.")
    parser.add_argument("--tickers", nargs="*", help="Optional subset of ticker symbols.")
    parser.add_argument(
        "--constant-loss",
        default="weighted_mse",
        help="Loss override applied across the retrain run. `weighted_mse` favors the target week-end close.",
    )
    parser.add_argument(
        "--horizon",
        type=int,
        default=5,
        help="Unified forecast horizon applied to all selected tickers for this retrain run.",
    )
    parser.add_argument("--epochs", type=int, default=20, help="Unified epochs override for selected tickers.")
    parser.add_argument("--backtest-splits", type=int, default=2, help="Unified backtest splits override.")
    parser.add_argument("--max-attempts", type=int, default=2, help="Retry attempts per ticker training.")
    parser.add_argument("--base-sleep-seconds", type=int, default=15, help="Base sleep between retry attempts.")
    parser.add_argument("--max-sleep-seconds", type=int, default=180, help="Maximum adaptive retry sleep.")
    parser.add_argument("--mae-threshold", type=float, default=10.0, help="MAE threshold for active status.")
    parser.add_argument("--r2-threshold", type=float, default=0.60, help="R2 threshold for active status.")
    parser.add_argument(
        "--summary-out",
        type=Path,
        help="Optional explicit weekly summary output path. Defaults to reports/risk_package naming.",
    )
    parser.add_argument(
        "--seed-out",
        type=Path,
        default=Path("app/seed/weekly_forecast_summary_simple_seed.json"),
        help="Local seed summary path written for the dashboard.",
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=Path("reports/risk_package/automation_state.json"),
        help="Adaptive retry state file for self-tuning sleep intervals.",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        help="Logging level for orchestration output.",
    )
    parser.add_argument(
        "--as-of-date",
        type=str,
        help="Optional market-session cutoff date (YYYY-MM-DD) used for historical weekly catch-up runs.",
    )
    parser.add_argument(
        "--prefer-local-prior-summary",
        action="store_true",
        help="Prefer the newest local weekly summary.",
    )
    parser.add_argument(
        "--catch-up-from-latest-summary",
        action="store_true",
        help="Run weekly retrain/publish repeatedly from the latest published target week-end through the latest available market observation.",
    )
    parser.add_argument(
        "--catch-up-start-target-week-end",
        type=str,
        help="Optional override for the starting target week-end (YYYY-MM-DD) when catch-up mode should not use the latest summary.",
    )
    parser.add_argument(
        "--catch-up-until-date",
        type=str,
        help="Optional upper-bound date (YYYY-MM-DD) for catch-up observation selection. Defaults to today.",
    )
    parser.add_argument(
        "--active-cohort-only",
        action="store_true",
        help="Restrict runs to the active promoted cohort (AMZN, BA, GOOG, NVDA).",
    )
    parser.add_argument(
        "--require-exact-target-match",
        action="store_true",
        help="Fail a ticker publish when the forecast does not hit the exact market week-end close date.",
    )
    parser.add_argument(
        "--ledger-local-root",
        type=Path,
        default=Path("reports/forecast_ledger"),
        help="Local root for cycle snapshots and NDJSON ledger artifacts.",
    )
    return parser.parse_args()


def run_cycle(
    args: argparse.Namespace,
    *,
    as_of_date_override: str | None = None,
    prefer_local_prior_summary: bool | None = None,
) -> dict[str, Any]:
    """Run one retrain, forecast, publish, and summary generation cycle."""
    effective_anchor = _resolve_anchor_date(as_of_date_override if as_of_date_override is not None else args.as_of_date)
    effective_as_of_date = effective_anchor.isoformat()
    effective_prefer_local_prior_summary = (
        args.prefer_local_prior_summary if prefer_local_prior_summary is None else prefer_local_prior_summary
    )
    pipeline_cfg = load_config(args.config)
    selected = {ticker.symbol for ticker in pipeline_cfg.tickers}
    if args.tickers:
        selected = {symbol.upper() for symbol in args.tickers}
    if args.active_cohort_only:
        selected &= set(ACTIVE_PROMOTED_COHORT)

    _apply_constant_overrides(
        pipeline_cfg,
        selected,
        constant_loss=args.constant_loss,
        horizon=args.horizon,
        epochs=args.epochs,
        splits=args.backtest_splits,
        end_date=effective_as_of_date,
    )

    runner = PipelineRunner(pipeline_cfg)
    ledger_local_root = _canonical(args.ledger_local_root)
    ledger_local_root.mkdir(parents=True, exist_ok=True)
    state_path = _canonical(args.state_file)
    state = _load_state(state_path)
    ticker_state: dict[str, Any] = state.setdefault("tickers", {})

    anchor = effective_anchor
    default_week_end_iso = market_week_end(anchor).isoformat()
    run_date_iso = effective_as_of_date
    calendar_anchor: date | datetime = (
        datetime.now(timezone.utc)
        if args.as_of_date is None and as_of_date_override is None
        else anchor
    )
    calendar_context = market_week_context(calendar_anchor)
    calendar_context["target_week_end_date"] = default_week_end_iso

    weekly_payload: dict[str, Any] = {
        "generated_at": _run_utc(),
        "week": {"start": None, "end": default_week_end_iso, "target": "market_close"},
        "market_calendar": calendar_context,
        "source_files": {},
        "tickers": {},
        "run": {
            "constant_loss": args.constant_loss,
            "constant_horizon": args.horizon,
            "epochs": args.epochs,
            "backtest_splits": args.backtest_splits,
            "attempts_per_ticker": args.max_attempts,
        },
    }

    recent_summary_candidates = _load_recent_weekly_summaries(
        local_risk_package_dir=Path("reports/risk_package"),
        local_seed_path=args.seed_out,
        prefer_local=effective_prefer_local_prior_summary,
    )
    prior_summary_source = recent_summary_candidates[0][1] if recent_summary_candidates else None
    prior_summary_generated_at = None
    if recent_summary_candidates and isinstance(recent_summary_candidates[0][0].get("generated_at"), str):
        prior_summary_generated_at = str(recent_summary_candidates[0][0].get("generated_at"))
    weekly_payload["run"]["prior_summary_source"] = prior_summary_source
    weekly_payload["run"]["prior_summary_generated_at"] = prior_summary_generated_at
    weekly_payload["run"]["prior_summary_history_loaded"] = len(recent_summary_candidates)

    bq_rows: list[dict[str, Any]] = []
    origin_rows: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []
    selection_rows: list[dict[str, Any]] = []
    cycle_snapshots: dict[tuple[str, str], dict[str, Any]] = {}
    resolved_cycle_snapshots: dict[tuple[str, str], dict[str, Any]] = {}
    week_starts: list[str] = []
    week_ends: list[str] = []
    successful_tickers: list[str] = []

    def load_existing_cycle(symbol: str, target_week_end_iso: str) -> dict[str, Any] | None:
        return load_local_cycle(ledger_local_root, symbol, target_week_end_iso)

    configured_symbols = [ticker.symbol for ticker in pipeline_cfg.tickers if ticker.symbol in selected]
    for symbol in configured_symbols:
        per_ticker_state = ticker_state.setdefault(symbol, {})
        sleep_seconds = int(per_ticker_state.get("recommended_sleep_seconds", args.base_sleep_seconds))
        success = False
        last_error = ""
        target_week_end_iso = default_week_end_iso

        for attempt in range(1, args.max_attempts + 1):
            started = time.time()
            try:
                logging.info("Training ticker %s (attempt %d/%d)", symbol, attempt, args.max_attempts)
                summaries = runner.run([symbol])
                summary = summaries[symbol]
                duration = round(time.time() - started, 2)
                per_ticker_state.update(
                    {
                        "last_status": "success",
                        "last_duration_seconds": duration,
                        "last_error": "",
                        "last_updated_at": _run_utc(),
                    }
                )
                sleep_seconds = max(args.base_sleep_seconds, int(sleep_seconds * 0.85))
                per_ticker_state["recommended_sleep_seconds"] = sleep_seconds

                latest_run = _latest_run_dir(pipeline_cfg.artifact_root, symbol)
                model_path = latest_run / "models" / "best_model.keras"
                scaler_path = latest_run / "scalers" / "best_scaler.pkl"
                forecast_path = _canonical(Path("predictions") / symbol / f"{run_date_iso}_weekly.json")
                forecast_path.parent.mkdir(parents=True, exist_ok=True)

                forecast_payload = run_forecast(
                    config_path=args.config,
                    ticker=symbol,
                    model_path=model_path,
                    scaler_path=scaler_path,
                    output_path=forecast_path,
                    end_date=effective_as_of_date,
                    dump_json=True,
                )

                last_observation = (
                    str(forecast_payload.get("last_observation_date"))
                    if forecast_payload.get("last_observation_date")
                    else None
                )
                target_week_end_iso = _target_market_week_end(last_observation, anchor)
                forecast_rows = forecast_payload.get("forecast", [])
                if not isinstance(forecast_rows, list):
                    forecast_rows = []
                week_end_row, daily_rows, projection_selection = _select_week_end_projection(
                    forecast_rows, target_week_end_iso
                )
                last_close = forecast_payload.get("context", {}).get("last_close")
                predicted_week_end_close = (
                    float(week_end_row["predicted_close"])
                    if week_end_row and week_end_row.get("predicted_close") is not None
                    else None
                )
                current_last_close = float(last_close) if isinstance(last_close, (int, float)) else None
                expected_week_return_pct = None
                if (
                    isinstance(last_close, (int, float))
                    and last_close not in (0, 0.0)
                    and predicted_week_end_close is not None
                ):
                    expected_week_return_pct = (
                        (predicted_week_end_close - float(last_close)) / float(last_close) * 100.0
                )

                status = _status_for_metrics(summary.aggregated_metrics, args.mae_threshold, args.r2_threshold)
                tone = _tone_for_return(expected_week_return_pct)
                forecast_risk = _forecast_risk(expected_week_return_pct=expected_week_return_pct)
                (
                    previous_ticker_payload,
                    selected_prior_generated_at,
                    selected_prior_source,
                ) = _select_prior_ticker_payload(
                    symbol=symbol,
                    current_last_observation=last_observation,
                    summary_candidates=recent_summary_candidates,
                )
                previous_week = _previous_week_comparison(
                    previous_ticker_payload=previous_ticker_payload,
                    previous_generated_at=selected_prior_generated_at,
                    previous_summary_source=selected_prior_source,
                    current_last_observation=last_observation,
                    current_last_close=current_last_close,
                )

                anchored_daily_rows = _attach_target_anchored_display_path(
                    daily_rows,
                    week_start_close=current_last_close,
                    target_close=predicted_week_end_close,
                )
                daily_payload = []
                running_prev = float(last_close) if isinstance(last_close, (int, float)) else None
                for row in anchored_daily_rows:
                    forecast_date = str(row.get("forecast_date", ""))
                    if row.get("predicted_close") is None:
                        continue
                    predicted_close = float(row.get("predicted_close"))
                    display_close = (
                        float(row["display_close"])
                        if isinstance(row.get("display_close"), (int, float))
                        else predicted_close
                    )
                    daily_change_pct = None
                    cumulative_change_pct = None
                    if running_prev not in (None, 0.0):
                        daily_change_pct = (predicted_close - running_prev) / running_prev * 100.0
                    if isinstance(last_close, (int, float)) and float(last_close) not in (0.0,):
                        cumulative_change_pct = (predicted_close - float(last_close)) / float(last_close) * 100.0
                    running_prev = predicted_close
                    daily_payload.append(
                        {
                            "date": forecast_date,
                            "day": _select_display_day_label(forecast_date),
                            "predicted_close": predicted_close,
                            "display_close": display_close,
                            "raw_predicted_close": (
                                float(row["raw_predicted_close"])
                                if isinstance(row.get("raw_predicted_close"), (int, float))
                                else predicted_close
                            ),
                            "daily_change_pct": daily_change_pct,
                            "cumulative_change_pct": cumulative_change_pct,
                            "is_target_week_end": forecast_date == target_week_end_iso,
                        }
                    )

                final_forecast_date = (
                    str(week_end_row.get("forecast_date"))
                    if week_end_row is not None and week_end_row.get("forecast_date")
                    else (daily_payload[-1]["date"] if daily_payload else None)
                )
                if args.require_exact_target_match and projection_selection != "exact_market_close":
                    raise RuntimeError(
                        f"{symbol} did not produce an exact target-date forecast for {target_week_end_iso}; "
                        f"selection={projection_selection}"
                    )
                if last_observation:
                    week_starts.append(last_observation)
                if target_week_end_iso:
                    week_ends.append(target_week_end_iso)

                source_file = str(Path("predictions") / symbol / f"{run_date_iso}_weekly.json")
                existing_cycle = load_existing_cycle(symbol, target_week_end_iso)
                origin_record = build_origin_record(
                    ticker=symbol,
                    target_week_end_date=target_week_end_iso,
                    last_observation_date=last_observation,
                    issued_at=weekly_payload["generated_at"],
                    final_forecast_date=final_forecast_date,
                    projection_selection=projection_selection,
                    week_start_close=current_last_close,
                    predicted_target_close=predicted_week_end_close,
                    predicted_target_return_pct=expected_week_return_pct,
                    model_run_dir=str(_canonical(latest_run)),
                    config_snapshot_path=str(_canonical(args.config)),
                    forecast_rows=daily_payload,
                    run_date=run_date_iso,
                    summary_source_file=None,
                    existing_cycle=existing_cycle,
                )
                cycle_snapshot = merge_origin_into_cycle(existing_cycle, origin_record)
                save_local_cycle(ledger_local_root, cycle_snapshot)
                cycle_snapshots[(symbol, target_week_end_iso)] = cycle_snapshot

                origin_rows.append(
                    {
                        **{key: value for key, value in origin_record.items() if key != "forecast"},
                        "forecast_json": json.dumps(origin_record.get("forecast", [])),
                    }
                )
                candidate_rows.append(
                    model_candidate_row(
                        ticker=symbol,
                        target_week_end_date=target_week_end_iso,
                        model_run_dir=str(_canonical(latest_run)),
                        metrics=summary.aggregated_metrics,
                        runtime_config={
                            "constant_loss": args.constant_loss,
                            "constant_horizon": args.horizon,
                            "epochs": args.epochs,
                            "backtest_splits": args.backtest_splits,
                            "require_exact_target_match": args.require_exact_target_match,
                        },
                    )
                )
                selection_rows.append(
                    model_selection_row(
                        ticker=symbol,
                        target_week_end_date=target_week_end_iso,
                        model_run_dir=str(_canonical(latest_run)),
                        reason="current retrain selected as staging candidate",
                        decision={
                            "projection_selection": projection_selection,
                            "target_matched": origin_record.get("target_matched"),
                            "metrics": summary.aggregated_metrics,
                        },
                    )
                )
                if (
                    isinstance(previous_week.get("status"), str)
                    and previous_week.get("status") == "resolved"
                    and isinstance(previous_week.get("target_week_end_date"), str)
                    and isinstance(previous_week.get("actual_close"), (int, float))
                ):
                    previous_cycle = load_existing_cycle(symbol, str(previous_week["target_week_end_date"]))
                    if previous_cycle is not None:
                        resolved_cycle = resolve_cycle(
                            previous_cycle,
                            actual_target_close=float(previous_week["actual_close"]),
                            resolved_at=weekly_payload["generated_at"],
                            source_run_date=run_date_iso,
                        )
                        save_local_cycle(ledger_local_root, resolved_cycle)
                        resolved_cycle_snapshots[(symbol, str(previous_week["target_week_end_date"]))] = resolved_cycle

                weekly_payload["source_files"][symbol] = source_file
                weekly_payload["tickers"][symbol] = {
                    "last_observation": last_observation,
                    "last_close": current_last_close,
                    "target_week_end_date": target_week_end_iso,
                    "final_forecast_date": final_forecast_date,
                    "projection_selection": projection_selection,
                    "expected_week_close": predicted_week_end_close,
                    "expected_week_return_pct": expected_week_return_pct,
                    "tone": tone,
                    "forecast_risk": forecast_risk,
                    "note": forecast_risk.get("note"),
                    "daily": daily_payload,
                    "status": status,
                    "target_matched": final_forecast_date == target_week_end_iso if final_forecast_date else False,
                    "cycle_status": cycle_snapshot.get("cycle_status"),
                    "initial_forecast": cycle_snapshot.get("initial_forecast"),
                    "latest_forecast": cycle_snapshot.get("latest_forecast"),
                    "revisions": cycle_snapshot.get("revisions"),
                    "resolved_actual": cycle_snapshot.get("resolved_actual"),
                    "kpis": cycle_snapshot.get("kpis"),
                    "model_metrics": {
                        "mae": summary.aggregated_metrics.get("MAE"),
                        "rmse": summary.aggregated_metrics.get("RMSE"),
                        "mape": summary.aggregated_metrics.get("MAPE"),
                        "r2": summary.aggregated_metrics.get("R2"),
                    },
                    "previous_week_comparison": previous_week,
                    "artifact_run_dir": str(_canonical(latest_run)),
                }

                bq_rows.append(
                    {
                        "run_date": run_date_iso,
                        "week_start": last_observation,
                        "week_end": target_week_end_iso,
                        "ticker": symbol,
                        "status": status,
                        "last_observation": last_observation,
                        "target_week_end_date": target_week_end_iso,
                        "final_forecast_date": final_forecast_date,
                        "last_close": float(last_close) if isinstance(last_close, (int, float)) else None,
                        "expected_week_close": predicted_week_end_close,
                        "expected_week_return_pct": expected_week_return_pct,
                        "mae": summary.aggregated_metrics.get("MAE"),
                        "rmse": summary.aggregated_metrics.get("RMSE"),
                        "mape": summary.aggregated_metrics.get("MAPE"),
                        "r2": summary.aggregated_metrics.get("R2"),
                        "source_file": source_file,
                        "projection_selection": projection_selection,
                        "note": forecast_risk.get("note"),
                        "generated_at": _run_utc(),
                    }
                )
                successful_tickers.append(symbol)
                success = True
                break
            except Exception as exc:  # noqa: BLE001 - orchestration should continue on ticker failures
                duration = round(time.time() - started, 2)
                last_error = f"{type(exc).__name__}: {exc}"
                logging.exception("Ticker %s failed on attempt %d/%d", symbol, attempt, args.max_attempts)
                per_ticker_state.update(
                    {
                        "last_status": "failure",
                        "last_duration_seconds": duration,
                        "last_error": last_error,
                        "last_updated_at": _run_utc(),
                    }
                )
                sleep_seconds = min(args.max_sleep_seconds, int(max(args.base_sleep_seconds, sleep_seconds) * 1.5))
                per_ticker_state["recommended_sleep_seconds"] = sleep_seconds
                if attempt < args.max_attempts:
                    logging.warning(
                        "Sleeping %d seconds before retrying ticker %s (attempt %d/%d).",
                        sleep_seconds,
                        symbol,
                        attempt + 1,
                        args.max_attempts,
                    )
                    time.sleep(sleep_seconds)

        if not success:
            logging.error("Ticker %s failed after %d attempts: %s", symbol, args.max_attempts, last_error)
            (
                previous_ticker_payload,
                selected_prior_generated_at,
                selected_prior_source,
            ) = _select_prior_ticker_payload(
                symbol=symbol,
                current_last_observation=None,
                summary_candidates=recent_summary_candidates,
            )
            weekly_payload["source_files"][symbol] = None
            weekly_payload["tickers"][symbol] = {
                "last_observation": None,
                "last_close": None,
                "target_week_end_date": target_week_end_iso,
                "final_forecast_date": None,
                "projection_selection": "none",
                "expected_week_close": None,
                "expected_week_return_pct": None,
                "tone": "Data unavailable",
                "daily": [],
                "status": "under_review",
                "note": last_error or "Training/forecasting failed.",
                "forecast_risk": {
                    "state": "unknown",
                    "severity": "warning",
                    "label": "Forecast unavailable",
                    "message": last_error or "Training/forecasting failed.",
                    "expected_week_return_pct": None,
                    "abs_expected_week_return_pct": None,
                    "elevated_threshold_pct": 15.0,
                    "extreme_threshold_pct": 25.0,
                    "threshold_pct": None,
                    "note": last_error or "Training/forecasting failed.",
                },
                "previous_week_comparison": _previous_week_comparison(
                    previous_ticker_payload=previous_ticker_payload,
                    previous_generated_at=selected_prior_generated_at,
                    previous_summary_source=selected_prior_source,
                    current_last_observation=None,
                    current_last_close=None,
                ),
            }
            bq_rows.append(
                {
                    "run_date": run_date_iso,
                    "week_start": None,
                    "week_end": target_week_end_iso,
                    "ticker": symbol,
                    "status": "under_review",
                    "last_observation": None,
                    "target_week_end_date": target_week_end_iso,
                    "final_forecast_date": None,
                    "last_close": None,
                    "expected_week_close": None,
                    "expected_week_return_pct": None,
                    "mae": None,
                    "rmse": None,
                    "mape": None,
                    "r2": None,
                    "source_file": None,
                    "projection_selection": "none",
                    "note": last_error or "Training/forecasting failed.",
                    "generated_at": _run_utc(),
                }
            )

    weekly_payload["week"]["start"] = min(week_starts) if week_starts else run_date_iso
    weekly_payload["week"]["end"] = max(week_ends) if week_ends else default_week_end_iso
    weekly_payload["run"]["successful_tickers"] = sorted(successful_tickers)
    weekly_payload["run"]["failed_tickers"] = sorted(
        [symbol for symbol in configured_symbols if symbol not in successful_tickers]
    )

    summary_path = (
        _canonical(args.summary_out)
        if args.summary_out
        else _canonical(
            Path("reports/risk_package")
            / f"weekly_forecast_summary_simple_{weekly_payload['week']['start']}_to_{weekly_payload['week']['end']}.json"
        )
    )
    _save_json(summary_path, weekly_payload)
    _save_json(_canonical(args.seed_out), weekly_payload)

    cycle_rows: list[dict[str, Any]] = [
        cycle_summary_row(cycle, source_run_date=run_date_iso, source_summary_file=str(summary_path))
        for cycle in cycle_snapshots.values()
    ]
    for cycle in resolved_cycle_snapshots.values():
        cycle_rows.append(cycle_summary_row(cycle, source_run_date=run_date_iso, source_summary_file=str(summary_path)))
    resolution_rows = [
        row
        for row in (
            resolution_event_row(cycle, source_run_date=run_date_iso) for cycle in resolved_cycle_snapshots.values()
        )
        if row is not None
    ]

    ledger_rows_dir = _canonical(ledger_local_root / "rows")
    ledger_rows_dir.mkdir(parents=True, exist_ok=True)
    origin_rows_path = _canonical(
        ledger_rows_dir / f"forecast_origin_ledger_{weekly_payload['week']['start']}_to_{weekly_payload['week']['end']}.ndjson"
    )
    cycle_rows_path = _canonical(
        ledger_rows_dir / f"forecast_cycle_summary_{weekly_payload['week']['start']}_to_{weekly_payload['week']['end']}.ndjson"
    )
    resolution_rows_path = _canonical(
        ledger_rows_dir
        / f"forecast_resolution_events_{weekly_payload['week']['start']}_to_{weekly_payload['week']['end']}.ndjson"
    )
    candidate_rows_path = _canonical(
        ledger_rows_dir / f"model_candidate_runs_{weekly_payload['week']['start']}_to_{weekly_payload['week']['end']}.ndjson"
    )
    selection_rows_path = _canonical(
        ledger_rows_dir / f"model_selection_decisions_{weekly_payload['week']['start']}_to_{weekly_payload['week']['end']}.ndjson"
    )

    def _write_ndjson(path: Path, rows: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(_json_dumps(row) + "\n")

    _write_ndjson(origin_rows_path, origin_rows)
    _write_ndjson(cycle_rows_path, cycle_rows)
    _write_ndjson(resolution_rows_path, resolution_rows)
    _write_ndjson(candidate_rows_path, candidate_rows)
    _write_ndjson(selection_rows_path, selection_rows)

    rows_path = _canonical(
        Path("reports/risk_package")
        / f"weekly_forecast_rows_{weekly_payload['week']['start']}_to_{weekly_payload['week']['end']}.ndjson"
    )
    rows_path.parent.mkdir(parents=True, exist_ok=True)
    with rows_path.open("w", encoding="utf-8") as handle:
        for row in bq_rows:
            handle.write(_json_dumps(row) + "\n")

    _save_state(state_path, state)

    logging.info("Weekly summary written to %s", summary_path)
    logging.info("UI seed summary updated at %s", _canonical(args.seed_out))
    logging.info(
        "Processed tickers: success=%d failed=%d",
        len(successful_tickers),
        len(configured_symbols) - len(successful_tickers),
    )
    return weekly_payload


def _latest_target_week_end_from_payload(payload: dict[str, Any]) -> str | None:
    """Extract the latest target week-end date from a weekly summary payload."""
    week = payload.get("week")
    if isinstance(week, dict) and isinstance(week.get("end"), str) and week.get("end"):
        return str(week["end"])
    tickers = payload.get("tickers")
    if not isinstance(tickers, dict):
        return None
    target_dates = [
        str(info.get("target_week_end_date"))
        for info in tickers.values()
        if isinstance(info, dict) and isinstance(info.get("target_week_end_date"), str)
    ]
    return max(target_dates) if target_dates else None


def main() -> None:
    """Run the full retrain/publish flow once or as a weekly catch-up sequence."""
    args = parse_args()
    configure_logging(args.log_level)
    if not args.catch_up_from_latest_summary:
        run_cycle(args)
        return

    if args.as_of_date:
        raise ValueError("--as-of-date cannot be combined with --catch-up-from-latest-summary.")

    start_target_week_end = args.catch_up_start_target_week_end
    if start_target_week_end is None:
        latest_payload, latest_source = _load_previous_weekly_summary(
            local_risk_package_dir=Path("reports/risk_package"),
            local_seed_path=args.seed_out,
            prefer_local=args.prefer_local_prior_summary,
        )
        start_target_week_end = _latest_target_week_end_from_payload(latest_payload)
        if start_target_week_end is None:
            raise ValueError(
                "Catch-up mode requires an existing weekly summary or --catch-up-start-target-week-end."
            )
        logging.info(
            "Catch-up start resolved from prior summary %s at target %s.",
            latest_source,
            start_target_week_end,
        )

    catch_up_until = _parse_iso_date(args.catch_up_until_date, field_name="--catch-up-until-date")
    latest_available_observation = (
        latest_market_session_on_or_before(catch_up_until) if catch_up_until else _live_market_anchor_date()
    )
    observation_dates = _catch_up_observation_dates(start_target_week_end, latest_available_observation)
    if not observation_dates:
        logging.info(
            "No catch-up runs required. start_target_week_end=%s latest_available_observation=%s",
            start_target_week_end,
            latest_available_observation.isoformat(),
        )
        return

    logging.info(
        "Executing %d catch-up weekly cycles from %s through %s.",
        len(observation_dates),
        observation_dates[0],
        observation_dates[-1],
    )
    for observation_date in observation_dates:
        logging.info("Catch-up cycle starting for observation date %s", observation_date)
        run_cycle(args, as_of_date_override=observation_date, prefer_local_prior_summary=True)


if __name__ == "__main__":
    main()
