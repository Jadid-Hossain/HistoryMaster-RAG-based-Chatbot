"""One-command setup verifier - run this AFTER putting your API key in .env.

    python scripts/check_setup.py

Checks: venv packages, .env key, embedding model, Chroma vector DB,
LLM connectivity (a tiny live API call), and prints a full report.
"""
import os
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

OK, FAIL, WARN = "[OK]  ", "[FAIL]", "[WARN]"


def main() -> int:
    from app import database
    from app.config import LLM_MODEL, PROJECT_ROOT
    from app.logger import setup_logging
    from app.services.embeddings import embedder
    from app.services.llm import llm_service
    from app.services.vectorstore import vector_store

    setup_logging()
    failures = 0

    print("=" * 64)
    print("History Master setup check")
    print("=" * 64)

    # 1. .env + API key ------------------------------------------------------
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        print(f"{OK} .env file found: {env_path}")
    else:
        print(f"{WARN} No .env file at project root (checked {env_path})")

    provider, _key = ("none", "")
    try:
        from app.services.llm import resolve_provider

        provider, _key = resolve_provider()
    except RuntimeError as exc:
        print(f"{FAIL} {exc}")
        failures += 1

    if provider in ("none", ""):
        print(f"{FAIL} No LLM API key found. Open .env and set GEMINI_API_KEY=<your key>")
        print("       (Google AI Studio: https://aistudio.google.com/apikey - free)")
        failures += 1
    else:
        print(f"{OK} LLM provider configured: {provider}")

    # 2. embedding model -----------------------------------------------------
    try:
        embedder.load()
        print(f"{OK} Embedding model loaded (local, offline).")
    except Exception as exc:
        print(f"{FAIL} Embedding model failed: {exc}")
        failures += 1
        return failures

    # 3. vector DB ------------------------------------------------------------
    database.init_db()
    vector_store.load()
    print(f"{OK} Chroma vector DB opened ({vector_store.count()} chunks indexed).")

    # 4. documents ------------------------------------------------------------
    database.init_db()
    docs = database.query("SELECT filename, num_chunks, status FROM documents ORDER BY id")
    ready = [d for d in docs if d["status"] == "ready"]
    if ready:
        print(f"{OK} Knowledge base: {len(ready)} document(s), e.g. " +
              ", ".join(d['filename'] for d in ready[:5]))
        for d in docs:
            if d["status"] != "ready":
                print(f"{WARN} Document '{d['filename']}' status={d['status']}")
    else:
        print(f"{WARN} Knowledge base is empty. Run: python scripts/seed_kb.py")

    # 5. live LLM call ---------------------------------------------------------
    if provider in ("none", ""):
        print(f"{WARN} Skipping live LLM test (no key).")
    else:
        try:
            from app.services.rag import extract_text

            llm_service.load()
            started = time.time()
            response = llm_service.get().invoke("Reply with exactly one word: OK")
            text = extract_text(response).strip()
            if text:
                print(f"{OK} Live LLM call succeeded in {time.time() - started:.1f}s "
                      f"(model={llm_service.model_name}, reply={text!r}).")
            else:
                raise RuntimeError("Empty response from LLM.")
        except Exception as exc:
            print(f"{FAIL} Live LLM call failed: {exc}")
            print("       Check the key and the model name (LLM_MODEL in .env).")
            failures += 1

    print("=" * 64)
    if failures:
        print(f"RESULT: {failures} problem(s) found - fix them, then run again.")
    else:
        print("RESULT: All good! Start the server:  python -m uvicorn app.main:app --port 8000")
        print("        (from the backend folder, with the venv activated)")
    print("=" * 64)
    return failures


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
