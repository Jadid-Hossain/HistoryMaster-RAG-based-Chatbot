"""History Master FastAPI application entry point.

A RAG (Retrieval-Augmented Generation) chatbot:
  LangChain loaders -> Chroma vector DB -> Gemini LLM (API key from .env)

- /api/auth    -> register / login / me
- /api/chat    -> ask questions, sessions, history
- /api/kb      -> knowledge base management (admin)
- /api/health  -> service + model status
- /docs        -> auto-generated Swagger API documentation
- serves the built React frontend from frontend/dist when present
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import database
from .config import PROJECT_ROOT
from .logger import RequestLoggingMiddleware, get_logger, setup_logging
from .routers import auth, chat, kb
from .services.embeddings import embedder
from .services.llm import llm_service
from .services.vectorstore import vector_store

log = get_logger("historymaster.app")

DESCRIPTION = """
Knowledge-base chatbot API built on a **RAG (Retrieval-Augmented Generation)** pipeline:

`documents -> LangChain loaders -> chunk splitter -> embeddings -> Chroma vector DB
-> similarity retrieval -> Gemini LLM (grounded generation)`

* **Authentication**: JWT bearer tokens, `admin` and `user` roles.
* **Chat**: answers grounded strictly in the knowledge base, with sources,
  similarity scores, short-term conversation memory and a polite fallback
  for out-of-scope questions.
* **Knowledge base**: admins upload PDF / TXT / MD / DOCX / HTML files or web
  page URLs; new documents are embedded incrementally (no retraining).
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    database.init_db()
    _seed_default_users()
    try:
        embedder.load()
        vector_store.load()
    except Exception as exc:  # pragma: no cover - first run without internet
        log.error("Embedding/vector-store startup failed: %s", exc)
        log.error("Run `python scripts/download_models.py` once with internet access.")
    try:
        llm_service.load()
    except Exception as exc:
        log.error("LLM configuration error: %s", exc)
    log.info(
        "History Master ready: %d documents, %d chunks in Chroma, LLM=%s.",
        len(database.query("SELECT id FROM documents")),
        vector_store.count(),
        llm_service.provider or "NOT CONFIGURED",
    )
    yield


def _seed_default_users() -> None:
    """Create demo accounts on first launch (change passwords for real use)."""
    from .security import hash_password

    if database.query_one("SELECT id FROM users LIMIT 1") is None:
        database.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'admin')",
            ("admin", hash_password("admin123")),
        )
        database.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'user')",
            ("user", hash_password("user123")),
        )
        log.info("Seeded default accounts: admin/admin123 (admin), user/user123 (user).")


app = FastAPI(
    title="History Master API",
    version="2.0.0",
    description=DESCRIPTION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # dev convenience; same-origin in production build
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)

app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(kb.router, prefix="/api/kb", tags=["Knowledge Base (admin)"])


@app.get("/api/health", tags=["System"], summary="Service and model status")
def health():
    documents = database.query_one("SELECT COUNT(*) AS n FROM documents")
    return {
        "status": "ok" if (embedder.ready and vector_store.ready and llm_service.ready) else "degraded",
        "embeddings": embedder.ready,
        "vector_db": vector_store.ready,
        "vector_db_chunks": vector_store.count(),
        "llm_provider": llm_service.provider,
        "llm_model": llm_service.model_name,
        "llm_ready": llm_service.ready,
        "documents": documents["n"],
    }


# Serve the built React frontend (npm run build) when available.
_frontend_dist = PROJECT_ROOT / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
    log.info("Serving frontend from %s", _frontend_dist)
