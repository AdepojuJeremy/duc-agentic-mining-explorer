from pathlib import Path

from duc_agentic_mining.acquisition import (
    SourceAcquisitionConfig,
    SourceJobConfig,
    _extract_document_text,
    _ncbi_article_records,
    load_source_config,
    source_status,
    sync_sources,
)


def test_source_config_resolves_outputs_under_raw_root(tmp_path: Path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    path = config_dir / "sources.yaml"
    path.write_text(
        """
raw_root: ../data/raw
manifest_path: ../data/raw/manifests/source_manifest.jsonl
sources:
  nice:
    kind: nice
    output: primary/nice/guidance.jsonl
    api_key_env: NICE_API_KEY
    credential_required: true
""",
        encoding="utf-8",
    )
    cfg = load_source_config(path)
    assert cfg.raw_root == (tmp_path / "data" / "raw").resolve()
    assert cfg.sources["nice"].output == (
        tmp_path / "data" / "raw" / "primary" / "nice" / "guidance.jsonl"
    ).resolve()


def test_status_reports_optional_and_required_credentials(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("NICE_API_KEY", raising=False)
    cfg = SourceAcquisitionConfig(
        raw_root=tmp_path,
        manifest_path=tmp_path / "manifest.jsonl",
        sources={
            "nice": SourceJobConfig(
                kind="nice",
                output=tmp_path / "nice.jsonl",
                api_key_env="NICE_API_KEY",
                credential_required=True,
            ),
            "who": SourceJobConfig(kind="who", output=tmp_path / "who.jsonl"),
        },
    )
    status = source_status(cfg)
    assert status["nice"]["credential_present"] is False
    assert status["nice"]["credential_required"] is True
    assert status["who"]["credential_present"] is None


def test_required_missing_credential_skips_without_network(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("NICE_API_KEY", raising=False)
    cfg = SourceAcquisitionConfig(
        raw_root=tmp_path,
        manifest_path=tmp_path / "manifest.jsonl",
        sources={
            "nice": SourceJobConfig(
                kind="nice",
                output=tmp_path / "nice.jsonl",
                api_key_env="NICE_API_KEY",
                credential_required=True,
            )
        },
    )
    result = sync_sources(cfg)
    assert result["nice"]["status"] == "credential_missing"
    assert not (tmp_path / "nice.jsonl").exists()


def test_html_document_extraction_removes_scripts():
    payload = b"<html><body><h1>Guideline</h1><script>bad()</script><p>Recommendation text</p></body></html>"
    text = _extract_document_text(payload, "text/html", "https://example.org/guideline")
    assert "Guideline" in text
    assert "Recommendation text" in text
    assert "bad()" not in text


def test_pubmed_xml_is_normalized_to_indexable_record():
    xml = b"""
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>12345</PMID>
      <Article>
        <ArticleTitle>Clinical Practice Guideline</ArticleTitle>
        <Abstract><AbstractText>Use treatment A when indicated.</AbstractText></Abstract>
        <Journal><JournalIssue><PubDate><Year>2026</Year></PubDate></JournalIssue></Journal>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>
"""
    records = _ncbi_article_records(xml, "pubmed")
    assert len(records) == 1
    record = records[0]
    assert record["id"] == "ncbi:pubmed:12345"
    assert record["source"] == "PubMed / PMC"
    assert record["title"] == "Clinical Practice Guideline"
    assert "Use treatment A" in record["text"]
    assert record["url"] == "https://pubmed.ncbi.nlm.nih.gov/12345/"
