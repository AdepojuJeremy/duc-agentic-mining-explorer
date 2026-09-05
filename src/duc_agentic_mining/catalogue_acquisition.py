from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

import yaml
from pydantic import BaseModel, Field
from pypdf import PdfReader

from .acquisition import HTTPSettings


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class CatalogueJobConfig(BaseModel):
    enabled: bool = True
    canonical_source: str
    output: Path
    seed_urls: list[str]
    allowed_hosts: list[str]
    crawl_patterns: list[str] = Field(default_factory=list)
    record_patterns: list[str] = Field(default_factory=list)
    deny_patterns: list[str] = Field(default_factory=list)
    required_text_patterns: list[str] = Field(default_factory=list)
    max_depth: int = Field(default=2, ge=0, le=5)
    max_pages: int = Field(default=250, ge=1)
    max_records: int = Field(default=300, ge=1)
    min_record_chars: int = Field(default=250, ge=20)
    rate_limit_per_second: float = Field(default=1.0, gt=0)
    allow_pdfs: bool = False
    respect_robots_txt: bool = True


class CatalogueAcquisitionConfig(BaseModel):
    raw_root: Path
    manifest_path: Path
    http: HTTPSettings = Field(default_factory=HTTPSettings)
    catalogues: dict[str, CatalogueJobConfig] = Field(default_factory=dict)


def load_catalogue_config(path: Path) -> CatalogueAcquisitionConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw_root = Path(data.get("raw_root", "../data/raw"))
    manifest_path = Path(data.get("manifest_path", "../data/raw/manifests/source_manifest.jsonl"))
    cfg = CatalogueAcquisitionConfig.model_validate(
        {
            "raw_root": raw_root,
            "manifest_path": manifest_path,
            "http": data.get("http") or {},
            "catalogues": data.get("catalogues") or {},
        }
    )
    base = path.parent.resolve()
    if not cfg.raw_root.is_absolute():
        cfg.raw_root = (base / cfg.raw_root).resolve()
    if not cfg.manifest_path.is_absolute():
        cfg.manifest_path = (base / cfg.manifest_path).resolve()
    for job in cfg.catalogues.values():
        if not job.output.is_absolute():
            job.output = (cfg.raw_root / job.output).resolve()
    return cfg


class _HTMLCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.text_parts: list[str] = []
        self.title_parts: list[str] = []
        self._suppressed = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        low = tag.lower()
        attrs_dict = {str(k).lower(): str(v) for k, v in attrs if k and v is not None}
        if low in {"script", "style", "noscript", "svg"}:
            self._suppressed += 1
        if low == "title":
            self._in_title = True
        if low == "a" and attrs_dict.get("href"):
            self.links.append(attrs_dict["href"])

    def handle_endtag(self, tag: str) -> None:
        low = tag.lower()
        if low in {"script", "style", "noscript", "svg"} and self._suppressed:
            self._suppressed -= 1
        if low == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        value = data.strip()
        if not value or self._suppressed:
            return
        self.text_parts.append(value)
        if self._in_title:
            self.title_parts.append(value)


@dataclass(frozen=True)
class _Fetched:
    payload: bytes
    headers: dict[str, str]
    final_url: str


class BlockedBySource(RuntimeError):
    pass


class RobotsDisallowed(RuntimeError):
    pass


class _RobotsCache:
    def __init__(self, settings: HTTPSettings):
        self.settings = settings
        self._parsers: dict[str, RobotFileParser | None] = {}

    def allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        root = f"{parsed.scheme}://{parsed.netloc}"
        if root not in self._parsers:
            robots_url = f"{root}/robots.txt"
            rp = RobotFileParser()
            rp.set_url(robots_url)
            try:
                request = Request(robots_url, headers={"User-Agent": self.settings.user_agent})
                with urlopen(request, timeout=min(self.settings.timeout_seconds, 20.0)) as response:
                    body = response.read().decode("utf-8", errors="replace")
                rp.parse(body.splitlines())
                self._parsers[root] = rp
            except HTTPError as exc:
                # 401/403 on robots.txt is conventionally treated conservatively.
                if exc.code in {401, 403}:
                    self._parsers[root] = None
                else:
                    rp.parse([])
                    self._parsers[root] = rp
            except Exception:
                rp.parse([])
                self._parsers[root] = rp
        parser = self._parsers[root]
        if parser is None:
            return False
        return parser.can_fetch(self.settings.user_agent, url)


