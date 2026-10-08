"""Embedding service (LangChain Embeddings interface).

Default: local sentence-transformers model (offline, free, no API key needed).
Optional: Gemini API embeddings via EMBEDDINGS_PROVIDER=gemini.
"""
import threading

from ..config import (
    EMBEDDING_MODEL,
    EMBEDDINGS_PROVIDER,
    GEMINI_EMBEDDING_MODEL,
)
from ..logger import get_logger

log = get_logger("historymaster.embeddings")


class EmbeddingService:
    def __init__(self) -> None:
        self._embeddings = None
        self._lock = threading.Lock()

    @property
    def ready(self) -> bool:
        return self._embeddings is not None

    def load(self) -> None:
        with self._lock:
            if self._embeddings is not None:
                return
            if EMBEDDINGS_PROVIDER == "gemini":
                import os

                from langchain_google_genai import GoogleGenerativeAIEmbeddings

                log.info("Using Gemini API embeddings (%s).", GEMINI_EMBEDDING_MODEL)
                self._embeddings = GoogleGenerativeAIEmbeddings(
                    model=GEMINI_EMBEDDING_MODEL,
                    google_api_key=os.getenv("GEMINI_API_KEY", ""),
                )
            else:
                from langchain_huggingface import HuggingFaceEmbeddings

                log.info("Loading local embedding model '%s' ...", EMBEDDING_MODEL)
                self._embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
                log.info("Embedding model ready.")

    def get(self):
        """Return a LangChain Embeddings instance for the vector store."""
        if self._embeddings is None:
            raise RuntimeError("Embeddings not loaded yet.")
        return self._embeddings


embedder = EmbeddingService()
