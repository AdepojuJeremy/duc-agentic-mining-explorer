import pytest

from duc_agentic_mining.models import Candidate, CandidateValidation, Gate


def test_candidate_requires_distinct_sources():
    with pytest.raises(ValueError):
        Candidate(
            candidate_uid="c1",
            round_id="r1",
            anchor_source_id="s1",
            decision_question="Q?",
            baseline_source_id="s1",
            modifier_source_id="s1",
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
            promote=True,
            normalized_arm="contradictory",
            normalized_update="revise",
            concerns=[],
        )
