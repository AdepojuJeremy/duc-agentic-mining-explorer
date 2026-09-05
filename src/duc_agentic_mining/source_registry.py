from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .models import DecisionDomain

AccessMode = Literal[
    "download_seed",
    "official_api",
    "licensed_api",
    "ncbi_eutils",
    "controlled_web",
    "structured_api",
]


@dataclass(frozen=True)
class AuthoritativeSource:
    canonical: str
    domains: tuple[DecisionDomain, ...]
    access_mode: AccessMode
    tier: int
    recommendation_authority: bool
    aliases: tuple[str, ...]
    api_key_env: str | None = None
    notes: str = ""


ALL_DOMAINS: tuple[DecisionDomain, ...] = (
    "diagnosis",
    "treatment_selection",
    "triage_urgency",
    "medication_safety",
    "public_health_advice",
    "patient_counselling",
)


SOURCES: tuple[AuthoritativeSource, ...] = (
    AuthoritativeSource(
        "NICE",
        ALL_DOMAINS,
        "licensed_api",
        1,
        True,
        ("nice.org.uk", "national institute for health and care excellence", "nice"),
        api_key_env="NICE_API_KEY",
        notes="Use the licensed NICE syndication API; do not commit the API key or licensed content.",
    ),
    AuthoritativeSource(
        "WHO",
        ALL_DOMAINS,
        "official_api",
        1,
        True,
        ("who.int", "world health organization", "who"),
        notes="Prefer current WHO guideline/publication records and retain publication date/version metadata.",
    ),
    AuthoritativeSource(
        "CDC",
        (
            "diagnosis",
            "treatment_selection",
            "public_health_advice",
            "patient_counselling",
        ),
        "official_api",
        1,
        True,
        ("cdc.gov", "centers for disease control and prevention", "cdc"),
    ),
    AuthoritativeSource(
        "USPSTF",
        ("diagnosis", "public_health_advice", "patient_counselling"),
        "controlled_web",
        1,
        True,
        ("uspstf", "us preventive services task force", "u.s. preventive services task force"),
    ),
    AuthoritativeSource(
        "IDSA",
        ("diagnosis", "treatment_selection", "medication_safety"),
        "controlled_web",
        1,
        True,
        ("idsociety.org", "infectious diseases society of america", "idsa"),
    ),
    AuthoritativeSource(
        "Ontario Health / Cancer Care Ontario",
        ("diagnosis", "treatment_selection", "patient_counselling"),
        "controlled_web",
        1,
        True,
        ("cancercareontario.ca", "cancer care ontario", "ontario health"),
    ),
    AuthoritativeSource(
        "WHO / ICRC emergency care",
        ("triage_urgency", "treatment_selection"),
        "controlled_web",
        1,
        True,
        ("interagency integrated triage tool", "basic emergency care", "icrc.org"),
    ),
    AuthoritativeSource(
        "ACEP",
        ("triage_urgency", "diagnosis", "treatment_selection"),
        "controlled_web",
        1,
        True,
        ("acep.org", "american college of emergency physicians", "acep"),
    ),
    AuthoritativeSource(
        "Resuscitation Council UK / ILCOR",
        ("triage_urgency", "treatment_selection"),
        "controlled_web",
        1,
        True,
        ("resus.org.uk", "resuscitation council uk", "ilcor"),
    ),
    AuthoritativeSource(
        "FDA",
        ("medication_safety", "treatment_selection"),
        "official_api",
        1,
        True,
        ("fda.gov", "food and drug administration", "fda"),
        notes="Use official drug-safety communications, labeling and regulatory safety records where applicable.",
    ),
    AuthoritativeSource(
        "MHRA",
        ("medication_safety", "treatment_selection"),
        "controlled_web",
        1,
        True,
        ("mhra", "medicines and healthcare products regulatory agency", "drug safety update"),
    ),
    AuthoritativeSource(
        "EMA",
        ("medication_safety", "treatment_selection"),
        "controlled_web",
        1,
        True,
        ("ema.europa.eu", "european medicines agency", "ema"),
    ),
    AuthoritativeSource(
        "BNF",
        ("medication_safety", "treatment_selection"),
        "licensed_api",
        1,
        True,
        ("bnf", "british national formulary"),
        api_key_env="BNF_API_KEY",
        notes="Only enable when the applicable BNF syndication/API licence is available.",
    ),
    AuthoritativeSource(
        "ISMP",
        ("medication_safety",),
        "controlled_web",
        1,
        True,
        ("ismp.org", "institute for safe medication practices", "ismp"),
    ),
    AuthoritativeSource(
        "ECDC",
        ("diagnosis", "public_health_advice", "treatment_selection"),
        "controlled_web",
        1,
        True,
        ("ecdc.europa.eu", "european centre for disease prevention and control", "ecdc"),
    ),
    AuthoritativeSource(
        "UKHSA",
        ("diagnosis", "public_health_advice"),
        "controlled_web",
        1,
        True,
        ("ukhsa", "uk health security agency"),
    ),
    AuthoritativeSource(
        "Africa CDC",
        ("diagnosis", "public_health_advice"),
        "controlled_web",
        1,
        True,
        ("africacdc.org", "africa cdc", "africa centres for disease control and prevention"),
    ),
    AuthoritativeSource(
        "ACR",
        ("diagnosis", "treatment_selection"),
        "controlled_web",
        1,
        True,
        ("acr.org", "american college of radiology", "appropriateness criteria"),
    ),
    AuthoritativeSource(
        "ACC / AHA",
        ("diagnosis", "treatment_selection", "patient_counselling"),
        "controlled_web",
        1,
        True,
        ("acc.org", "heart.org", "american college of cardiology", "american heart association"),
    ),
    AuthoritativeSource(
        "ASCO",
        ("diagnosis", "treatment_selection", "patient_counselling"),
        "controlled_web",
        1,
        True,
        ("asco.org", "american society of clinical oncology", "asco"),
    ),
    AuthoritativeSource(
        "ACOG",
        ("diagnosis", "treatment_selection", "patient_counselling"),
        "controlled_web",
        1,
        True,
        ("acog.org", "american college of obstetricians and gynecologists", "acog"),
    ),
    AuthoritativeSource(
        "AAP",
        ("diagnosis", "treatment_selection", "triage_urgency", "patient_counselling"),
        "controlled_web",
        1,
        True,
        ("aap.org", "american academy of pediatrics", "aap"),
    ),
    AuthoritativeSource(
        "KDIGO",
        ("diagnosis", "treatment_selection", "patient_counselling"),
        "controlled_web",
        1,
        True,
        ("kdigo.org", "kidney disease improving global outcomes", "kdigo"),
    ),
    AuthoritativeSource(
        "GINA",
        ("diagnosis", "treatment_selection", "patient_counselling"),
        "controlled_web",
        1,
        True,
        ("ginasthma.org", "global initiative for asthma", "gina"),
    ),
    AuthoritativeSource(
        "GOLD",
        ("diagnosis", "treatment_selection", "patient_counselling"),
        "controlled_web",
        1,
        True,
        ("goldcopd.org", "global initiative for chronic obstructive lung disease", "gold"),
    ),
    AuthoritativeSource(
        "PubMed / PMC",
        ALL_DOMAINS,
        "ncbi_eutils",
        3,
        False,
        ("pubmed", "pubmed.ncbi.nlm.nih.gov", "pmc.ncbi.nlm.nih.gov", "pubmed central"),
        notes="Evidence support and recency checks; a study is not automatically a guideline recommendation.",
    ),
    AuthoritativeSource(
        "RxNorm",
        ("medication_safety", "treatment_selection"),
        "structured_api",
        2,
        False,
        ("rxnorm",),
    ),
    AuthoritativeSource(
        "UMLS / SNOMED CT",
        ALL_DOMAINS,
        "structured_api",
        2,
        False,
        ("umls", "snomed", "snomed ct"),
        notes="Terminology/entity normalization only; not final recommendation authority.",
    ),
    AuthoritativeSource(
        "Meditron Guidelines Collection",
        ALL_DOMAINS,
        "download_seed",
        1,
        False,
        ("meditron", "epfl-llm-guidelines", "open_guidelines"),
        notes="High-coverage discovery seed. Resolve the underlying organization and refresh primary guidance before gold use when required.",
    ),
)


def sources_for_domain(domain: DecisionDomain) -> tuple[AuthoritativeSource, ...]:
    return tuple(source for source in SOURCES if domain in source.domains)


def recommendation_authorities_for_domain(domain: DecisionDomain) -> tuple[str, ...]:
    return tuple(
        source.canonical
        for source in sources_for_domain(domain)
        if source.recommendation_authority and source.tier == 1
    )


def source_by_name(name: str) -> AuthoritativeSource | None:
    needle = name.strip().lower()
    for source in SOURCES:
        if source.canonical.lower() == needle or any(alias.lower() == needle for alias in source.aliases):
            return source
    return None
