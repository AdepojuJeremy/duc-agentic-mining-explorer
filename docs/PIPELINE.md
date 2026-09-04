# Pipeline contract

## 1. Exploration

Each round starts with one anchor source and a bounded tool budget. The explorer may search the indexed corpus, open exact records, and record up to the configured number of candidate evidence routes. Candidate creation is intentionally permissive: it captures promising routes for an independent validator rather than pretending exploration is adjudication.

## 2. Six-gate route validation

A route is promoted only when all six gates pass: same decision, source support, defensible Stage 1, genuine update pressure, applicability coherence, and arm/update coherence. The validator is instructed to fail closed on population leakage, different decisions, optional-vs-default distortions, unframed temporal supersession, and unsupported patient facts.

## 3. Vignette construction

The generator constructs a fixed clinical decision question with Stage 1 evidence and a Stage 2 update. It must distinguish source-grounded facts from constructed scenario premises. Scenario premises are explicit and reviewable rather than smuggled into the vignette as if they appeared in the source.

## 4. Independent grounding review

The reviewer checks source fidelity, route integrity, Stage-1 leakage, unsupported facts, recommendation grounding, taxonomy consistency, and provenance. Local construction defects can be repaired. Route-level defects request candidate revalidation.

## 5. Release artifact

`passed_vignettes.jsonl` contains automatically passed, deduplicated proposals. It is suitable as a generated dataset artifact, but the pipeline deliberately does not label automated passage as clinician gold.
