from pathlib import Path

from duc_agentic_mining.corpus import CorpusStore
from duc_agentic_mining.models import SourceRecord


def test_fts_search(tmp_path: Path):
    store = CorpusStore(tmp_path / "x.sqlite")
    store.add(
        SourceRecord(
            source_id="a",
            title="Renal",
            text="renal impairment changes treatment selection",
            source="demo",
        )
    )
    store.add(
        SourceRecord(
            source_id="b",
            title="Other",
            text="unrelated vaccination schedule",
            source="demo",
        )
    )
    store.commit()
    rows = store.search("renal impairment", limit=2)
    assert rows and rows[0]["source_id"] == "a"
    store.close()
