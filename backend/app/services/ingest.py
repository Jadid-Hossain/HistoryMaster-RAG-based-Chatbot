"""Document ingestion the LangChain way.

Loaders (PyPDF / Text / Docx2txt / BSHTML / WebBase) -> RecursiveCharacterTextSplitter
-> local or API embeddings -> persistent Chroma vector DB.

Every document registers in SQLite (metadata) while its chunks go to the
vector DB; uploads are incremental so the knowledge base grows with no
retraining.
"""
import re
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .. import database
from ..config import CHUNK_OVERLAP, CHUNK_SIZE, UPLOAD_DIR
from ..logger import get_logger
from .vectorstore import vector_store

log = get_logger("historymaster.ingest")

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", ". ", " ", ""],
    length_function=len,
)


# ------------------------------------------------------------- extraction --
def load_documents(filename: str, data: bytes) -> list[Document]:
    """Extract text from raw bytes using the LangChain loader for the type."""
    ext = Path(filename).suffix.lower()
    import tempfile

    if ext == ".pdf":
        from langchain_community.document_loaders import PyPDFLoader

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        try:
            return PyPDFLoader(tmp_path).load()
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    if ext == ".docx":
        from langchain_community.document_loaders import Docx2txtLoader

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        try:
            return Docx2txtLoader(tmp_path).load()
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    if ext in {".html", ".htm"}:
        from langchain_community.document_loaders import BSHTMLLoader

        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        try:
            return BSHTMLLoader(tmp_path, open_encoding="utf-8").load()
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    if ext in {".txt", ".md"}:
        text = data.decode("utf-8", errors="ignore")
        return [Document(page_content=text, metadata={"source": filename})]
    raise ValueError(f"Unsupported file type: '{ext}'. Allowed: pdf, txt, md, docx, html.")


def load_documents_from_path(path: str | Path) -> list[Document]:
    return load_documents(Path(path).name, Path(path).read_bytes())


def extract_text_from_url(url: str) -> list[Document]:
    from langchain_community.document_loaders import WebBaseLoader

    loader = WebBaseLoader(url, requests_per_second=2)
    docs = loader.load()
    if not docs or not any(d.page_content.strip() for d in docs):
        raise ValueError("The web page contained no extractable text.")
    return docs


def save_upload_file(filename: str, data: bytes) -> Path:
    """Keep a copy of the original upload for audit / re-indexing."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^\w.\- ]", "_", filename)
    path = UPLOAD_DIR / safe_name
    counter = 1
    while path.exists():
        path = UPLOAD_DIR / f"{Path(safe_name).stem}_{counter}{Path(safe_name).suffix}"
        counter += 1
    path.write_bytes(data)
    return path


# -------------------------------------------------------------- pipeline --
def ingest_documents(filename: str, doc_type: str, documents: list[Document],
                     uploaded_by: str, size_bytes: int = 0) -> dict:
    """Register + split + embed + store one logical document."""
    documents = [d for d in documents if d.page_content.strip()]
    if not documents:
        raise ValueError("Document contains no extractable text.")

    doc_id = database.execute(
        "INSERT INTO documents (filename, doc_type, size_bytes, status, uploaded_by) "
        "VALUES (?, ?, ?, 'processing', ?)",
        (filename, doc_type, size_bytes, uploaded_by),
    )
    try:
        chunks = _splitter.split_documents(documents)
        for i, chunk in enumerate(chunks):
            chunk.metadata = {"doc_id": int(doc_id), "filename": filename, "chunk_index": i}
        stored = vector_store.add_chunks(
            doc_id=doc_id, filename=filename, chunks=[c.page_content for c in chunks]
        )
        database.execute(
            "UPDATE documents SET num_chunks = ?, status = 'ready' WHERE id = ?",
            (stored, doc_id),
        )
        log.info("Ingested '%s': %d chunks -> Chroma.", filename, stored)
        return {
            "id": doc_id,
            "filename": filename,
            "doc_type": doc_type,
            "num_chunks": stored,
            "status": "ready",
            "error": None,
        }
    except Exception as exc:
        database.execute(
            "UPDATE documents SET status = 'failed', error = ? WHERE id = ?", (str(exc), doc_id)
        )
        vector_store.delete_document(doc_id)
        raise


def delete_document(doc_id: int) -> bool:
    row = database.query_one("SELECT id, filename FROM documents WHERE id = ?", (doc_id,))
    if row is None:
        return False
    vector_store.delete_document(doc_id)
    database.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    log.info("Deleted document %s and removed its vectors from Chroma.", row["filename"])
    return True


def reindex_all() -> int:
    """Re-embed every document from its stored upload file (full re-index)."""
    docs = database.query("SELECT id, filename, doc_type FROM documents ORDER BY id")
    total = 0
    for row in docs:
        upload = UPLOAD_DIR / row["filename"]
        if not upload.exists():
            log.warning("Re-index skipped '%s' (original file missing).", row["filename"])
            continue
        vector_store.delete_document(row["id"])
        documents = load_documents_from_path(upload)
        chunks = _splitter.split_documents(documents)
        for i, chunk in enumerate(chunks):
            chunk.metadata = {"doc_id": row["id"], "filename": row["filename"], "chunk_index": i}
        total += vector_store.add_chunks(row["id"], row["filename"], [c.page_content for c in chunks])
        database.execute(
            "UPDATE documents SET num_chunks = ? WHERE id = ?", (len(chunks), row["id"])
        )
    return total
