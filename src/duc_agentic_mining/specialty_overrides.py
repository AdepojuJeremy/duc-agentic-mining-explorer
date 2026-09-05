from __future__ import annotations

from .catalogue_acquisition import CatalogueAcquisitionConfig


def apply_specialty_catalogue_overrides(
    cfg: CatalogueAcquisitionConfig,
) -> CatalogueAcquisitionConfig:
    """Apply source-specific fixes for catalogues that need non-generic discovery."""
    acr = cfg.catalogues.get("acr")
    if acr is not None:
        # The public ACR /list endpoint currently rejects automated fetches, while
        # individual TopicNarrativePdf endpoints remain publicly retrievable.
        # Enumerating the documented topic-id endpoint preserves official-source
        # retrieval without bypassing access controls.
        acr.seed_urls = [
            f"https://acsearch.acr.org/list/TopicNarrativePdf?topicId={topic_id}"
            for topic_id in range(1, 321)
        ]
        acr.allowed_hosts = ["acsearch.acr.org"]
        acr.crawl_patterns = []
        acr.record_patterns = [r"TopicNarrativePdf\?topicId="]
        acr.required_text_patterns = [
            r"ACR|American College of Radiology|Appropriateness Criteria"
        ]
        acr.max_depth = 0
        acr.max_pages = 320
        acr.max_records = 300
        acr.rate_limit_per_second = 1.0
        acr.allow_pdfs = True

    ismp = cfg.catalogues.get("ismp")
    if ismp is not None:
        # ISMP moved its public guidance catalogue to the ECRI site in 2026.
        ismp.seed_urls = [
            "https://home.ecri.org/blogs/ismp-resources",
            "https://home.ecri.org/blogs/ismp-resources/targeted-medication-safety-best-practices-for-hospitals",
        ]
        ismp.allowed_hosts = ["home.ecri.org"]
        ismp.crawl_patterns = [r"/blogs/ismp-resources"]
        ismp.record_patterns = [r"/blogs/ismp-resources/.+"]
        ismp.required_text_patterns = [
            r"ISMP|Institute for Safe Medication Practices|medication safety"
        ]
        ismp.max_depth = 2
        ismp.max_pages = 120
        ismp.max_records = 80
        ismp.rate_limit_per_second = 0.75
        # Keep this conservative: use current public landing-page guidance text
        # rather than automatically mirroring downloadable files.
        ismp.allow_pdfs = False

    return cfg
