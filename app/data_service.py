"""Data-loading helpers for the dashboard API."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import json
import math
import os
from pathlib import Path
import re
from statistics import mean
from typing import Any
import tomllib

from src.forecast_ledger import (
    ACTIVE_PROMOTED_COHORT,
    build_origin_record,
    cycle_payload_from_summary_row,
    merge_origin_into_cycle,
    resolve_cycle,
)
from src.market_calendar import market_week_context

DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")
DISPLAY_GROUPS = (
    (
        "stale",
        "Stale / Needs Refresh",
        "Forecast rows that are behind the current market week and need a catch-up retrain or publish.",
    ),
    (
        "under_review",
        "Under Review",
        "Live symbols that failed a quality gate or are showing weak resolved accuracy.",
    ),
    (
        "active",
        "Live / On Track",
        "Current weekly forecasts that are being refreshed on schedule and have no major quality warning.",
    ),
)
MIN_CONFIDENCE_HISTORY_SAMPLES = 4


def _canonical(path: Path) -> Path:
    """Return an absolute canonical path without requiring existence."""
    return path.expanduser().resolve(strict=False)


def _safe_float(value: Any) -> float | None:
    """Best-effort conversion to float for dashboard payloads."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    """Best-effort conversion to int for dashboard payloads."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_dict(value: Any) -> dict[str, Any]:
    """Best-effort dictionary guard for nested dashboard fields."""
    return value if isinstance(value, dict) else {}


def _safe_read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object from disk and return an empty dict on failure."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_iso_datetime(value: Any) -> datetime | None:
    """Parse ISO datetime strings with optional Z suffix."""
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_iso_date(value: Any) -> date | None:
    """Parse YYYY-MM-DD dates."""
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _latest_file(directory: Path, pattern: str) -> Path | None:
    """Return the newest matching file in a directory."""
    if not directory.exists():
        return None
    files = [item for item in directory.glob(pattern) if item.is_file()]
    if not files:
        return None
    return max(files, key=lambda item: item.stat().st_mtime)


def _extract_date(value: str) -> str | None:
    """Extract the first YYYY-MM-DD token from a filename or free-form string."""
    match = DATE_PATTERN.search(value)
    return match.group(0) if match else None


def _mean_or_none(values: list[float]) -> float | None:
    """Return arithmetic mean when values are present."""
    return mean(values) if values else None


