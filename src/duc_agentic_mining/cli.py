from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer
from rich.console import Console

from .config import load_config
from .corpus import build_index
from .pipeline import AgenticMiningPipeline

app = typer.Typer(no_args_is_help=True, help="DUC comprehensive agentic source-mining explorer")
console = Console()


@app.command()
def index(
    config: Path,
    replace: bool = typer.Option(False, help="Rebuild the SQLite FTS index from scratch."),
) -> None:
    """Index configured JSON/JSONL/YAML source corpora into local SQLite FTS5."""
    cfg = load_config(config)
    store, added = build_index(cfg.corpus, replace=replace)
    console.print(
        json.dumps(
            {
                "index": str(cfg.corpus.index_path),
                "added_or_updated": added,
                "records": store.count(),
            },
            indent=2,
        )
    )
    store.close()


@app.command()
def mine(
    config: Path,
    run_id: str = typer.Option(..., help="Stable run identifier; reuse it to resume."),
    target_passed: int | None = typer.Option(
        None,
        min=1,
        help="Override the configured final passed-vignette target.",
    ),
) -> None:
    """Run/resume exploration → validation → generation → independent review."""
    cfg = load_config(config)
    pipeline = AgenticMiningPipeline(
        cfg,
        run_id=run_id,
        target_passed=target_passed,
    )
    summary = asyncio.run(pipeline.run())
    console.print(json.dumps(summary, indent=2))


@app.command("validate-config")
def validate_config(config: Path) -> None:
    cfg = load_config(config)
    console.print(cfg.model_dump_json(indent=2))


if __name__ == "__main__":
    app()
