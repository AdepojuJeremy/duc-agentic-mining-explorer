from pathlib import Path

from duc_agentic_mining.contracts import build_construction_contract
from duc_agentic_mining.corpus import CorpusStore
from duc_agentic_mining.models import Candidate, CandidateValidation, Gate, SourceRecord


def test_contract_is_stable_and_locks_route(tmp_path: Path):
    store = CorpusStore(tmp_path / "sources.sqlite")
    store.add(SourceRecord(source_id="s1", source="WHO", text="Baseline recommendation evidence span for testing."))
    store.add(SourceRecord(source_id="s2", source="NICE", text="Modifier recommendation evidence span for testing."))
    store.commit()

    candidate = Candidate(
        candidate_uid="c1",
        round_id="r1",
        anchor_source_id="s1",
        decision_domain="treatment_selection",
        decision_question="What treatment is recommended?",
        baseline_source_id="s1",
        modifier_source_id="s2",
        baseline_evidence_span="Baseline recommendation evidence span for testing.",
        modifier_evidence_span="Modifier recommendation evidence span for testing.",
        relationship_summary="same decision with modifying evidence",
        proposed_arm="complicating",
        expected_update="revise",
        rationale="test",
    )
    good = Gate(passed=True, rationale="ok")
    validation = CandidateValidation(
        candidate_uid="c1",
        same_decision=good,
        source_supported=good,
        stage1_defensible=good,
        genuine_update_pressure=good,
        applicability_coherent=good,
        arm_and_update_coherent=good,
        source_policy=good,
        promote=True,
        normalized_domain="treatment_selection",
        normalized_arm="complicating",
        normalized_update="revise",
        affected_decision_components=["action_choice"],
        allowed_scenario_premises=[],
        concerns=[],
    )

    first = build_construction_contract(candidate, validation, store)
    second = build_construction_contract(candidate, validation, store)
    assert first == second
    assert first.baseline_evidence_span == candidate.baseline_evidence_span
    assert first.affected_decision_components == ["action_choice"]
