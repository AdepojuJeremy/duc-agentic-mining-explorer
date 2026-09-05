from __future__ import annotations

import re
from difflib import SequenceMatcher

from .models import Candidate, ConstructionContract, VignetteProposal


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", text.lower())).strip()


def _contains_answer_cue(context: str, answer: str) -> bool:
    answer_norm = _norm(answer)
    context_norm = _norm(context)
    if len(answer_norm) < 24:
        return False
    return answer_norm in context_norm


def static_vignette_checks(
    candidate: Candidate,
    contract: ConstructionContract,
    proposal: VignetteProposal,
) -> dict[str, object]:
    concerns: list[str] = []

    stage1 = _norm(proposal.stage_1_context)
    stage2 = _norm(proposal.stage_2_update)
    nonduplicative_stage2 = bool(stage2) and SequenceMatcher(None, stage1, stage2).ratio() < 0.85
    if not nonduplicative_stage2:
        concerns.append("Stage 2 is empty or too similar to Stage 1")

    no_answer_cues = not (
        _contains_answer_cue(proposal.stage_1_context, proposal.expected_initial_recommendation)
        or _contains_answer_cue(proposal.stage_2_update, proposal.expected_revised_recommendation)
    )
    if not no_answer_cues:
        concerns.append("stage context appears to contain an exact expected-answer cue")

    source_ids_match = set(proposal.source_ids) == {
        contract.baseline_source_id,
        contract.modifier_source_id,
    }
    if not source_ids_match:
        concerns.append("proposal source_ids do not match the locked construction contract")

    provenance_ids = {row.source_id for row in proposal.source_provenance}
    provenance_complete = provenance_ids == set(proposal.source_ids)
    if not provenance_complete:
        concerns.append("source provenance does not cover both locked route sources")

    contract_locked = (
        proposal.contract_uid == contract.contract_uid
        and proposal.candidate_uid == candidate.candidate_uid
        and proposal.decision_domain == contract.decision_domain
        and proposal.clinical_question == contract.decision_question
        and proposal.evidence_arm == contract.evidence_arm
        and proposal.expected_update == contract.expected_update
        and proposal.affected_decision_components == contract.affected_decision_components
    )
    if not contract_locked:
        concerns.append("proposal changed one or more immutable construction-contract fields")

    return {
        "passed": not concerns,
        "nonduplicative_stage2": nonduplicative_stage2,
        "no_answer_cues": no_answer_cues,
        "source_ids_match": source_ids_match,
        "provenance_complete": provenance_complete,
        "contract_locked": contract_locked,
        "concerns": concerns,
    }
