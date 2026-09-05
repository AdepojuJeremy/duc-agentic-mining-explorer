# Specialty and regulatory catalogue acquisition

`duc-agentic sources status/sync config/sources.yaml` automatically loads the specialty catalogue configuration in `config/specialty_catalogues.yaml` and `config/specialty_catalogues_extra.yaml`.

The catalogue layer is intentionally constrained:

- only explicitly configured official seed pages are used;
- only explicitly allow-listed official hosts can be followed;
- URL allow/deny patterns constrain discovery to guideline/safety areas;
- `robots.txt` is respected;
- 401/402/403 access controls are not bypassed;
- blocked sources are reported as `blocked_by_source` and the remaining jobs continue;
- rate limits, page caps, depth caps, and record caps are source-specific;
- every stored record carries retrieval provenance and the output snapshot is hashed in the shared source manifest.

## Implemented catalogue authorities

| Job | Authority | Primary role | Seed catalogue |
|---|---|---|---|
| `uspstf` | USPSTF | prevention, screening, counselling | Recommendation Topics / published topic search |
| `idsa` | IDSA | infectious-disease diagnosis/treatment/safety | All Practice Guidelines |
| `ontario_health` | Ontario Health / Cancer Care Ontario | oncology diagnosis/treatment/counselling | Guidelines & Advice |
| `acr` | American College of Radiology | diagnostic imaging / interventional decisions | ACR Appropriateness Criteria + AC Search |
| `acc_aha` | ACC / AHA | cardiovascular diagnosis/treatment/counselling | ACC Guidelines + AHA Guidelines & Statements |
| `asco` | ASCO | oncology treatment/diagnosis/counselling | ASCO guideline area |
| `acog` | ACOG | obstetric/gynecologic diagnosis/treatment/counselling | Clinical Guidance |
| `aap` | AAP | pediatric diagnosis/treatment/triage/counselling | Clinical Practice Guidelines |
| `kdigo` | KDIGO | kidney-disease diagnosis/treatment/counselling | KDIGO Guidelines |
| `gina` | GINA | asthma diagnosis/treatment/counselling | GINA Reports |
| `gold` | GOLD | COPD diagnosis/treatment/counselling | GOLD Report/Pocket Guide landing pages |
| `acep` | ACEP | emergency diagnosis/treatment/triage | Clinical Policies |
| `resuscitation` | Resuscitation Council UK / ILCOR | resuscitation / triage | 2025 Resuscitation Guidelines |
| `mhra` | MHRA | medication safety | Drug Safety Update / product-specific safety collections |
| `ema` | EMA | medication safety / regulatory product information | Medicines + pharmacovigilance/safety pages |
| `ecdc` | ECDC | infectious-disease/public-health guidance | Publications & Data |
| `ukhsa` | UKHSA | infectious disease/public-health guidance | UKHSA organisation/collection pages |
| `africa_cdc` | Africa CDC | public-health guidance | Resources / guidelines |
| `who_icrc_emergency` | WHO / ICRC emergency care | triage and emergency treatment | IITT, Emergency Care Toolkit, Basic Emergency Care |
| `ismp` | ISMP | medication safety | ISMP guidelines/resources |

## Copyright/access-sensitive sources

The crawler does not treat public visibility as blanket redistribution permission.

For GINA, GOLD, AAP, ACOG, and ASCO, the default configuration is conservative: public landing/page text is captured where accessible, while report PDFs are not automatically mirrored unless the source is configured to permit PDF retrieval. If a site blocks automated access, the job reports the block rather than attempting to bypass it.

The same principle applies to any future source added to this layer.

## BNF

BNF is present in the authoritative-source registry as a licensed Tier-1 medication source. It is **not** implemented as a public catalogue crawler because applicable BNF access is licence/API-dependent. It should only be enabled through the applicable licensed endpoint/credential (for example `BNF_API_KEY`) once that access is configured. The public-web crawler must not be used as a substitute for licensed BNF access.

## Currentness semantics

A live successful fetch establishes that the material came from the official source at the recorded retrieval time. It does **not** by itself establish that every document is the current recommendation for a clinical decision.

Catalogue records therefore set:

- `primary_source_verified: true`;
- `live_primary_retrieval: true`;
- `freshness_verified: false` by default;
- `source_status: versioned` only when a response date/version signal is available, otherwise `unknown`.

The downstream validator still decides whether chronology, status, population, indication, and authority are suitable for a DUC route.

## Commands

Check all API/bulk and catalogue sources:

```bash
duc-agentic sources status config/sources.yaml
```

Sync everything enabled:

```bash
duc-agentic sources sync config/sources.yaml
```

Sync selected specialty sources:

```bash
duc-agentic sources sync config/sources.yaml \
  --only idsa \
  --only acr \
  --only kdigo \
  --only ismp
```

On completion, snapshots are written under `data/raw/primary/` or `data/raw/regulatory/` and are automatically included by the existing `config/makeup_1200.yaml` recursive input directories when the corpus index is rebuilt.
