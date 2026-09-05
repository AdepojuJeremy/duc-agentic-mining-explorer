from __future__ import annotations

import re
from difflib import SequenceMatcher

from .models import Candidate, VignetteProposal


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
        candidate.baseline_source_id,
        candidate.modifier_source_id,
    }
    if not source_ids_match:
        concerns.append("proposal source_ids do not match the locked candidate route")

    provenance_ids = {row.source_id for row in proposal.source_provenance}
    provenance_complete = provenance_ids == set(proposal.source_ids)
    if not provenance_complete:
        concerns.append("source provenance does not cover both locked route sources")

    affected_components_present = bool(
        [x for x in proposal.affected_decision_components if x.strip()]
    )
    if not affected_components_present:
        concerns.append("affected_decision_components is empty")

    domain_locked = proposal.decision_domain == candidate.decision_domain
    if not domain_locked:
        concerns.append("proposal changed the locked decision domain")

    return {
        "passed": not concerns,
        "nonduplicative_stage2": nonduplicative_stage2,
        "no_answer_cues": no_answer_cues,
        "source_ids_match": source_ids_match,
        "provenance_complete": provenance_complete,
        "affected_components_present": affected_components_present,
        "domain_locked": domain_locked,
        "concerns": concerns,
    }
