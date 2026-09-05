from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .artifacts import atomic_yaml


def _ratio(numerator: float | int, denominator: float | int) -> float | None:
    if not denominator:
        return None
    return round(float(numerator) / float(denominator), 6)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _unique_reviewed_routes(run_dir: Path) -> int:
    payload = _load_yaml(run_dir / "proposal_reviews.yaml")
    reviews = payload.get("reviews") or []
    candidate_ids = {
        str(row.get("candidate_uid"))
        for row in reviews
        if isinstance(row, dict) and row.get("candidate_uid")
    }
    return len(candidate_ids)


def _human_review_counts(run_dir: Path) -> tuple[int, int]:
    payload = _load_yaml(run_dir / "human_review.yaml")
    reviewed = int(payload.get("reviewed", 0) or 0)
    accepted = int(payload.get("accepted", 0) or 0)
    if reviewed < 0 or accepted < 0 or accepted > reviewed:
        raise ValueError("human review counts must satisfy 0 <= accepted <= reviewed")
    return reviewed, accepted


def derive_scaling_metrics(
    raw: dict[str, Any],
    run_dir: Path,
    concurrent_anchor_rounds: int,
) -> dict[str, Any]:
    role_usage = raw.get("role_usage") or {}
    explorer_usage = role_usage.get("explorer") or {}

    anchors = int(raw.get("exploration_rounds_completed", 0) or 0)
    candidates_recorded = int(raw.get("candidates_recorded", 0) or 0)
    candidates_unique = int(raw.get("candidates_unique", 0) or 0)
    validations = int(raw.get("validations_completed", 0) or 0)
    promoted = int(raw.get("candidates_promoted", 0) or 0)
    accepted_routes = int(raw.get("proposals_passed", 0) or 0)
    repairs = int(raw.get("repairs_attempted", 0) or 0)
    elapsed_seconds = float(raw.get("elapsed_seconds", 0.0) or 0.0)
    unique_reviewed_routes = _unique_reviewed_routes(run_dir)

    total_requests = 0
    total_input_tokens = 0
    total_output_tokens = 0
    total_cached_input_tokens = 0
    total_errors = 0
    by_role_per_accepted_route: dict[str, dict[str, float | None]] = {}

    for role, usage in role_usage.items():
        if not isinstance(usage, dict):
            continue
        requests = int(usage.get("requests", 0) or 0)
        input_tokens = int(usage.get("input_tokens", 0) or 0)
        output_tokens = int(usage.get("output_tokens", 0) or 0)
        cached_input_tokens = int(usage.get("cached_input_tokens", 0) or 0)
        errors = int(usage.get("errors", 0) or 0)
        total_requests += requests
        total_input_tokens += input_tokens
        total_output_tokens += output_tokens
        total_cached_input_tokens += cached_input_tokens
        total_errors += errors
        by_role_per_accepted_route[str(role)] = {
            "requests": _ratio(requests, accepted_routes),
            "input_tokens": _ratio(input_tokens, accepted_routes),
            "output_tokens": _ratio(output_tokens, accepted_routes),
        }

    human_reviewed, human_accepted = _human_review_counts(run_dir)
    elapsed_hours = elapsed_seconds / 3600.0 if elapsed_seconds > 0 else 0.0

    return {
        "average_explorer_calls_per_anchor": _ratio(
            int(explorer_usage.get("requests", 0) or 0), anchors
        ),
        "candidates_found_per_anchor": _ratio(candidates_recorded, anchors),
        "unique_candidates_per_anchor": _ratio(candidates_unique, anchors),
        "validator_promotion_rate": _ratio(promoted, validations),
        "grounding_pass_rate": _ratio(accepted_routes, unique_reviewed_routes),
        "average_repair_attempts": _ratio(repairs, unique_reviewed_routes),
        "average_repair_attempts_per_accepted_route": _ratio(repairs, accepted_routes),
        "usable_routes_produced_per_anchor": _ratio(accepted_routes, anchors),
        "average_wall_clock_seconds_per_accepted_route": _ratio(
            elapsed_seconds, accepted_routes
        ),
        "accepted_routes_per_hour": _ratio(accepted_routes, elapsed_hours),
        "concurrent_anchor_rounds": concurrent_anchor_rounds,
        "unique_reviewed_routes": unique_reviewed_routes,
        "api_requests_per_accepted_route": _ratio(total_requests, accepted_routes),
        "api_input_tokens_per_accepted_route": _ratio(total_input_tokens, accepted_routes),
        "api_output_tokens_per_accepted_route": _ratio(total_output_tokens, accepted_routes),
        "api_tokens_per_accepted_route": _ratio(
            total_input_tokens + total_output_tokens, accepted_routes
        ),
        "cached_input_tokens_per_accepted_route": _ratio(
            total_cached_input_tokens, accepted_routes
        ),
        "total_api_requests": total_requests,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_cached_input_tokens": total_cached_input_tokens,
        "total_api_errors": total_errors,
        "api_by_role_per_accepted_route": by_role_per_accepted_route,
        "human_reviews_completed": human_reviewed,
        "human_reviews_accepted": human_accepted,
        "human_acceptance_rate": _ratio(human_accepted, human_reviewed),
        "metric_notes": {
            "anchor": "one completed agentic exploration round",
            "grounding_pass_rate": "accepted deduplicated routes divided by unique routes with an automated proposal review",
            "average_repair_attempts": "repair attempts divided by unique automatically reviewed routes",
            "wall_clock_time": "effective total elapsed run time divided by accepted routes; includes concurrency",
            "human_acceptance_rate": "null until human_review.yaml contains reviewed/accepted counts",
        },
    }


def enrich_metrics_file(
    metrics_path: Path,
    concurrent_anchor_rounds: int,
) -> dict[str, Any]:
    raw = _load_yaml(metrics_path)
    if not raw:
        raise FileNotFoundError(f"metrics file not found or empty: {metrics_path}")
    raw.pop("derived_metrics", None)
    derived = derive_scaling_metrics(raw, metrics_path.parent, concurrent_anchor_rounds)
    raw["derived_metrics"] = derived
    atomic_yaml(metrics_path, raw)
    return derived


def record_human_review(run_dir: Path, reviewed: int, accepted: int) -> None:
    if reviewed < 0 or accepted < 0 or accepted > reviewed:
        raise ValueError("human review counts must satisfy 0 <= accepted <= reviewed")
    atomic_yaml(
        run_dir / "human_review.yaml",
        {
            "reviewed": reviewed,
            "accepted": accepted,
        },
    )
