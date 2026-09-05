from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer
from rich.console import Console

from .acquisition import load_source_config, source_status, sync_sources
from .catalogue_acquisition import catalogue_status, load_catalogue_config, sync_catalogues
from .config import load_config
from .corpus import build_index
from .derived_metrics import enrich_metrics_file, record_human_review
from .nice_public import annotate_nice_status, apply_nice_public_fallback
from .pipeline import AgenticMiningPipeline

app = typer.Typer(no_args_is_help=True, help="DUC comprehensive agentic source-mining explorer")
sources_app = typer.Typer(no_args_is_help=True, help="Acquire and inspect external clinical sources.")
app.add_typer(sources_app, name="sources")
console = Console()


def _load_catalogues_for_source_config(config: Path):
    sibling = config.parent / "specialty_catalogues.yaml"
    return load_catalogue_config(sibling if sibling.exists() else config)


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


@sources_app.command("status")
def sources_status(config: Path) -> None:
    """Show API/bulk and specialty-catalogue source readiness."""
    cfg = load_source_config(config)
    catalogue_cfg = _load_catalogues_for_source_config(config)
    rows = annotate_nice_status(cfg, source_status(cfg))
    rows.update(catalogue_status(catalogue_cfg))
    console.print(json.dumps(rows, indent=2))


@sources_app.command("sync")
def sources_sync(
    config: Path,
    only: list[str] = typer.Option(
        [],
        "--only",
        help="Run only named source jobs. Repeat --only for multiple jobs.",
    ),
    force: bool = typer.Option(False, help="Re-download bulk seed files that already exist."),
) -> None:
    """Fetch/cache configured API sources and constrained specialty catalogues."""
    cfg = load_source_config(config)
    catalogue_cfg = _load_catalogues_for_source_config(config)
    known = set(cfg.sources) | set(catalogue_cfg.catalogues)
    unknown = sorted(set(only) - known)
    if unknown:
        raise typer.BadParameter(f"unknown source jobs: {unknown}")
    selected = set(only) or None
    result = sync_sources(cfg, only=selected, force=force)
    result = apply_nice_public_fallback(cfg, result, only=selected)
    result.update(sync_catalogues(catalogue_cfg, only=selected))
    console.print(json.dumps(result, indent=2))


@sources_app.command("download-meditron")
def download_meditron(
    config: Path,
    force: bool = typer.Option(False, help="Re-download even when a local snapshot exists."),
) -> None:
    """Convenience wrapper for the configured Meditron/Hugging Face seed job."""
    cfg = load_source_config(config)
    if "meditron" not in cfg.sources:
        raise typer.BadParameter("source config has no 'meditron' job")
    result = sync_sources(cfg, only={"meditron"}, force=force)
    console.print(json.dumps(result, indent=2))


@app.command("validate-config")
def validate_config(config: Path) -> None:
    cfg = load_config(config)
    console.print(cfg.model_dump_json(indent=2))


if __name__ == "__main__":
    app()
