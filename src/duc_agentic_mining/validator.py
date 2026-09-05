from __future__ import annotations

import json

from .config import SourcePolicyConfig, ValidationConfig
from .corpus import CorpusStore
from .llm import OpenAIRoleClient
from .models import Candidate, CandidateValidation, Gate
from .prompts import VALIDATOR_SYSTEM
from .source_policy import assess_source_pair


async def validate_candidate(
    candidate: Candidate,
    corpus: CorpusStore,
    client: OpenAIRoleClient,
    cfg: ValidationConfig,
    source_policy_cfg: SourcePolicyConfig,
    extra_concerns: list[str] | None = None,
) -> CandidateValidation:
    baseline = corpus.get(candidate.baseline_source_id)
    modifier = corpus.get(candidate.modifier_source_id)
    if not baseline or not modifier:
        raise ValueError("candidate references missing source record")

    policy = assess_source_pair(
        baseline,
        modifier,
        candidate.proposed_arm,
        source_policy_cfg,
    )
    payload = {
        "candidate": candidate.model_dump(mode="json"),
        "baseline_source": baseline.model_dump(mode="json"),
        "modifier_source": modifier.model_dump(mode="json"),
        "deterministic_source_policy": policy.to_dict(),
        "extra_review_concerns": extra_concerns or [],
    }
    text = json.dumps(payload, ensure_ascii=False)
    if len(text) > cfg.max_input_chars:
        each = max(5000, (cfg.max_input_chars - 20_000) // 2)
        payload["baseline_source"]["text"] = payload["baseline_source"]["text"][:each]
        payload["modifier_source"]["text"] = payload["modifier_source"]["text"][:each]
    result = await client.structured(
        VALIDATOR_SYSTEM,
        json.dumps(payload, ensure_ascii=False),
        CandidateValidation,
        "candidate_validation",
    )
    value = result.value
    assert isinstance(value, CandidateValidation)
    value.candidate_uid = candidate.candidate_uid

    concerns = list(dict.fromkeys([*value.concerns, *policy.concerns]))
    value.concerns = concerns
    if not policy.passed:
        rationale = "; ".join(policy.concerns) or "deterministic source policy failed"
        value.source_policy = Gate(passed=False, rationale=rationale)
        value.promote = False
    return value
