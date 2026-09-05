# DUC Agentic Mining Explorer

A standalone, resumable **agentic source-mining → candidate validation → locked vignette construction → independent grounding review** pipeline for building staged clinical decision-update datasets.

This repository reconstructs the comprehensive agentic explorer used in the earlier DUC team-review workflow while making the implementation explicit, testable, OpenAI-native, and aware of decision-domain coverage and source authority/currentness.

## Dataset axes

The formal dataset is organized across **six clinical decision domains** and **three DUC evidence taxonomies**.

### Six decision domains

1. `diagnosis`
2. `treatment_selection`
3. `triage_urgency`
4. `medication_safety`
5. `public_health_advice`
6. `patient_counselling`

### Three evidence taxonomies

1. `contradictory`
2. `complicating`
3. `uncertainty_inducing`

No-conflict, weak-evidence, irrelevant-evidence, or framing variants can be added as controls, but they are **not a fourth DUC taxonomy**.

For a 1,200-item equal build, the pipeline allocates the exact total across the 18 domain × taxonomy cells. Because 1,200 is not divisible by 18, cells receive either 66 or 67 accepted items.

## Pipeline

```text
Trusted / versioned clinical source corpus
        │
        ▼
6 × 3 coverage planner
        │
        ▼
Agentic exploration rounds
(search → open → search → record candidate)
        │
        ▼
Independent route validation
(same decision + warrant + applicability + source policy)
        │
        ▼
Locked construction record
(domain + fixed question + stage evidence + transition + components + premises)
        │
        ▼
Source-grounded vignette generation
        │
        ▼
Deterministic integrity checks + independent grounding review
        │
        ├── repair and retry when local defects are fixable
        └── send back to route validation when the route itself is suspect
        │
        ▼
Balanced, deduplicated passed_vignettes.jsonl
```

A candidate is never treated as accepted merely because the explorer recorded it. Likewise, a vignette can be textually grounded yet fail because the underlying route mixes decisions, populations, indications, care stages, or source authority/currentness.

## Source-first policy

The miner treats **Meditron / EPFL guideline collections as seed corpora, not final sources of truth**. When source metadata permits, the underlying organization is classified separately from the seed collection.

The default source hierarchy is:

- **Tier 1 — primary guideline authorities:** NICE, WHO, CDC, USPSTF, IDSA, Ontario Health / Cancer Care Ontario, and comparable specialty guideline authorities;
- **Tier 2 — structured biomedical knowledge bases:** UMLS, SNOMED CT, RxNorm, DrugBank;
- **Tier 3 — primary literature:** PubMed / PMC and comparable primary evidence;
- **Tier 4 — secondary / aggregated clinical sources:** AAFP, CPS, GuidelineCentral, MAGIC, RCH Melbourne, StatPearls, and similar resources;
- **Tier 5 — patient-facing / fallback sources:** Mayo Clinic, MedlinePlus, WikiDoc.

Tier 2 and Tier 5 sources are useful for grounding, normalization, or explanatory support but are blocked from silently becoming the final Stage-1 decision authority. Primary literature may support recent updates or evidence checks, but a study finding is not automatically treated as a guideline recommendation.

Source metadata tracks organization, tier, source kind, date/status, freshness verification, Meditron seed status, and a redistribution-review hint. These redistribution fields are workflow hints, not legal determinations. See `docs/SOURCE_POLICY.md`.

## Outputs

Each run writes:

```text
runs/<run-id>/
├── candidates.yaml
├── validations.yaml
├── vignette_proposals.yaml
├── proposal_reviews.yaml
├── passed_vignettes.jsonl
├── target_matrix.yaml
├── metrics.yaml
├── run_manifest.yaml
└── trajectories/
    └── round_000001.jsonl
```

`target_matrix.yaml` reports accepted counts by domain, evidence taxonomy, and domain × taxonomy cell.

Runs are resumable: reuse the same `--run-id` and already-completed candidate, validation, generation, and review work is loaded from disk.

## What the explorer does

Each independent exploration round starts from one anchor source and, when balanced mining is enabled, receives a target domain × taxonomy cell. The OpenAI model can call four local tools:

