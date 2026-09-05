from __future__ import annotations

import re

from .models import VignetteProposal


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def jaccard(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def proposal_signature(p: VignetteProposal) -> str:
    return " ".join(
        [p.clinical_question, p.expected_initial_recommendation, p.expected_revised_recommendation]
    )


def is_near_duplicate(
    candidate: VignetteProposal,
    accepted: list[VignetteProposal],
    threshold: float,
) -> bool:
    sig = proposal_signature(candidate)
    for other in accepted:
        if set(candidate.source_ids) == set(other.source_ids):
            return True
        if jaccard(sig, proposal_signature(other)) >= threshold:
            return True
    return False
