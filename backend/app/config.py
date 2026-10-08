"""Central configuration for History Master backend.

Reads .env (project root or backend/) for secrets and knobs:
  GEMINI_API_KEY / OPENAI_API_KEY / GROQ_API_KEY ...  -> LLM credentials
  LLM_PROVIDER, LLM_MODEL, OPENAI_BASE_URL            -> LLM selection
Tests override KB_DATA_DIR and KB_LLM_PROVIDER to stay isolated and hermetic.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent      # backend/
PROJECT_ROOT = BASE_DIR.parent                          # HistoryMaster/

# .env lives at the project root; backend/.env also accepted.
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(BASE_DIR / ".env")

DATA_DIR = Path(os.getenv("KB_DATA_DIR", str(BASE_DIR / "data")))
UPLOAD_DIR = DATA_DIR / "uploads"
CHROMA_DIR = DATA_DIR / "chroma"                        # vector database
LOG_DIR = BASE_DIR / "logs"
DB_PATH = DATA_DIR / "knowbot.db"                       # relational metadata only

# ---------------------------------------------------------------- security --
SECRET_FILE = DATA_DIR / ".jwt_secret"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 12))


def _load_or_create_secret() -> str:
    """Persist a random JWT secret so tokens survive server restarts."""
    try:
        if SECRET_FILE.exists():
            secret = SECRET_FILE.read_text(encoding="utf-8").strip()
            if secret:
                return secret
        import secrets

        secret = secrets.token_hex(32)
        SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
        SECRET_FILE.write_text(secret, encoding="utf-8")
        return secret
    except OSError:
        return "knowbot-dev-secret"


SECRET_KEY = _load_or_create_secret()

# ------------------------------------------------------------- LLM / RAG ---
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto")        # auto|gemini|openai|groq|openrouter|deepseek|openai_compatible|fake
LLM_MODEL = os.getenv("LLM_MODEL", "")                  # empty -> provider default
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))
LLM_MAX_OUTPUT_TOKENS = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "1024"))
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")      # for OpenAI-compatible APIs

GEMINI_MODEL_DEFAULT = "gemini-flash-lite-latest"
OPENAI_MODEL_DEFAULT = "gpt-4o-mini"
GROQ_MODEL_DEFAULT = "llama-3.3-70b-versatile"
OPENROUTER_MODEL_DEFAULT = "openai/gpt-4o-mini"
DEEPSEEK_MODEL_DEFAULT = "deepseek-chat"

# Local (offline, free) embeddings by default; set EMBEDDINGS_PROVIDER=gemini to use API embeddings.
EMBEDDINGS_PROVIDER = os.getenv("EMBEDDINGS_PROVIDER", "local")   # local|gemini
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
GEMINI_EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "models/text-embedding-004")

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 1000))         # characters per chunk
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 150))    # character overlap
RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", 20))

# Cheap pre-filter only: below this cosine similarity the bot skips the LLM and
# answers "not in my knowledge base" directly. The precise guard is the LLM's
# NOT_IN_KB contract, so this floor stays low to not miss short entity questions.
RETRIEVAL_FLOOR = float(os.getenv("RETRIEVAL_FLOOR", 0.15))

MEMORY_WINDOW = int(os.getenv("MEMORY_WINDOW", 6))      # recent messages kept as context

# ---------------------------------------------------------------- uploads --
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", 25))
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx", ".html", ".htm"}
