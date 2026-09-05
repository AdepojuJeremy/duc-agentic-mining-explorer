from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Literal

from .config import SourcePolicyConfig
from .models import SourceRecord

SourceKind = Literal[
    "guideline_authority",
    "structured_knowledge_base",
    "primary_literature",
    "secondary_clinical",
    "patient_facing_fallback",
    "unknown",
]
RedistributionStatus = Literal["redistributable", "restricted_or_check", "unknown"]
SourceStatus = Literal["current", "versioned", "stale_or_superseded", "unknown"]


@dataclass(frozen=True)
class SourceRule:
    canonical: str
    tier: int
    kind: SourceKind
    recommendation_authority: bool
    redistribution: RedistributionStatus
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class SourcePolicyAssessment:
    canonical_organization: str | None
    authority_tier: int | None
    source_kind: SourceKind
    recommendation_authority: bool
    redistribution_status: RedistributionStatus
    source_status: SourceStatus
    freshness_verified: bool
    seed_collection: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PairPolicyAssessment:
    passed: bool
    baseline: SourcePolicyAssessment
    modifier: SourcePolicyAssessment
    concerns: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "baseline": self.baseline.to_dict(),
            "modifier": self.modifier.to_dict(),
            "concerns": list(self.concerns),
        }


RULES: tuple[SourceRule, ...] = (
    SourceRule(
        "NICE",
        1,
        "guideline_authority",
        True,
        "redistributable",
        ("nice.org.uk", "national institute for health and care excellence", "nice"),
    ),
    SourceRule(
        "WHO",
        1,
        "guideline_authority",
        True,
        "redistributable",
        ("who.int", "world health organization", "who"),
    ),
    SourceRule(
        "CDC",
        1,
        "guideline_authority",
        True,
        "redistributable",
        ("cdc.gov", "centers for disease control and prevention", "cdc"),
    ),
    SourceRule(
        "USPSTF",
        1,
        "guideline_authority",
        True,
        "unknown",
        (
            "uspstf",
            "us preventive services task force",
            "u.s. preventive services task force",
        ),
    ),
    SourceRule(
        "IDSA",
        1,
        "guideline_authority",
        True,
        "restricted_or_check",
        ("idsociety.org", "infectious diseases society of america", "idsa"),
    ),
    SourceRule(
        "Ontario Health / Cancer Care Ontario",
        1,
        "guideline_authority",
        True,
        "redistributable",
        ("cancercareontario.ca", "cancer care ontario", "ontario health"),
    ),
    SourceRule(
        "ICRC",
        1,
        "guideline_authority",
        True,
        "redistributable",
        ("icrc.org", "international committee of the red cross", "icrc"),
    ),
    SourceRule("UMLS", 2, "structured_knowledge_base", False, "restricted_or_check", ("umls",)),
    SourceRule(
        "SNOMED CT",
        2,
        "structured_knowledge_base",
        False,
        "restricted_or_check",
        ("snomed ct", "snomed"),
    ),
    SourceRule("RxNorm", 2, "structured_knowledge_base", False, "unknown", ("rxnorm",)),
    SourceRule(
        "DrugBank",
        2,
        "structured_knowledge_base",
        False,
        "restricted_or_check",
        ("drugbank",),
    ),
    SourceRule(
        "PubMed / PMC",
        3,
        "primary_literature",
        False,
        "unknown",
        ("pubmed", "pubmed.ncbi.nlm.nih.gov", "pmc.ncbi.nlm.nih.gov", "pubmed central"),
    ),
    SourceRule(
        "AAFP",
        4,
        "secondary_clinical",
        True,
        "restricted_or_check",
        ("aafp.org", "american academy of family physicians", "aafp"),
    ),
    SourceRule(
        "Canadian Paediatric Society",
        4,
        "secondary_clinical",
        True,
        "restricted_or_check",
        ("cps.ca", "canadian paediatric society", "canadian pediatric society"),
    ),
    SourceRule(
        "GuidelineCentral",
        4,
        "secondary_clinical",
        True,
        "restricted_or_check",
        ("guidelinecentral", "guideline central"),
    ),
    SourceRule(
        "MAGIC",
        4,
        "secondary_clinical",
        True,
        "restricted_or_check",
        ("magicapp", "magic evidence ecosystem foundation", "making grade the irresistible choice"),
    ),
    SourceRule(
        "Royal Children's Hospital Melbourne",
        4,
        "secondary_clinical",
        True,
        "restricted_or_check",
        ("rch.org.au", "royal children's hospital melbourne"),
    ),
    SourceRule("StatPearls", 4, "secondary_clinical", False, "unknown", ("statpearls",)),
    SourceRule(
        "Drugs.com",
        4,
        "secondary_clinical",
        False,
        "restricted_or_check",
        ("drugs.com",),
    ),
    SourceRule(
        "Canadian Medical Association",
        4,
        "secondary_clinical",
        True,
        "redistributable",
        ("canadian medical association", "cma.ca"),
    ),
    SourceRule(
        "SPOR",
        4,
        "secondary_clinical",
        False,
        "redistributable",
        ("strategy for patient-oriented research", "spor"),
    ),
    SourceRule(
        "Mayo Clinic",
        5,
        "patient_facing_fallback",
        False,
        "restricted_or_check",
        ("mayoclinic.org", "mayo clinic"),
    ),
    SourceRule(
        "MedlinePlus",
        5,
        "patient_facing_fallback",
        False,
        "redistributable",
        ("medlineplus", "medlineplus.gov"),
    ),
    SourceRule(
        "WikiDoc",
        5,
        "patient_facing_fallback",
        False,
        "redistributable",
        ("wikidoc", "wikidoc.org"),
    ),
)


