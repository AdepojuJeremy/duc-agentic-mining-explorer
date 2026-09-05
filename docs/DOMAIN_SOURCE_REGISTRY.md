# Domain-aware authoritative source registry

DUC mining does not use one flat source hierarchy for every clinical question. Source authority is assessed at both the organization level and the document/topic level. The registry therefore tags primary authorities by the decision domains in which they are commonly relevant, while leaving the final route validator responsible for topic fit, population, chronology, recommendation status, and applicability.

## Core principles

- Meditron / EPFL is a discovery seed, not final recommendation authority.
- NICE is a first-class licensed Tier-1 source. The API key is expected in `NICE_API_KEY` and must never be committed.
- BNF is represented as a licensed medication source and remains disabled operationally until an applicable API licence/key is configured.
- Official APIs/feeds are preferred where available.
- Controlled retrieval from official guideline pages/PDFs is used where no suitable API exists, subject to source terms and rate limits.
- PubMed / PMC supports recency and evidence checks but does not automatically become guideline-level decision authority.
- Structured KBs such as UMLS, SNOMED CT and RxNorm are for terminology/entity/drug normalization rather than final recommendation authority.

## Decision-domain source map

### Diagnosis

Primary/high-authority candidates include:

- NICE
- WHO
- CDC
- USPSTF for screening/preventive diagnostic decisions
- IDSA for infectious diseases
- Ontario Health / Cancer Care Ontario for oncology
- ACR for diagnostic imaging and image-guided decisions
- ACC / AHA for cardiovascular diagnosis and evaluation
- ASCO for oncology
- ACOG for obstetrics/gynecology
- AAP for pediatrics
- KDIGO for kidney disease
- GINA for asthma
- GOLD for COPD
- ECDC / UKHSA / Africa CDC for relevant communicable-disease/public-health diagnostic guidance

### Treatment selection

Primary/high-authority candidates include:

- NICE
- WHO
- CDC where treatment guidance is explicitly issued
- IDSA
- Ontario Health / Cancer Care Ontario
- FDA / EMA / MHRA where regulatory status or safety changes affect therapy choice
- ACC / AHA
- ASCO
- ACOG
- AAP
- KDIGO
- GINA
- GOLD
- ACEP / WHO-ICRC emergency care for acute-care decisions

### Triage / urgency

Primary/high-authority candidates include:

- NICE
- WHO
- WHO / ICRC emergency-care guidance and the Interagency Integrated Triage Tool
- ACEP
- Resuscitation Council UK / ILCOR
- AAP for pediatric urgent-care topics

### Medication safety

Primary/high-authority candidates include:

- NICE
- FDA
- MHRA
- EMA
- BNF, when licensed API access is configured
- ISMP
- IDSA for antimicrobial-specific safety/selection questions

RxNorm and other structured drug resources may support identity/normalization but are not final recommendation authority.

### Public-health advice

Primary/high-authority candidates include:

- WHO
- CDC
- NICE where applicable
- USPSTF for preventive-service recommendations
- ECDC
- UKHSA
- Africa CDC

### Patient counselling

Primary/high-authority candidates include:

- NICE
- WHO
- CDC
- USPSTF
- Ontario Health / Cancer Care Ontario
- ACC / AHA
- ASCO
- ACOG
- AAP
- KDIGO
- GINA
- GOLD

Patient-facing summaries may help phrase information but should not silently override professional recommendation-bearing guidance.

## Access modes

The registry uses the following acquisition labels:

- `download_seed`: bulk seed corpus such as Meditron/EPFL;
- `licensed_api`: licensed feeds such as NICE and, where separately licensed, BNF;
- `official_api`: official public APIs/feeds such as CDC/WHO/FDA where appropriate;
- `ncbi_eutils`: PubMed/PMC retrieval through NCBI;
- `controlled_web`: official guideline index/page/PDF retrieval when no suitable public API is available;
- `structured_api`: terminology/knowledge-base services such as RxNorm/UMLS/SNOMED integrations.

These labels are acquisition strategies, not claims that all content from an organization may be redistributed. The pipeline retains a separate redistribution/licensing hint and provenance metadata.

## Explorer behavior

When a target DUC decision domain is supplied, the explorer receives the corresponding Tier-1 organization list as a search hint. The hint only applies when relevant records are present in the local corpus. It does not force a route to use a named organization, and document-level clinical relevance and authority take precedence.

## Acquisition layer

The registry is the authoritative source plan for the acquisition layer. Source adapters should normalize fetched material into records containing at least:

- `source_id`;
- canonical organization;
- title;
- text or permitted extract;
- source URL;
- publication/update date;
- retrieval timestamp;
- source/guideline status when available;
- `freshness_verified` / primary-source verification metadata;
- acquisition method;
- content hash/version identifier;
- redistribution/licensing hint.

The raw downloads and normalized source snapshots remain under `data/raw/` and stay git-ignored. Only acquisition code, source registry, configuration templates, and metadata schemas belong in Git.
