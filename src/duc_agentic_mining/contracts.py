from __future__ import annotations

from .corpus import CorpusStore
from .models import (
    Candidate,
    CandidateValidation,
    ConstructionContract,
    SourceProvenance,
    stable_id,
)
from .source_policy import classify_source


def source_provenance(record) -> SourceProvenance:
    policy = classify_source(record)
    return SourceProvenance(
        source_id=record.source_id,
        canonical_organization=policy.canonical_organization,
        authority_tier=policy.authority_tier,
        source_kind=policy.source_kind,
        recommendation_authority=policy.recommendation_authority,
        redistribution_status=policy.redistribution_status,
        source_status=policy.source_status,
        freshness_verified=policy.freshness_verified,
        seed_collection=policy.seed_collection,
        title=record.title,
        source=record.source,
        url=record.url,
        date=record.date,
    )


def build_construction_contract(
    candidate: Candidate,
    validation: CandidateValidation,
    corpus: CorpusStore,
) -> ConstructionContract:
    if not validation.promote:
        raise ValueError("cannot build a construction contract from a non-promoted candidate")
    baseline = corpus.get(candidate.baseline_source_id)
    modifier = corpus.get(candidate.modifier_source_id)
    if not baseline or not modifier:
        raise ValueError("candidate references missing source record")

    contract_uid = stable_id(
        "contract",
        candidate.candidate_uid,
        validation.normalized_domain,
        validation.normalized_arm,
        validation.normalized_update,
    )
    return ConstructionContract(
        contract_uid=contract_uid,
        candidate_uid=candidate.candidate_uid,
        decision_domain=validation.normalized_domain,
        decision_question=candidate.decision_question,
        baseline_source_id=candidate.baseline_source_id,
        modifier_source_id=candidate.modifier_source_id,
        baseline_evidence_span=candidate.baseline_evidence_span,
        modifier_evidence_span=candidate.modifier_evidence_span,
        evidence_arm=validation.normalized_arm,
        expected_update=validation.normalized_update,
        affected_decision_components=validation.affected_decision_components,
        allowed_scenario_premises=validation.allowed_scenario_premises,
        source_provenance=[source_provenance(baseline), source_provenance(modifier)],
        # Stable rather than wall-clock generated so equality/resume checks do not
        # rewrite an otherwise identical locked contract every exploration wave.
        created_at=candidate.created_at,
    )