- `search_sources(query, limit)` — SQLite FTS5 search over the trusted corpus, returning source-authority metadata with each hit;
- `open_source(source_id)` — retrieve the exact normalized source record;
- `record_candidate(...)` — propose a stageable evidence route with decision domain and evidence taxonomy;
- `finish_round(reason)` — terminate the round cleanly.

The explorer is sequential **within** a round because later searches depend on earlier findings, while independent rounds run concurrently.

## Candidate validation

Every candidate is independently checked on seven construction gates:

1. same clinical decision;
2. source support;
3. defensible Stage-1 recommendation;
4. genuine Stage-2 update pressure;
5. coherent population / indication / timing / setting / subtype applicability;
6. coherent domain / evidence-taxonomy / update annotation;
7. source authority, status/currentness, and role.

All gates must pass for promotion. Deterministic source-policy rules can fail a route even if the model validator would otherwise promote it.

## Controlled vignette construction

The generator receives only the validated route and exact source records. The construction is locked on:

- decision domain;
- fixed clinical question;
- Stage-1 and Stage-2 evidence;
- warranted update class;
- affected decision components;
- explicit scenario premises;
- source provenance and chronology.

The generator must keep **source facts** separate from **constructed scenario premises**. A guideline saying “if diagnosis X is confirmed, do Y” does not itself establish that the vignette patient has diagnosis X.

## Automated review

Before an item can enter `passed_vignettes.jsonl`, the pipeline checks:

- source fidelity;
- preservation of the same decision;
- cross-stage leakage;
- unsupported patient facts;
- answer cues;
- duplicated / redundant Stage-2 evidence;
- recommendation grounding;
- consistency of affected decision components;
- evidence-taxonomy / update consistency;
- source authority/currentness policy;
- provenance completeness.

Repairable wording or grounding defects can trigger another draft. Route-level defects can trigger candidate revalidation.

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

For the 1,200-item run, edit `config/makeup_1200.yaml` so `corpus.input_paths` points at the Meditron/EPFL guideline snapshot and any refreshed primary-source exports you have available, then:

```bash
duc-agentic index config/makeup_1200.yaml --replace
```

All configured source files are normalized into one local SQLite FTS5 index. No external vector database is required.

## Smoke test

```bash
duc-agentic mine config/ad_hoc.example.yaml \
  --run-id smoke-001 \
  --target-passed 3
```

## 1,200-item makeup run

`config/makeup_1200.yaml` is intentionally practical rather than publication-grade. It records source authority/currentness and blocks obvious source-role misuse, but does not require a live primary-source refresh for every contradictory route.

```bash
duc-agentic index config/makeup_1200.yaml --replace

duc-agentic mine config/makeup_1200.yaml \
  --run-id makeup-1200 \
  --target-passed 1200
```

The run plans against the 18 domain × taxonomy cells and stops when all 1,200 balanced accepted slots are filled or the configured exploration ceiling is reached.

If the run stops with `target_reached: false`, inspect `target_matrix.yaml` to see which cells are under-filled, inspect `metrics.yaml`, increase `exploration.max_rounds`, and rerun **with the same run id**.

## Model choice

The repository is model-ID driven. `config/makeup_1200.yaml` uses `gpt-5.6-luna` for low-cost/high-volume work. For a stronger but more expensive run, change `validator` and `reviewer` (and optionally `explorer`) to `gpt-5.6-terra`.

## Throughput controls

Concurrency is role-specific:

```yaml
roles:
  explorer:  {concurrency: 8, ...}
  validator: {concurrency: 6, ...}
  generator: {concurrency: 6, ...}
  reviewer:  {concurrency: 6, ...}
```

Increase these only if your OpenAI project rate limits support it. API inference is remote; local hardware mainly affects corpus indexing, SQLite search, serialization, and orchestration.

## Metrics

`metrics.yaml` records exploration, candidate, validation, generation, review, repair, API-token, error, elapsed-time, domain, evidence-taxonomy, and domain × taxonomy counts.

These numbers are sufficient to estimate accepted-route throughput and identify hard-to-fill cells rather than guessing from hardware.

## Tests

```bash
pytest -q
ruff check .
```

## Notes

- The pipeline is a dataset-construction tool, not a clinical authority.
- `passed_vignettes.jsonl` means automated route + grounding checks passed; it does not imply clinician gold review.
- Source records are not committed by default. `data/raw/`, local indexes, API credentials, and run outputs are git-ignored.