def _ordered_unique(values: list[str]) -> list[str]:
    """Return unique strings while preserving first-seen order."""
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _percentile(values: list[float], quantile: float) -> float | None:
    """Compute percentile via linear interpolation for a sorted sample."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    clamped = max(0.0, min(1.0, float(quantile)))
    position = clamped * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _iso_date(value: date | None) -> str | None:
    """Serialize a date value to YYYY-MM-DD when present."""
    return value.isoformat() if isinstance(value, date) else None


def _current_market_week_end(anchor: date) -> date:
    """Return the exchange-calendar weekly target for dashboard freshness checks."""
    context = market_week_context(anchor)
    parsed = _parse_iso_date(context.get("current_week_end_date"))
    return parsed or anchor


@dataclass
class DashboardDataStore:
    """Project-local data access for UI and API responses."""

    project_root: Path = field(
        default_factory=lambda: Path(
            os.getenv("TICKERS_DATA_ROOT", str(Path(__file__).resolve().parents[1]))
        ).expanduser()
    )
    cycle_cache_ttl_seconds: int = 120
    _status_cache: dict[str, Any] = field(default_factory=dict, init=False, repr=False)
    _cycle_history_cache: dict[str, Any] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self.project_root = _canonical(self.project_root)

    @property
    def active_cohort_only(self) -> bool:
        """Restrict staging surfaces to the promoted active cohort when requested."""
        raw = os.getenv("TICKERS_ACTIVE_COHORT_ONLY", "").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    @property
    def allowed_symbols(self) -> set[str]:
        """Return the active staging symbol scope when enabled."""
        if not self.active_cohort_only:
            return set()
        return {symbol.upper() for symbol in ACTIVE_PROMOTED_COHORT}

    def _filter_symbol_set(self, symbols: set[str]) -> set[str]:
        """Apply optional active-cohort scoping to a symbol set."""
        if not self.active_cohort_only:
            return symbols
        return {symbol for symbol in symbols if symbol.upper() in self.allowed_symbols}

    def _filter_symbol_map(self, mapping: dict[str, Any]) -> dict[str, Any]:
        """Apply optional active-cohort scoping to a symbol-keyed mapping."""
        if not self.active_cohort_only:
            return mapping
        return {
            symbol: value
            for symbol, value in mapping.items()
            if str(symbol).upper() in self.allowed_symbols
        }

    @property
    def config_path(self) -> Path:
        return _canonical(self.project_root / "configs" / "tickers.toml")

    @property
    def static_dir(self) -> Path:
        return _canonical(self.project_root / "app" / "static")

    @property
    def predictions_dir(self) -> Path:
        return _canonical(self.project_root / "predictions")

    @property
    def daily_reports_dir(self) -> Path:
        return _canonical(self.project_root / "reports" / "daily")

    @property
    def risk_package_dir(self) -> Path:
        return _canonical(self.project_root / "reports" / "risk_package")

    @property
    def automation_state_path(self) -> Path:
        return _canonical(self.risk_package_dir / "automation_state.json")

    @property
    def bundled_weekly_seed(self) -> Path:
        return _canonical(self.project_root / "app" / "seed" / "weekly_forecast_summary_simple_seed.json")

    @property
    def summary_history_cache_dir(self) -> Path:
        return _canonical(self.risk_package_dir / "_summary_history_cache")

    def configured_tickers(self) -> list[str]:
        """Load ticker symbols declared in configs/tickers.toml."""
        if not self.config_path.exists():
            return []
        try:
            with self.config_path.open("rb") as handle:
                payload = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError):
            return []
        tickers = payload.get("tickers", {})
        if not isinstance(tickers, dict):
            return []
        symbols = {str(symbol).upper() for symbol in tickers}
        return sorted(self._filter_symbol_set(symbols))

    def discovered_tickers(self) -> list[str]:
        """Discover ticker directories from predictions and evaluation outputs."""
        symbols: set[str] = set()
        for directory in (self.predictions_dir, self.daily_reports_dir):
            if not directory.exists():
                continue
            for child in directory.iterdir():
                if child.is_dir():
                    symbols.add(child.name.upper())
        if not symbols:
            symbols.update(self.configured_tickers())
        return sorted(self._filter_symbol_set(symbols))

    def weekly_status(self) -> tuple[dict[str, dict[str, Any]], str | None]:
        """Load the most recent local weekly status file if present."""
        source = self._latest_weekly_summary_source()
        if source is None:
            return {}, None
        payload = _safe_read_json(source)
        status_map = self._weekly_status_map_from_payload(payload)
        return status_map, str(_canonical(source))

    def _weekly_status_map_from_payload(self, payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Normalize ticker weekly status payload into dashboard shape."""
        ticker_payload = payload.get("tickers", {})
        if not isinstance(ticker_payload, dict):
            return {}
        status_map: dict[str, dict[str, Any]] = {}
        for symbol, info in ticker_payload.items():
            if not isinstance(info, dict):
                continue
            previous_week = _safe_dict(info.get("previous_week_comparison"))
            status_map[str(symbol).upper()] = {
                "status": info.get("status", "unknown"),
                "tone": info.get("tone", "Unknown"),
                "generated_at": payload.get("generated_at"),
                "note": info.get("note"),
                "expected_week_return_pct": _safe_float(info.get("expected_week_return_pct")),
                "expected_week_close": _safe_float(info.get("expected_week_close")),
                "target_week_end_date": info.get("target_week_end_date"),
                "final_forecast_date": info.get("final_forecast_date"),
                "projection_selection": info.get("projection_selection"),
                "target_matched": bool(info.get("target_matched")),
                "last_observation": info.get("last_observation"),
                "last_close": _safe_float(info.get("last_close")),
                "model_metrics": info.get("model_metrics", {}),
                "daily": info.get("daily", []),
                "forecast_risk": _safe_dict(info.get("forecast_risk")),
                "previous_week_comparison": previous_week,
            }
        return self._filter_symbol_map(status_map)

    def _weekly_summary_candidates(self) -> list[Path]:
        """List all local summary candidates using canonical absolute paths."""
        candidates = [
            _canonical(path)
            for path in self.risk_package_dir.glob("weekly_forecast_summary_simple_*.json")
            if path.is_file()
        ]
        if self.bundled_weekly_seed.exists():
            candidates.append(_canonical(self.bundled_weekly_seed))
        unique: dict[str, Path] = {}
        for candidate in candidates:
            unique[str(candidate)] = candidate
        return list(unique.values())

    def _weekly_summary_sort_key(self, source: Path) -> tuple[date, datetime, float]:
        """Prefer newest week-end and generated timestamp when picking local summary."""
        payload = _safe_read_json(source)
        week = _safe_dict(payload.get("week"))
        week_end = _parse_iso_date(week.get("end"))
        if week_end is None:
            extracted_dates = [_parse_iso_date(token) for token in DATE_PATTERN.findall(source.name)]
            valid_dates = [item for item in extracted_dates if item is not None]
            week_end = max(valid_dates) if valid_dates else date.min
        generated_at = _parse_iso_datetime(payload.get("generated_at"))
        if generated_at is None:
            generated_at = datetime.fromtimestamp(source.stat().st_mtime, tz=timezone.utc)
        return week_end, generated_at, source.stat().st_mtime

    def _latest_weekly_summary_source(self) -> Path | None:
        """Select canonical local weekly summary source with deterministic freshness ranking."""
        candidates = self._weekly_summary_candidates()
        if not candidates:
            return None
        return max(candidates, key=self._weekly_summary_sort_key)

    def _historical_weekly_summary_candidates(self) -> list[Path]:
        """Return all known local weekly summaries, including cached prior remote copies."""
        candidates = list(self._weekly_summary_candidates())
        if self.summary_history_cache_dir.exists():
            candidates.extend(
                _canonical(path)
                for path in self.summary_history_cache_dir.glob("summary_*.json")
                if path.is_file()
            )
        previous_remote = _canonical(self.risk_package_dir / "_previous_weekly_summary_remote.json")
        if previous_remote.exists():
            candidates.append(previous_remote)
        unique: dict[str, Path] = {}
        for candidate in candidates:
            unique[str(candidate)] = candidate
        return sorted(unique.values(), key=self._weekly_summary_sort_key)

    def automation_state(self) -> tuple[dict[str, dict[str, Any]], str | None]:
        """Load adaptive retry state from the local state file."""
        payload = _safe_read_json(self.automation_state_path)
        tickers = payload.get("tickers")
        if isinstance(tickers, dict):
            state_map = {}
            for symbol, item in tickers.items():
                if isinstance(item, dict):
                    state_map[str(symbol).upper()] = item
            return self._filter_symbol_map(state_map), str(self.automation_state_path)
        return {}, str(self.automation_state_path) if self.automation_state_path.exists() else None

    def _local_cycle_history(self) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
        """Load historical cycle snapshots from the local forecast-ledger directory when available."""
        root = _canonical(self.project_root / "reports" / "forecast_ledger" / "cycles")
        if not root.exists():
            return {}, {"source": None, "error": "Local forecast-ledger cycles are unavailable.", "row_count": 0}

        cycle_history: dict[str, list[dict[str, Any]]] = {}
        row_count = 0
        for source in root.glob("*/*.json"):
            payload = _safe_read_json(source)
            ticker = str(payload.get("ticker", "")).upper().strip()
            if not ticker:
                continue
            cycle_history.setdefault(ticker, []).append(payload)
            row_count += 1
        for ticker, cycles in cycle_history.items():
            cycle_history[ticker] = sorted(
                cycles,
                key=lambda item: (
                    str(item.get("target_week_end_date") or ""),
                    str(item.get("updated_at") or ""),
                ),
            )
        cycle_history = self._filter_symbol_map(cycle_history)
        return cycle_history, {"source": str(root), "error": None, "row_count": row_count}

    def latest_ledger_cycles(self) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Expose the latest local cycle summary for each ticker."""
        local_history, local_meta = self._local_cycle_history()
        if local_history:
            latest_rows = {
                ticker: cycles[-1]
                for ticker, cycles in local_history.items()
                if isinstance(cycles, list) and cycles
            }
            return latest_rows, local_meta
        cycle_history, cycle_history_meta = self.cycle_history_by_ticker()
        if cycle_history:
            latest_rows = {
                ticker: cycles[-1]
                for ticker, cycles in cycle_history.items()
                if isinstance(cycles, list) and cycles
            }
            return latest_rows, cycle_history_meta
        return {}, local_meta

    def _cycle_history_from_local_weekly_summaries(self) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
        """Build cycle history from local weekly-summary archives from local weekly summaries."""
        summaries: list[tuple[datetime, str, Path, dict[str, Any]]] = []
        for source in self._historical_weekly_summary_candidates():
            payload = _safe_read_json(source)
            generated_at = payload.get("generated_at")
            tickers = payload.get("tickers")
            if not isinstance(generated_at, str) or not isinstance(tickers, dict):
                continue
            parsed_generated_at = _parse_iso_datetime(generated_at)
            if parsed_generated_at is None:
                parsed_generated_at = datetime.fromtimestamp(source.stat().st_mtime, tz=timezone.utc)
            summaries.append((parsed_generated_at, generated_at, source, payload))
        summaries.sort(key=lambda item: (item[0], str(item[2])))

        cycle_snapshots: dict[tuple[str, str], dict[str, Any]] = {}
        for _, generated_at, source, payload in summaries:
            tickers = payload.get("tickers", {})
            if not isinstance(tickers, dict):
                continue
            run_date = generated_at[:10]
            for symbol, info in tickers.items():
                if not isinstance(info, dict):
                    continue
                symbol_upper = str(symbol).upper()
                target_week_end_date = info.get("target_week_end_date")
                if not isinstance(target_week_end_date, str) or not target_week_end_date:
                    continue
                cycle_key = (symbol_upper, target_week_end_date)
                origin = build_origin_record(
                    ticker=symbol_upper,
                    target_week_end_date=target_week_end_date,
                    last_observation_date=info.get("last_observation") if isinstance(info.get("last_observation"), str) else None,
                    issued_at=generated_at,
                    final_forecast_date=info.get("final_forecast_date") if isinstance(info.get("final_forecast_date"), str) else None,
                    projection_selection=str(info.get("projection_selection") or "none"),
                    week_start_close=_safe_float(info.get("last_close")),
                    predicted_target_close=_safe_float(info.get("expected_week_close")),
                    predicted_target_return_pct=_safe_float(info.get("expected_week_return_pct")),
                    model_run_dir=str(info.get("artifact_run_dir")) if info.get("artifact_run_dir") else None,
                    config_snapshot_path=str(self.config_path) if self.config_path.exists() else None,
                    forecast_rows=info.get("daily") if isinstance(info.get("daily"), list) else [],
                    run_date=run_date,
                    summary_source_file=str(_canonical(source)),
                    existing_cycle=cycle_snapshots.get(cycle_key),
                )
                cycle_snapshots[cycle_key] = merge_origin_into_cycle(cycle_snapshots.get(cycle_key), origin)

                previous_week = info.get("previous_week_comparison")
                if (
                    isinstance(previous_week, dict)
                    and previous_week.get("status") == "resolved"
                    and isinstance(previous_week.get("target_week_end_date"), str)
                    and isinstance(previous_week.get("actual_close"), (int, float))
                ):
                    previous_key = (symbol_upper, str(previous_week["target_week_end_date"]))
                    existing_cycle = cycle_snapshots.get(previous_key)
                    if existing_cycle is None:
                        continue
                    cycle_snapshots[previous_key] = resolve_cycle(
                        existing_cycle,
                        actual_target_close=float(previous_week["actual_close"]),
                        resolved_at=generated_at,
                        source_run_date=run_date,
                    )

        grouped: dict[str, list[dict[str, Any]]] = {}
        for cycle in cycle_snapshots.values():
            ticker = str(cycle.get("ticker", "")).upper()
            if not ticker:
                continue
            grouped.setdefault(ticker, []).append(cycle)
        filtered = self._filter_symbol_map(grouped)
        for ticker, rows in filtered.items():
            rows.sort(
                key=lambda item: (
                    str(item.get("target_week_end_date") or ""),
                    str(item.get("updated_at") or ""),
                )
            )
        row_count = sum(len(rows) for rows in filtered.values())
        return filtered, {"source": "local_weekly_summary_history", "error": None, "row_count": row_count}

    def _merge_cycle_history_maps(
        self,
        *mappings: dict[str, list[dict[str, Any]]],
    ) -> dict[str, list[dict[str, Any]]]:
        """Merge cycle-history maps, letting later sources override earlier rows by cycle id."""
        merged: dict[str, dict[str, dict[str, Any]]] = {}
        for mapping in mappings:
            if not isinstance(mapping, dict):
                continue
            for ticker, cycles in mapping.items():
                ticker_upper = str(ticker).upper()
                ticker_map = merged.setdefault(ticker_upper, {})
                if not isinstance(cycles, list):
                    continue
                for cycle in cycles:
                    if not isinstance(cycle, dict):
                        continue
                    cycle_id = cycle.get("forecast_cycle_id")
                    target_week_end_date = cycle.get("target_week_end_date")
                    if isinstance(cycle_id, str) and cycle_id:
                        key = cycle_id
                    elif isinstance(target_week_end_date, str) and target_week_end_date:
                        key = f"{ticker_upper}:{target_week_end_date}"
                    else:
                        continue
                    ticker_map[key] = cycle
        return {
            ticker: sorted(
                cycles.values(),
                key=lambda item: (
                    str(item.get("target_week_end_date") or ""),
                    str(item.get("updated_at") or ""),
                ),
            )
            for ticker, cycles in merged.items()
        }

    def cycle_history_by_ticker(self) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
        """Expose per-ticker cycle history from local files."""
        now = datetime.now(timezone.utc)
        fetched_at = self._cycle_history_cache.get("fetched_at")
        if isinstance(fetched_at, datetime):
            if (now - fetched_at).total_seconds() < self.cycle_cache_ttl_seconds:
                cached_rows = self._cycle_history_cache.get("rows")
                cached_meta = self._cycle_history_cache.get("meta")
                if isinstance(cached_rows, dict) and isinstance(cached_meta, dict):
                    return cached_rows, cached_meta

        local_rows, local_meta = self._local_cycle_history()
        local_summary_rows, local_summary_meta = self._cycle_history_from_local_weekly_summaries()
        rows = self._merge_cycle_history_maps(local_summary_rows, local_rows)
        meta = local_meta if local_rows else local_summary_meta
        self._cycle_history_cache = {"fetched_at": now, "rows": rows, "meta": meta}
        return rows, meta

    def _resolved_cycle_history_rows(self, cycles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Normalize resolved cycle history into week-by-week predicted-vs-actual rows."""
        rows: list[dict[str, Any]] = []
        for cycle in cycles:
            if not isinstance(cycle, dict):
                continue
            target_week_end_date = cycle.get("target_week_end_date")
            if not isinstance(target_week_end_date, str) or not target_week_end_date:
                continue
            resolved_actual = cycle.get("resolved_actual")
            if not isinstance(resolved_actual, dict):
                continue
            actual_close = _safe_float(resolved_actual.get("actual_target_close"))
            if actual_close is None:
                continue

            initial_forecast = cycle.get("initial_forecast") if isinstance(cycle.get("initial_forecast"), dict) else {}
            latest_forecast = cycle.get("latest_forecast") if isinstance(cycle.get("latest_forecast"), dict) else {}
            kpis = cycle.get("kpis") if isinstance(cycle.get("kpis"), dict) else {}
            first_call = (
                kpis.get("first_call_week_ahead") if isinstance(kpis.get("first_call_week_ahead"), dict) else {}
            )
            latest_call = (
                kpis.get("rolling_revision_accuracy") if isinstance(kpis.get("rolling_revision_accuracy"), dict) else {}
            )
            revisions = cycle.get("revisions") if isinstance(cycle.get("revisions"), list) else []

            initial_predicted_close = _safe_float(first_call.get("predicted_target_close"))
            if initial_predicted_close is None:
                initial_predicted_close = _safe_float(initial_forecast.get("predicted_target_close"))
            latest_predicted_close = _safe_float(latest_call.get("predicted_target_close"))
            if latest_predicted_close is None:
                latest_predicted_close = _safe_float(latest_forecast.get("predicted_target_close"))

            first_call_absolute_error = _safe_float(first_call.get("absolute_error"))
            if first_call_absolute_error is None and initial_predicted_close is not None:
                first_call_absolute_error = abs(initial_predicted_close - actual_close)
            latest_absolute_error = _safe_float(latest_call.get("absolute_error"))
            if latest_absolute_error is None and latest_predicted_close is not None:
                latest_absolute_error = abs(latest_predicted_close - actual_close)

            first_call_percent_error = None
            if initial_predicted_close is not None and actual_close != 0:
                first_call_percent_error = (initial_predicted_close - actual_close) / actual_close * 100.0
            latest_percent_error = None
            if latest_predicted_close is not None and actual_close != 0:
                latest_percent_error = (latest_predicted_close - actual_close) / actual_close * 100.0

            rows.append(
                {
                    "forecast_cycle_id": cycle.get("forecast_cycle_id"),
                    "target_week_end_date": target_week_end_date,
                    "cycle_status": cycle.get("cycle_status"),
                    "issued_at": initial_forecast.get("issued_at"),
                    "latest_issued_at": latest_forecast.get("issued_at"),
                    "initial_predicted_close": initial_predicted_close,
                    "latest_predicted_close": latest_predicted_close,
                    "actual_close": actual_close,
                    "first_call_absolute_error": first_call_absolute_error,
                    "latest_absolute_error": latest_absolute_error,
                    "first_call_error_pct": _safe_float(first_call.get("error_pct")),
                    "latest_error_pct": _safe_float(latest_call.get("error_pct")),
                    "first_call_percent_error": first_call_percent_error,
                    "latest_percent_error": latest_percent_error,
                    "first_call_direction_match": first_call.get("direction_match"),
                    "latest_direction_match": latest_call.get("direction_match"),
                    "revision_count": len([item for item in revisions if isinstance(item, dict)]),
                }
            )

        rows.sort(key=lambda item: str(item.get("target_week_end_date") or ""))
        return rows

    def _cycle_history_rollup(self, cycles: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Aggregate target-close accuracy across resolved weekly cycles."""
        history_rows = self._resolved_cycle_history_rows(cycles)
        if not history_rows:
            return {
                "sample_count": 0,
                "forecast_date_count": 0,
                "window_start": None,
                "window_end": None,
                "mae": None,
                "rmse": None,
                "mape": None,
                "bias": None,
                "percent_bias": None,
                "abs_error_p50": None,
                "abs_error_p90": None,
                "abs_error_max": None,
                "coverage_within_1pct": None,
                "coverage_within_2pct": None,
                "coverage_within_5pct": None,
                "percent_error_samples": 0,
                "source_file_count": 0,
                "source_files": [],
                "recent_samples": [],
                "source_kind": "forecast_cycle_history",
                "latest_mae": None,
                "latest_rmse": None,
                "latest_mape": None,
                "latest_bias": None,
                "latest_percent_bias": None,
                "latest_coverage_within_1pct": None,
                "latest_coverage_within_2pct": None,
                "latest_coverage_within_5pct": None,
                "direction_accuracy_pct": None,
                "latest_direction_accuracy_pct": None,
            }, history_rows

        first_abs_errors = [
            float(row["first_call_absolute_error"])
            for row in history_rows
            if isinstance(row.get("first_call_absolute_error"), (int, float))
        ]
        latest_abs_errors = [
            float(row["latest_absolute_error"])
            for row in history_rows
            if isinstance(row.get("latest_absolute_error"), (int, float))
        ]
        first_signed_errors = [
            float(row["initial_predicted_close"]) - float(row["actual_close"])
            for row in history_rows
            if isinstance(row.get("initial_predicted_close"), (int, float))
            and isinstance(row.get("actual_close"), (int, float))
        ]
        latest_signed_errors = [
            float(row["latest_predicted_close"]) - float(row["actual_close"])
            for row in history_rows
            if isinstance(row.get("latest_predicted_close"), (int, float))
            and isinstance(row.get("actual_close"), (int, float))
        ]
        first_percent_errors = [
            float(row["first_call_percent_error"])
            for row in history_rows
            if isinstance(row.get("first_call_percent_error"), (int, float))
        ]
        latest_percent_errors = [
            float(row["latest_percent_error"])
            for row in history_rows
            if isinstance(row.get("latest_percent_error"), (int, float))
        ]
        first_direction_matches = [
            bool(row["first_call_direction_match"])
            for row in history_rows
            if isinstance(row.get("first_call_direction_match"), bool)
        ]
        latest_direction_matches = [
            bool(row["latest_direction_match"])
            for row in history_rows
            if isinstance(row.get("latest_direction_match"), bool)
        ]

        def _rmse(values: list[float]) -> float | None:
            if not values:
                return None
            return math.sqrt(sum(value * value for value in values) / len(values))

        def _coverage(values: list[float], threshold: float) -> float | None:
            if not values:
                return None
            hits = sum(1 for value in values if abs(value) <= threshold)
            return hits / len(values) * 100.0

        recent_samples = [
            {
                "forecast_date": row.get("target_week_end_date"),
                "predicted_close": row.get("initial_predicted_close"),
                "latest_predicted_close": row.get("latest_predicted_close"),
                "actual_close": row.get("actual_close"),
                "error": (
                    float(row["initial_predicted_close"]) - float(row["actual_close"])
                    if isinstance(row.get("initial_predicted_close"), (int, float))
                    and isinstance(row.get("actual_close"), (int, float))
                    else None
                ),
                "absolute_error": row.get("first_call_absolute_error"),
                "percent_error": row.get("first_call_percent_error"),
                "latest_percent_error": row.get("latest_percent_error"),
                "source_file": row.get("forecast_cycle_id"),
            }
            for row in history_rows[-10:]
        ]

        return {
            "sample_count": len(history_rows),
            "forecast_date_count": len(history_rows),
            "window_start": history_rows[0].get("target_week_end_date"),
            "window_end": history_rows[-1].get("target_week_end_date"),
            "mae": _mean_or_none(first_abs_errors),
            "rmse": _rmse(first_abs_errors),
            "mape": _mean_or_none([abs(value) for value in first_percent_errors]),
            "bias": _mean_or_none(first_signed_errors),
            "percent_bias": _mean_or_none(first_percent_errors),
            "abs_error_p50": _percentile(first_abs_errors, 0.50),
            "abs_error_p90": _percentile(first_abs_errors, 0.90),
            "abs_error_max": max(first_abs_errors) if first_abs_errors else None,
            "coverage_within_1pct": _coverage(first_percent_errors, 1.0),
            "coverage_within_2pct": _coverage(first_percent_errors, 2.0),
            "coverage_within_5pct": _coverage(first_percent_errors, 5.0),
            "percent_error_samples": len(first_percent_errors),
            "source_file_count": len(history_rows),
            "source_files": [],
            "recent_samples": recent_samples,
            "source_kind": "forecast_cycle_history",
            "latest_mae": _mean_or_none(latest_abs_errors),
            "latest_rmse": _rmse(latest_abs_errors),
            "latest_mape": _mean_or_none([abs(value) for value in latest_percent_errors]),
            "latest_bias": _mean_or_none(latest_signed_errors),
            "latest_percent_bias": _mean_or_none(latest_percent_errors),
            "latest_coverage_within_1pct": _coverage(latest_percent_errors, 1.0),
            "latest_coverage_within_2pct": _coverage(latest_percent_errors, 2.0),
            "latest_coverage_within_5pct": _coverage(latest_percent_errors, 5.0),
            "direction_accuracy_pct": (
                sum(1 for value in first_direction_matches if value) / len(first_direction_matches) * 100.0
                if first_direction_matches
                else None
            ),
            "latest_direction_accuracy_pct": (
                sum(1 for value in latest_direction_matches if value) / len(latest_direction_matches) * 100.0
                if latest_direction_matches
                else None
            ),
        }, history_rows

    def _apply_target_close_history(
        self,
        symbol: str,
        row: dict[str, Any],
        cycle_history: list[dict[str, Any]] | None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Overlay target-close history metrics when cycle history is available."""
        history_metrics = self.historical_evaluation_rollup(symbol)
        history_rows: list[dict[str, Any]] = []
        if isinstance(cycle_history, list) and cycle_history:
            cycle_metrics, history_rows = self._cycle_history_rollup(cycle_history)
            if (_safe_int(cycle_metrics.get("sample_count")) or 0) > 0:
                history_metrics = cycle_metrics

        merged = dict(row)
        merged["history_metrics"] = history_metrics
        merged["history_sample_count"] = history_metrics.get("sample_count")
        merged["history_window_start"] = history_metrics.get("window_start")
        merged["history_window_end"] = history_metrics.get("window_end")
        merged["history_mae"] = history_metrics.get("mae")
        merged["history_rmse"] = history_metrics.get("rmse")
        merged["history_mape"] = history_metrics.get("mape")
        merged["history_bias"] = history_metrics.get("bias")
        merged["history_abs_error_p50"] = history_metrics.get("abs_error_p50")
        merged["history_abs_error_p90"] = history_metrics.get("abs_error_p90")
        merged["history_coverage_within_1pct"] = history_metrics.get("coverage_within_1pct")
        merged["history_coverage_within_2pct"] = history_metrics.get("coverage_within_2pct")
        merged["history_coverage_within_5pct"] = history_metrics.get("coverage_within_5pct")
        merged["history_source_kind"] = history_metrics.get("source_kind")
        return merged, history_rows

    def ledger_cycle_history(self) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
        """Expose historical local cycle summaries keyed by ticker."""
        now = datetime.now(timezone.utc)
        fetched_at = self._cycle_history_cache.get("fetched_at")
        if isinstance(fetched_at, datetime) and (now - fetched_at).total_seconds() < self.cycle_cache_ttl_seconds:
            cached_rows = self._cycle_history_cache.get("rows")
            cached_meta = self._cycle_history_cache.get("meta")
            if isinstance(cached_rows, dict) and isinstance(cached_meta, dict):
                return cached_rows, cached_meta
        rows, meta = self._local_cycle_history()
        self._cycle_history_cache = {"fetched_at": now, "rows": rows, "meta": meta}
        return rows, meta

    def _merge_row_with_ledger(self, row: dict[str, Any], ledger_cycle: dict[str, Any]) -> dict[str, Any]:
        """Overlay ledger cycle data on top of legacy weekly-summary rows."""
        merged = dict(row)
        latest_forecast = ledger_cycle.get("latest_forecast")
        if not isinstance(latest_forecast, dict):
            latest_forecast = {}
        revisions = ledger_cycle.get("revisions")
        if not isinstance(revisions, list):
            revisions = []
        latest_forecast_path = latest_forecast.get("forecast")
        forecast_points = []
        if isinstance(latest_forecast_path, list):
            for point in latest_forecast_path:
                if not isinstance(point, dict):
                    continue
                close = _safe_float(point.get("predicted_close"))
                if close is None:
                    continue
                display_close = _safe_float(point.get("display_close"))
                raw_predicted_close = _safe_float(point.get("raw_predicted_close"))
                forecast_points.append(
                    {
                        "date": point.get("date") or point.get("forecast_date"),
                        "predicted_close": close,
                        "display_close": display_close if display_close is not None else close,
                        "raw_predicted_close": raw_predicted_close if raw_predicted_close is not None else close,
                        "predicted_return": _safe_float(point.get("predicted_return")),
                        "horizon": _safe_int(point.get("horizon")),
                    }
                )
        if forecast_points:
            merged["forecast_points"] = forecast_points

        target_week_end_date = ledger_cycle.get("target_week_end_date")
        if isinstance(target_week_end_date, str):
            merged["target_week_end_date"] = target_week_end_date
        if isinstance(latest_forecast.get("final_forecast_date"), str):
            merged["final_forecast_date"] = latest_forecast.get("final_forecast_date")
        if isinstance(latest_forecast.get("last_observation_date"), str):
            merged["last_observation_date"] = latest_forecast.get("last_observation_date")
        predicted_target_close = _safe_float(latest_forecast.get("predicted_target_close"))
        if predicted_target_close is not None:
            merged["week_end_predicted_close"] = predicted_target_close
        predicted_target_return_pct = _safe_float(latest_forecast.get("predicted_target_return_pct"))
        if predicted_target_return_pct is not None:
            merged["expected_week_return_pct"] = predicted_target_return_pct
            merged["week_return_pct"] = predicted_target_return_pct

        merged["cycle_status"] = ledger_cycle.get("cycle_status")
        merged["initial_forecast"] = ledger_cycle.get("initial_forecast")
        merged["latest_forecast"] = latest_forecast
        merged["revisions"] = revisions
        merged["resolved_actual"] = ledger_cycle.get("resolved_actual")
        merged["kpis"] = ledger_cycle.get("kpis")
        return merged

    def _forecast_sources(self, row: dict[str, Any]) -> list[str]:
        """Return ordered forward-data source labels for one ticker row."""
        sources: list[str] = []
        latest_forecast = row.get("latest_forecast")
        if isinstance(latest_forecast, dict):
            if _safe_float(latest_forecast.get("predicted_target_close")) is not None or isinstance(
                latest_forecast.get("forecast"), list
            ):
                sources.append("Ledger")
        if isinstance(row.get("latest_forecast_file"), str) and row["latest_forecast_file"]:
            sources.append("Forecast File")
        if isinstance(row.get("forecast_points"), list) and row["forecast_points"]:
            if "Ledger" not in sources and "Forecast File" not in sources:
                sources.append("Weekly Summary")
        elif isinstance(row.get("week_end_predicted_close"), (int, float)) or isinstance(
            row.get("week_return_pct"), (int, float)
        ):
            sources.append("Weekly Summary")
        return _ordered_unique(sources)

    def _evaluation_sources(self, row: dict[str, Any]) -> list[str]:
        """Return ordered backward/evaluation source labels for one ticker row."""
        sources: list[str] = []
        if isinstance(row.get("latest_evaluation_file"), str) and row["latest_evaluation_file"]:
            sources.append("Evaluation File")
        history_sample_count = _safe_int(row.get("history_sample_count")) or 0
        if history_sample_count > 0:
            if row.get("history_source_kind") == "forecast_cycle_history":
                sources.append("Forecast Cycle History")
            else:
                sources.append("Historical Rollup")
        if row.get("previous_week_status") == "resolved" or isinstance(row.get("previous_week_actual_close"), (int, float)):
            sources.append("Prior Week Resolution")
        return _ordered_unique(sources)

    def _reference_target_week_end(
        self,
        *,
        rows: list[dict[str, Any]] | None = None,
        status_map: dict[str, dict[str, Any]] | None = None,
        ledger_cycles: dict[str, dict[str, Any]] | None = None,
        market_context: dict[str, Any] | None = None,
    ) -> date:
        """Return the current weekly target date the dashboard should consider 'fresh'."""
        reference = _parse_iso_date(_safe_dict(market_context).get("current_week_end_date"))
        candidates = [reference or _current_market_week_end(datetime.now(timezone.utc).date())]

        for row in rows or []:
            parsed = _parse_iso_date(row.get("target_week_end_date"))
            if parsed is not None:
                candidates.append(parsed)

        for mapping in (status_map or {}).values():
            if not isinstance(mapping, dict):
                continue
            parsed = _parse_iso_date(mapping.get("target_week_end_date"))
            if parsed is not None:
                candidates.append(parsed)

        for cycle in (ledger_cycles or {}).values():
            if not isinstance(cycle, dict):
                continue
            parsed = _parse_iso_date(cycle.get("target_week_end_date"))
            if parsed is not None:
                candidates.append(parsed)

        return max(candidates)

    def market_context(self, now: date | datetime | None = None) -> dict[str, Any]:
        """Return live exchange-calendar context for API payloads."""
        return market_week_context(now)

    def _business_health(self, row: dict[str, Any], reference_target_week_end: date) -> dict[str, Any]:
        """Translate model freshness and resolved accuracy into business-facing health guidance."""
        history = _safe_dict(row.get("history_metrics"))
        previous_week = _safe_dict(row.get("previous_week_comparison"))
        forecast_risk = _safe_dict(row.get("forecast_risk"))
        target_week_end = _parse_iso_date(row.get("target_week_end_date"))
        forecast_sources = self._forecast_sources(row)
        evaluation_sources = self._evaluation_sources(row)

        typical_gap_pct = _safe_float(history.get("mape"))
        latest_gap_pct = None
        if str(previous_week.get("status", "")).lower() == "resolved":
            previous_error_pct = _safe_float(previous_week.get("error_pct"))
            if previous_error_pct is not None:
                latest_gap_pct = abs(previous_error_pct)
        if latest_gap_pct is None:
            latest_gap_pct = _safe_float(history.get("latest_mape"))

        direction_hit_rate = _safe_float(history.get("direction_accuracy_pct"))
        history_samples = _safe_int(history.get("sample_count")) or 0
        effective_history_samples = history_samples
        if effective_history_samples <= 0 and str(previous_week.get("status", "")).lower() == "resolved":
            effective_history_samples = 1

        forecast_risk_state = str(forecast_risk.get("state", "normal")).lower()
        forecast_risk_label = str(forecast_risk.get("label", "")).strip()
        forecast_risk_message = str(forecast_risk.get("message", "")).strip()
        abs_expected_return_pct = _safe_float(forecast_risk.get("abs_expected_week_return_pct"))
        if abs_expected_return_pct is None:
            expected_move = _safe_float(row.get("expected_week_return_pct"))
            if expected_move is not None:
                abs_expected_return_pct = abs(expected_move)

        risk_flags: list[dict[str, Any]] = []
        if forecast_risk_state in {"elevated_move", "extreme_move"}:
            risk_flags.append(
                {
                    "key": forecast_risk_state,
                    "severity": forecast_risk.get("severity") or ("warning" if forecast_risk_state == "extreme_move" else "info"),
                    "label": forecast_risk_label or ("Extreme move" if forecast_risk_state == "extreme_move" else "Elevated move"),
                    "message": forecast_risk_message
                    or (
                        f"Projected move of {abs_expected_return_pct:.2f}% is outside the normal weekly band."
                        if abs_expected_return_pct is not None
                        else "Projected move is outside the normal weekly band."
                    ),
                }
            )
        if 0 < effective_history_samples < MIN_CONFIDENCE_HISTORY_SAMPLES:
            risk_flags.append(
                {
                    "key": "limited_history",
                    "severity": "info",
                    "label": "Limited history",
                    "message": (
                        f"Only {effective_history_samples} resolved week"
                        f"{'' if effective_history_samples == 1 else 's'} are available, so confidence is still limited."
                    ),
                }
            )

        forecast_freshness = "missing"
        stale_since = None
        weeks_behind = 0
        if target_week_end is not None:
            if target_week_end < reference_target_week_end:
                forecast_freshness = "stale"
                stale_since = target_week_end.isoformat()
                weeks_behind = max(1, (reference_target_week_end - target_week_end).days // 7)
            else:
                forecast_freshness = "current"

        status = str(row.get("status", "unknown")).lower()
        state = "on_track"
        severity = "good"
        label = "On track"
        message = "Current weekly forecast is live and there is no active quality warning."

        if forecast_freshness == "stale":
            state = "stale"
            severity = "critical"
            label = "Stale forecast"
            message = (
                f"This ticker is behind the current weekly cycle. The dashboard is targeting "
                f"{reference_target_week_end.isoformat()}, but this row is still on {stale_since or 'an older cycle'}."
            )
        elif not forecast_sources:
            state = "missing_forecast"
            severity = "warning"
            label = "Forecast missing"
            message = "No live week-ahead forecast is currently available for this ticker."
        elif effective_history_samples <= 0 and not evaluation_sources:
            state = "awaiting_score"
            severity = "info"
            label = "Awaiting score"
            message = "Forecast is live, but predicted-vs-actual scoring starts after the first resolved week closes."
        else:
            gap_parts: list[str] = []
            if typical_gap_pct is not None:
                gap_parts.append(f"typical miss +/- {typical_gap_pct:.2f}%")
            if latest_gap_pct is not None:
                gap_parts.append(f"last resolved miss {latest_gap_pct:.2f}%")
            if direction_hit_rate is not None:
                gap_parts.append(f"direction hit {direction_hit_rate:.0f}%")
            metrics_clause = ", ".join(gap_parts) if gap_parts else "resolved accuracy is still being established"
            risk_messages = [str(flag.get("message", "")).strip() for flag in risk_flags if str(flag.get("message", "")).strip()]

            low_accuracy = (
                status == "under_review"
                or (typical_gap_pct is not None and typical_gap_pct >= 8.0)
                or (latest_gap_pct is not None and latest_gap_pct >= 10.0)
                or (direction_hit_rate is not None and direction_hit_rate < 45.0)
            )
            watch_accuracy = (
                (typical_gap_pct is not None and typical_gap_pct >= 4.0)
                or (latest_gap_pct is not None and latest_gap_pct >= 5.0)
                or (direction_hit_rate is not None and direction_hit_rate < 60.0)
            )
            limited_history = any(flag.get("key") == "limited_history" for flag in risk_flags)
            extreme_move = any(flag.get("key") == "extreme_move" for flag in risk_flags)

            if low_accuracy:
                state = "low_accuracy"
                severity = "warning"
                label = "Low accuracy"
                message = f"Recent model accuracy is weak: {metrics_clause}."
                if risk_messages:
                    message = f"{message} {' '.join(risk_messages)}"
            elif limited_history:
                state = "watch_accuracy"
                severity = "warning" if extreme_move else "info"
                label = "Limited history"
                message = (
                    f"Forecast is live and early resolved accuracy looks promising, but only {effective_history_samples} resolved week"
                    f"{'' if effective_history_samples == 1 else 's'} are available so confidence is still limited."
                )
                supplemental_messages = [msg for msg in risk_messages if "resolved week" not in msg]
                if supplemental_messages:
                    message = f"{message} {' '.join(supplemental_messages)}"
            elif extreme_move:
                state = "watch_accuracy"
                severity = "warning"
                label = forecast_risk_label or "Extreme move"
                message = (
                    forecast_risk_message
                    or (
                        f"Projected move of {abs_expected_return_pct:.2f}% is unusually large for one week."
                        if abs_expected_return_pct is not None
                        else "Projected move is unusually large for one week."
                    )
                )
            elif watch_accuracy:
                state = "watch_accuracy"
                severity = "info"
                label = "Watch accuracy"
                message = f"Recent model accuracy is mixed: {metrics_clause}."
                if risk_messages:
                    message = f"{message} {' '.join(risk_messages)}"
            else:
                message = f"Resolved accuracy is within the current watch band: {metrics_clause}."
                if risk_messages:
                    message = f"{message} {' '.join(risk_messages)}"

        return {
            "state": state,
            "severity": severity,
            "label": label,
            "message": message,
            "forecast_freshness": forecast_freshness,
            "reference_target_week_end_date": reference_target_week_end.isoformat(),
            "ticker_target_week_end_date": _iso_date(target_week_end),
            "stale_since": stale_since,
            "weeks_behind": weeks_behind,
            "typical_gap_pct": typical_gap_pct,
            "latest_gap_pct": latest_gap_pct,
            "direction_hit_rate": direction_hit_rate,
            "history_sample_count": effective_history_samples,
            "minimum_history_samples": MIN_CONFIDENCE_HISTORY_SAMPLES,
            "forecast_risk_state": forecast_risk_state,
            "forecast_risk_label": forecast_risk_label or None,
            "forecast_risk_message": forecast_risk_message or None,
            "abs_expected_return_pct": abs_expected_return_pct,
            "risk_flags": risk_flags,
        }

    def _display_group_key(self, row: dict[str, Any], business_health: dict[str, Any]) -> str:
        """Classify a ticker row into live, review, or stale dashboard groups."""
        if business_health.get("forecast_freshness") == "stale":
            return "stale"
        if str(row.get("status", "unknown")).lower() == "under_review":
            return "under_review"
        if business_health.get("state") == "low_accuracy":
            return "under_review"
        return "active"

    def _display_group_meta(self, group_key: str) -> tuple[str, str, int]:
        """Return label, description, and sort order for a display group."""
        for order, (key, label, description) in enumerate(DISPLAY_GROUPS):
            if key == group_key:
                return label, description, order
        return "Other", "Rows outside the primary staged grouping.", len(DISPLAY_GROUPS)

    def _decorate_row(self, row: dict[str, Any], reference_target_week_end: date) -> dict[str, Any]:
        """Attach UI/display metadata after weekly and ledger data are merged."""
        decorated = dict(row)
        group_health = self._business_health(decorated, reference_target_week_end)
        group_key = self._display_group_key(decorated, group_health)
        group_label, group_description, group_order = self._display_group_meta(group_key)
        forecast_sources = self._forecast_sources(decorated)
        evaluation_sources = self._evaluation_sources(decorated)
        freshness = str(group_health.get("forecast_freshness") or "missing")
        if freshness == "stale":
            coverage_key = "stale_history"
            coverage_label = "Stale history"
        elif group_health.get("state") == "awaiting_score":
            coverage_key = "live_score_pending"
            coverage_label = "Live, score pending"
        elif group_health.get("state") == "missing_forecast":
            coverage_key = "forecast_missing"
            coverage_label = "Forecast missing"
        else:
            coverage_key = "live_automation"
            coverage_label = "Live automation"
        decorated["cohort_key"] = coverage_key
        decorated["cohort_label"] = coverage_label
        decorated["display_group"] = group_key
        decorated["display_group_label"] = group_label
        decorated["display_group_description"] = group_description
        decorated["display_group_order"] = group_order
        decorated["forecast_sources"] = forecast_sources
        decorated["evaluation_sources"] = evaluation_sources
        decorated["has_forecast_feed"] = bool(forecast_sources)
        decorated["has_evaluation_feed"] = bool(evaluation_sources)
        decorated["primary_forecast_source"] = forecast_sources[0] if forecast_sources else "No forecast feed"
        decorated["primary_evaluation_source"] = evaluation_sources[0] if evaluation_sources else "No evaluation feed"
        decorated["business_health"] = group_health
        decorated["has_business_warning"] = group_health.get("state") not in {"on_track"}
        decorated["business_warning_label"] = group_health.get("label")
        decorated["business_warning_message"] = group_health.get("message")
        decorated["history_sample_count"] = group_health.get("history_sample_count")
        decorated["risk_flags"] = group_health.get("risk_flags", [])
        decorated["forecast_risk_state"] = group_health.get("forecast_risk_state")
        decorated["forecast_risk_label"] = group_health.get("forecast_risk_label")
        decorated["forecast_risk_message"] = group_health.get("forecast_risk_message")
        decorated["abs_expected_return_pct"] = group_health.get("abs_expected_return_pct")
        decorated["typical_gap_pct"] = group_health.get("typical_gap_pct")
        decorated["latest_gap_pct"] = group_health.get("latest_gap_pct")
        decorated["direction_hit_rate"] = group_health.get("direction_hit_rate")
        history_metrics = _safe_dict(decorated.get("history_metrics"))
        if history_metrics and (group_health.get("history_sample_count") or 0) > (_safe_int(history_metrics.get("sample_count")) or 0):
            patched_history_metrics = dict(history_metrics)
            patched_history_metrics["sample_count"] = group_health.get("history_sample_count")
            decorated["history_metrics"] = patched_history_metrics
        return decorated

    def _cycle_matches_row(self, row: dict[str, Any], ledger_cycle: dict[str, Any]) -> bool:
        """Reject stale ledger merges when the weekly summary has moved to a new cycle."""
        row_target = row.get("target_week_end_date")
        cycle_target = ledger_cycle.get("target_week_end_date")
        if isinstance(row_target, str) and row_target and isinstance(cycle_target, str) and cycle_target:
            return row_target == cycle_target
        return True

    def _alert_severity_name(self, score: int) -> str:
        if score >= 3:
            return "critical"
        if score == 2:
            return "warning"
        return "info"

    def build_failed_ticker_alerts(
        self,
        rows: list[dict[str, Any]],
        symbols: list[str] | None = None,
    ) -> dict[str, Any]:
        """Build failed-ticker alerts from the local automation file and weekly status."""
        automation_map, automation_source = self.automation_state()
        weekly_map, weekly_source = self.weekly_status()
        row_map = {
            str(row.get("symbol", "")).upper(): row
            for row in rows
            if isinstance(row, dict) and isinstance(row.get("symbol"), str)
        }
        universe = sorted(set(row_map) | set(automation_map) | set(weekly_map))
        if symbols:
            requested = {symbol.upper() for symbol in symbols}
            universe = [symbol for symbol in universe if symbol in requested]
        items: list[dict[str, Any]] = []
        for symbol in universe:
            automation = _safe_dict(automation_map.get(symbol))
            weekly_row = _safe_dict(weekly_map.get(symbol))
            dashboard_row = _safe_dict(row_map.get(symbol))
            messages: list[str] = []
            severity_score = 0
            automation_status = str(automation.get("last_status", "")).lower()
            if automation_status == "failure":
                last_error = str(automation.get("last_error", "")).strip()
                messages.append(
                    f"Automation retry state is failure{': ' + last_error if last_error else ''}."
                )
                severity_score = max(severity_score, 3)
            weekly_status_name = str(weekly_row.get("status", "")).lower()
            if weekly_status_name == "under_review":
                messages.append("Latest local weekly status is under_review.")
                severity_score = max(severity_score, 2)
            dashboard_status = str(dashboard_row.get("status", "")).lower()
            if not messages and dashboard_status == "under_review":
                messages.append("Dashboard weekly status is under_review.")
                severity_score = max(severity_score, 1)
            if not messages:
                continue
            severity = self._alert_severity_name(severity_score)
            items.append(
                {
                    "symbol": symbol,
                    "severity": severity,
                    "messages": messages,
                    "dashboard_status": dashboard_row.get("status"),
                    "automation": {"last_status": automation.get("last_status")},
                    "weekly": {"status": weekly_row.get("status")},
                }
            )
        severity_rank = {"critical": 3, "warning": 2, "info": 1}
        items.sort(key=lambda item: (-severity_rank.get(str(item.get("severity")), 0), str(item.get("symbol"))))
        return {
            "open_count": len(items),
            "critical_count": sum(1 for item in items if item.get("severity") == "critical"),
            "warning_count": sum(1 for item in items if item.get("severity") == "warning"),
            "info_count": sum(1 for item in items if item.get("severity") == "info"),
            "items": items,
            "by_symbol": {str(item.get("symbol")): item for item in items},
            "sources": {"automation_state": automation_source, "weekly": weekly_source},
        }

    def latest_prediction(self, symbol: str) -> dict[str, Any]:
        """Load the newest forecast payload for a ticker."""
        folder = self.predictions_dir / symbol
        source = _latest_file(folder, "*.json")
        if source is None:
            return {
                "path": None,
                "payload": {},
                "forecast_points": [],
                "predicted_move_pct": None,
                "next_forecast_date": None,
                "final_forecast_date": None,
                "last_close": None,
                "context": {},
            }

        payload = _safe_read_json(source)
        raw_points = payload.get("forecast", [])
        forecast_points = []
        if isinstance(raw_points, list):
            for row in raw_points:
                if not isinstance(row, dict):
                    continue
                close = _safe_float(row.get("predicted_close"))
                if close is None:
                    continue
                display_close = _safe_float(row.get("display_close"))
                raw_predicted_close = _safe_float(row.get("raw_predicted_close"))
                forecast_points.append(
                    {
                        "date": row.get("forecast_date"),
                        "predicted_close": close,
                        "display_close": display_close if display_close is not None else close,
                        "raw_predicted_close": raw_predicted_close if raw_predicted_close is not None else close,
                        "predicted_return": _safe_float(row.get("predicted_return")),
                        "horizon": row.get("horizon"),
                    }
                )

        first_close = forecast_points[0]["predicted_close"] if forecast_points else None
        final_close = forecast_points[-1]["predicted_close"] if forecast_points else None
        predicted_move_pct = None
        if first_close not in (None, 0.0) and final_close is not None:
            predicted_move_pct = (final_close - first_close) / first_close * 100.0

        context = payload.get("context", {})
        if not isinstance(context, dict):
            context = {}
        window_close = context.get("window_close")
        if isinstance(window_close, list):
            context = dict(context)
            context["window_close"] = window_close[-30:]

        return {
            "path": str(_canonical(source)),
            "payload": payload,
            "forecast_points": forecast_points,
            "predicted_move_pct": predicted_move_pct,
            "next_forecast_date": forecast_points[0]["date"] if forecast_points else None,
            "final_forecast_date": forecast_points[-1]["date"] if forecast_points else None,
            "last_close": _safe_float(context.get("last_close")),
            "context": context,
        }

    def latest_evaluation(self, symbol: str) -> dict[str, Any]:
        """Load the newest evaluation payload for a ticker."""
        folder = self.daily_reports_dir / symbol
        source = _latest_file(folder, "*_evaluation.json") or _latest_file(folder, "*.json")
        if source is None:
            return {
                "path": None,
                "payload": {},
                "mae": None,
                "rmse": None,
                "mape": None,
                "count": None,
                "per_date": [],
            }

        payload = _safe_read_json(source)
        metrics = payload.get("metrics", {})
        if not isinstance(metrics, dict):
            metrics = {}
        per_date = payload.get("per_date", [])
        per_date_rows = per_date if isinstance(per_date, list) else []

        return {
            "path": str(_canonical(source)),
            "payload": payload,
            "mae": _safe_float(metrics.get("mae")),
            "rmse": _safe_float(metrics.get("rmse")),
            "mape": _safe_float(metrics.get("mape")),
            "count": metrics.get("count"),
            "per_date": per_date_rows,
        }

    def historical_evaluation_rollup(self, symbol: str) -> dict[str, Any]:
        """Aggregate predicted-vs-actual history from all evaluation files for a ticker."""
        folder = self.daily_reports_dir / symbol
        if not folder.exists():
            return {
                "sample_count": 0,
                "forecast_date_count": 0,
                "window_start": None,
                "window_end": None,
                "mae": None,
                "rmse": None,
                "mape": None,
                "bias": None,
                "percent_bias": None,
                "abs_error_p50": None,
                "abs_error_p90": None,
                "abs_error_max": None,
                "coverage_within_1pct": None,
                "coverage_within_2pct": None,
                "coverage_within_5pct": None,
                "percent_error_samples": 0,
                "source_file_count": 0,
                "source_files": [],
                "recent_samples": [],
            }

        source_files: list[str] = []
        entries: list[dict[str, Any]] = []
        sources = sorted((item for item in folder.glob("*.json") if item.is_file()), key=lambda item: item.stat().st_mtime)
        for source in sources:
            payload = _safe_read_json(source)
            per_date = payload.get("per_date")
            if not isinstance(per_date, list):
                continue
            canonical_source = str(_canonical(source))
            parsed_rows = 0
            for row in per_date:
                if not isinstance(row, dict):
                    continue
                predicted_close = _safe_float(row.get("predicted_close"))
                actual_close = _safe_float(row.get("actual_close"))
                if predicted_close is None or actual_close is None:
                    continue
                error = _safe_float(row.get("error"))
                if error is None:
                    error = predicted_close - actual_close
                absolute_error = _safe_float(row.get("absolute_error"))
                if absolute_error is None:
                    absolute_error = abs(error)
                percent_error = _safe_float(row.get("percent_error"))
                if percent_error is None and actual_close != 0:
                    percent_error = (error / actual_close) * 100.0

                entries.append(
                    {
                        "forecast_date": row.get("forecast_date"),
                        "predicted_close": predicted_close,
                        "actual_close": actual_close,
                        "error": error,
                        "absolute_error": absolute_error,
                        "percent_error": percent_error,
                        "source_file": canonical_source,
                    }
                )
                parsed_rows += 1
            if parsed_rows:
                source_files.append(canonical_source)

        if not entries:
            return {
                "sample_count": 0,
                "forecast_date_count": 0,
                "window_start": None,
                "window_end": None,
                "mae": None,
                "rmse": None,
                "mape": None,
                "bias": None,
                "percent_bias": None,
                "abs_error_p50": None,
                "abs_error_p90": None,
                "abs_error_max": None,
                "coverage_within_1pct": None,
                "coverage_within_2pct": None,
                "coverage_within_5pct": None,
                "percent_error_samples": 0,
                "source_file_count": 0,
                "source_files": [],
                "recent_samples": [],
            }

        entries.sort(key=lambda row: (str(row.get("forecast_date") or ""), str(row.get("source_file") or "")))
        errors = [float(row["error"]) for row in entries if isinstance(row.get("error"), (int, float))]
        abs_errors = [float(row["absolute_error"]) for row in entries if isinstance(row.get("absolute_error"), (int, float))]
        percent_errors = [float(row["percent_error"]) for row in entries if isinstance(row.get("percent_error"), (int, float))]
        abs_percent_errors = [abs(value) for value in percent_errors]

        forecast_dates = sorted(
            {
                str(row["forecast_date"])
                for row in entries
                if isinstance(row.get("forecast_date"), str) and row["forecast_date"]
            }
        )

        sample_count = len(abs_errors)
        rmse = None
        if errors:
            rmse = math.sqrt(sum(value * value for value in errors) / len(errors))

        coverage_1pct = None
        coverage_2pct = None
        coverage_5pct = None
        if abs_percent_errors:
            total_pct = len(abs_percent_errors)
            coverage_1pct = sum(1 for value in abs_percent_errors if value <= 1.0) / total_pct * 100.0
            coverage_2pct = sum(1 for value in abs_percent_errors if value <= 2.0) / total_pct * 100.0
            coverage_5pct = sum(1 for value in abs_percent_errors if value <= 5.0) / total_pct * 100.0

        recent_samples = entries[-10:]
        return {
            "sample_count": sample_count,
            "forecast_date_count": len(forecast_dates),
            "window_start": forecast_dates[0] if forecast_dates else None,
            "window_end": forecast_dates[-1] if forecast_dates else None,
            "mae": _mean_or_none(abs_errors),
            "rmse": rmse,
            "mape": _mean_or_none(abs_percent_errors),
            "bias": _mean_or_none(errors),
            "percent_bias": _mean_or_none(percent_errors),
            "abs_error_p50": _percentile(abs_errors, 0.50),
            "abs_error_p90": _percentile(abs_errors, 0.90),
            "abs_error_max": max(abs_errors) if abs_errors else None,
            "coverage_within_1pct": coverage_1pct,
            "coverage_within_2pct": coverage_2pct,
            "coverage_within_5pct": coverage_5pct,
            "percent_error_samples": len(percent_errors),
            "source_file_count": len(source_files),
            "source_files": source_files[-8:],
            "recent_samples": recent_samples,
        }

    def portfolio_history_rollup(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        """Build portfolio-level historical error metrics across all tickers."""
        total_tickers = len(rows)
        with_history = 0
        sample_count = 0
        percent_error_samples = 0
        mae_weighted_sum = 0.0
        rmse_weighted_sum = 0.0
        mape_weighted_sum = 0.0
        bias_weighted_sum = 0.0
        coverage1_hits = 0.0
        coverage2_hits = 0.0
        coverage5_hits = 0.0
        window_start: str | None = None
        window_end: str | None = None

        for row in rows:
            history = row.get("history_metrics")
            if not isinstance(history, dict):
                continue
            ticker_samples = _safe_int(history.get("sample_count")) or 0
            ticker_percent_samples = _safe_int(history.get("percent_error_samples")) or 0
            if ticker_samples <= 0:
                continue
            with_history += 1
            sample_count += ticker_samples
            percent_error_samples += ticker_percent_samples

            mae_value = _safe_float(history.get("mae"))
            if mae_value is not None:
                mae_weighted_sum += mae_value * ticker_samples
            rmse_value = _safe_float(history.get("rmse"))
            if rmse_value is not None:
                rmse_weighted_sum += rmse_value * ticker_samples
            mape_value = _safe_float(history.get("mape"))
            if mape_value is not None and ticker_percent_samples > 0:
                mape_weighted_sum += mape_value * ticker_percent_samples
            bias_value = _safe_float(history.get("bias"))
            if bias_value is not None:
                bias_weighted_sum += bias_value * ticker_samples

            coverage1 = _safe_float(history.get("coverage_within_1pct"))
            coverage2 = _safe_float(history.get("coverage_within_2pct"))
            coverage5 = _safe_float(history.get("coverage_within_5pct"))
            if coverage1 is not None and ticker_percent_samples > 0:
                coverage1_hits += (coverage1 / 100.0) * ticker_percent_samples
            if coverage2 is not None and ticker_percent_samples > 0:
                coverage2_hits += (coverage2 / 100.0) * ticker_percent_samples
            if coverage5 is not None and ticker_percent_samples > 0:
                coverage5_hits += (coverage5 / 100.0) * ticker_percent_samples

            ticker_start = history.get("window_start")
            ticker_end = history.get("window_end")
            if isinstance(ticker_start, str) and ticker_start:
                if window_start is None or ticker_start < window_start:
                    window_start = ticker_start
            if isinstance(ticker_end, str) and ticker_end:
                if window_end is None or ticker_end > window_end:
                    window_end = ticker_end

        average_mae = (mae_weighted_sum / sample_count) if sample_count > 0 else None
        average_rmse = (rmse_weighted_sum / sample_count) if sample_count > 0 else None
        average_bias = (bias_weighted_sum / sample_count) if sample_count > 0 else None
        average_mape = (mape_weighted_sum / percent_error_samples) if percent_error_samples > 0 else None
        coverage1 = (coverage1_hits / percent_error_samples * 100.0) if percent_error_samples > 0 else None
        coverage2 = (coverage2_hits / percent_error_samples * 100.0) if percent_error_samples > 0 else None
        coverage5 = (coverage5_hits / percent_error_samples * 100.0) if percent_error_samples > 0 else None

        return {
            "ticker_count": total_tickers,
            "tickers_with_history": with_history,
            "sample_count": sample_count,
            "percent_error_samples": percent_error_samples,
            "window_start": window_start,
            "window_end": window_end,
            "average_mae": average_mae,
            "average_rmse": average_rmse,
            "average_mape": average_mape,
            "average_bias": average_bias,
            "coverage_within_1pct": coverage1,
            "coverage_within_2pct": coverage2,
            "coverage_within_5pct": coverage5,
        }

    def prior_week_rollup(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        """Aggregate prior-week resolved outcomes across ticker rows."""
        total_tickers = len(rows)
        status_counts: dict[str, int] = {}
        absolute_errors: list[float] = []
        absolute_percent_errors: list[float] = []
        direction_matches: list[bool] = []

        for row in rows:
            comparison = row.get("previous_week_comparison")
            if not isinstance(comparison, dict):
                continue
            status = str(comparison.get("status") or "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1

            predicted_close = _safe_float(comparison.get("predicted_close"))
            actual_close = _safe_float(comparison.get("actual_close"))
            if predicted_close is None or actual_close is None:
                continue

            absolute_error = _safe_float(comparison.get("absolute_error"))
            if absolute_error is None:
                absolute_error = abs(predicted_close - actual_close)
            absolute_errors.append(absolute_error)

            error_pct = _safe_float(comparison.get("error_pct"))
            if error_pct is None and actual_close != 0:
                error_pct = (predicted_close - actual_close) / actual_close * 100.0
            if error_pct is not None:
                absolute_percent_errors.append(abs(error_pct))

            direction_match = comparison.get("direction_match")
            if isinstance(direction_match, bool):
                direction_matches.append(direction_match)

        resolved_count = len(absolute_errors)
        pending_count = total_tickers - resolved_count
        direction_accuracy_pct = None
        if direction_matches:
            direction_accuracy_pct = sum(1 for matched in direction_matches if matched) / len(direction_matches) * 100.0

        return {
            "ticker_count": total_tickers,
            "resolved_count": resolved_count,
            "pending_count": pending_count,
            "mae": _mean_or_none(absolute_errors),
            "mape": _mean_or_none(absolute_percent_errors),
            "direction_accuracy_pct": direction_accuracy_pct,
            "status_counts": status_counts,
        }

    def ticker_row(
        self,
        symbol: str,
        configured: set[str],
        status_map: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """Build one ticker row for the overview page."""
        prediction = self.latest_prediction(symbol)
        evaluation = self.latest_evaluation(symbol)
        weekly = status_map.get(symbol, {})
        forecast_points = prediction["forecast_points"]
        if not forecast_points and isinstance(weekly.get("daily"), list):
            weekly_daily = []
            for idx, row in enumerate(weekly["daily"]):
                if not isinstance(row, dict):
                    continue
                close = _safe_float(row.get("predicted_close"))
                if close is None:
                    continue
                display_close = _safe_float(row.get("display_close"))
                raw_predicted_close = _safe_float(row.get("raw_predicted_close"))
                weekly_daily.append(
                    {
                        "date": row.get("date"),
                        "predicted_close": close,
                        "display_close": display_close if display_close is not None else close,
                        "raw_predicted_close": raw_predicted_close if raw_predicted_close is not None else close,
                        "predicted_return": None,
                        "horizon": idx + 1,
                    }
                )
            forecast_points = weekly_daily

        weekly_expected_close = (
            float(weekly["expected_week_close"])
            if isinstance(weekly.get("expected_week_close"), (int, float))
            else None
        )
        final_predicted_close = weekly_expected_close
        if final_predicted_close is None:
            final_predicted_close = (
                forecast_points[-1]["predicted_close"]
                if forecast_points and isinstance(forecast_points[-1].get("predicted_close"), (int, float))
                else None
            )
        week_start_close = (
            prediction["last_close"]
            if prediction["last_close"] is not None
            else weekly.get("last_close")
        )
        week_return_pct = None
        if isinstance(week_start_close, (int, float)) and week_start_close not in (None, 0.0) and isinstance(
            final_predicted_close, (int, float)
        ):
            week_return_pct = (float(final_predicted_close) - float(week_start_close)) / float(week_start_close) * 100.0
        elif isinstance(weekly.get("expected_week_return_pct"), (int, float)):
            week_return_pct = float(weekly["expected_week_return_pct"])

        model_metrics = weekly.get("model_metrics", {})
        if not isinstance(model_metrics, dict):
            model_metrics = {}
        previous_week = weekly.get("previous_week_comparison", {})
        if not isinstance(previous_week, dict):
            previous_week = {}
        history_metrics = self.historical_evaluation_rollup(symbol)

        return {
            "symbol": symbol,
            "configured": symbol in configured,
            "status": weekly.get("status", "unknown"),
            "tone": weekly.get("tone", "Unknown"),
            "weekly_generated_at": weekly.get("generated_at"),
            "latest_forecast_file": prediction["path"],
            "latest_evaluation_file": evaluation["path"],
            "last_observation_date": (
                prediction["payload"].get("last_observation_date")
                or weekly.get("last_observation")
                or _extract_date(prediction["path"] or "")
            ),
            "next_forecast_date": prediction["next_forecast_date"],
            "target_week_end_date": weekly.get("target_week_end_date"),
            "final_forecast_date": (
                weekly.get("final_forecast_date")
                or prediction["final_forecast_date"]
                or (forecast_points[-1]["date"] if forecast_points else None)
            ),
            "projection_selection": weekly.get("projection_selection"),
            "target_matched": bool(weekly.get("target_matched")),
            "note": weekly.get("note"),
            "forecast_risk": _safe_dict(weekly.get("forecast_risk")),
            "predicted_move_pct": prediction["predicted_move_pct"],
            "expected_week_return_pct": weekly.get("expected_week_return_pct"),
            "week_return_pct": week_return_pct,
            "week_start_close": week_start_close,
            "week_end_predicted_close": final_predicted_close,
            "last_close": week_start_close,
            "forecast_points": forecast_points,
            "mae": evaluation["mae"],
            "rmse": evaluation["rmse"],
            "mape": evaluation["mape"],
            "model_mae": _safe_float(model_metrics.get("mae")),
            "model_rmse": _safe_float(model_metrics.get("rmse")),
            "model_mape": _safe_float(model_metrics.get("mape")),
            "model_r2": _safe_float(model_metrics.get("r2")),
            "evaluation_count": evaluation["count"],
            "previous_week_comparison": previous_week,
            "previous_week_status": previous_week.get("status"),
            "previous_week_target_date": previous_week.get("target_week_end_date"),
            "previous_week_predicted_close": _safe_float(previous_week.get("predicted_close")),
            "previous_week_actual_close": _safe_float(previous_week.get("actual_close")),
            "previous_week_absolute_error": _safe_float(previous_week.get("absolute_error")),
            "previous_week_error_pct": _safe_float(previous_week.get("error_pct")),
            "history_metrics": history_metrics,
            "history_sample_count": history_metrics.get("sample_count"),
            "history_window_start": history_metrics.get("window_start"),
            "history_window_end": history_metrics.get("window_end"),
            "history_mae": history_metrics.get("mae"),
            "history_rmse": history_metrics.get("rmse"),
            "history_mape": history_metrics.get("mape"),
            "history_bias": history_metrics.get("bias"),
            "history_abs_error_p50": history_metrics.get("abs_error_p50"),
            "history_abs_error_p90": history_metrics.get("abs_error_p90"),
            "history_coverage_within_1pct": history_metrics.get("coverage_within_1pct"),
            "history_coverage_within_2pct": history_metrics.get("coverage_within_2pct"),
            "history_coverage_within_5pct": history_metrics.get("coverage_within_5pct"),
        }

    def build_overview(self) -> dict[str, Any]:
        """Create the aggregate dashboard payload."""
        configured = set(self.configured_tickers())
        discovered = set(self.discovered_tickers())
        status_map, weekly_source = self.weekly_status()
        ledger_cycles, ledger_meta = self.latest_ledger_cycles()
        cycle_history_map, cycle_history_meta = self.cycle_history_by_ticker()
        symbols = sorted(configured | discovered | set(status_map) | set(ledger_cycles))

        rows = []
        for symbol in symbols:
            row = self.ticker_row(symbol, configured, status_map)
            ledger_cycle = ledger_cycles.get(symbol)
            if isinstance(ledger_cycle, dict) and self._cycle_matches_row(row, ledger_cycle):
                row = self._merge_row_with_ledger(row, ledger_cycle)
            row, _ = self._apply_target_close_history(symbol, row, cycle_history_map.get(symbol))
            rows.append(row)

        market_context = self.market_context()
        reference_target_week_end = self._reference_target_week_end(
            rows=rows,
            status_map=status_map,
            ledger_cycles=ledger_cycles,
            market_context=market_context,
        )
        rows = [self._decorate_row(row, reference_target_week_end) for row in rows]

        rows.sort(key=lambda row: (row.get("display_group_order", 99), str(row.get("symbol", ""))))

        mae_values = [row["mae"] for row in rows if isinstance(row.get("mae"), float)]
        active_count = sum(1 for row in rows if row.get("status") == "active")
        review_count = sum(1 for row in rows if row.get("status") == "under_review")
        current_count = sum(
            1
            for row in rows
            if _safe_dict(row.get("business_health")).get("forecast_freshness") == "current"
            and bool(row.get("has_forecast_feed"))
        )
        stale_count = sum(
            1
            for row in rows
            if _safe_dict(row.get("business_health")).get("forecast_freshness") == "stale"
        )
        low_accuracy_count = sum(
            1
            for row in rows
            if _safe_dict(row.get("business_health")).get("state") == "low_accuracy"
        )
        watch_accuracy_count = sum(
            1
            for row in rows
            if _safe_dict(row.get("business_health")).get("state") == "watch_accuracy"
        )
        limited_history_count = sum(
            1
            for row in rows
            if any(_safe_dict(flag).get("key") == "limited_history" for flag in row.get("risk_flags", []))
        )
        extreme_move_count = sum(
            1
            for row in rows
            if any(_safe_dict(flag).get("key") == "extreme_move" for flag in row.get("risk_flags", []))
        )
        awaiting_score_count = sum(
            1
            for row in rows
            if _safe_dict(row.get("business_health")).get("state") == "awaiting_score"
        )
        weighted_week_terms = [
            (float(row["week_start_close"]), float(row["week_return_pct"]))
            for row in rows
            if isinstance(row.get("week_start_close"), (int, float))
            and isinstance(row.get("week_return_pct"), (int, float))
            and float(row["week_start_close"]) > 0
        ]
        weighted_week_return_pct = None
        if weighted_week_terms:
            weight_sum = sum(weight for weight, _ in weighted_week_terms)
            if weight_sum > 0:
                weighted_week_return_pct = (
                    sum(weight * week_return for weight, week_return in weighted_week_terms) / weight_sum
                )
        history_rollup = self.portfolio_history_rollup(rows)
        previous_week_rollup = self.prior_week_rollup(rows)
        alerts = self.build_failed_ticker_alerts(rows)
        groups = []
        for key, label, description in DISPLAY_GROUPS:
            group_rows = [row for row in rows if row.get("display_group") == key]
            if not group_rows:
                continue
            groups.append(
                {
                    "key": key,
                    "label": label,
                    "description": description,
                    "count": len(group_rows),
                    "symbols": [str(row.get("symbol", "")) for row in group_rows],
                }
            )

        summary = {
            "configured_tickers": len(configured),
            "visible_tickers": len(rows),
            "discovered_tickers": len(symbols),
            "current_tickers": current_count,
            "stale_tickers": stale_count,
            "low_accuracy_tickers": low_accuracy_count,
            "watch_accuracy_tickers": watch_accuracy_count,
            "limited_history_tickers": limited_history_count,
            "extreme_move_tickers": extreme_move_count,
            "awaiting_score_tickers": awaiting_score_count,
            "tickers_with_forecasts": sum(1 for row in rows if row.get("has_forecast_feed")),
            "tickers_with_evaluation": sum(1 for row in rows if row.get("has_evaluation_feed")),
            "average_mae": mean(mae_values) if mae_values else None,
            "active_count": active_count,
            "under_review_count": review_count,
            "weighted_week_return_pct": weighted_week_return_pct,
            "weighted_week_coverage": len(weighted_week_terms),
            "target_week_end_date": reference_target_week_end.isoformat(),
            "market_status": "open" if market_context.get("is_market_open_now") else "closed",
            "market_time": market_context.get("market_time"),
            "latest_market_session_date": market_context.get("latest_market_session_date"),
            "next_market_session_date": market_context.get("next_market_session_date"),
            "calendar_source": market_context.get("calendar_source"),
            "historical_rollup": history_rollup,
            "previous_week_rollup": previous_week_rollup,
            "historical_samples": history_rollup.get("sample_count"),
            "historical_average_mape": history_rollup.get("average_mape"),
            "prior_week_resolved": previous_week_rollup.get("resolved_count"),
            "prior_week_mae": previous_week_rollup.get("mae"),
            "prior_week_direction_accuracy_pct": previous_week_rollup.get("direction_accuracy_pct"),
            "open_alerts": alerts.get("open_count"),
            "critical_alerts": alerts.get("critical_count"),
            "warning_alerts": alerts.get("warning_count"),
        }

        return {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "market_clock": market_context,
            "summary": summary,
            "alerts": {
                "open_count": alerts.get("open_count"),
                "critical_count": alerts.get("critical_count"),
                "warning_count": alerts.get("warning_count"),
                "info_count": alerts.get("info_count"),
                "items": alerts.get("items", []),
                "sources": alerts.get("sources", {}),
            },
            "source_files": {
                "config": str(_canonical(self.config_path)) if self.config_path.exists() else None,
                "weekly_status": weekly_source,
                "automation_state": alerts.get("sources", {}).get("automation_state"),
                "weekly_alerts": alerts.get("sources", {}).get("weekly"),
                "ledger_cycle_summary": ledger_meta.get("source"),
                "ledger_cycle_history": cycle_history_meta.get("source"),
            },
            "groups": groups,
            "tickers": rows,
        }

    def build_ticker_detail(self, symbol: str) -> dict[str, Any]:
        """Create a full detail payload for one ticker."""
        symbol = symbol.upper()
        configured = set(self.configured_tickers())
        status_map, weekly_source = self.weekly_status()
        ledger_cycles, ledger_meta = self.latest_ledger_cycles()
        cycle_history_map, cycle_history_meta = self.cycle_history_by_ticker()

        row = self.ticker_row(symbol, configured, status_map)
        ledger_cycle = ledger_cycles.get(symbol)
        if isinstance(ledger_cycle, dict) and self._cycle_matches_row(row, ledger_cycle):
            row = self._merge_row_with_ledger(row, ledger_cycle)
        else:
            ledger_cycle = None
        row, history_rows = self._apply_target_close_history(symbol, row, cycle_history_map.get(symbol))
        market_context = self.market_context()
        reference_target_week_end = self._reference_target_week_end(
            rows=[row],
            status_map=status_map,
            ledger_cycles=ledger_cycles,
            market_context=market_context,
        )
        row = self._decorate_row(row, reference_target_week_end)
        prediction = self.latest_prediction(symbol)
        evaluation = self.latest_evaluation(symbol)
        weekly = status_map.get(symbol, {})
        forecast_points = row.get("forecast_points", [])
        alerts = self.build_failed_ticker_alerts([row], symbols=[symbol])
        ticker_alert = alerts.get("by_symbol", {}).get(symbol)

        has_data = bool(prediction["path"] or evaluation["path"] or symbol in configured or isinstance(ledger_cycle, dict))
        if not has_data:
            raise KeyError(symbol)

        return {
            **row,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "market_clock": market_context,
            "forecast": forecast_points,
            "context": prediction["context"],
            "evaluation": evaluation["payload"],
            "weekly": weekly,
            "cycle": ledger_cycle,
            "history_rows": history_rows,
            "alert": ticker_alert,
            "source_files": {
                "weekly_status": weekly_source,
                "automation_state": alerts.get("sources", {}).get("automation_state"),
                "weekly_alerts": alerts.get("sources", {}).get("weekly"),
                "ledger_cycle_summary": ledger_meta.get("source"),
                "ledger_cycle_history": cycle_history_meta.get("source"),
            },
        }
