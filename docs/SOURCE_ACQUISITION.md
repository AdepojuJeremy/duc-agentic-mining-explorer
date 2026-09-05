# Source acquisition and refresh

The DUC miner does not treat GitHub as a clinical data store. Raw source snapshots remain under `data/raw/` and are git-ignored. The repository contains the acquisition logic, configuration, provenance manifest, and indexing rules needed to reproduce a local corpus.

## Implemented adapters

| Job kind | Intended source | Access |
|---|---|---|
| `meditron` | EPFL/Meditron Guidelines Collection | public Hugging Face bulk download; `HF_TOKEN` optional |
| `nice` | NICE Guidance Data Service | licensed NICE Syndication API; `NICE_API_KEY` required |
| `who` | WHO publications | official WHO REST publication endpoint |
| `cdc` | CDC guidance/content | official CDC Content Services v2 API plus `/content` retrieval |
| `ncbi` | PubMed / PMC | NCBI E-utilities; `NCBI_API_KEY` optional but recommended; set `NCBI_EMAIL` |
| `openfda` | FDA drug labels/safety fields | openFDA; `OPENFDA_API_KEY` recommended for scale |
| `official_urls` | USPSTF, IDSA, ACR, ACC/AHA, ASCO, ACOG, AAP, KDIGO, GINA, GOLD, ACEP, MHRA, EMA, ECDC, UKHSA, Africa CDC, etc. | controlled retrieval of explicitly configured official HTML/PDF URLs |

The `official_urls` adapter intentionally does **not** spider arbitrary websites. Add current official guideline/document URLs in `config/sources.yaml`; the adapter retrieves HTML/PDF, extracts text, and records the final URL, content type, ETag/Last-Modified where present, retrieval time, and a snapshot hash in the manifest.

## Credentials

Keep all credentials in environment variables. Do not put them in YAML or commit them.

```bash
export OPENAI_API_KEY='...'
export NICE_API_KEY='...'
export NCBI_API_KEY='...'       # optional, recommended
export NCBI_EMAIL='you@example.org'
export OPENFDA_API_KEY='...'    # optional at low volume, recommended for scale
export HF_TOKEN='...'           # optional for the public Meditron dataset
```

Only `NICE_API_KEY` is marked as required by the default acquisition configuration. Missing optional credentials reduce rate limits but do not stop the whole sync. Missing required credentials produce `credential_missing` for that source job while other jobs continue.

## Check readiness

```bash
duc-agentic sources status config/sources.yaml
```

This reports each configured job, whether it is enabled, whether its output exists, and whether the configured credential environment variable is present.

## Download the Meditron seed

```bash
duc-agentic sources download-meditron config/sources.yaml
```

The default URL is the public `epfl-llm/guidelines` `open_guidelines.jsonl` snapshot. Re-download explicitly with:

```bash
duc-agentic sources download-meditron config/sources.yaml --force
```

## Sync official sources

Run all enabled jobs:

```bash
duc-agentic sources sync config/sources.yaml
```

Run only selected sources:

```bash
duc-agentic sources sync config/sources.yaml \
  --only nice \
  --only who \
  --only cdc \
  --only pubmed \
  --only pmc \
  --only openfda
```

Every source job writes an indexable JSONL snapshot and appends a snapshot event to:

```text
data/raw/manifests/source_manifest.jsonl
```

Manifest entries contain the source job, adapter kind, retrieval status, output path, byte size, SHA-256 hash, and record count where available.

## Default local layout

```text
data/raw/
├── epfl-llm-guidelines/
│   └── open_guidelines.jsonl
├── primary/
│   ├── nice/
│   ├── who/
│   ├── cdc/
│   └── ...
├── literature/
│   ├── pubmed_guidelines.jsonl
│   └── pmc_guidelines.jsonl
├── regulatory/
│   ├── fda/
│   ├── mhra/
│   └── ema/
└── manifests/
    └── source_manifest.jsonl
```

`config/makeup_1200.yaml` indexes the Meditron seed plus the `primary/`, `literature/`, and `regulatory/` directories, so newly acquired snapshots are automatically included on the next `duc-agentic index ... --replace`.

## Provenance and currentness

Acquired official-source records are normalized with:

- retrieval time;
- retrieval method;
- primary-source verification flag;
- freshness-verification flag;
- source/version status;
- official source URL;
- adapter-specific IDs and response metadata where available.

The corpus normalizer promotes nested acquisition metadata into `SourceRecord.metadata`, allowing the existing source-policy classifier and validator to see the freshness/currentness flags. A successful API fetch means the record came from the primary source at the recorded time; it does **not** imply every historical publication is clinically current. Publication/edition chronology still has to be validated for the route.

## NICE

The default NICE adapter starts from:

```text
https://api.nice.org.uk/services/guidance/index
```

It sends the licensed API key in the `API-Key` header and follows NICE guidance API links only within `api.nice.org.uk/services/guidance`, bounded by `max_pages` and `max_records`. API resources are cached as normalized JSONL records rather than committed to Git.

Your NICE licence terms remain authoritative for what may be stored, processed, or redistributed. The acquisition code does not override licence restrictions.

## NCBI

The PubMed/PMC adapter uses the official E-utilities base:

```text
https://eutils.ncbi.nlm.nih.gov/entrez/eutils/
```

The default configuration searches guideline/practice-guideline material and retrieves XML in batches. `NCBI_API_KEY` is optional but increases the supported request rate; `NCBI_EMAIL` is included when configured.

## CDC

The CDC adapter uses:

```text
https://tools.cdc.gov/api/v2/resources/media
```

It searches configured clinical terms, deduplicates CDC media IDs, and retrieves syndicated content from each media resource's `/content` endpoint.

## WHO

The WHO adapter uses the official publication REST collection and records official publication metadata/URLs. `follow_documents` can be enabled in the source job when a run should also retrieve linked publication documents; keep the record/page limits conservative when enabling it.

## FDA

The default FDA job uses the openFDA drug-label endpoint for warning, boxed-warning, drug-interaction, and contraindication fields. These are regulatory evidence sources; they do not automatically replace specialty clinical guidelines for treatment-selection targets.

## Specialty authorities

The domain registry already identifies the preferred specialty/regulatory authorities for the six DUC decision domains. Their `official_urls` jobs are present but disabled in `config/sources.yaml` until explicit current official URLs are supplied or a source-specific catalogue adapter is added.

This separation is deliberate:

1. registry = which organizations are authoritative for which decision domains;
2. acquisition = how we obtain a reproducible primary-source snapshot;
3. source policy = whether a particular document is suitable for the benchmark route;
4. miner = discovery, validation, construction, review, and balancing.
