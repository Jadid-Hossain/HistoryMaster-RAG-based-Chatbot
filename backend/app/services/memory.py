"""Short-term conversation memory.

Stores every turn in SQLite and rewrites follow-up questions into
self-contained retrieval queries, e.g. after "Who heads the robotics lab?"
the question "Where is his office?" becomes
"Who heads the robotics lab? Where is his office?" before embedding.
"""
import re
from pathlib import Path

from .. import database
from ..config import MEMORY_WINDOW

# Pronouns / demonstratives / continuation cues that signal a follow-up.
_FOLLOWUP_PATTERN = re.compile(
    r"\b(it|its|it's|this|that|these|those|they|them|their|he|she|his|her|him|"
    r"more|again|also|another|explain|continue|and|which|such)\b",
    re.IGNORECASE,
)
# Questions referring to the book/document itself ("who wrote this book?").
_META_DOC_PATTERN = re.compile(
    r"\b(this book|the book|this document|the document|this pdf|this file)\b",
    re.IGNORECASE,
)


def get_recent_messages(session_id: int, limit: int = MEMORY_WINDOW) -> list[dict]:
    rows = database.query(
        "SELECT role, content FROM messages WHERE session_id = ? "
        "ORDER BY id DESC LIMIT ?",
        (session_id, limit),
    )
    return list(reversed(rows))


def last_user_question(history: list[dict]) -> str | None:
    for message in reversed(history):
        if message["role"] == "user":
            return message["content"]
    return None


def is_followup(question: str) -> bool:
    """Heuristic: short, pronoun-heavy questions depend on previous context."""
    if len(question) > 90:
        return False
    return _FOLLOWUP_PATTERN.search(question) is not None


def build_search_query(question: str, history: list[dict]) -> str:
    """Return the question to embed, resolving context when needed."""
    if not history:
        return question
    if not is_followup(question):
        return question
    previous = last_user_question(history)
    if not previous:
        return question
    return f"{previous} {question}"


def augment_search_query(question: str, search_query: str) -> str:
    """Boost meta-questions ("who wrote this book?") with the document titles.

    The title page rarely wins a semantic match against content chunks, but
    adding the knowledge base's document titles to the retrieval query lets
    those front-matter chunks surface.
    """
    if not _META_DOC_PATTERN.search(question):
        return search_query
    rows = database.query(
        "SELECT filename FROM documents WHERE status = 'ready' ORDER BY id LIMIT 5"
    )
    titles = " ".join(
        re.sub(r"[_\-.]", " ", Path(row["filename"]).stem) for row in rows
    )
    return f"{search_query} {titles}".strip() if titles else search_query
