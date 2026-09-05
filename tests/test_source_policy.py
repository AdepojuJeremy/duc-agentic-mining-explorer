from duc_agentic_mining.config import SourcePolicyConfig
from duc_agentic_mining.models import SourceRecord
from duc_agentic_mining.source_policy import assess_source_pair, classify_source


def test_who_record_is_tier1_guideline_authority():
    record = SourceRecord(
        source_id="who-1",
        source="WHO",
        title="Clinical guideline",
        text="Recommendation text",
        url="https://www.who.int/publications/example",
        date="2025",
        metadata={"origin": "open_guidelines.jsonl"},
    )
    policy = classify_source(record)
    assert policy.authority_tier == 1
    assert policy.recommendation_authority is True
    assert policy.source_status == "versioned"
    assert policy.seed_collection == "Meditron Guidelines Collection"


def test_tier2_baseline_can_be_rejected_as_decision_authority():
    baseline = SourceRecord(
        source_id="rx",
        source="RxNorm",
        text="Drug normalization record",
    )
    modifier = SourceRecord(
        source_id="who",
        source="WHO",
        text="Guideline recommendation",
        date="2025",
    )
    assessment = assess_source_pair(
        baseline,
        modifier,
        "complicating",
        SourcePolicyConfig(reject_tier2_as_decision_authority=True),
    )
    assert assessment.passed is False


def test_strict_contradiction_requires_known_currentness():
    baseline = SourceRecord(source_id="a", source="WHO", text="Old recommendation")
    modifier = SourceRecord(source_id="b", source="NICE", text="Different recommendation")
    assessment = assess_source_pair(
        baseline,
        modifier,
        "contradictory",
        SourcePolicyConfig(require_known_currentness_for_contradictory=True),
    )
    assert assessment.passed is False
