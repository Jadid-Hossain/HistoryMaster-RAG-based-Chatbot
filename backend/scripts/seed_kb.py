"""Load the knowledge base into the Chroma vector DB.

Two ways to use it:

1. Drop your file(s) into backend/knowledge_base/ then run:
       python scripts/seed_kb.py
2. Or point directly at any file:
       python scripts/seed_kb.py "C:\\path\\to\\my_document.pdf"

Add --reset to wipe ALL existing knowledge (documents, vectors, chat
history) before loading - useful to start clean with only your PDF.
"""
import shutil
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app import database                      # noqa: E402
from app.logger import setup_logging          # noqa: E402
from app.services import ingest               # noqa: E402
from app.services.embeddings import embedder  # noqa: E402
from app.services.vectorstore import vector_store  # noqa: E402

ALLOWED = {".pdf", ".txt", ".md", ".docx", ".html", ".htm"}


def reset_stores() -> None:
    data_dir = BACKEND_DIR / "data"
    for name in ["knowbot.db", "knowbot.db-wal", "knowbot.db-shm"]:
        path = data_dir / name
        if path.exists():
            path.unlink()
            print(f"Removed {path.name}")
    chroma_dir = data_dir / "chroma"
    if chroma_dir.exists():
        shutil.rmtree(chroma_dir)
        print("Removed chroma vector store")
    uploads = data_dir / "uploads"
    if uploads.exists():
        shutil.rmtree(uploads)
        print("Removed stored upload copies")
    sessions = database.query("SELECT id FROM chat_sessions")
    print(f"Wiped knowledge base ({len(sessions)} chat sessions removed with the DB).")


def collect_files(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            files.extend(
                f for f in sorted(p.iterdir()) if f.suffix.lower() in ALLOWED
            )
        elif p.is_file() and p.suffix.lower() in ALLOWED:
            files.append(p)
        else:
            print(f"  [SKIP] {p} (not found or unsupported type)")
    return files


def main() -> None:
    setup_logging()
    reset_requested = "--reset" in sys.argv
    file_args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if reset_requested:
        reset_stores()
    database.init_db()
    embedder.load()
    vector_store.load()

    if file_args:
        files = collect_files(file_args)
    else:
        kb_dir = BACKEND_DIR / "knowledge_base"
        files = sorted(
            p for p in kb_dir.iterdir()
            if p.suffix.lower() in ALLOWED and not p.stem.upper().startswith("README")
        ) if kb_dir.exists() else []

    if not files:
        existing = vector_store.count()
        print(f"\nNo files to load. Knowledge base currently holds {existing} chunks.")
        print("Drop your PDF into backend/knowledge_base/ or pass its path:")
        print('   python scripts/seed_kb.py "C:\\path\\to\\your.pdf"')
        return

    print(f"Loading {len(files)} file(s) into the vector DB ...\n")
    for path in files:
        try:
            documents = ingest.load_documents_from_path(path)
            ingest.save_upload_file(path.name, path.read_bytes())
            result = ingest.ingest_documents(
                path.name, path.suffix.lstrip("."), documents, "admin",
                size_bytes=path.stat().st_size,
            )
            print(f"  [OK]   {path.name:<50} {result['num_chunks']:>4} chunks")
        except Exception as exc:
            print(f"  [FAIL] {path.name:<50} {exc}")

    docs = database.query_one("SELECT COUNT(*) AS n FROM documents")
    print(f"\nDone. Knowledge base now has {docs['n']} document(s) / "
          f"{vector_store.count()} chunks in the Chroma vector DB.")
    print("Restart the backend (or it already picked it up) and ask away - "
          "questions outside these documents get the polite 'not in my knowledge base' answer.")


if __name__ == "__main__":
    main()
