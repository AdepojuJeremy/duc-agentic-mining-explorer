from __future__ import annotations

import hashlib
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse, urlunparse, parse_qsl
from urllib.request import Request, urlopen

import yaml
from pydantic import BaseModel, Field, model_validator
from pypdf import PdfReader

SourceJobKind = Literal[
    "meditron",
    "nice",
    "who",
    "cdc",
    "ncbi",
    "openfda",
    "official_urls",
]


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class HTTPSettings(BaseModel):
    timeout_seconds: float = Field(default=90.0, gt=0)
    max_retries: int = Field(default=4, ge=1, le=10)
    user_agent: str = "DUC-Agentic-Mining/0.1 research-source-acquisition"


class SourceJobConfig(BaseModel):
    enabled: bool = True
    kind: SourceJobKind
    output: Path
    canonical_source: str | None = None
    endpoint: str | None = None
    url: str | None = None
    api_key_env: str | None = None
    credential_required: bool = False
    email_env: str | None = None
    db: Literal["pubmed", "pmc"] | None = None
    queries: list[str] = Field(default_factory=list)
    max_records: int = Field(default=5000, ge=1)
    max_pages: int = Field(default=1000, ge=1)
    rate_limit_per_second: float = Field(default=2.5, gt=0)
    follow_documents: bool = False
    official_urls: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_shape(self) -> SourceJobConfig:
        if self.kind == "ncbi" and not self.db:
            raise ValueError("ncbi source jobs require db=pubmed or db=pmc")
        if self.kind == "official_urls" and not self.canonical_source:
            raise ValueError("official_urls source jobs require canonical_source")
        return self


class SourceAcquisitionConfig(BaseModel):
    raw_root: Path = Path("data/raw")
    manifest_path: Path = Path("data/raw/manifests/source_manifest.jsonl")
    http: HTTPSettings = Field(default_factory=HTTPSettings)
    sources: dict[str, SourceJobConfig]


def load_source_config(path: Path) -> SourceAcquisitionConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cfg = SourceAcquisitionConfig.model_validate(data)
    base = path.parent.resolve()
    if not cfg.raw_root.is_absolute():
        cfg.raw_root = (base / cfg.raw_root).resolve()
    if not cfg.manifest_path.is_absolute():
        cfg.manifest_path = (base / cfg.manifest_path).resolve()
    for job in cfg.sources.values():
        if not job.output.is_absolute():
            job.output = (cfg.raw_root / job.output).resolve()
    return cfg


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._suppressed = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {"script", "style", "noscript"}:
            self._suppressed += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"} and self._suppressed:
            self._suppressed -= 1

    def handle_data(self, data: str) -> None:
        if not self._suppressed and data.strip():
            self.parts.append(data.strip())


def _html_to_text(value: str) -> str:
    parser = _TextExtractor()
    parser.feed(value)
    return re.sub(r"\s+", " ", "\n".join(parser.parts)).strip()


def _flatten(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return _html_to_text(value) if "<" in value and ">" in value else value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return "\n".join(x for x in (_flatten(v) for v in value) if x)
    if isinstance(value, dict):
        return "\n".join(
            f"{k}: {text}" for k, v in value.items() if (text := _flatten(v))
        )
    return str(value)


def _pick(obj: Any, names: tuple[str, ...]) -> str | None:
    wanted = {name.lower() for name in names}
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key.lower() in wanted and value not in (None, ""):
                text = _flatten(value).strip()
                if text:
                    return text
        for value in obj.values():
            hit = _pick(value, names)
            if hit:
                return hit
    elif isinstance(obj, list):
        for value in obj:
            hit = _pick(value, names)
            if hit:
                return hit
    return None


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}:{hashlib.sha256(value.encode('utf-8')).hexdigest()[:20]}"


