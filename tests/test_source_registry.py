from duc_agentic_mining.models import SourceRecord
from duc_agentic_mining.source_policy import classify_source
from duc_agentic_mining.source_registry import (
    recommendation_authorities_for_domain,
    source_by_name,
    sources_for_domain,
)


def test_nice_is_licensed_authority_for_all_domains():
    nice = source_by_name("NICE")
    assert nice is not None
    assert nice.access_mode == "licensed_api"
    assert nice.api_key_env == "NICE_API_KEY"
    assert nice.recommendation_authority is True
    assert len(nice.domains) == 6


def test_medication_safety_has_regulatory_authorities():
    names = {source.canonical for source in sources_for_domain("medication_safety")}
    assert {"NICE", "FDA", "MHRA", "EMA", "BNF", "ISMP"} <= names


def test_diagnosis_has_specialty_authorities():
    names = set(recommendation_authorities_for_domain("diagnosis"))
    assert {"NICE", "WHO", "CDC", "IDSA", "ACR", "ACC / AHA", "ASCO", "ACOG", "AAP", "KDIGO"} <= names


def test_triage_has_emergency_authorities():
    names = set(recommendation_authorities_for_domain("triage_urgency"))
    assert {"NICE", "WHO", "WHO / ICRC emergency care", "ACEP", "Resuscitation Council UK / ILCOR"} <= names


def test_new_authority_is_classified_by_source_policy():
    record = SourceRecord(
        source_id="fda-1",
        source="FDA",
        title="Drug Safety Communication",
        text="Safety recommendation",
        url="https://www.fda.gov/drugs/example",
        date="2026-09-01",
    )
    policy = classify_source(record)
    assert policy.canonical_organization == "FDA"
    assert policy.authority_tier == 1
    assert policy.recommendation_authority is True


def test_meditron_is_seed_not_recommendation_authority():
    source = source_by_name("Meditron Guidelines Collection")
    assert source is not None
    assert source.access_mode == "download_seed"
    assert source.recommendation_authority is False
