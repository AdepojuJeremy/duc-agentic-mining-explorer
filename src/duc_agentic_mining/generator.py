from __future__ import annotations

import json

from .config import GenerationConfig
from .contracts import source_provenance
from .corpus import CorpusStore
from .llm import OpenAIRoleClient
from .models import Candidate, ConstructionContract, VignetteProposal
from .prompts import GENERATOR_SYSTEM


async def generate_vignette(
    candidate: Candidate,
    contract: ConstructionContract,
    corpus: CorpusStore,
    client: OpenAIRoleClient,
    cfg: GenerationConfig,
    draft_number: int,
    repair_instructions: list[str] | None = None,
) -> VignetteProposal:
    baseline = corpus.get(contract.baseline_source_id)
    modifier = corpus.get(contract.modifier_source_id)
    if not baseline or not modifier:
        raise ValueError("construction contract references missing source")
    baseline_data = baseline.model_dump(mode="json")
    modifier_data = modifier.model_dump(mode="json")
    baseline_data["text"] = baseline_data["text"][: cfg.max_source_chars_each]
    modifier_data["text"] = modifier_data["text"][: cfg.max_source_chars_each]
    payload = {
        "construction_contract": contract.model_dump(mode="json"),
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

    # Host-owned contract fields are copied back deterministically rather than
    # trusting the model to reproduce immutable construction metadata.
    value.candidate_uid = candidate.candidate_uid
    value.contract_uid = contract.contract_uid
    value.draft_number = draft_number
    value.decision_domain = contract.decision_domain
    value.clinical_question = contract.decision_question
    value.evidence_arm = contract.evidence_arm
    value.expected_update = contract.expected_update
    value.affected_decision_components = list(contract.affected_decision_components)
    value.source_ids = [contract.baseline_source_id, contract.modifier_source_id]
    value.source_provenance = [source_provenance(baseline), source_provenance(modifier)]
    return value
