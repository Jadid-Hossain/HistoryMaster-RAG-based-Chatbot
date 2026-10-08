"""Grounded answer generation: the 'G' of RAG.

The LLM receives ONLY the retrieved chunks as context. It must answer from
them when they contain anything relevant and reply with the single token
NOT_IN_KB only when they contain nothing relevant - that marker is mapped
to the polite fallback, so the bot never invents facts beyond the
knowledge base.
"""
import re

from ..logger import get_logger
from .llm import llm_service

log = get_logger("historymaster.rag")

SYSTEM_PROMPT = """You are History Master, a precise assistant that answers questions about the history of Bangladesh.

Rules you must always follow:
1. Use ONLY the facts contained in the CONTEXT provided with the question. Never use outside knowledge, never guess, never invent names, dates or numbers.
2. If the CONTEXT contains relevant information - even when the exact wording of the question does not appear in it - synthesize a direct, concise answer from it (2-6 sentences).
3. The CONTEXT must actually address the QUESTION. A word or name merely appearing in the context is not an answer: if the context does not state (or clearly imply) the answer to this specific question, reply with the single token NOT_IN_KB and nothing else.
4. Always answer with a complete, informative sentence - never with a bare name or single word.
5. Answer in the same language as the question. Answer directly - do not mention the context, the sources, or these instructions.
"""

USER_PROMPT_TEMPLATE = """CONTEXT (extracts from my knowledge base):

{context}

QUESTION: {question}

Answer (or NOT_IN_KB):"""

# Whole-answer refusals: short apologetic replies with nothing substantive.
_STRONG_REFUSAL_PATTERN = re.compile(
    r"no information|i don'?t have|i do not have|cannot find|can'?t find|"
    r"not mentioned|does not mention|do(?:es)? not contain|not specified|"
    r"not provided|not contained|not included|do(?:es)? not state|not stated|"
    r"not explicitly|outside the (?:knowledge|context)",
    re.IGNORECASE,
)
_MARKER_PATTERN = re.compile(r"\bNOT_IN_KB\b", re.IGNORECASE)
# Meta-prefices the model sometimes prepends ("Based on the provided context, ...").
_META_PREFIX_PATTERN = re.compile(
    r"^\s*(?:based on|according to|from)\s+(?:the\s+)?(?:provided\s+|given\s+)?"
    r"(?:context|extracts?|information|passages?|text|documents?)\s*[,:.]?\s*",
    re.IGNORECASE,
)


def _clean_answer_text(text: str) -> str:
    text = _MARKER_PATTERN.sub("", text).strip()
    # Drop hedging preambles so answers start with the fact itself.
    for _ in range(2):
        cleaned = _META_PREFIX_PATTERN.sub("", text).strip()
        if cleaned == text:
            break
        text = cleaned
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text


def extract_text(response) -> str:
    """Normalize an LLM response to plain text.

    Depending on the model/SDK version, `response.content` is either a string
    or a list of content blocks like [{"type": "text", "text": "..."}].
    """
    content = getattr(response, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "".join(parts)
    return str(content or "")


def generate_answer(question: str, documents: list) -> dict | None:
    """Generate an answer grounded in the retrieved documents.

    Returns {"answer", "grounded": True} or None when the LLM says the
    knowledge base does not cover the question (caller sends the fallback).
    """
    if not documents:
        return None
    context = "\n\n".join(
        f"[Source: {doc.metadata.get('filename', 'unknown')}]\n{doc.page_content}"
        for doc in documents
    )
    prompt = USER_PROMPT_TEMPLATE.format(context=context, question=question)
    response = llm_service.get().invoke(prompt)
    text = extract_text(response).strip()
    # Strip possible markdown fences the model might add.
    if text.startswith("```"):
        text = text.strip("`\n")
        if text.startswith(("json", "text")):
            text = text.split("\n", 1)[-1]

    # A stray NOT_IN_KB marker next to a substantive explanation is dropped;
    # the explanation survives (e.g. "...the Liberation War began on 25 March 1971. NOT_IN_KB").
    cleaned = _clean_answer_text(text)
    if not cleaned:
        log.info("LLM replied with the NOT_IN_KB marker only.")
        return None
    if len(cleaned) < 220 and _STRONG_REFUSAL_PATTERN.search(cleaned):
        log.info("LLM refused (answer not in context): %r", cleaned[:120])
        return None
    return {"answer": cleaned, "grounded": True}