def _request(url: str, settings: HTTPSettings) -> _Fetched:
    last_error: Exception | None = None
    headers = {
        "User-Agent": settings.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.5",
    }
    for attempt in range(settings.max_retries):
        try:
            request = Request(url, headers=headers)
            with urlopen(request, timeout=settings.timeout_seconds) as response:
                payload = response.read()
                response_headers = {k.lower(): v for k, v in response.headers.items()}
                return _Fetched(payload, response_headers, response.geturl())
        except HTTPError as exc:
            if exc.code in {401, 402, 403}:
                raise BlockedBySource(f"HTTP {exc.code} for {url}") from exc
            last_error = exc
            if exc.code < 500 and exc.code not in {408, 429}:
                raise
        except (URLError, TimeoutError) as exc:
            last_error = exc
        if attempt + 1 < settings.max_retries:
            time.sleep(min(8.0, 2.0**attempt))
    assert last_error is not None
    raise last_error


def _normalize_url(base: str, href: str) -> str | None:
    if not href or href.startswith(("mailto:", "tel:", "javascript:")):
        return None
    absolute = urljoin(base, href)
    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return urlunparse(parsed._replace(fragment=""))


def _matches_any(patterns: list[str], value: str) -> bool:
    return any(re.search(pattern, value, flags=re.IGNORECASE) for pattern in patterns)


def _allowed_host(job: CatalogueJobConfig, url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in {item.lower() for item in job.allowed_hosts}


def _should_crawl(job: CatalogueJobConfig, url: str) -> bool:
    if not _allowed_host(job, url):
        return False
    if job.deny_patterns and _matches_any(job.deny_patterns, url):
        return False
    path = urlparse(url).path.lower()
    if any(path.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".css", ".js", ".zip", ".ppt", ".pptx", ".doc", ".docx")):
        return False
    if path.endswith(".pdf") and not job.allow_pdfs:
        return False
    return not job.crawl_patterns or _matches_any(job.crawl_patterns, url)


def _is_record(job: CatalogueJobConfig, url: str, text: str) -> bool:
    if job.record_patterns and not _matches_any(job.record_patterns, url):
        return False
    if len(text) < job.min_record_chars:
        return False
    if job.required_text_patterns and not _matches_any(job.required_text_patterns, text):
        return False
    return True


def _extract_html(payload: bytes, base_url: str) -> tuple[str, str, list[str]]:
    raw = payload.decode("utf-8", errors="replace")
    parser = _HTMLCollector()
    parser.feed(raw)
    text = re.sub(r"\s+", " ", "\n".join(parser.text_parts)).strip()
    title = re.sub(r"\s+", " ", " ".join(parser.title_parts)).strip()
    links: list[str] = []
    seen: set[str] = set()
    for href in parser.links:
        normalized = _normalize_url(base_url, href)
        if normalized and normalized not in seen:
            seen.add(normalized)
            links.append(normalized)
    return title, text, links


def _extract_pdf(payload: bytes) -> str:
    reader = PdfReader(BytesIO(payload))
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


def _record(job: CatalogueJobConfig, url: str, title: str, text: str, headers: dict[str, str]) -> dict[str, Any]:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
    last_modified = headers.get("last-modified")
    return {
        "id": f"catalogue:{re.sub(r'[^a-z0-9]+', '_', job.canonical_source.lower()).strip('_')}:{digest}",
        "title": title or url,
        "text": text,
        "source": job.canonical_source,
        "url": url,
        "date": last_modified,
        "metadata": {
            "retrieved_at": utc_now(),
            "retrieval_method": "constrained_official_catalogue",
            "primary_source_verified": True,
            "freshness_verified": False,
            "source_status": "versioned" if last_modified else "unknown",
            "last_modified": last_modified,
            "etag": headers.get("etag"),
            "content_type": headers.get("content-type"),
            "live_primary_retrieval": True,
            "catalogue_source": job.canonical_source,
        },
    }


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    tmp.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _append_manifest(cfg: CatalogueAcquisitionConfig, entry: dict[str, Any]) -> None:
    cfg.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with cfg.manifest_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"timestamp": utc_now(), **entry}, ensure_ascii=False) + "\n")


