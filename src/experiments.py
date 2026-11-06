"""Experiment orchestration utilities for automated model iteration."""

from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import fmean
from typing import Any, Dict, Iterable, List, Optional, Sequence
import tomllib

from .config import PipelineConfig, build_pipeline_config, deep_merge_dicts
from .pipeline import PipelineRunner


class ExperimentConfigError(Exception):
    """Raised when the experiment configuration is invalid."""


@dataclass
class ExperimentSpec:
    """Declarative description of an experiment variant."""

    name: str
    description: Optional[str]
    tickers: Optional[List[str]]
    overrides: Dict[str, Any]
    score_metric: str


@dataclass
class ExperimentResult:
    """Summary of a completed experiment run."""

    name: str
    ticker_metrics: Dict[str, Dict[str, float]]
    best_folds: Dict[str, int]
    aggregate_score: Optional[float]
    output_dirs: Dict[str, str]


def _load_raw_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise ExperimentConfigError(f"Base pipeline config not found: {path}")
    with path.open("rb") as fp:
        return tomllib.load(fp)


def _select_experiments(experiments: Sequence[ExperimentSpec], selected: Optional[Iterable[str]]) -> List[ExperimentSpec]:
    if not selected:
        return list(experiments)
    selected_set = set(selected)
    filtered = [spec for spec in experiments if spec.name in selected_set]
    missing = selected_set.difference({spec.name for spec in filtered})
    if missing:
        raise ExperimentConfigError(f"Unknown experiment names requested: {sorted(missing)}")
    return filtered


def _ensure_metric_available(metrics: Dict[str, float], metric_name: str, ticker: str, experiment: str) -> None:
    if metric_name not in metrics:
        raise ExperimentConfigError(
            f"Metric '{metric_name}' not found for ticker '{ticker}' in experiment '{experiment}'. "
            "Update score_metric or ensure the metric is produced by the pipeline."
        )


class ExperimentRunner:
    """Runs a suite of experiments by applying overrides to the base pipeline config."""

    def __init__(self, base_config_path: Path, artifact_root: Path, experiments: Sequence[ExperimentSpec]):
        self.base_config_path = base_config_path
        self.base_raw_config = _load_raw_config(base_config_path)
        self.artifact_root = artifact_root
        self.experiments = list(experiments)

    def run(self, selected: Optional[Iterable[str]] = None) -> List[ExperimentResult]:
        """Execute the requested experiments and return their summaries."""
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        run_root = self.artifact_root / timestamp
        run_root.mkdir(parents=True, exist_ok=True)

        chosen_experiments = _select_experiments(self.experiments, selected)
        results: List[ExperimentResult] = []

        for spec in chosen_experiments:
            logging.info("Starting experiment '%s'", spec.name)
            experiment_dir = run_root / spec.name
            experiment_dir.mkdir(parents=True, exist_ok=True)

            raw_config = copy.deepcopy(self.base_raw_config)
            if spec.overrides:
                raw_config = deep_merge_dicts(raw_config, spec.overrides)

            pipeline_config: PipelineConfig = build_pipeline_config(raw_config, source=self.base_config_path)
            runner = PipelineRunner(pipeline_config)
            ticker_subset = spec.tickers
            pipeline_results = runner.run(ticker_subset)

            ticker_metrics: Dict[str, Dict[str, float]] = {}
            best_folds: Dict[str, int] = {}
            output_dirs: Dict[str, str] = {}

            for ticker, summary in pipeline_results.items():
                ticker_metrics[ticker] = summary.aggregated_metrics
                best_folds[ticker] = summary.best_fold
                # best fold model directory is parent of saved model path; reuse first fold path.
                if summary.fold_results:
                    best_model_path = next(
                        fold.model_path for fold in summary.fold_results if fold.fold_index == summary.best_fold
                    )
                    output_dirs[ticker] = str(Path(best_model_path).parent.parent)

            aggregate_score: Optional[float] = None
            if ticker_metrics:
                metric_values = []
                for ticker, metrics in ticker_metrics.items():
                    _ensure_metric_available(metrics, spec.score_metric, ticker, spec.name)
                    metric_values.append(metrics[spec.score_metric])
                aggregate_score = fmean(metric_values) if metric_values else None

            summary_payload = {
                "experiment": {
                    "name": spec.name,
                    "description": spec.description,
                    "tickers": spec.tickers,
                    "score_metric": spec.score_metric,
                    "overrides": spec.overrides,
                },
                "results": {
                    "aggregated_score": aggregate_score,
                    "ticker_metrics": ticker_metrics,
                    "best_folds": best_folds,
                    "output_dirs": output_dirs,
                },
            }

            summary_path = experiment_dir / "summary.json"
            with summary_path.open("w", encoding="utf-8") as fp:
                json.dump(summary_payload, fp, indent=2, default=str)

            logging.info("Completed experiment '%s' (score: %s)", spec.name, aggregate_score)
            results.append(
                ExperimentResult(
                    name=spec.name,
                    ticker_metrics=ticker_metrics,
                    best_folds=best_folds,
                    aggregate_score=aggregate_score,
                    output_dirs=output_dirs,
                )
            )

        return results


def load_experiment_plan(path: Path | str) -> tuple[Path, Path, List[ExperimentSpec]]:
    """
    Load an experiment definition file.

    Returns:
        Tuple containing the base pipeline config path, artifacts root, and experiment specs.
    """
    config_path = Path(path)
    if not config_path.exists():
        raise ExperimentConfigError(f"Experiment config does not exist: {config_path}")

    with config_path.open("rb") as fp:
        raw = tomllib.load(fp)

    base_section = raw.get("base")
    if not base_section or "config" not in base_section:
        raise ExperimentConfigError("Experiment file must define [base] with a 'config' entry.")

    base_config_path = Path(base_section["config"])
    artifact_root = Path(base_section.get("artifact_root", "artifacts/experiments"))

    experiments_raw = raw.get("experiments")
    if not experiments_raw:
        raise ExperimentConfigError("No experiments defined under [[experiments]].")

    specs: List[ExperimentSpec] = []
    for item in experiments_raw:
        name = item.get("name")
        if not name:
            raise ExperimentConfigError("Each experiment must have a 'name'.")

        overrides = item.get("overrides", {})
        tickers = item.get("tickers")
        if tickers is not None and not isinstance(tickers, list):
            raise ExperimentConfigError(f"'tickers' must be a list for experiment '{name}'.")

        score_metric = item.get("score_metric", "MAE")

        specs.append(
            ExperimentSpec(
                name=name,
                description=item.get("description"),
                tickers=[ticker.upper() for ticker in tickers] if tickers else None,
                overrides=overrides,
                score_metric=score_metric,
            )
        )

    return base_config_path, artifact_root, specs
