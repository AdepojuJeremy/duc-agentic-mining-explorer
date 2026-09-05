from pathlib import Path

import duc_agentic_mining.catalogue_acquisition as catalogue
from duc_agentic_mining.catalogue_acquisition import (
    BlockedBySource,
    CatalogueAcquisitionConfig,
    CatalogueJobConfig,
    _Fetched,
    catalogue_status,
    load_catalogue_config,
    sync_catalogue_job,
)
from duc_agentic_mining.cli import _load_catalogues_for_source_config


def test_catalogue_config_resolves_outputs_under_raw_root(tmp_path: Path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    path = config_dir / "specialty_catalogues.yaml"
    path.write_text(
        """
raw_root: ../data/raw
manifest_path: ../data/raw/manifests/source_manifest.jsonl
catalogues:
  idsa:
    canonical_source: IDSA
    output: primary/idsa/idsa.jsonl
    seed_urls: [https://example.org/catalog]
    allowed_hosts: [example.org]
""",
        encoding="utf-8",
    )
    cfg = load_catalogue_config(path)
    assert cfg.raw_root == (tmp_path / "data" / "raw").resolve()
    assert cfg.catalogues["idsa"].output == (
        tmp_path / "data" / "raw" / "primary" / "idsa" / "idsa.jsonl"
    ).resolve()


def test_catalogue_crawler_discovers_and_records_matching_official_page(
    monkeypatch, tmp_path: Path
):
    pages = {
        "https://example.org/catalog": _Fetched(
            b'<html><head><title>Catalogue</title></head><body><a href="/guideline/a">A</a></body></html>',
            {"content-type": "text/html"},
            "https://example.org/catalog",
        ),
        "https://example.org/guideline/a": _Fetched(
            b"<html><head><title>Guideline A</title></head><body>Example Authority clinical guideline recommendation text that is intentionally long enough to be indexed safely for the test fixture.</body></html>",
            {"content-type": "text/html", "last-modified": "Sat, 05 Sep 2026 10:00:00 GMT"},
            "https://example.org/guideline/a",
        ),
    }

    monkeypatch.setattr(catalogue._RobotsCache, "allowed", lambda self, url: True)
    monkeypatch.setattr(catalogue, "_request", lambda url, settings: pages[url])
    job = CatalogueJobConfig(
        canonical_source="Example Authority",
        output=tmp_path / "example.jsonl",
        seed_urls=["https://example.org/catalog"],
        allowed_hosts=["example.org"],
        crawl_patterns=[r"/guideline/"],
        record_patterns=[r"/guideline/"],
        required_text_patterns=[r"Example Authority"],
        min_record_chars=80,
        max_depth=2,
        max_pages=10,
        max_records=10,
        rate_limit_per_second=1000,
    )
    cfg = CatalogueAcquisitionConfig(
        raw_root=tmp_path,
        manifest_path=tmp_path / "manifest.jsonl",
        catalogues={},
    )

    result = sync_catalogue_job("example", job, cfg)
    assert result["status"] == "synced"
    assert result["records"] == 1
    assert job.output.exists()
    line = job.output.read_text(encoding="utf-8")
    assert "Guideline A" in line
    assert '"source": "Example Authority"' in line
    assert '"primary_source_verified": true' in line


def test_catalogue_crawler_reports_blocked_source_without_bypass(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(catalogue._RobotsCache, "allowed", lambda self, url: True)

    def blocked(url, settings):
        raise BlockedBySource("HTTP 403")

    monkeypatch.setattr(catalogue, "_request", blocked)
    job = CatalogueJobConfig(
        canonical_source="Blocked Authority",
        output=tmp_path / "blocked.jsonl",
        seed_urls=["https://blocked.example/catalog"],
        allowed_hosts=["blocked.example"],
        max_pages=2,
        max_records=2,
        rate_limit_per_second=1000,
    )
    cfg = CatalogueAcquisitionConfig(
        raw_root=tmp_path,
        manifest_path=tmp_path / "manifest.jsonl",
        catalogues={},
    )
    result = sync_catalogue_job("blocked", job, cfg)
    assert result["status"] == "blocked_by_source"
    assert result["blocked_pages"] == 1
    assert job.output.exists()


def test_catalogue_stops_after_consecutive_network_errors(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(catalogue._RobotsCache, "allowed", lambda self, url: True)

    def timeout(url, settings):
        raise TimeoutError("test timeout")

    monkeypatch.setattr(catalogue, "_request", timeout)
    job = CatalogueJobConfig(
        canonical_source="Flaky Authority",
        output=tmp_path / "flaky.jsonl",
        seed_urls=[f"https://flaky.example/{idx}" for idx in range(10)],
        allowed_hosts=["flaky.example"],
        max_pages=10,
        max_records=10,
        rate_limit_per_second=1000,
        request_timeout_seconds=1,
        request_max_retries=1,
        max_consecutive_fetch_errors=3,
    )
    cfg = CatalogueAcquisitionConfig(
        raw_root=tmp_path,
        manifest_path=tmp_path / "manifest.jsonl",
        catalogues={},
    )
    result = sync_catalogue_job("flaky", job, cfg)
    assert result["status"] == "network_error"
    assert result["pages_visited"] == 3
    assert result["fetch_errors"] == 3
    assert result["stopped_after_consecutive_errors"] is True


def test_status_exposes_catalogue_policy(tmp_path: Path):
    cfg = CatalogueAcquisitionConfig(
        raw_root=tmp_path,
        manifest_path=tmp_path / "manifest.jsonl",
        catalogues={
            "gina": CatalogueJobConfig(
                canonical_source="GINA",
                output=tmp_path / "gina.jsonl",
                seed_urls=["https://ginasthma.org/reports/"],
                allowed_hosts=["ginasthma.org"],
                allow_pdfs=False,
            )
        },
    )
    row = catalogue_status(cfg)["gina"]
    assert row["enabled"] is True
    assert row["allow_pdfs"] is False
    assert row["respect_robots_txt"] is True


def test_cli_merges_primary_and_extra_specialty_catalogues(tmp_path: Path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    source_config = config_dir / "sources.yaml"
    source_config.write_text("sources: {}\n", encoding="utf-8")
    (config_dir / "specialty_catalogues.yaml").write_text(
        """
raw_root: ../data/raw
manifest_path: ../data/raw/manifest.jsonl
catalogues:
  idsa:
    canonical_source: IDSA
    output: primary/idsa.jsonl
    seed_urls: [https://idsociety.org/guidelines]
    allowed_hosts: [idsociety.org]
""",
        encoding="utf-8",
    )
    (config_dir / "specialty_catalogues_extra.yaml").write_text(
        """
raw_root: ../data/raw
manifest_path: ../data/raw/manifest.jsonl
catalogues:
  ismp:
    canonical_source: ISMP
    output: primary/ismp.jsonl
    seed_urls: [https://ismp.org/guidelines]
    allowed_hosts: [ismp.org]
""",
        encoding="utf-8",
    )
    cfg = _load_catalogues_for_source_config(source_config)
    assert set(cfg.catalogues) == {"idsa", "ismp"}


def test_repo_specialty_config_covers_controlled_web_tier1_sources():
    repo_root = Path(__file__).resolve().parents[1]
    cfg = _load_catalogues_for_source_config(repo_root / "config" / "sources.yaml")
    expected = {
        "uspstf",
        "idsa",
        "ontario_health",
        "acr",
        "acc_aha",
        "asco",
        "acog",
        "aap",
        "kdigo",
        "gina",
        "gold",
        "acep",
        "resuscitation",
        "mhra",
        "ema",
        "ecdc",
        "ukhsa",
        "africa_cdc",
        "who_icrc_emergency",
        "ismp",
    }
    assert expected.issubset(cfg.catalogues)
    assert all(cfg.catalogues[name].enabled for name in expected)
