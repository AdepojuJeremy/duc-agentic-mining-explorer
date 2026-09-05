from duc_agentic_mining.models import (
    Candidate,
    ConstructionContract,
    SourceProvenance,
    VignetteProposal,
)
from duc_agentic_mining.quality import static_vignette_checks


def provenance(source_id: str) -> SourceProvenance:
    return SourceProvenance(
        source_id=source_id,
        canonical_organization="WHO",
        authority_tier=1,
        source_kind="guideline_authority",
        recommendation_authority=True,
        redistribution_status="redistributable",
        source_status="versioned",
        freshness_verified=False,
        seed_collection=None,
        title="Guideline",
        source="WHO",
        url=None,
        date="2025",
    )


def test_static_checks_preserve_contract_and_stage_difference():
    candidate = Candidate(
        candidate_uid="c1",
        round_id="r1",
        anchor_source_id="s1",
        decision_domain="medication_safety",
        decision_question="Should the medicine be continued?",
        baseline_source_id="s1",
        modifier_source_id="s2",
        baseline_evidence_span="Baseline evidence recommends continuing the medicine.",
        modifier_evidence_span="Modifier evidence identifies a clinically relevant interaction.",
        relationship_summary="interaction complicates continuation",
        proposed_arm="complicating",
        expected_update="revise",
        rationale="test",
    )
    contract = ConstructionContract(
        contract_uid="contract1",
        candidate_uid="c1",
        decision_domain="medication_safety",
        decision_question="Should the medicine be continued?",
        baseline_source_id="s1",
        modifier_source_id="s2",
        baseline_evidence_span=candidate.baseline_evidence_span,
        modifier_evidence_span=candidate.modifier_evidence_span,
        evidence_arm="complicating",
        expected_update="revise",
        affected_decision_components=["administration"],
        allowed_scenario_premises=[],
        source_provenance=[provenance("s1"), provenance("s2")],
        created_at=candidate.created_at,
    )
    proposal = VignetteProposal(
        candidate_uid="c1",
        contract_uid="contract1",
        constructible=True,
        unconstructible_reason=None,
        decision_domain="medication_safety",
        clinical_question="Should the medicine be continued?",
        stage_1_context="The patient is receiving the medicine under the baseline indication.",
        stage_2_update="A newly identified interacting medicine changes how administration should be managed.",
        expected_initial_recommendation="Continue the medicine under the baseline recommendation.",
        expected_revised_recommendation="Continue with a revised administration plan.",
        evidence_arm="complicating",
        expected_update="revise",
        affected_decision_components=["administration"],
        confidence_direction="maintain",
        warrant="The modifier changes implementation without necessarily replacing the treatment.",
        scenario_premises=[],
        claim_source_map=[],
        source_ids=["s1", "s2"],
        source_provenance=[provenance("s1"), provenance("s2")],
        unresolved_questions=[],
        draft_number=1,
    )
    result = static_vignette_checks(candidate, contract, proposal)
    assert result["contract_locked"] is True
    assert result["nonduplicative_stage2"] is True
    assert result["provenance_complete"] is True
