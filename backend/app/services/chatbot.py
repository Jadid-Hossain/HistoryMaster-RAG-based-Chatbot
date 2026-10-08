"""History Master's brain: the RAG pipeline orchestrator.

Pipeline per question:
  1. small talk / capability questions -> canned answers (no LLM call)
  2. conversation memory               -> rewrite follow-ups into standalone queries
  3. retrieval (Chroma vector DB)      -> top-k chunks by cosine similarity
  4. grounded generation (Gemini LLM)  -> answer strictly from retrieved context
  5. graceful fallback                 -> polite "not in my knowledge base"

Every answer carries its sources so the UI can show *where* each fact came from.
"""
import re
import time

from .. import database
from ..config import RETRIEVAL_FLOOR, RETRIEVAL_TOP_K
from ..logger import get_logger
from . import memory, rag
from .vectorstore import vector_store

log = get_logger("historymaster.chatbot")

_GREETING_PATTERN = re.compile(
    r"^\s*(hi+|hello+|hey+|good\s+(morning|afternoon|evening)|assalam(u|o)? ?alaikum|"
    r"thanks?|thank you|thx|bye+|goodbye|see you)\s*[!.]?\s*$",
    re.IGNORECASE,
)
_CAPABILITY_PATTERN = re.compile(
    r"\b(what can you do|who are you|what are you|your name|how do you work|help me|"
    r"what do you know)\b",
    re.IGNORECASE,
)

_FALLBACK_TEMPLATES = [
    "I'm sorry, but I couldn't find that in my knowledge base about the history of "
    "Bangladesh. Please try to ask about something related to the history of Bangladesh.",
    "That doesn't appear to be covered in my knowledge base yet. "
    "I can only answer questions about the history of Bangladesh from the book I've learned from - "
    "could you rephrase?",
    "I don't have enough information in my knowledge base to answer that reliably. "
    "Please ask me something about the history of Bangladesh.",
]


def _doc_topics() -> list[str]:
    rows = database.query(
        "SELECT filename FROM documents WHERE status = 'ready' ORDER BY filename"
    )
    names = []
    for row in rows:
        stem = row["filename"].rsplit(".", 1)[0]
        stem = re.sub(r"^\d+[_\-\s]*", "", stem).replace("_", " ").replace("-", " ")
        names.append(stem.title())
    return names


def _canned_greeting(question: str) -> dict:
    lowered = question.lower()
    if "thank" in lowered:
        answer = "You're welcome! Is there anything else you'd like to know from my knowledge base?"
    elif "bye" in lowered or "see you" in lowered:
        answer = "Goodbye! Feel free to come back whenever you have a question about my knowledge base."
    else:
        answer = (
            "Hello! I'm History Master. Ask me anything about the history of "
            "Bangladesh - I answer from the book in my knowledge base."
        )
    return {
        "answer": answer,
        "sources": [],
        "confidence": None,
        "in_scope": True,
        "kind": "greeting",
        "latency_ms": 0,
    }


def _canned_capabilities() -> dict:
    topics = _doc_topics()
    topic_line = ", ".join(topics) if topics else "no documents yet"
    answer = (
        "I'm History Master, a retrieval-augmented (RAG) chatbot. I answer questions strictly "
        f"from my knowledge base: {topic_line}. When something is not in it, I tell you "
        "honestly instead of guessing. Admins can upload new documents any time - "
        "I pick them up instantly, no retraining needed."
    )
    return {
        "answer": answer,
        "sources": [],
        "confidence": None,
        "in_scope": True,
        "kind": "capabilities",
        "latency_ms": 0,
    }


def _fallback() -> dict:
    return {
        "answer": _FALLBACK_TEMPLATES[int(time.time()) % len(_FALLBACK_TEMPLATES)],
        "sources": [],
        "confidence": None,
        "in_scope": False,
        "kind": "fallback",
        "latency_ms": 0,
    }


def _not_configured() -> dict:
    return {
        "answer": (
            "The LLM is not configured yet. An admin needs to put the API key "
            "(e.g. GEMINI_API_KEY) into the .env file and restart the backend."
        ),
        "sources": [],
        "confidence": None,
        "in_scope": False,
        "kind": "not_configured",
        "latency_ms": 0,
    }


def answer_question(question: str, history: list[dict] | None = None) -> dict:
    started = time.perf_counter()
    question = question.strip()
    history = history or []

    # 1. canned answers ------------------------------------------------
    if _GREETING_PATTERN.match(question):
        return _canned_greeting(question)
    if _CAPABILITY_PATTERN.search(question) and len(question) < 80:
        return _canned_capabilities()

    if not rag.llm_service.ready:
        result = _not_configured()
        result["latency_ms"] = int((time.perf_counter() - started) * 1000)
        return result

    # 2. retrieval with memory-aware query rewriting ---------------------
    search_query = memory.build_search_query(question, history)
    search_query = memory.augment_search_query(question, search_query)
    results = vector_store.search(search_query, RETRIEVAL_TOP_K)
    log.info(
        "Q: %r | search_query=%r | top_similarity=%s",
        question,
        search_query,
        round(results[0][1], 3) if results else None,
    )

    if not results or results[0][1] < RETRIEVAL_FLOOR:
        log.info(
            "Out of scope (best similarity %.3f < %.2f).",
            results[0][1] if results else 0.0, RETRIEVAL_FLOOR,
        )
        result = _fallback()
        result["latency_ms"] = int((time.perf_counter() - started) * 1000)
        return result

    # 3. grounded generation ---------------------------------------------
    documents = [doc for doc, _score in results]
    try:
        generated = rag.generate_answer(question, documents)
    except Exception as exc:
        # Rate limits / network problems must never crash a chat response.
        log.error("LLM call failed: %s", exc)
        result = {
            "answer": (
                "I found relevant information in my knowledge base, but the AI service "
                "is temporarily unavailable (rate limit or network issue). Please try "
                "again in a moment."
            ),
            "sources": [
                {
                    "document": doc.metadata.get("filename", "unknown"),
                    "snippet": doc.page_content[:280] + ("..." if len(doc.page_content) > 280 else ""),
                    "retrieval_score": round(score, 4),
                }
                for doc, score in results[:3]
            ],
            "confidence": round(results[0][1], 4),
            "in_scope": False,
            "kind": "llm_error",
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }
        return result
    if generated is None:
        # Retrieved something related, but the LLM confirms the facts are absent.
        result = _fallback()
        result["latency_ms"] = int((time.perf_counter() - started) * 1000)
        return result

    sources = [
        {
            "document": doc.metadata.get("filename", "unknown"),
            "snippet": doc.page_content[:280] + ("..." if len(doc.page_content) > 280 else ""),
            "retrieval_score": round(score, 4),
        }
        for doc, score in results[:3]
    ]
    result = {
        "answer": generated["answer"],
        "sources": sources,
        "confidence": round(results[0][1], 4),
        "in_scope": True,
        "kind": "kb_answer",
        "latency_ms": int((time.perf_counter() - started) * 1000),
    }
    log.info(
        "A: %r (top_similarity=%.3f, %dms)",
        result["answer"][:120], results[0][1], result["latency_ms"],
    )
    return result


def suggested_questions() -> list[str]:
    """Starter chips for the UI.

    Kept empty on purpose: questions should match whatever knowledge base the
    admin loads (drop a PDF into backend/knowledge_base/ and re-seed), never a
    hardcoded sample. The welcome screen simply hides the chips when empty.
    """
    return []
