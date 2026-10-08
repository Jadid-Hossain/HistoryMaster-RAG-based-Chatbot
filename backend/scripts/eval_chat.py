"""Live accuracy evaluation of the RAG pipeline against the CURRENT knowledge base.

Create backend/eval_questions.json first (or ask the project maintainer to
generate it from the loaded PDF):

    [
      {"question": "A fact from the PDF?", "expect": ["expected substring"]},
      {"question": "Something NOT in the PDF?", "expect": null},
      {"question": "hello", "expect": null}
    ]

`expect: null` means the bot must answer with the graceful fallback (or a
canned greeting), never a made-up answer.

Run:  python scripts/eval_chat.py
Prints PASS/FAIL per question and saves docs/EVAL_RESULTS.md.
"""
import json
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

QUESTIONS_FILE = BACKEND_DIR / "eval_questions.json"


def load_cases() -> list[dict]:
    if not QUESTIONS_FILE.exists():
        print(f"Create {QUESTIONS_FILE} first - see the docstring of this script.")
        print('Example: [{"question": "Who is the dean?", "expect": ["Dr. Someone"]},'
              ' {"question": "Who won the World Cup?", "expect": null}]')
        return []
    with QUESTIONS_FILE.open(encoding="utf-8") as fh:
        cases = json.load(fh)
    return [
        {"question": c["question"], "expect": c.get("expect")}
        for c in cases
        if isinstance(c, dict) and c.get("question")
    ]


def main() -> int:
    from app.logger import setup_logging  # noqa: E402
    from app.services import chatbot  # noqa: E402
    from app.services.embeddings import embedder  # noqa: E402
    from app.services.llm import llm_service  # noqa: E402
    from app.services.vectorstore import vector_store  # noqa: E402

    setup_logging()
    cases = load_cases()
    if not cases:
        return 1

    embedder.load()
    vector_store.load()
    llm_service.load()
    if not llm_service.ready:
        print("LLM not configured - put your API key in .env first.")
        return 1
    print(f"Evaluating {len(cases)} questions | provider={llm_service.provider} "
          f"model={llm_service.model_name} | chunks={vector_store.count()}\n")

    passed = 0
    rows = []
    for case in cases:
        question, must_include = case["question"], case["expect"]
        started = time.time()
        result = chatbot.answer_question(question)
        elapsed = time.time() - started
        answer = result["answer"].replace("\n", " ")
        if must_include is None:
            ok = (not result["in_scope"]) or result["kind"] in ("greeting", "capabilities")
            expect = "<graceful fallback / canned>"
        else:
            ok = result["in_scope"] and all(m.lower() in answer.lower() for m in must_include)
            expect = " AND ".join(must_include)
        passed += ok
        mark = "PASS" if ok else "FAIL"
        rows.append((mark, question, expect, answer[:110], elapsed))
        print(f"[{mark}] {question}")
        print(f"       -> {answer[:150]}")
        print(f"       (expected: {expect}) {elapsed:.1f}s\n")

    print("=" * 70)
    print(f"RESULT: {passed}/{len(cases)} passed")
    print("=" * 70)

    out = BACKEND_DIR.parent / "docs" / "EVAL_RESULTS.md"
    with out.open("w", encoding="utf-8") as f:
        f.write("# History Master RAG evaluation results\n\n")
        f.write(f"- LLM: `{llm_service.provider}/{llm_service.model_name}`\n")
        f.write(f"- Knowledge base: {vector_store.count()} chunks\n")
        f.write(f"- Score: **{passed}/{len(cases)}**\n\n")
        f.write("| Status | Question | Expected | Answer (trimmed) | Time |\n|---|---|---|---|---|\n")
        for mark, question, expect, answer, elapsed in rows:
            f.write(f"| {mark} | {question} | {expect} | {answer} | {elapsed:.1f}s |\n")
    print(f"Report saved to {out}")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
