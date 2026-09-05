from __future__ import annotations

import json
import sqlite3
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Iterator

import yaml

from .config import CorpusConfig
from .models import SourceRecord


class CorpusError(RuntimeError):
    pass


def _first(row: dict[str, Any], fields: list[str]) -> Any:
    for field in fields:
        value = row.get(field)
        if value not in (None, ""):
            return value
    return None


def _flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return "\n".join(_flatten_text(x) for x in value)
    if isinstance(value, dict):
        return "\n".join(f"{k}: {_flatten_text(v)}" for k, v in value.items())
    return str(value)


def iter_rows(path: Path) -> Iterator[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix in {".jsonl", ".ndjson"}:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        yield obj
        return
    if suffix == ".json":
        obj = json.loads(path.read_text(encoding="utf-8"))
    elif suffix in {".yaml", ".yml"}:
        obj = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        raise CorpusError(f"unsupported corpus file: {path}")
    if isinstance(obj, list):
        yield from (x for x in obj if isinstance(x, dict))
    elif isinstance(obj, dict):
        for key in ("items", "records", "documents", "data"):
            if isinstance(obj.get(key), list):
                yield from (x for x in obj[key] if isinstance(x, dict))
                return
        yield obj


def normalize_row(row: dict[str, Any], cfg: CorpusConfig, origin: str, ordinal: int) -> SourceRecord | None:
    text = _flatten_text(_first(row, cfg.text_fields)).strip()
    if not text:
        return None
    source_id = _first(row, cfg.id_fields)
    if not source_id:
        source_id = sha256(f"{origin}:{ordinal}:{text[:1000]}".encode()).hexdigest()[:20]
    metadata = {k: v for k, v in row.items() if k not in set(cfg.text_fields)}
    return SourceRecord(
        source_id=str(source_id),
        title=_flatten_text(_first(row, cfg.title_fields)).strip(),
        text=text[: cfg.max_record_chars],
        source=_flatten_text(_first(row, cfg.source_fields)).strip(),
        url=(str(_first(row, cfg.url_fields)) if _first(row, cfg.url_fields) else None),
        date=(str(_first(row, cfg.date_fields)) if _first(row, cfg.date_fields) else None),
        metadata={"origin": origin, **metadata},
    )


class CorpusStore:
    def __init__(self, path: Path, snippet_chars: int = 1200):
        self.path = path
        self.snippet_chars = snippet_chars
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def close(self) -> None:
        self.conn.close()

    def _init_db(self) -> None:
        self.conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS sources (
                source_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                text TEXT NOT NULL,
                source TEXT NOT NULL,
                url TEXT,
                date TEXT,
                metadata_json TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS sources_fts USING fts5(
                source_id UNINDEXED, title, text, source, content='sources', content_rowid='rowid'
            );
            CREATE TRIGGER IF NOT EXISTS sources_ai AFTER INSERT ON sources BEGIN
              INSERT INTO sources_fts(rowid, source_id, title, text, source)
              VALUES (new.rowid, new.source_id, new.title, new.text, new.source);
            END;
            CREATE TRIGGER IF NOT EXISTS sources_ad AFTER DELETE ON sources BEGIN
              INSERT INTO sources_fts(sources_fts, rowid, source_id, title, text, source)
              VALUES ('delete', old.rowid, old.source_id, old.title, old.text, old.source);
            END;
            CREATE TRIGGER IF NOT EXISTS sources_au AFTER UPDATE ON sources BEGIN
              INSERT INTO sources_fts(sources_fts, rowid, source_id, title, text, source)
              VALUES ('delete', old.rowid, old.source_id, old.title, old.text, old.source);
              INSERT INTO sources_fts(rowid, source_id, title, text, source)
              VALUES (new.rowid, new.source_id, new.title, new.text, new.source);
            END;
            """
        )
        self.conn.commit()

    def add(self, record: SourceRecord) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO sources(source_id,title,text,source,url,date,metadata_json)
               VALUES(?,?,?,?,?,?,?)""",
            (
                record.source_id,
                record.title,
                record.text,
                record.source,
                record.url,
                record.date,
                json.dumps(record.metadata, ensure_ascii=False, default=str),
            ),
        )

    def commit(self) -> None:
        self.conn.commit()

    def count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0])

    def get(self, source_id: str) -> SourceRecord | None:
        row = self.conn.execute("SELECT * FROM sources WHERE source_id=?", (source_id,)).fetchone()
        if not row:
            return None
        return SourceRecord(
            source_id=row["source_id"],
            title=row["title"],
            text=row["text"],
            source=row["source"],
            url=row["url"],
            date=row["date"],
            metadata=json.loads(row["metadata_json"]),
        )

    def get_by_offset(self, offset: int) -> SourceRecord:
        row = self.conn.execute("SELECT source_id FROM sources ORDER BY source_id LIMIT 1 OFFSET ?", (offset,)).fetchone()
        if not row:
            raise CorpusError(f"no source at offset {offset}")
        record = self.get(row["source_id"])
        assert record is not None
        return record

    def search(self, query: str, limit: int = 5, exclude_ids: Iterable[str] = ()) -> list[dict[str, Any]]:
        tokens = [token.strip("()[]{}:;,+-*/\\") for token in query.replace('"', " ").split()]
        tokens = [token for token in tokens if token]
        if not tokens:
            return []
        fts_query = " OR ".join(f'"{token}"' for token in tokens[:24])
        rows = self.conn.execute(
            """SELECT s.source_id,s.title,s.source,s.date,s.url,s.text,bm25(sources_fts) AS score
               FROM sources_fts JOIN sources s ON s.rowid=sources_fts.rowid
               WHERE sources_fts MATCH ? ORDER BY score LIMIT ?""",
            (fts_query, max(limit * 3, limit)),
        ).fetchall()
        excluded = set(exclude_ids)
        out = []
        for row in rows:
            if row["source_id"] in excluded:
                continue
            out.append(
                {
                    "source_id": row["source_id"],
                    "title": row["title"],
                    "source": row["source"],
                    "date": row["date"],
                    "url": row["url"],
                    "snippet": row["text"][: self.snippet_chars],
                    "score": row["score"],
                }
            )
            if len(out) >= limit:
                break
        return out


def build_index(cfg: CorpusConfig, replace: bool = False) -> tuple[CorpusStore, int]:
    if replace:
        for suffix in ("", "-wal", "-shm"):
            path = Path(str(cfg.index_path) + suffix)
            if path.exists():
                path.unlink()
    store = CorpusStore(cfg.index_path, snippet_chars=cfg.search_snippet_chars)
    added = 0
    for input_path in cfg.input_paths:
        paths = [input_path]
        if input_path.is_dir():
            paths = sorted(
                p
                for p in input_path.rglob("*")
                if p.suffix.lower() in {".jsonl", ".ndjson", ".json", ".yaml", ".yml"}
            )
        for path in paths:
            if not path.exists():
                continue
            for i, row in enumerate(iter_rows(path)):
                record = normalize_row(row, cfg, str(path), i)
                if record:
                    store.add(record)
                    added += 1
    store.commit()
    return store, added
