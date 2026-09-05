import pytest

from duc_agentic_mining.models import Candidate, CandidateValidation, Gate


def test_candidate_requires_distinct_sources():
    with pytest.raises(ValueError):
        Candidate(
            candidate_uid="c1",
            round_id="r1",
            anchor_source_id="s1",
            decision_domain="diagnosis",
            decision_question="Q?",
            baseline_source_id="s1",
            modifier_source_id="s1",
            baseline_evidence_span="This is a sufficiently long baseline source evidence span.",
            modifier_evidence_span="This is a sufficiently long modifier source evidence span.",
            relationship_summary="x",
            proposed_arm="contradictory",
            expected_update="revise",
            rationale="x",
        )


def test_promote_requires_all_gates():
    good = Gate(passed=True, rationale="ok")
    bad = Gate(passed=False, rationale="no")
    with pytest.raises(ValueError):
        CandidateValidation(
            candidate_uid="c1",
            same_decision=good,
            source_supported=good,
            stage1_defensible=good,
            genuine_update_pressure=bad,
            applicability_coherent=good,
            arm_and_update_coherent=good,
            source_policy=good,
            promote=True,
            normalized_domain="diagnosis",
            normalized_arm="contradictory",
            normalized_update="revise",
            affected_decision_components=["action_choice"],
            allowed_scenario_premises=[],
            concerns=[],
        )


def test_promoted_route_requires_affected_components():
    good = Gate(passed=True, rationale="ok")
    with pytest.raises(ValueError):
        CandidateValidation(
            candidate_uid="c1",
            same_decision=good,
            source_supported=good,
            stage1_defensible=good,
            genuine_update_pressure=good,
            applicability_coherent=good,
            arm_and_update_coherent=good,
            source_policy=good,
            promote=True,
            normalized_domain="diagnosis",
            normalized_arm="complicating",
            normalized_update="revise",
            affected_decision_components=[],
            allowed_scenario_premises=[],
            concerns=[],
        )
