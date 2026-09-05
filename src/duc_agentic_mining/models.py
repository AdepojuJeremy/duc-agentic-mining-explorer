from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DecisionDomain = Literal[
    "diagnosis",
    "treatment_selection",
    "triage_urgency",
    "medication_safety",
    "public_health_advice",
    "patient_counselling",
]
FormalArm = Literal["contradictory", "complicating", "uncertainty_inducing"]
Arm = Literal["contradictory", "complicating", "uncertainty_inducing", "no_conflict_control"]
UpdateClass = Literal["maintain", "revise", "weaken", "strengthen", "abstain"]
ConfidenceDirection = Literal["increase", "decrease", "maintain", "case_dependent"]


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def stable_id(prefix: str, *parts: str) -> str:
    raw = "\x1f".join(p.strip().lower() for p in parts if p is not None)
    return f"{prefix}_{sha256(raw.encode('utf-8')).hexdigest()[:16]}"


class SourceRecord(BaseModel):
    model_config = ConfigDict(extra="allow")
    source_id: str
    title: str = ""
    text: str
    source: str = ""
    url: str | None = None
    date: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Candidate(BaseModel):
    candidate_uid: str
    round_id: str
    anchor_source_id: str
    decision_domain: DecisionDomain
    decision_question: str
    baseline_source_id: str
    modifier_source_id: str
    baseline_evidence_span: str
    modifier_evidence_span: str
    relationship_summary: str
    proposed_arm: Arm
    expected_update: UpdateClass
    rationale: str
    concerns: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def distinct_sources(self) -> Candidate:
        if self.baseline_source_id == self.modifier_source_id:
            raise ValueError("baseline_source_id and modifier_source_id must be different")
        return self


class Gate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    passed: bool
    rationale: str


class CandidateValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_uid: str
    same_decision: Gate
    source_supported: Gate
    stage1_defensible: Gate
    genuine_update_pressure: Gate
    applicability_coherent: Gate
    arm_and_update_coherent: Gate
    source_policy: Gate
    promote: bool
    normalized_domain: DecisionDomain
    normalized_arm: Arm
    normalized_update: UpdateClass
    affected_decision_components: list[str]
    allowed_scenario_premises: list[str]
    concerns: list[str]

    @model_validator(mode="after")
    def promotion_matches_gates(self) -> CandidateValidation:
        gates = [
            self.same_decision,
            self.source_supported,
            self.stage1_defensible,
            self.genuine_update_pressure,
            self.applicability_coherent,
            self.arm_and_update_coherent,
            self.source_policy,
        ]
        if self.promote and not all(g.passed for g in gates):
            raise ValueError("promote=true requires all validation gates to pass")
        if self.promote and not self.affected_decision_components:
            raise ValueError("promoted routes require affected_decision_components")
        return self


class SourceProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str
    canonical_organization: str | None
    authority_tier: int | None
    source_kind: Literal[
        "guideline_authority",
        "structured_knowledge_base",
        "primary_literature",
        "secondary_clinical",
        "patient_facing_fallback",
        "unknown",
    ]
    recommendation_authority: bool
    redistribution_status: Literal["redistributable", "restricted_or_check", "unknown"]
    source_status: Literal["current", "versioned", "stale_or_superseded", "unknown"]
    freshness_verified: bool
    seed_collection: str | None
    title: str
    source: str
    url: str | None
    date: str | None


class ConstructionContract(BaseModel):
    contract_uid: str
    candidate_uid: str
    decision_domain: DecisionDomain
    decision_question: str
    baseline_source_id: str
    modifier_source_id: str
    baseline_evidence_span: str
    modifier_evidence_span: str
    evidence_arm: Arm
    expected_update: UpdateClass
    affected_decision_components: list[str]
    allowed_scenario_premises: list[str]
    source_provenance: list[SourceProvenance]
    created_at: str = Field(default_factory=utc_now)


class ScenarioPremise(BaseModel):
    model_config = ConfigDict(extra="forbid")
    premise_id: str
    stage: Literal["stage_1", "stage_2"]
    text: str
    status: Literal["source_grounded", "constructed_requires_review"]


class ClaimSourceMapEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim: str
    source_ids: list[str]
    support: Literal["direct", "inference", "scenario_premise"]


class VignetteDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    constructible: bool
    unconstructible_reason: str | None
    stage_1_context: str
    stage_2_update: str
    expected_initial_recommendation: str
    expected_revised_recommendation: str
    confidence_direction: ConfidenceDirection
    warrant: str
    scenario_premises: list[ScenarioPremise]
    claim_source_map: list[ClaimSourceMapEntry]
    unresolved_questions: list[str]


class VignetteProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_uid: str
    contract_uid: str
    constructible: bool
    unconstructible_reason: str | None
    decision_domain: DecisionDomain
    clinical_question: str
    stage_1_context: str
    stage_2_update: str
    expected_initial_recommendation: str
    expected_revised_recommendation: str
    evidence_arm: Arm
    expected_update: UpdateClass
    affected_decision_components: list[str]
    confidence_direction: ConfidenceDirection
    warrant: str
    scenario_premises: list[ScenarioPremise]
    claim_source_map: list[ClaimSourceMapEntry]
    source_ids: list[str]
    source_provenance: list[SourceProvenance]
    unresolved_questions: list[str]
    draft_number: int


class GroundingGate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    passed: bool
    rationale: str


class ProposalReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_uid: str
    source_fidelity: GroundingGate
    same_decision_preserved: GroundingGate
    stage_separation: GroundingGate
    no_unsupported_patient_facts: GroundingGate
    scenario_premises_authorized: GroundingGate
    no_answer_cues: GroundingGate
    nonduplicative_stage2: GroundingGate
    recommendation_grounding: GroundingGate
    affected_components_consistent: GroundingGate
    arm_and_update_consistency: GroundingGate
    source_policy_consistent: GroundingGate
    provenance_complete: GroundingGate
    overall_pass: bool
    repairable: bool
    needs_candidate_revalidation: bool
    repair_instructions: list[str]
    concerns: list[str]


class ToolEvent(BaseModel):
    timestamp: str = Field(default_factory=utc_now)
    kind: Literal["model_call", "tool_call", "tool_result", "round_end", "error"]
    name: str
    payload: dict[str, Any] = Field(default_factory=dict)


class RoleUsage(BaseModel):
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    errors: int = 0


class RunMetrics(BaseModel):
    run_id: str
    started_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
    elapsed_seconds: float = 0.0
    exploration_rounds_started: int = 0
    exploration_rounds_completed: int = 0
    searches: int = 0
    opens: int = 0
    candidates_recorded: int = 0
    candidates_unique: int = 0
    validations_completed: int = 0
    candidates_promoted: int = 0
    construction_contracts: int = 0
    proposals_generated: int = 0
    proposal_reviews_completed: int = 0
    proposals_passed: int = 0
    repairs_attempted: int = 0
    passed_by_domain: dict[str, int] = Field(default_factory=dict)
    passed_by_arm: dict[str, int] = Field(default_factory=dict)
    passed_by_cell: dict[str, int] = Field(default_factory=dict)
    role_usage: dict[str, RoleUsage] = Field(default_factory=dict)

    def usage_for(self, role: str) -> RoleUsage:
        if role not in self.role_usage:
            self.role_usage[role] = RoleUsage()
        return self.role_usage[role]
