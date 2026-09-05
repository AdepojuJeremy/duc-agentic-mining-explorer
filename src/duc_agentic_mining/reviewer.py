from __future__ import annotations

import json

from .corpus import CorpusStore
from .llm import OpenAIRoleClient
from .models import Candidate, CandidateValidation, ProposalReview, VignetteProposal
from .prompts import REVIEWER_SYSTEM


async def review_proposal(
    candidate: Candidate,
    validation: CandidateValidation,
    proposal: VignetteProposal,
    corpus: CorpusStore,
    client: OpenAIRoleClient,
) -> ProposalReview:
    baseline = corpus.get(candidate.baseline_source_id)
    modifier = corpus.get(candidate.modifier_source_id)
    if not baseline or not modifier:
        raise ValueError("proposal references missing source")
    payload = {
        "candidate": candidate.model_dump(mode="json"),
        "validation": validation.model_dump(mode="json"),
        "proposal": proposal.model_dump(mode="json"),
        "baseline_source": baseline.model_dump(mode="json"),
        "modifier_source": modifier.model_dump(mode="json"),
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
    return value