def _record(
    *,
    source_id: str,
    title: str,
    text: str,
    source: str,
    url: str | None,
    date: str | None,
    retrieval_method: str,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = {
        "retrieved_at": utc_now(),
        "retrieval_method": retrieval_method,
        "primary_source_verified": retrieval_method != "meditron_huggingface_seed",
        "freshness_verified": retrieval_method != "meditron_huggingface_seed",
        "source_status": "versioned",
    }
    if extra_metadata:
        metadata.update(extra_metadata)
    return {
        "id": source_id,
        "title": title,
        "text": text,
        "source": source,
        "url": url,
        "date": date,
        "metadata": metadata,
    }


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        for record in records:
            if record.get("text"):
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    tmp.replace(path)
    return len(records)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _append_manifest(cfg: SourceAcquisitionConfig, entry: dict[str, Any]) -> None:
    cfg.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with cfg.manifest_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"timestamp": utc_now(), **entry}, ensure_ascii=False) + "\n")


def _request(
    url: str,
    settings: HTTPSettings,
    *,
    headers: dict[str, str] | None = None,
) -> tuple[bytes, dict[str, str], str]:
    merged = {
        "User-Agent": settings.user_agent,
        "Accept": "*/*",
        **(headers or {}),
    }
    last_error: Exception | None = None
    for attempt in range(settings.max_retries):
        try:
            request = Request(url, headers=merged)
            with urlopen(request, timeout=settings.timeout_seconds) as response:
                payload = response.read()
                response_headers = {k.lower(): v for k, v in response.headers.items()}
                return payload, response_headers, response.geturl()
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
            if isinstance(exc, HTTPError) and exc.code < 500 and exc.code not in {408, 429}:
                raise
            if attempt + 1 < settings.max_retries:
                time.sleep(min(8.0, 2.0**attempt))
    assert last_error is not None
    raise last_error


def _with_query(url: str, params: dict[str, Any]) -> str:
    parsed = urlparse(url)
    current = dict(parse_qsl(parsed.query, keep_blank_values=True))
    current.update({k: str(v) for k, v in params.items() if v is not None})
    return urlunparse(parsed._replace(query=urlencode(current)))


def _decode_json_or_xml(payload: bytes, content_type: str = "") -> Any:
    text = payload.decode("utf-8", errors="replace")
    if "json" in content_type.lower() or text.lstrip().startswith(("{", "[")):
        return json.loads(text)
    if "xml" in content_type.lower() or text.lstrip().startswith("<"):
        return ET.fromstring(text)
    return text


def _xml_text(root: ET.Element) -> str:
    return re.sub(r"\s+", " ", " ".join(x.strip() for x in root.itertext() if x.strip())).strip()


def _extract_links(value: Any) -> set[str]:
    links: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in {"url", "uri", "href", "sourceurl", "targeturl", "persistenturl"}:
                if isinstance(item, str) and item.startswith(("http://", "https://")):
                    links.add(item)
            links.update(_extract_links(item))
    elif isinstance(value, list):
        for item in value:
            links.update(_extract_links(item))
    elif isinstance(value, ET.Element):
        for element in value.iter():
            for key in ("url", "uri", "href"):
                item = element.attrib.get(key)
                if item and item.startswith(("http://", "https://")):
                    links.add(item)
    return links


def _extract_document_text(payload: bytes, content_type: str, url: str) -> str:
    if "pdf" in content_type.lower() or urlparse(url).path.lower().endswith(".pdf"):
        reader = PdfReader(BytesIO(payload))
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    text = payload.decode("utf-8", errors="replace")
    if "html" in content_type.lower() or "<html" in text[:1000].lower():
        return _html_to_text(text)
    if "json" in content_type.lower() or text.lstrip().startswith(("{", "[")):
        try:
            return _flatten(json.loads(text))
        except json.JSONDecodeError:
            pass
    if "xml" in content_type.lower() or text.lstrip().startswith("<"):
        try:
            return _xml_text(ET.fromstring(text))
        except ET.ParseError:
            pass
    return re.sub(r"\s+", " ", text).strip()


