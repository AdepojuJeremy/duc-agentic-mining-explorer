from __future__ import annotations

import json

from .config import GenerationConfig
from .corpus import CorpusStore
from .llm import OpenAIRoleClient
from .models import Candidate, CandidateValidation, VignetteProposal
from .prompts import GENERATOR_SYSTEM


async def generate_vignette(
    candidate: Candidate,
    validation: CandidateValidation,
    corpus: CorpusStore,
    client: OpenAIRoleClient,
    cfg: GenerationConfig,
    draft_number: int,
    repair_instructions: list[str] | None = None,
) -> VignetteProposal:
    baseline = corpus.get(candidate.baseline_source_id)
    modifier = corpus.get(candidate.modifier_source_id)
    if not baseline or not modifier:
        raise ValueError("candidate references missing source")
    baseline_data = baseline.model_dump(mode="json")
    modifier_data = modifier.model_dump(mode="json")
    baseline_data["text"] = baseline_data["text"][: cfg.max_source_chars_each]
    modifier_data["text"] = modifier_data["text"][: cfg.max_source_chars_each]
    payload = {
        "candidate": candidate.model_dump(mode="json"),
        "validation": validation.model_dump(mode="json"),
        "baseline_source": baseline_data,
        "modifier_source": modifier_data,
        "draft_number": draft_number,
        "repair_instructions": repair_instructions or [],
    }
    result = await client.structured(
        GENERATOR_SYSTEM,
        json.dumps(payload, ensure_ascii=False),
        VignetteProposal,
        "vignette_proposal",
    )
    value = result.value
    assert isinstance(value, VignetteProposal)
    value.candidate_uid = candidate.candidate_uid
    value.draft_number = draft_number
    value.evidence_arm = validation.normalized_arm
    value.expected_update = validation.normalized_update
    value.source_ids = [candidate.baseline_source_id, candidate.modifier_source_id]
    return value