def sync_catalogue_job(name: str, job: CatalogueJobConfig, cfg: CatalogueAcquisitionConfig) -> dict[str, Any]:
    queue: list[tuple[str, int]] = [(url, 0) for url in job.seed_urls]
    visited: set[str] = set()
    records: list[dict[str, Any]] = []
    robots = _RobotsCache(cfg.http)
    blocked = 0
    robots_skipped = 0
    fetch_errors = 0

    while queue and len(visited) < job.max_pages and len(records) < job.max_records:
        url, depth = queue.pop(0)
        if url in visited or not _allowed_host(job, url):
            continue
        visited.add(url)
        if job.respect_robots_txt and not robots.allowed(url):
            robots_skipped += 1
            continue
        try:
            fetched = _request(url, cfg.http)
        except BlockedBySource:
            blocked += 1
            continue
        except Exception:
            fetch_errors += 1
            continue

        final = fetched.final_url
        content_type = fetched.headers.get("content-type", "").lower()
        is_pdf = "pdf" in content_type or urlparse(final).path.lower().endswith(".pdf")
        if is_pdf:
            if not job.allow_pdfs:
                continue
            try:
                text = _extract_pdf(fetched.payload)
            except Exception:
                fetch_errors += 1
                continue
            title = final.rsplit("/", 1)[-1]
            links: list[str] = []
        else:
            title, text, links = _extract_html(fetched.payload, final)

        if _is_record(job, final, text):
            records.append(_record(job, final, title, text, fetched.headers))

        if depth < job.max_depth:
            for link in links:
                if link not in visited and _should_crawl(job, link):
                    queue.append((link, depth + 1))

        time.sleep(1.0 / max(job.rate_limit_per_second, 0.1))

    _write_jsonl(job.output, records)
    status = "synced"
    if not records and blocked:
        status = "blocked_by_source"
    elif not records and robots_skipped and not fetch_errors:
        status = "robots_disallowed"
    elif not records:
        status = "no_records"
    result = {
        "status": status,
        "records": len(records),
        "pages_visited": len(visited),
        "blocked_pages": blocked,
        "robots_skipped": robots_skipped,
        "fetch_errors": fetch_errors,
        "output": str(job.output),
    }
    _append_manifest(
        cfg,
        {
            "source_job": name,
            "kind": "catalogue",
            "canonical_source": job.canonical_source,
            "status": status,
            "output": str(job.output),
            "bytes": job.output.stat().st_size,
            "sha256": _sha256(job.output),
            "records": len(records),
            "pages_visited": len(visited),
        },
    )
    return result


def catalogue_status(cfg: CatalogueAcquisitionConfig) -> dict[str, Any]:
    return {
        name: {
            "enabled": job.enabled,
            "kind": "catalogue",
            "canonical_source": job.canonical_source,
            "output": str(job.output),
            "output_exists": job.output.exists(),
            "output_bytes": job.output.stat().st_size if job.output.exists() else 0,
            "seed_urls": job.seed_urls,
            "allowed_hosts": job.allowed_hosts,
            "allow_pdfs": job.allow_pdfs,
            "respect_robots_txt": job.respect_robots_txt,
        }
        for name, job in cfg.catalogues.items()
    }


def sync_catalogues(
    cfg: CatalogueAcquisitionConfig,
    *,
    only: set[str] | None = None,
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for name, job in cfg.catalogues.items():
        if only and name not in only:
            continue
        if not job.enabled:
            results[name] = {"status": "disabled"}
            continue
        try:
            results[name] = sync_catalogue_job(name, job, cfg)
        except Exception as exc:
            results[name] = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    return results
