"""Knowledge base management (admin only): upload, URL ingest, list, delete, stats."""
import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .. import database
from ..config import ALLOWED_EXTENSIONS, MAX_UPLOAD_MB
from ..logger import get_logger
from ..security import require_admin
from ..services import ingest
from ..services.vectorstore import vector_store

router = APIRouter()
log = get_logger("historymaster.kb")


@router.post("/documents", summary="Upload one or more documents (PDF, TXT, MD, DOCX, HTML)")
async def upload_documents(
    files: list[UploadFile] = File(...),
    admin: dict = Depends(require_admin),
):
    results = []
    for upload in files:
        filename = Path(upload.filename or "untitled").name
        ext = Path(filename).suffix.lower()
        summary = {"filename": filename, "status": "failed", "num_chunks": 0, "error": None}
        try:
            if ext not in ALLOWED_EXTENSIONS:
                raise ValueError(
                    f"Unsupported type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}."
                )
            data = await upload.read()
            if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
                raise ValueError(f"File exceeds the {MAX_UPLOAD_MB} MB limit.")
            ingest.save_upload_file(filename, data)
            documents = ingest.load_documents(filename, data)
            result = ingest.ingest_documents(
                filename, ext.lstrip("."), documents, admin["username"], size_bytes=len(data)
            )
            summary.update(result)
        except Exception as exc:
            log.warning("Upload failed for %s: %s", filename, exc)
            summary["error"] = str(exc)
        results.append(summary)
    failed = [r for r in results if r["status"] == "failed"]
    if results and len(failed) == len(results):
        raise HTTPException(400, detail={"message": "All uploads failed.", "results": results})
    return {"results": results, "index_size": vector_store.count()}


class UrlRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)


@router.post("/url", summary="Ingest a web page into the knowledge base")
def add_url(payload: UrlRequest, admin: dict = Depends(require_admin)):
    url = payload.url.strip()
    if not re.match(r"^https?://", url):
        raise HTTPException(400, "URL must start with http:// or https://")
    try:
        documents = ingest.extract_text_from_url(url)
        name = re.sub(r"[^\w.-]", "_", url.split("//", 1)[1])[:80] or "web_page"
        result = ingest.ingest_documents(f"{name}.html", "url", documents, admin["username"])
    except Exception as exc:
        log.warning("URL ingest failed for %s: %s", url, exc)
        raise HTTPException(400, f"Could not ingest that URL: {exc}")
    return result


@router.get("/documents", summary="List all knowledge base documents")
def list_documents(admin: dict = Depends(require_admin)):
    return database.query(
        "SELECT id, filename, doc_type, size_bytes, num_chunks, status, error, "
        "uploaded_by, created_at FROM documents ORDER BY id DESC"
    )


@router.delete("/documents/{doc_id}", summary="Delete a document and its vectors")
def delete_document(doc_id: int, admin: dict = Depends(require_admin)):
    if not ingest.delete_document(doc_id):
        raise HTTPException(404, "Document not found.")
    return {"deleted": True, "index_size": vector_store.count()}


@router.post("/rebuild", summary="Re-embed every document (full re-index of the vector DB)")
def rebuild_index(admin: dict = Depends(require_admin)):
    total = ingest.reindex_all()
    log.info("Admin %s re-indexed the vector DB (%d chunks).", admin["username"], total)
    return {"rebuilt": True, "chunks": total, "index_size": vector_store.count()}


@router.get("/stats", summary="Knowledge base + usage statistics")
def stats(admin: dict = Depends(require_admin)):
    documents = database.query_one("SELECT COUNT(*) AS n, COALESCE(SUM(size_bytes),0) AS bytes FROM documents")
    users = database.query_one("SELECT COUNT(*) AS n FROM users")
    sessions = database.query_one("SELECT COUNT(*) AS n FROM chat_sessions")
    messages = database.query_one(
        "SELECT COUNT(*) AS n, SUM(CASE WHEN in_scope = 1 THEN 1 ELSE 0 END) AS answered "
        "FROM messages WHERE role='assistant'"
    )
    from ..services.llm import llm_service

    return {
        "documents": documents["n"],
        "storage_bytes": documents["bytes"],
        "chunks": vector_store.count(),
        "vector_db": "Chroma (persistent)",
        "llm_provider": llm_service.provider,
        "llm_model": llm_service.model_name,
        "users": users["n"],
        "chat_sessions": sessions["n"],
        "answers_generated": messages["n"] or 0,
        "in_scope_answers": messages["answered"] or 0,
    }
