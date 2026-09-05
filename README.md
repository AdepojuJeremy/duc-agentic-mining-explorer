# DUC Agentic Mining Explorer

A standalone, resumable **agentic source-mining → candidate validation → vignette generation → independent grounding review** pipeline for building staged clinical decision-update datasets.

This repository reconstructs the comprehensive agentic explorer used in the earlier DUC team-review workflow while making the implementation explicit, testable, and OpenAI-native.

## Pipeline

```text
Trusted local source corpus
        │
        ▼
Agentic exploration rounds
(search → open → search → record candidate)
        │
        ▼
Six-gate candidate validation
        │
        ▼
Source-grounded vignette generation
        │
        ▼
Independent grounding / structural review
        │
        ├── repair and retry when local defects are fixable
        └── send back to candidate validation when the route itself is suspect
        │
        ▼
Deduplicated passed_vignettes.jsonl
```

A candidate is never treated as accepted merely because the explorer recorded it. Likewise, a vignette can be textually grounded yet fail because the underlying route mixes decisions, populations, indications, or care stages.

## Outputs

Each run writes the same core artifacts expected from the earlier team-review pipeline:

```text
runs/<run-id>/
├── candidates.yaml
├── validations.yaml
├── vignette_proposals.yaml
├── proposal_reviews.yaml
├── passed_vignettes.jsonl
├── metrics.yaml
├── run_manifest.yaml
└── trajectories/
    └── round_000001.jsonl
```

Runs are resumable: reuse the same `--run-id` and already-completed candidate, validation, generation, and review work is loaded from disk.

## What the explorer does

Each independent exploration round starts from one anchor source. The OpenAI model can call four local tools:

- `search_sources(query, limit)` — SQLite FTS5 search over the trusted corpus;
- `open_source(source_id)` — retrieve the exact normalized source record;
- `record_candidate(...)` — propose a stageable evidence route;
- `finish_round(reason)` — terminate the round cleanly.

The explorer is sequential **within** a round because later searches depend on earlier findings, while independent rounds run concurrently.

## Candidate validation

Every candidate is independently checked on six construction gates:

1. same clinical decision;
2. source support;
3. defensible Stage-1 recommendation;
4. genuine Stage-2 update pressure;
5. coherent population / indication / timing / setting / subtype applicability;
6. coherent evidence-arm and update-class annotation.

All six gates must pass for promotion.

## Vignette generation and review

The generator receives only the validated route and exact source records. It must keep **source facts** separate from **constructed scenario premises**. For example, a guideline saying “if diagnosis X is confirmed, do Y” does not itself establish that the vignette patient has diagnosis X.

The independent reviewer checks source fidelity, same-decision preservation, Stage-1 leakage, unsupported patient facts, recommendation grounding, label consistency, and provenance. Repairable wording/grounding defects can trigger another draft. Route-level defects can trigger candidate revalidation.

## OpenAI implementation

The explorer uses the OpenAI **Responses API function-calling** loop. Validator, generator, and reviewer outputs use strict JSON Schema so pipeline state is machine-readable rather than parsed from free-form prose.

The API key is read from the environment only; it is never written to run artifacts.

## Install

Python 3.11+ is recommended.

```bash
git clone https://github.com/AdepojuJeremy/duc-agentic-mining-explorer.git
cd duc-agentic-mining-explorer
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\\Scripts\\activate
pip install -e '.[dev]'
```

Set the API key:

```bash
export OPENAI_API_KEY='YOUR_KEY'
```

Do not commit the key.

## Index your source corpus

The corpus loader accepts JSONL/NDJSON, JSON, YAML, or YML and uses configurable field-name fallbacks.

For the included demo:

```bash
duc-agentic index config/ad_hoc.example.yaml --replace
```

For your guideline dataset, edit `config/makeup_1200.yaml` so `corpus.input_paths` points at the local source file, then:

```bash
duc-agentic index config/makeup_1200.yaml --replace
```

The local index is SQLite FTS5, so no external vector database is required for the explorer.

## Smoke test

Do a small run first by temporarily setting `target_passed: 3` and `exploration.max_rounds: 20`, or override only the final target:

```bash
duc-agentic mine config/ad_hoc.example.yaml \
  --run-id smoke-001 \
  --target-passed 3
```

## 1,200-item makeup run

`config/makeup_1200.yaml` is intentionally practical rather than publication-grade. It uses the cost-sensitive OpenAI model for all four roles and mines in waves until either 1,200 reviewer-passed, deduplicated items are reached or the configured `max_rounds` safety cap is exhausted.

```bash
duc-agentic index config/makeup_1200.yaml --replace

duc-agentic mine config/makeup_1200.yaml \
  --run-id makeup-1200 \
  --target-passed 1200
```

If the run stops with `target_reached: false`, inspect `metrics.yaml`, increase `exploration.max_rounds`, and rerun **with the same run id**. The pipeline resumes from existing artifacts rather than starting over.

## Model choice

The repository is model-ID driven. `config/makeup_1200.yaml` currently uses `gpt-5.6-luna` for low-cost/high-volume work. For a stronger but more expensive run, change `validator` and `reviewer` (and optionally `explorer`) to `gpt-5.6-terra`.

## Throughput controls

Concurrency is role-specific:

```yaml
roles:
  explorer:  {concurrency: 8, ...}
  validator: {concurrency: 6, ...}
  generator: {concurrency: 6, ...}
  reviewer:  {concurrency: 6, ...}
```

Increase these only if your OpenAI project rate limits support it. API inference is remote; local hardware mainly affects corpus indexing, SQLite search, serialization, and the Python orchestration process.

## Metrics

`metrics.yaml` records:

- exploration rounds started/completed;
- search/open counts;
- candidate count and unique source-pair count;
- validator promotions;
- proposal generation, review, repair, and pass counts;
- request counts by role;
- input/output/cached tokens by role;
- API errors and elapsed wall time.

These numbers are sufficient to estimate accepted-route throughput and scale a later run without guessing from hardware.

## Tests

```bash
pytest -q
ruff check .
```

## Notes

- The pipeline is a dataset-construction tool, not a clinical authority.
- `passed_vignettes.jsonl` means automated route + grounding checks passed; it does not imply clinician gold review.
- Source records are not committed by default. `data/raw/`, local indexes, API credentials, and run outputs are git-ignored.
