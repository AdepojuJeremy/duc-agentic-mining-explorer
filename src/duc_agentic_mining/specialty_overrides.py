from __future__ import annotations

from .catalogue_acquisition import CatalogueAcquisitionConfig


def apply_specialty_catalogue_overrides(
    cfg: CatalogueAcquisitionConfig,
) -> CatalogueAcquisitionConfig:
    """Apply source-specific fixes for catalogues that need non-generic discovery."""
    acr = cfg.catalogues.get("acr")
    if acr is not None:
        # The acsearch /list endpoint rejects urllib-based acquisition in some
        # environments. Use the public ACR AC Portal host instead, which serves
        # the same official TopicNarrativePdf documents.
        acr.seed_urls = [
            f"https://gravitas.acr.org/ACPortal/TopicNarrativePdf?topicId={topic_id}"
            for topic_id in range(1, 401)
        ]
        acr.allowed_hosts = ["gravitas.acr.org"]
        acr.crawl_patterns = []
        acr.record_patterns = [r"TopicNarrativePdf\?topicId="]
        acr.required_text_patterns = [
            r"ACR|American College of Radiology|Appropriateness Criteria"
        ]
        acr.max_depth = 0
        acr.max_pages = 400
        acr.max_records = 300
        acr.rate_limit_per_second = 1.0
        acr.allow_pdfs = True
        acr.request_timeout_seconds = 20.0
        acr.request_max_retries = 1
        acr.max_consecutive_fetch_errors = 5
        acr.progress_every = 25

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
