from pathlib import Path

from duc_agentic_mining.catalogue_acquisition import (
    CatalogueAcquisitionConfig,
    CatalogueJobConfig,
)
from duc_agentic_mining.specialty_overrides import apply_specialty_catalogue_overrides


def _job(tmp_path: Path, name: str) -> CatalogueJobConfig:
    return CatalogueJobConfig(
        canonical_source=name,
        output=tmp_path / f"{name}.jsonl",
        seed_urls=["https://example.org/catalog"],
        allowed_hosts=["example.org"],
    )


def test_acr_override_uses_public_gravitas_html_narratives(tmp_path: Path):
    cfg = CatalogueAcquisitionConfig(
        raw_root=tmp_path,
        manifest_path=tmp_path / "manifest.jsonl",
        catalogues={"acr": _job(tmp_path, "ACR")},
    )
    result = apply_specialty_catalogue_overrides(cfg)
    acr = result.catalogues["acr"]
    assert len(acr.seed_urls) == 400
    assert acr.seed_urls[0] == "https://gravitas.acr.org/ACPortal/TopicNarrative?topicId=1"
    assert acr.seed_urls[-1].endswith("topicId=400")
    assert all("TopicNarrativePdf" not in url for url in acr.seed_urls)
    assert acr.allowed_hosts == ["gravitas.acr.org"]
    assert acr.max_depth == 0
    assert acr.allow_pdfs is False
    assert acr.request_timeout_seconds == 20.0
    assert acr.request_max_retries == 1
    assert acr.max_consecutive_fetch_errors == 5
    assert acr.progress_every == 25


def test_ismp_override_targets_current_ecri_catalogue(tmp_path: Path):
    cfg = CatalogueAcquisitionConfig(
        raw_root=tmp_path,
        manifest_path=tmp_path / "manifest.jsonl",
        catalogues={"ismp": _job(tmp_path, "ISMP")},
    )
    result = apply_specialty_catalogue_overrides(cfg)
    ismp = result.catalogues["ismp"]
    assert all(url.startswith("https://home.ecri.org/") for url in ismp.seed_urls)
    assert ismp.allowed_hosts == ["home.ecri.org"]
    assert ismp.allow_pdfs is False
    assert any("targeted-medication-safety-best-practices" in url for url in ismp.seed_urls)
