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


def test_acr_override_uses_public_topic_endpoints(tmp_path: Path):
    cfg = CatalogueAcquisitionConfig(
        raw_root=tmp_path,
        manifest_path=tmp_path / "manifest.jsonl",
        catalogues={"acr": _job(tmp_path, "ACR")},
    )
    result = apply_specialty_catalogue_overrides(cfg)
    acr = result.catalogues["acr"]
    assert len(acr.seed_urls) == 320
    assert acr.seed_urls[0].endswith("topicId=1")
    assert acr.seed_urls[-1].endswith("topicId=320")
    assert acr.allowed_hosts == ["acsearch.acr.org"]
    assert acr.max_depth == 0
    assert acr.allow_pdfs is True


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
