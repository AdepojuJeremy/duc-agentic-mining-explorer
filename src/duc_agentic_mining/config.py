from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator


class ModelRoleConfig(BaseModel):
    model: str
    concurrency: int = Field(default=4, ge=1, le=128)
    max_output_tokens: int = Field(default=5000, ge=256)
    reasoning_effort: Literal["none", "low", "medium", "high", "xhigh", "max"] | None = None
    temperature: float | None = None


class OpenAIConfig(BaseModel):
    api_key_env: str = "OPENAI_API_KEY"
    base_url: str | None = None
    timeout_seconds: float = Field(default=180.0, gt=0)
    max_retries: int = Field(default=5, ge=1, le=12)


class CorpusConfig(BaseModel):
    index_path: Path = Path("data/index/sources.sqlite")
    input_paths: list[Path] = Field(default_factory=list)
    id_fields: list[str] = Field(default_factory=lambda: ["id", "source_id", "uuid", "doc_id"])
    title_fields: list[str] = Field(default_factory=lambda: ["title", "name", "document_title"])
    text_fields: list[str] = Field(default_factory=lambda: ["text", "content", "body", "document", "recommendation", "passage"])
    source_fields: list[str] = Field(default_factory=lambda: ["source", "publisher", "organization"])
    url_fields: list[str] = Field(default_factory=lambda: ["url", "source_url", "link"])
    date_fields: list[str] = Field(default_factory=lambda: ["date", "published_at", "year"])
    max_record_chars: int = Field(default=160_000, ge=1_000)
    search_snippet_chars: int = Field(default=1_200, ge=200)


class ExplorationConfig(BaseModel):
    max_rounds: int = Field(default=1600, ge=1)
    round_batch_size: int = Field(default=50, ge=1)
    max_turns_per_round: int = Field(default=32, ge=1)
    max_searches_per_round: int = Field(default=6, ge=0)
    max_opens_per_round: int = Field(default=10, ge=0)
    max_candidates_per_round: int = Field(default=3, ge=1)
    max_results_per_search: int = Field(default=5, ge=1, le=20)
    random_seed: int = 42
    trace_include_tool_outputs: bool = False


class ValidationConfig(BaseModel):
    max_input_chars: int = Field(default=400_000, ge=10_000)


class GenerationConfig(BaseModel):
    max_drafts_per_candidate: int = Field(default=3, ge=1, le=8)
    max_source_chars_each: int = Field(default=120_000, ge=5_000)


class DedupConfig(BaseModel):
    enabled: bool = True
    lexical_similarity_threshold: float = Field(default=0.92, gt=0, le=1)


class PipelineConfig(BaseModel):
    project_root: Path = Path(".")
    output_root: Path = Path("runs")
    target_passed: int = Field(default=1200, ge=1)
    corpus: CorpusConfig = Field(default_factory=CorpusConfig)
    openai: OpenAIConfig = Field(default_factory=OpenAIConfig)
    roles: dict[str, ModelRoleConfig]
    exploration: ExplorationConfig = Field(default_factory=ExplorationConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    generation: GenerationConfig = Field(default_factory=GenerationConfig)
    dedup: DedupConfig = Field(default_factory=DedupConfig)

    @model_validator(mode="after")
    def required_roles(self) -> "PipelineConfig":
        missing = {"explorer", "validator", "generator", "reviewer"} - set(self.roles)
        if missing:
            raise ValueError(f"missing role configs: {sorted(missing)}")
        return self


def load_config(path: Path) -> PipelineConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cfg = PipelineConfig.model_validate(data)
    base = path.parent.resolve()
    cfg.corpus.input_paths = [((base / p).resolve() if not p.is_absolute() else p) for p in cfg.corpus.input_paths]
    if not cfg.corpus.index_path.is_absolute():
        cfg.corpus.index_path = (base / cfg.corpus.index_path).resolve()
    if not cfg.output_root.is_absolute():
        cfg.output_root = (base / cfg.output_root).resolve()
    return cfg