def _sync_meditron(
    job: SourceJobConfig, cfg: SourceAcquisitionConfig, force: bool
) -> dict[str, Any]:
    url = job.url or (
        "https://huggingface.co/datasets/epfl-llm/guidelines/resolve/main/"
        "open_guidelines.jsonl?download=true"
    )
    if job.output.exists() and not force:
        return {"status": "cached", "output": str(job.output), "bytes": job.output.stat().st_size}
    headers: dict[str, str] = {}
    if token := os.getenv("HF_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    job.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = job.output.with_suffix(job.output.suffix + ".tmp")
    request = Request(url, headers={"User-Agent": cfg.http.user_agent, **headers})
    digest = hashlib.sha256()
    total = 0
    with urlopen(request, timeout=max(cfg.http.timeout_seconds, 300.0)) as response, tmp.open("wb") as out:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
            out.write(chunk)
    tmp.replace(job.output)
    return {
        "status": "downloaded",
        "output": str(job.output),
        "bytes": total,
        "sha256": digest.hexdigest(),
        "source_url": url,
    }


def _sync_nice(job: SourceJobConfig, cfg: SourceAcquisitionConfig) -> dict[str, Any]:
    api_key = os.getenv(job.api_key_env or "NICE_API_KEY")
    if not api_key:
        return {"status": "credential_missing", "credential": job.api_key_env or "NICE_API_KEY"}
    start = job.endpoint or "https://api.nice.org.uk/services/guidance/index"
    queue = [start]
    visited: set[str] = set()
    records: list[dict[str, Any]] = []
    while queue and len(visited) < job.max_pages and len(records) < job.max_records:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        payload, headers, final_url = _request(
            url,
            cfg.http,
            headers={
                "API-Key": api_key,
                "Accept": "application/vnd.nice.syndication.services+json, application/json, application/xml;q=0.9",
            },
        )
        content_type = headers.get("content-type", "")
        parsed = _decode_json_or_xml(payload, content_type)
        text = _xml_text(parsed) if isinstance(parsed, ET.Element) else _flatten(parsed)
        if len(text) >= 80:
            title = (
                parsed.findtext(".//Title") if isinstance(parsed, ET.Element) else _pick(parsed, ("Title", "title", "Name", "name"))
            ) or final_url
            date = (
                parsed.findtext(".//LastModified") if isinstance(parsed, ET.Element) else _pick(parsed, ("LastModified", "lastModified", "PublicationDate", "date"))
            )
            records.append(
                _record(
                    source_id=_stable_id("nice", final_url),
                    title=title,
                    text=text,
                    source="NICE",
                    url=final_url,
                    date=date,
                    retrieval_method="nice_syndication_api",
                    extra_metadata={
                        "etag": headers.get("etag"),
                        "last_modified": headers.get("last-modified"),
                        "api_resource": True,
                    },
                )
            )
        for link in sorted(_extract_links(parsed)):
            parsed_link = urlparse(link)
            if parsed_link.hostname == "api.nice.org.uk" and parsed_link.path.startswith("/services/guidance"):
                if link not in visited:
                    queue.append(link)
        time.sleep(1.0 / max(job.rate_limit_per_second, 0.1))
    _write_jsonl(job.output, records)
    return {"status": "synced", "records": len(records), "pages": len(visited), "output": str(job.output)}


def _items_from_json(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("value", "results", "items", "records", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def _sync_who(job: SourceJobConfig, cfg: SourceAcquisitionConfig) -> dict[str, Any]:
    endpoint = job.endpoint or "https://www.who.int/api/hubs/publications"
    records: list[dict[str, Any]] = []
    skip = 0
    page_size = min(100, job.max_records)
    pages = 0
    while len(records) < job.max_records and pages < job.max_pages:
        url = _with_query(endpoint, {"$top": page_size, "$skip": skip})
        payload, headers, _ = _request(url, cfg.http, headers={"Accept": "application/json"})
        data = json.loads(payload.decode("utf-8", errors="replace"))
        items = _items_from_json(data)
        if not items:
            break
        for item in items:
            item_url = _pick(item, ("Url", "url", "ItemDefaultUrl", "PublicationUrl", "DownloadUrl"))
            if item_url and item_url.startswith("/"):
                item_url = urljoin("https://www.who.int", item_url)
            text = _flatten(item)
            if job.follow_documents and item_url and item_url.startswith("http"):
                try:
                    body, body_headers, final = _request(item_url, cfg.http)
                    doc_text = _extract_document_text(body, body_headers.get("content-type", ""), final)
                    if len(doc_text) > len(text):
                        text = doc_text
                        item_url = final
                except Exception:
                    pass
            title = _pick(item, ("Title", "title", "Name", "name")) or "WHO publication"
            date = _pick(item, ("PublicationDate", "publicationDate", "LastModified", "DateCreated"))
            key = _pick(item, ("Id", "id", "SystemSourceKey", "UrlName")) or f"{title}:{item_url or ''}"
            records.append(
                _record(
                    source_id=_stable_id("who", key),
                    title=title,
                    text=text,
                    source="WHO",
                    url=item_url,
                    date=date,
                    retrieval_method="who_publications_api",
                    extra_metadata={"api_endpoint": endpoint},
                )
            )
            if len(records) >= job.max_records:
                break
        pages += 1
        skip += len(items)
        if len(items) < page_size:
            break
        time.sleep(1.0 / max(job.rate_limit_per_second, 0.1))
    _write_jsonl(job.output, records)
    return {"status": "synced", "records": len(records), "pages": pages, "output": str(job.output)}


def _sync_cdc(job: SourceJobConfig, cfg: SourceAcquisitionConfig) -> dict[str, Any]:
    endpoint = job.endpoint or "https://tools.cdc.gov/api/v2/resources/media"
    queries = job.queries or [""]
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    pages = 0
    for query in queries:
        pagenum = 1
        while len(records) < job.max_records and pages < job.max_pages:
            params: dict[str, Any] = {"max": min(100, job.max_records), "pagenum": pagenum}
            if query:
                params["q"] = query
            payload, _, _ = _request(_with_query(endpoint, params), cfg.http, headers={"Accept": "application/json"})
            data = json.loads(payload.decode("utf-8", errors="replace"))
            items = _items_from_json(data)
            if not items:
                break
            new_on_page = 0
            for item in items:
                media_id = str(item.get("id") or "")
                if not media_id or media_id in seen:
                    continue
                seen.add(media_id)
                new_on_page += 1
                content_url = f"{endpoint.rstrip('/')}/{media_id}/content"
                content = ""
                try:
                    body, body_headers, final = _request(content_url, cfg.http, headers={"Accept": "application/json"})
                    content_data = _decode_json_or_xml(body, body_headers.get("content-type", ""))
                    if isinstance(content_data, dict) and "results" in content_data:
                        content = _flatten(content_data["results"])
                    elif isinstance(content_data, ET.Element):
                        content = _xml_text(content_data)
                    else:
                        content = _flatten(content_data)
                    content_url = final
                except Exception:
                    content = ""
                text = "\n".join(x for x in (_flatten(item), content) if x)
                title = str(item.get("name") or item.get("title") or "CDC resource")
                date = str(item.get("dateModified") or item.get("lastModified") or "") or None
                source_url = str(item.get("sourceUrl") or item.get("targetUrl") or content_url)
                records.append(
                    _record(
                        source_id=f"cdc:{media_id}",
                        title=title,
                        text=text,
                        source="CDC",
                        url=source_url,
                        date=date,
                        retrieval_method="cdc_content_services_api",
                        extra_metadata={"media_id": media_id, "content_api_url": content_url},
                    )
                )
                if len(records) >= job.max_records:
                    break
                time.sleep(1.0 / max(job.rate_limit_per_second, 0.1))
            pages += 1
            if len(items) < params["max"] or not new_on_page:
                break
            pagenum += 1
    _write_jsonl(job.output, records)
    return {"status": "synced", "records": len(records), "pages": pages, "output": str(job.output)}


def _local_tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1].lower()


def _first_xml_text(root: ET.Element, tags: set[str]) -> str | None:
    for element in root.iter():
        if _local_tag(element) in tags:
            value = " ".join(x.strip() for x in element.itertext() if x.strip())
            if value:
                return value
    return None


def _ncbi_article_records(xml_payload: bytes, db: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_payload)
    article_tags = {"pubmedarticle"} if db == "pubmed" else {"article"}
    articles = [e for e in root.iter() if _local_tag(e) in article_tags]
    out: list[dict[str, Any]] = []
    for article in articles:
        identifier = _first_xml_text(article, {"pmid", "article-id"}) or _stable_id("ncbi", _xml_text(article)[:1000])
        title = _first_xml_text(article, {"articletitle", "article-title"}) or "NCBI record"
        year = _first_xml_text(article, {"year"})
        text = _xml_text(article)
        if db == "pubmed":
            url = f"https://pubmed.ncbi.nlm.nih.gov/{identifier}/"
        else:
            clean = identifier if str(identifier).upper().startswith("PMC") else f"PMC{identifier}"
            url = f"https://pmc.ncbi.nlm.nih.gov/articles/{clean}/"
        out.append(
            _record(
                source_id=f"ncbi:{db}:{identifier}",
                title=title,
                text=text,
                source="PubMed / PMC",
                url=url,
                date=year,
                retrieval_method="ncbi_eutils",
                extra_metadata={"database": db},
            )
        )
    return out


def _sync_ncbi(job: SourceJobConfig, cfg: SourceAcquisitionConfig) -> dict[str, Any]:
    assert job.db is not None
    base = job.endpoint or "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    api_key = os.getenv(job.api_key_env or "NCBI_API_KEY")
    email = os.getenv(job.email_env or "NCBI_EMAIL")
    queries = job.queries or [
        '("Practice Guideline"[Publication Type] OR "Guideline"[Publication Type])'
    ]
    ids: list[str] = []
    seen: set[str] = set()
    common: dict[str, Any] = {"tool": "duc_agentic_mining"}
    if api_key:
        common["api_key"] = api_key
    if email:
        common["email"] = email
    for query in queries:
        params = {"db": job.db, "term": query, "retmode": "json", "retmax": job.max_records, **common}
        payload, _, _ = _request(f"{base.rstrip('/')}/esearch.fcgi?{urlencode(params)}", cfg.http)
        data = json.loads(payload.decode("utf-8", errors="replace"))
        for identifier in data.get("esearchresult", {}).get("idlist", []):
            if identifier not in seen:
                seen.add(identifier)
                ids.append(identifier)
                if len(ids) >= job.max_records:
                    break
        if len(ids) >= job.max_records:
            break
        time.sleep(1.0 / max(job.rate_limit_per_second, 0.1))
    records: list[dict[str, Any]] = []
    batch_size = 100
    for offset in range(0, len(ids), batch_size):
        batch = ids[offset : offset + batch_size]
        params = {"db": job.db, "id": ",".join(batch), "retmode": "xml", **common}
        payload, _, _ = _request(f"{base.rstrip('/')}/efetch.fcgi?{urlencode(params)}", cfg.http)
        records.extend(_ncbi_article_records(payload, job.db))
        if len(records) >= job.max_records:
            records = records[: job.max_records]
            break
        time.sleep(1.0 / max(job.rate_limit_per_second, 0.1))
    _write_jsonl(job.output, records)
    return {"status": "synced", "records": len(records), "ids": len(ids), "output": str(job.output)}


def _sync_openfda(job: SourceJobConfig, cfg: SourceAcquisitionConfig) -> dict[str, Any]:
    endpoint = job.endpoint or "https://api.fda.gov/drug/label.json"
    api_key = os.getenv(job.api_key_env or "OPENFDA_API_KEY")
    queries = job.queries or ["_exists_:warnings"]
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for query in queries:
        skip = 0
        while len(records) < job.max_records and skip < 25000:
            params: dict[str, Any] = {"search": query, "limit": min(100, job.max_records - len(records)), "skip": skip}
            if api_key:
                params["api_key"] = api_key
            try:
                payload, _, final = _request(_with_query(endpoint, params), cfg.http, headers={"Accept": "application/json"})
            except HTTPError as exc:
                if exc.code == 404:
                    break
                raise
            data = json.loads(payload.decode("utf-8", errors="replace"))
            items = data.get("results", [])
            if not items:
                break
            for item in items:
                key = str(item.get("id") or item.get("set_id") or _stable_id("fda", _flatten(item)[:1000]))
                if key in seen:
                    continue
                seen.add(key)
                openfda = item.get("openfda") or {}
                brand = openfda.get("brand_name") or openfda.get("generic_name") or []
                title = brand[0] if isinstance(brand, list) and brand else str(brand or "FDA drug label")
                records.append(
                    _record(
                        source_id=f"fda:{key}",
                        title=title,
                        text=_flatten(item),
                        source="FDA",
                        url=final,
                        date=str(item.get("effective_time") or "") or None,
                        retrieval_method="openfda_api",
                        extra_metadata={"openfda_endpoint": endpoint},
                    )
                )
                if len(records) >= job.max_records:
                    break
            skip += len(items)
            if len(items) < params["limit"]:
                break
            time.sleep(1.0 / max(job.rate_limit_per_second, 0.1))
    _write_jsonl(job.output, records)
    return {"status": "synced", "records": len(records), "output": str(job.output)}


def _sync_official_urls(job: SourceJobConfig, cfg: SourceAcquisitionConfig) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for url in job.official_urls[: job.max_records]:
        payload, headers, final = _request(url, cfg.http)
        content_type = headers.get("content-type", "")
        text = _extract_document_text(payload, content_type, final)
        if not text:
            continue
        title = final.rsplit("/", 1)[-1] or job.canonical_source or "official source"
        records.append(
            _record(
                source_id=_stable_id((job.canonical_source or "official").lower().replace(" ", "_"), final),
                title=title,
                text=text,
                source=job.canonical_source or "Official source",
                url=final,
                date=headers.get("last-modified"),
                retrieval_method="controlled_official_url",
                extra_metadata={
                    "content_type": content_type,
                    "etag": headers.get("etag"),
                    "last_modified": headers.get("last-modified"),
                },
            )
        )
        time.sleep(1.0 / max(job.rate_limit_per_second, 0.1))
    _write_jsonl(job.output, records)
    return {"status": "synced", "records": len(records), "output": str(job.output)}


SYNCERS = {
    "meditron": _sync_meditron,
    "nice": _sync_nice,
    "who": _sync_who,
    "cdc": _sync_cdc,
    "ncbi": _sync_ncbi,
    "openfda": _sync_openfda,
    "official_urls": _sync_official_urls,
}


def source_status(cfg: SourceAcquisitionConfig) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    for name, job in cfg.sources.items():
        credential = job.api_key_env
        rows[name] = {
            "enabled": job.enabled,
            "kind": job.kind,
            "output": str(job.output),
            "output_exists": job.output.exists(),
            "output_bytes": job.output.stat().st_size if job.output.exists() else 0,
            "credential_env": credential,
            "credential_present": bool(os.getenv(credential)) if credential else None,
            "credential_required": job.credential_required,
        }
    return rows


def sync_sources(
    cfg: SourceAcquisitionConfig,
    *,
    only: set[str] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for name, job in cfg.sources.items():
        if not job.enabled:
            results[name] = {"status": "disabled"}
            continue
        if only and name not in only:
            continue
        if job.credential_required and job.api_key_env and not os.getenv(job.api_key_env):
            results[name] = {"status": "credential_missing", "credential": job.api_key_env}
            continue
        try:
            if job.kind == "meditron":
                result = _sync_meditron(job, cfg, force)
            else:
                result = SYNCERS[job.kind](job, cfg)
            results[name] = result
            if job.output.exists():
                _append_manifest(
                    cfg,
                    {
                        "source_job": name,
                        "kind": job.kind,
                        "status": result.get("status"),
                        "output": str(job.output),
                        "bytes": job.output.stat().st_size,
                        "sha256": _file_sha256(job.output),
                        "records": result.get("records"),
                    },
                )
        except Exception as exc:
            results[name] = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    return results
