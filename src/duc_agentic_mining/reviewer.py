from __future__ import annotations

import json

from .config import SourcePolicyConfig
from .corpus import CorpusStore
from .llm import OpenAIRoleClient
from .models import (
    Candidate,
    CandidateValidation,
    ConstructionContract,
    GroundingGate,
    ProposalReview,
    VignetteProposal,
)
from .prompts import REVIEWER_SYSTEM
from .quality import static_vignette_checks
from .source_policy import assess_source_pair


async def review_proposal(
    candidate: Candidate,
    validation: CandidateValidation,
    contract: ConstructionContract,
    proposal: VignetteProposal,
    corpus: CorpusStore,
    client: OpenAIRoleClient,
    source_policy_cfg: SourcePolicyConfig,
) -> ProposalReview:
    baseline = corpus.get(candidate.baseline_source_id)
    modifier = corpus.get(candidate.modifier_source_id)
    if not baseline or not modifier:
        raise ValueError("proposal references missing source")

    static = static_vignette_checks(candidate, contract, proposal)
    source_policy = assess_source_pair(
        baseline,
        modifier,
        validation.normalized_arm,
        source_policy_cfg,
    )
    payload = {
        "candidate": candidate.model_dump(mode="json"),
        "validation": validation.model_dump(mode="json"),
        "construction_contract": contract.model_dump(mode="json"),
        "proposal": proposal.model_dump(mode="json"),
        "baseline_source": baseline.model_dump(mode="json"),
        "modifier_source": modifier.model_dump(mode="json"),
        "deterministic_static_checks": static,
        "deterministic_source_policy": source_policy.to_dict(),
    }
    result = await client.structured(
        REVIEWER_SYSTEM,
        json.dumps(payload, ensure_ascii=False),
        ProposalReview,
        "proposal_review",
    )
    value = result.value
    assert isinstance(value, ProposalReview)
    value.candidate_uid = candidate.candidate_uid

    concerns = list(value.concerns)
    concerns.extend(str(x) for x in static["concerns"])
    concerns.extend(source_policy.concerns)
    value.concerns = list(dict.fromkeys(concerns))

    if not bool(static["no_answer_cues"]):
        value.no_answer_cues = GroundingGate(
            passed=False,
            rationale="deterministic check detected an exact expected-answer cue",
        )
    if not bool(static["nonduplicative_stage2"]):
        value.nonduplicative_stage2 = GroundingGate(
            passed=False,
            rationale="deterministic check found Stage 2 empty or too similar to Stage 1",
        )
    if not bool(static["provenance_complete"]) or not bool(static["source_ids_match"]):
        value.provenance_complete = GroundingGate(
            passed=False,
            rationale="deterministic source/provenance check failed",
        )
    if not bool(static["contract_locked"]):
        value.same_decision_preserved = GroundingGate(
            passed=False,
            rationale="proposal changed one or more immutable construction-contract fields",
        )
        value.affected_components_consistent = GroundingGate(
            passed=False,
            rationale="proposal did not preserve locked affected decision components",
        )
        value.needs_candidate_revalidation = True

    constructed_premises = [
        premise
        for premise in proposal.scenario_premises
        if premise.status == "constructed_requires_review"
    ]
    if constructed_premises and not contract.allowed_scenario_premises:
        value.scenario_premises_authorized = GroundingGate(
            passed=False,
            rationale="proposal introduced constructed scenario premises but the contract allows none",
        )

    if not source_policy.passed:
        value.source_policy_consistent = GroundingGate(
            passed=False,
            rationale="; ".join(source_policy.concerns) or "source policy failed",
        )
        value.needs_candidate_revalidation = True

    gates = [
        value.source_fidelity,
        value.same_decision_preserved,
        value.stage_separation,
        value.no_unsupported_patient_facts,
        value.scenario_premises_authorized,
        value.no_answer_cues,
        value.nonduplicative_stage2,
        value.recommendation_grounding,
        value.affected_components_consistent,
        value.arm_and_update_consistency,
        value.source_policy_consistent,
        value.provenance_complete,
    ]
    if not all(gate.passed for gate in gates):
        value.overall_pass = False
    return value
