import json
from pathlib import Path

from duc_agentic_mining.acquisition import SourceAcquisitionConfig, SourceJobConfig
from duc_agentic_mining.nice_public import (
    annotate_nice_status,
    apply_nice_public_fallback,
    discover_nice_guidance_codes,
)


def _write_seed(root: Path) -> Path:
    path = root / "epfl-llm-guidelines" / "open_guidelines.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "id": "seed-1",
                "source": "NICE",
                "title": "Example NICE guideline",
                "url": "https://www.nice.org.uk/guidance/ng123",
                "text": "Seed text from the Meditron Guidelines Collection.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _cfg(tmp_path: Path) -> SourceAcquisitionConfig:
    return SourceAcquisitionConfig(
        raw_root=tmp_path,
        manifest_path=tmp_path / "manifests" / "source_manifest.jsonl",
        sources={
            "nice": SourceJobConfig(
                kind="nice",
                output=tmp_path / "primary" / "nice" / "nice_guidance.jsonl",
                api_key_env="NICE_API_KEY",
                credential_required=True,
                max_records=20,
                rate_limit_per_second=100000,
            )
        },
    )


def test_discovers_nice_codes_from_meditron_seed(tmp_path: Path):
    seed = _write_seed(tmp_path)
    assert discover_nice_guidance_codes(seed, 10) == ["ng123"]


def test_missing_nice_key_falls_back_to_public_guidance(monkeypatch, tmp_path: Path):
    _write_seed(tmp_path)
    cfg = _cfg(tmp_path)
    monkeypatch.delenv("NICE_API_KEY", raising=False)

    def fake_request(url, settings, *, headers=None):
        payload = (
            b"<html><head><title>NICE guidance</title></head><body>"
            b"<h1>Example recommendation</h1>"
            b"<p>Offer treatment A when the stated indication is present.</p>"
            b"</body></html>"
        )
        return payload, {"content-type": "text/html", "last-modified": "Sat, 05 Sep 2026 00:00:00 GMT"}, url

    monkeypatch.setattr("duc_agentic_mining.nice_public._request", fake_request)
    results = {"nice": {"status": "credential_missing", "credential": "NICE_API_KEY"}}
    updated = apply_nice_public_fallback(cfg, results)

    assert updated["nice"]["status"] == "synced_public_fallback"
    assert updated["nice"]["records"] == 1
    output = cfg.sources["nice"].output
    row = json.loads(output.read_text(encoding="utf-8").splitlines()[0])
    assert row["source"] == "NICE"
    assert row["metadata"]["retrieval_method"] == "nice_public_guidance_fallback"
    assert row["metadata"]["fallback_from_meditron_seed"] is True
    assert row["metadata"]["guidance_code"] == "NG123"
    assert cfg.manifest_path.exists()


def test_status_explains_public_fallback_without_key(monkeypatch, tmp_path: Path):
    _write_seed(tmp_path)
    cfg = _cfg(tmp_path)
    monkeypatch.delenv("NICE_API_KEY", raising=False)
    rows = {
        "nice": {
            "credential_present": False,
            "credential_required": True,
            "enabled": True,
        }
    }
    annotated = annotate_nice_status(cfg, rows)
    assert annotated["nice"]["access_strategy"] == "public_web_fallback_from_meditron"
    assert annotated["nice"]["public_fallback_available"] is True
    assert annotated["nice"]["api_key_optional_for_pipeline"] is True
