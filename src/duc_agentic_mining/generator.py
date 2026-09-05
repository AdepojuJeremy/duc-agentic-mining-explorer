from __future__ import annotations

import json

from .config import GenerationConfig
from .contracts import source_provenance
from .corpus import CorpusStore
from .llm import OpenAIRoleClient
from .models import Candidate, ConstructionContract, VignetteDraft, VignetteProposal
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
        VignetteDraft,
        "vignette_draft",
    )
    draft = result.value
    assert isinstance(draft, VignetteDraft)

    return VignetteProposal(
        candidate_uid=candidate.candidate_uid,
        contract_uid=contract.contract_uid,
        constructible=draft.constructible,
        unconstructible_reason=draft.unconstructible_reason,
        decision_domain=contract.decision_domain,
        clinical_question=contract.decision_question,
        stage_1_context=draft.stage_1_context,
        stage_2_update=draft.stage_2_update,
        expected_initial_recommendation=draft.expected_initial_recommendation,
        expected_revised_recommendation=draft.expected_revised_recommendation,
        evidence_arm=contract.evidence_arm,
        expected_update=contract.expected_update,
        affected_decision_components=list(contract.affected_decision_components),
        confidence_direction=draft.confidence_direction,
        warrant=draft.warrant,
        scenario_premises=draft.scenario_premises,
        claim_source_map=draft.claim_source_map,
        source_ids=[contract.baseline_source_id, contract.modifier_source_id],
        source_provenance=[source_provenance(baseline), source_provenance(modifier)],
        unresolved_questions=draft.unresolved_questions,
        draft_number=draft_number,
    )
