from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer
from rich.console import Console

from .config import load_config
from .corpus import build_index
from .derived_metrics import enrich_metrics_file, record_human_review
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
    derived = enrich_metrics_file(
        pipeline.paths.metrics,
        concurrent_anchor_rounds=cfg.roles["explorer"].concurrency,
    )
    summary["derived_metrics"] = derived
    console.print(json.dumps(summary, indent=2))


@app.command("metrics")
def metrics_report(
    config: Path,
    run_id: str = typer.Option(..., help="Run identifier whose metrics should be refreshed."),
) -> None:
    """Recompute and persist scaling/throughput statistics in metrics.yaml."""
    cfg = load_config(config)
    metrics_path = cfg.output_root / run_id / "metrics.yaml"
    derived = enrich_metrics_file(
        metrics_path,
        concurrent_anchor_rounds=cfg.roles["explorer"].concurrency,
    )
    console.print(json.dumps(derived, indent=2))


@app.command("record-human-review")
def record_human_review_counts(
    config: Path,
    run_id: str = typer.Option(..., help="Run identifier to attach human review counts to."),
    reviewed: int = typer.Option(..., min=0, help="Number of routes reviewed by humans."),
    accepted: int = typer.Option(..., min=0, help="Number of human-reviewed routes accepted."),
) -> None:
    """Record optional human-review counts and refresh human_acceptance_rate."""
    cfg = load_config(config)
    run_dir = cfg.output_root / run_id
    try:
        record_human_review(run_dir, reviewed=reviewed, accepted=accepted)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    derived = enrich_metrics_file(
        run_dir / "metrics.yaml",
        concurrent_anchor_rounds=cfg.roles["explorer"].concurrency,
    )
    console.print(json.dumps(derived, indent=2))


@app.command("validate-config")
def validate_config(config: Path) -> None:
    cfg = load_config(config)
    console.print(cfg.model_dump_json(indent=2))


if __name__ == "__main__":
    app()
