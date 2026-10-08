"""Unit tests for the ingestion pipeline (no models needed)."""
from langchain_core.documents import Document


def test_splitter_chunk_sizes():
    from app.services.ingest import _splitter

    text = ("Alpha Valley University offers many programs. " * 120).strip()
    chunks = _splitter.split_documents(
        [Document(page_content=text, metadata={"source": "x.txt"})]
    )
    assert len(chunks) >= 2
    assert all(len(c.page_content) <= 1200 for c in chunks)
    assert all(c.page_content.strip() for c in chunks)


def test_unsupported_extension_raises():
    from app.services.ingest import load_documents

    try:
        load_documents("evil.exe", b"MZ")
    except ValueError as exc:
        assert "Unsupported file type" in str(exc)
    else:
        raise AssertionError("expected ValueError for .exe upload")