def _flatten_metadata(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(f"{k} {_flatten_metadata(v)}" for k, v in value.items())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_flatten_metadata(v) for v in value)
    return str(value)


def _matches(alias: str, haystack: str) -> bool:
    alias = alias.lower().strip()
    if not alias:
        return False
    if len(alias) <= 5 and alias.replace(".", "").isalnum():
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", haystack))
    return alias in haystack


def classify_source(record: SourceRecord) -> SourcePolicyAssessment:
    metadata_text = _flatten_metadata(record.metadata)
    haystack = " ".join(
        x for x in (record.source, record.title, record.url or "", metadata_text) if x
    ).lower()
    matched = next((rule for rule in RULES if any(_matches(alias, haystack) for alias in rule.aliases)), None)

    explicit_status = str(
        record.metadata.get("source_status")
        or record.metadata.get("guideline_status")
        or record.metadata.get("status")
        or ""
    ).lower()
    freshness_verified = bool(
        record.metadata.get("freshness_verified")
        or record.metadata.get("verified_current")
        or record.metadata.get("primary_source_verified")
    )
    if any(word in explicit_status for word in ("withdrawn", "retired", "superseded", "obsolete", "stale")):
        source_status: SourceStatus = "stale_or_superseded"
    elif any(word in explicit_status for word in ("current", "active", "updated")):
        source_status = "current"
    elif record.date:
        source_status = "versioned"
    else:
        source_status = "unknown"

    origin = str(record.metadata.get("origin") or "").lower()
    seed_collection = None
    if "meditron" in haystack or "epfl-llm-guidelines" in origin or "open_guidelines" in origin:
        seed_collection = "Meditron Guidelines Collection"

    return SourcePolicyAssessment(
        canonical_organization=matched.canonical if matched else None,
        authority_tier=matched.tier if matched else None,
        source_kind=matched.kind if matched else "unknown",
        recommendation_authority=matched.recommendation_authority if matched else False,
        redistribution_status=matched.redistribution if matched else "unknown",
        source_status=source_status,
        freshness_verified=freshness_verified,
        seed_collection=seed_collection,
    )


def assess_source_pair(
    baseline: SourceRecord,
    modifier: SourceRecord,
    proposed_arm: str,
    cfg: SourcePolicyConfig,
) -> PairPolicyAssessment:
    b = classify_source(baseline)
    m = classify_source(modifier)
    concerns: list[str] = []
    passed = True

    if not cfg.enabled:
        return PairPolicyAssessment(True, b, m, ())

    if cfg.require_recommendation_authority_baseline and not b.recommendation_authority:
        passed = False
        concerns.append("baseline source is not classified as recommendation authority")
    if cfg.reject_tier2_as_decision_authority and b.authority_tier == 2:
        passed = False
        concerns.append("Tier-2 knowledge base cannot serve as the final Stage-1 decision authority")
    if cfg.reject_tier5_as_decision_authority and b.authority_tier == 5:
        passed = False
        concerns.append("Tier-5 patient-facing/fallback source cannot serve as final decision authority")
    if b.source_status == "stale_or_superseded" or m.source_status == "stale_or_superseded":
        passed = False
        concerns.append("route contains a source explicitly marked stale, retired, or superseded")
    if cfg.require_known_currentness_for_contradictory and proposed_arm == "contradictory":
        if b.source_status == "unknown" or m.source_status == "unknown":
            passed = False
            concerns.append("contradictory route lacks known/versioned source status")
    if cfg.warn_on_restricted_redistribution:
        if b.redistribution_status == "restricted_or_check" or m.redistribution_status == "restricted_or_check":
            concerns.append("one or more sources require redistribution/licensing review")
    if b.seed_collection or m.seed_collection:
        concerns.append("Meditron is treated as a seed index; primary-source freshness should be checked before gold use")

    return PairPolicyAssessment(passed, b, m, tuple(concerns))
