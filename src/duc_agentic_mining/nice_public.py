from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from .acquisition import (
    SourceAcquisitionConfig,
    SourceJobConfig,
    _append_manifest,
    _extract_document_text,
    _file_sha256,
    _record,
    _request,
    _stable_id,
    _write_jsonl,
)

# NICE product prefixes that commonly identify published guidance relevant to
# clinical/public-health decisions. The list is deliberately conservative.
_NICE_CODE_RE = re.compile(
    r"(?:/guidance/|\b)(ng|cg|ta|dg|mtg|ipg|ph|hsc|sg)(\d{1,6})\b",
    re.IGNORECASE,
)


def _flatten_for_discovery(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(_flatten_for_discovery(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return " ".join(_flatten_for_discovery(v) for v in value)
    return str(value)


def discover_nice_guidance_codes(seed_path: Path, max_codes: int) -> list[str]:
    """Discover canonical NICE guidance IDs from the local Meditron seed.

    Meditron is used only to discover candidate NICE identifiers. Retrieved public
    NICE pages, not the seed text, become the refreshed primary-source records.
    """
    if not seed_path.exists():
        return []
    codes: list[str] = []
    seen: set[str] = set()
    with seed_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if len(codes) >= max_codes:
                break
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            haystack = _flatten_for_discovery(row)
            lowered = haystack.lower()
            # Avoid treating unrelated codes as NICE merely because they look similar.
            if "nice.org.uk" not in lowered and "national institute for health and care excellence" not in lowered and not re.search(r"\bnice\b", lowered):
                continue
            for prefix, number in _NICE_CODE_RE.findall(haystack):
                code = f"{prefix}{number}".lower()
                if code not in seen:
                    seen.add(code)
                    codes.append(code)
                    if len(codes) >= max_codes:
                        break
    return codes


def _fetch_public_guidance(code: str, cfg: SourceAcquisitionConfig) -> dict[str, Any] | None:
    base_url = f"https://www.nice.org.uk/guidance/{code}"
    urls = [base_url, f"{base_url}/chapter/Recommendations"]
    parts: list[str] = []
    final_urls: list[str] = []
    last_modified: str | None = None
    etag: str | None = None
    errors: list[str] = []

    for url in urls:
        try:
            payload, headers, final = _request(
                url,
                cfg.http,
                headers={"Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8"},
            )
            text = _extract_document_text(payload, headers.get("content-type", ""), final)
            if text and text not in parts:
                parts.append(text)
            final_urls.append(final)
            last_modified = last_modified or headers.get("last-modified")
            etag = etag or headers.get("etag")
        except Exception as exc:  # isolated per public page; other guidance IDs continue
            errors.append(f"{type(exc).__name__}: {exc}")

    text = "\n\n".join(part for part in parts if part).strip()
    if len(text) < 80:
        return None

    return _record(
        source_id=_stable_id("nice-public", code),
        title=f"NICE guidance {code.upper()}",
        text=text,
        source="NICE",
        url=final_urls[0] if final_urls else base_url,
        date=last_modified,
        retrieval_method="nice_public_guidance_fallback",
        extra_metadata={
            "guidance_code": code.upper(),
            "public_web": True,
            "fallback_from_meditron_seed": True,
            "canonical_guidance_url": base_url,
            "resolved_urls": final_urls,
            "etag": etag,
            "last_modified": last_modified,
            "retrieval_errors": errors,
        },
    )


def sync_nice_public_fallback(
    cfg: SourceAcquisitionConfig,
    job: SourceJobConfig,
) -> dict[str, Any]:
    seed_path = cfg.raw_root / "epfl-llm-guidelines" / "open_guidelines.jsonl"
    if not seed_path.exists():
        return {
            "status": "fallback_seed_missing",
            "seed": str(seed_path),
            "hint": "run 'duc-agentic sources download-meditron config/sources.yaml' first",
        }

    codes = discover_nice_guidance_codes(seed_path, job.max_records)
    if not codes:
        return {"status": "fallback_no_candidates", "seed": str(seed_path), "records": 0}

    records: list[dict[str, Any]] = []
    for code in codes:
        record = _fetch_public_guidance(code, cfg)
        if record:
            records.append(record)
        time.sleep(1.0 / max(job.rate_limit_per_second, 0.1))

    _write_jsonl(job.output, records)
    result = {
        "status": "synced_public_fallback",
        "records": len(records),
        "candidates": len(codes),
        "output": str(job.output),
        "api_key_used": False,
        "discovery_seed": str(seed_path),
    }
    if job.output.exists():
        _append_manifest(
            cfg,
            {
                "source_job": "nice",
                "kind": "nice_public_fallback",
                "status": result["status"],
                "output": str(job.output),
                "bytes": job.output.stat().st_size,
                "sha256": _file_sha256(job.output),
                "records": len(records),
            },
        )
    return result


def apply_nice_public_fallback(
    cfg: SourceAcquisitionConfig,
    results: dict[str, Any],
    *,
    only: set[str] | None = None,
) -> dict[str, Any]:
    """Replace a missing NICE API credential result with public-web fallback sync."""
    if only and "nice" not in only:
        return results
    job = cfg.sources.get("nice")
    if not job or not job.enabled:
        return results
    nice_result = results.get("nice") or {}
    missing_key = not os.getenv(job.api_key_env or "NICE_API_KEY")
    if missing_key and nice_result.get("status") == "credential_missing":
        results["nice"] = sync_nice_public_fallback(cfg, job)
    return results


def annotate_nice_status(cfg: SourceAcquisitionConfig, rows: dict[str, Any]) -> dict[str, Any]:
    job = cfg.sources.get("nice")
    if not job or "nice" not in rows:
        return rows
    api_present = bool(os.getenv(job.api_key_env or "NICE_API_KEY"))
    seed_path = cfg.raw_root / "epfl-llm-guidelines" / "open_guidelines.jsonl"
    rows["nice"]["access_strategy"] = (
        "licensed_api" if api_present else "public_web_fallback_from_meditron"
    )
    rows["nice"]["public_fallback_available"] = seed_path.exists()
    rows["nice"]["public_fallback_seed"] = str(seed_path)
    rows["nice"]["api_key_optional_for_pipeline"] = True
    return rows
