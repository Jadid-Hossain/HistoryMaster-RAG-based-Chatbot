"""One-off comprehensive accuracy test against the loaded history book."""
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.logger import setup_logging  # noqa: E402
from app.services import chatbot  # noqa: E402
from app.services.embeddings import embedder  # noqa: E402
from app.services.llm import llm_service  # noqa: E402
from app.services.vectorstore import vector_store  # noqa: E402

QUESTIONS = [
    # (question, keywords that MUST appear if the book truly answers it; None = judge manually)
    ("What is this book about?", None),
    ("Who wrote this book?", ["Schendel"]),
    ("When was Bangladesh liberated?", ["1971"]),
    ("When did the Liberation War begin?", ["1971"]),
    ("What was the Language Movement?", None),
    ("Who was Sheikh Mujibur Rahman?", ["Mujib"]),
    ("What was the Six Point movement?", ["Six Point"]),
    ("When did the Battle of Plassey take place?", ["1757"]),
    ("Who was Siraj ud-Daulah?", None),
    ("What was Operation Searchlight?", None),
    ("When did the great Bengal famine of 1943 happen?", ["1943"]),
    ("What was the Partition of Bengal in 1905?", ["1905"]),
    ("What was the Two Nation Theory?", None),
    ("Who was Ziaur Rahman?", None),
    ("What is the Shaheed Minar?", None),
    ("When did Bangladesh join the United Nations?", ["1974"]),
    ("What happened in the 1970 elections in Pakistan?", ["1970"]),
    ("How did the rivers shape the history of Bengal?", None),
    ("Who was Nawab Salimullah?", None),
    ("What was the	swadeshi movement?", None),
]


def main() -> int:
    setup_logging()
    embedder.load()
    vector_store.load()
    llm_service.load()
    if not llm_service.ready:
        print("LLM not configured.")
        return 1
    print(f"Testing {len(QUESTIONS)} history questions | model={llm_service.model_name} "
          f"| chunks={vector_store.count()}\n" + "=" * 78)

    results = []
    for question, must in QUESTIONS:
        started = time.time()
        result = chatbot.answer_question(question.strip())
        elapsed = time.time() - started
        answer = " ".join(result["answer"].split())
        ok = None
        if must:
            ok = result["in_scope"] and all(m.lower() in answer.lower() for m in must)
        results.append((question, must, ok, result, answer, elapsed))
        status = {True: "PASS", False: "FAIL", None: "REVIEW"}[ok]
        print(f"\n[{status}] {question}  ({elapsed:.1f}s, {result['kind']})")
        print(f"    -> {answer[:290]}")

    auto = [r for r in results if r[2] is not None]
    passed = sum(1 for r in auto if r[2])
    print("\n" + "=" * 78)
    print(f"Auto-gradable: {passed}/{len(auto)} passed | {len(results) - len(auto)} need manual review")

    out = BACKEND_DIR.parent / "docs" / "HISTORY_QA_REPORT.md"
    with out.open("w", encoding="utf-8") as f:
        f.write("# History Master - full-book accuracy test\n\n")
        f.write(f"- Model: `{llm_service.model_name}` | Chunks: {vector_store.count()}\n")
        f.write(f"- Auto-gradable: **{passed}/{len(auto)}** passed\n\n")
        for question, must, ok, result, answer, elapsed in results:
            status = {True: "PASS", False: "FAIL", None: "REVIEW"}[ok]
            f.write(f"### [{status}] {question}\n")
            f.write(f"- kind: {result['kind']} | similarity: "
                    f"{result['confidence']} | {elapsed:.1f}s\n")
            f.write(f"- **Answer:** {answer}\n\n")
    print(f"Report: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
