# Source policy

This project uses a **source-first** construction strategy. Source type, authority, currentness, and redistribution status are tracked separately from the DUC evidence taxonomy.

The source hierarchy below is a curation policy, not a legal opinion and not a claim that every document from an organization has identical authority. Per-document applicability and currentness still require validation.

## Seed corpus

The Meditron / EPFL guideline collection is treated as a high-coverage **seed index**. It is useful for discovery because it aggregates tens of thousands of guideline documents, but it is not treated as the final source of truth.

When a record originates from a Meditron/EPFL snapshot, the pipeline records `seed_collection: Meditron Guidelines Collection` while separately classifying the underlying organization where possible.

For gold-quality use, stale or ambiguous seed records should be refreshed against the primary organization before a contradiction or temporal-revision label is finalized.

## Tier 1 — primary guideline authorities

Preferred for benchmark decision targets.

- NICE
- WHO
- CDC
- USPSTF
- IDSA
- Ontario Health / Cancer Care Ontario
- other specialty-society guideline authorities when explicitly identified
- ICRC for relevant humanitarian / field-medicine guidance

A Tier-1 label means the organization is normally capable of issuing authoritative clinical guidance. The actual document still has to be a recommendation-bearing guideline rather than a definition, evidence summary, implementation note, or background publication.

## Tier 2 — structured biomedical knowledge bases

Used primarily for normalization, terminology, entity linking, drug identity, and grounding.

- UMLS
- SNOMED CT
- RxNorm
- DrugBank

These sources should not silently become the final Stage-1 recommendation authority. They may support terminology, entity resolution, medication identity, or other structured facts.

## Tier 3 — primary literature

Used for recent evidence, evidence checks, systematic reviews, and issues not yet reflected in a guideline.

- PubMed
- PubMed Central
- primary studies
- systematic reviews
- case reports where clinically appropriate

A study result is not automatically equivalent to a guideline recommendation. The miner and validator must preserve that distinction.

## Tier 4 — secondary or aggregated clinical sources

Useful for discovery, secondary support, and cases where primary guidance is unavailable, with verification where possible.

- AAFP
- Canadian Paediatric Society
- GuidelineCentral
- MAGIC
- Royal Children's Hospital Melbourne
- StatPearls
- Drugs.com
- Canadian Medical Association
- SPOR

## Tier 5 — patient-facing or fallback sources

Useful for explanatory support, not final clinical authority.

- Mayo Clinic
- MedlinePlus
- WikiDoc

The default policy prevents Tier-5 material from serving as the final Stage-1 decision authority.

## Currentness and chronology

Each normalized source can carry:

- `date`;
- explicit source/guideline status when present;
- `freshness_verified` / `verified_current` metadata when provided by an ingestion step;
- a derived status of `current`, `versioned`, `stale_or_superseded`, or `unknown`.

A dated record is treated as **versioned**, not automatically current. Explicitly withdrawn, retired, obsolete, or superseded material fails source policy.

For stricter runs, set:

```yaml
source_policy:
  require_recommendation_authority_baseline: true
  require_known_currentness_for_contradictory: true
```

This prevents an unknown-status source pair from receiving a contradictory benchmark target without additional source verification.

## Recommendation authority versus other source roles

The miner must distinguish:

- recommendation statements;
- evidence summaries;
- definitions;
- implementation notes;
- terminology / entity records;
- patient-facing explanations.

Two passages can both be medically correct while carrying very different authority for a decision update. A route should only be promoted when Stage 1 supports an interpretable initial recommendation and Stage 2 provides a non-redundant evidential change relevant to the same fixed decision.

## Redistribution status

The pipeline records a coarse routing hint:

- `redistributable`;
- `restricted_or_check`;
- `unknown`.

These values are intended to help curation workflows decide whether to store full text, excerpts, metadata-only references, or source URLs. They are not legal determinations. Terms should be checked before redistributing source content.

## Suggested ingestion pattern

A practical corpus can combine:

1. Meditron / EPFL guideline snapshots for broad discovery;
2. refreshed exports or captured records from NICE, WHO, CDC, USPSTF, and specialty societies;
3. PubMed / PMC records retrieved through NCBI APIs for recent evidence;
4. structured KB records for entity normalization;
5. secondary/fallback sources only where their role is explicit.

All configured input files are normalized into the same local corpus index, so the explorer can search across them while retaining per-record provenance and source-policy metadata.
