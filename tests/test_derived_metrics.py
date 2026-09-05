from pathlib import Path

import yaml

from duc_agentic_mining.derived_metrics import (
    derive_scaling_metrics,
    enrich_metrics_file,
    record_human_review,
)


def _raw_metrics() -> dict:
    return {
        "run_id": "r1",
        "elapsed_seconds": 3600.0,
        "exploration_rounds_completed": 5,
        "candidates_recorded": 10,
        "candidates_unique": 9,
        "validations_completed": 8,
        "candidates_promoted": 4,
        "proposal_reviews_completed": 6,
        "proposals_passed": 2,
        "repairs_attempted": 2,
        "role_usage": {
            "explorer": {
                "requests": 20,
                "input_tokens": 1000,
                "output_tokens": 200,
                "cached_input_tokens": 100,
                "errors": 1,
            },
            "validator": {
                "requests": 8,
                "input_tokens": 800,
                "output_tokens": 160,
                "cached_input_tokens": 0,
                "errors": 0,
            },
            "generator": {
                "requests": 6,
                "input_tokens": 600,
                "output_tokens": 300,
                "cached_input_tokens": 0,
                "errors": 0,
            },
            "reviewer": {
                "requests": 6,
                "input_tokens": 700,
                "output_tokens": 180,
                "cached_input_tokens": 0,
                "errors": 0,
            },
        },
    }


def test_derived_scaling_metrics(tmp_path: Path):
    reviews = {
        "reviews": [
            {"candidate_uid": "c1"},
            {"candidate_uid": "c2"},
            {"candidate_uid": "c3"},
            {"candidate_uid": "c4"},
        ]
    }
    (tmp_path / "proposal_reviews.yaml").write_text(
        yaml.safe_dump(reviews), encoding="utf-8"
    )
    record_human_review(tmp_path, reviewed=2, accepted=1)

    derived = derive_scaling_metrics(
        _raw_metrics(),
        run_dir=tmp_path,
        concurrent_anchor_rounds=8,
    )

    assert derived["average_explorer_calls_per_anchor"] == 4.0
    assert derived["candidates_found_per_anchor"] == 2.0
    assert derived["validator_promotion_rate"] == 0.5
    assert derived["grounding_pass_rate"] == 0.5
    assert derived["average_repair_attempts"] == 0.5
    assert derived["usable_routes_produced_per_anchor"] == 0.4
    assert derived["average_wall_clock_seconds_per_accepted_route"] == 1800.0
    assert derived["accepted_routes_per_hour"] == 2.0
    assert derived["concurrent_anchor_rounds"] == 8
    assert derived["api_requests_per_accepted_route"] == 20.0
    assert derived["api_tokens_per_accepted_route"] == 1970.0
    assert derived["human_acceptance_rate"] == 0.5


def test_enrich_metrics_persists_derived_section(tmp_path: Path):
    (tmp_path / "proposal_reviews.yaml").write_text(
        yaml.safe_dump({"reviews": [{"candidate_uid": "c1"}]}),
        encoding="utf-8",
    )
    metrics_path = tmp_path / "metrics.yaml"
    metrics_path.write_text(yaml.safe_dump(_raw_metrics()), encoding="utf-8")

    enrich_metrics_file(metrics_path, concurrent_anchor_rounds=4)
    payload = yaml.safe_load(metrics_path.read_text(encoding="utf-8"))

    assert "derived_metrics" in payload
    assert payload["derived_metrics"]["concurrent_anchor_rounds"] == 4
    assert payload["derived_metrics"]["human_acceptance_rate"] is None


def test_human_review_counts_are_validated(tmp_path: Path):
    try:
        record_human_review(tmp_path, reviewed=2, accepted=3)
    except ValueError:
        pass
    else:
        raise AssertionError("accepted > reviewed should fail")
