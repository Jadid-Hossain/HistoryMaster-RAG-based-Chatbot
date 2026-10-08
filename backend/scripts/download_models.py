"""Pre-download the local embedding model so the server can start offline afterwards.

The LLM is a cloud API (Gemini by default) configured via .env - only the
embedding model runs locally and needs a one-time download.

Run once with internet access:  python scripts/download_models.py
"""
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config import EMBEDDING_MODEL  # noqa: E402


def main() -> None:
    from langchain_huggingface import HuggingFaceEmbeddings

    print(f"Downloading/checking embedding model: {EMBEDDING_MODEL}")
    started = time.time()
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    vector = embeddings.embed_query("warm up")
    print(f"  OK in {time.time() - started:.0f}s (vector dim={len(vector)})")
    print("\nLocal embedding model is cached. The server can now start without internet.")
    print("(The answering LLM uses your API key from .env - nothing to download there.)")


if __name__ == "__main__":
    main()
