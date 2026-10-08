"""Chat endpoints: ask questions, manage sessions and history."""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import database
from ..logger import get_logger
from ..security import get_current_user
from ..services import chatbot, memory

router = APIRouter()
log = get_logger("historymaster.chat")


class AskRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: int | None = None


@router.post("/ask", summary="Ask the chatbot a question")
def ask(payload: AskRequest, user: dict = Depends(get_current_user)):
    question = payload.message.strip()
    if not question:
        raise HTTPException(400, "Message cannot be empty.")

    # Resolve or create the session (owned by this user).
    if payload.session_id is not None:
        session = database.query_one(
            "SELECT * FROM chat_sessions WHERE id = ? AND user_id = ?",
            (payload.session_id, user["id"]),
        )
        if session is None:
            raise HTTPException(404, "Chat session not found.")
    else:
        title = question[:60] + ("..." if len(question) > 60 else "")
        payload_session_id = database.execute(
            "INSERT INTO chat_sessions (user_id, title) VALUES (?, ?)",
            (user["id"], title),
        )
        session = database.query_one(
            "SELECT * FROM chat_sessions WHERE id = ?", (payload_session_id,)
        )

    session_id = session["id"]
    history = memory.get_recent_messages(session_id)

    database.execute(
        "INSERT INTO messages (session_id, role, content) VALUES (?, 'user', ?)",
        (session_id, question),
    )

    result = chatbot.answer_question(question, history)

    message_id = database.execute(
        "INSERT INTO messages (session_id, role, content, sources_json, confidence, in_scope, latency_ms) "
        "VALUES (?, 'assistant', ?, ?, ?, ?, ?)",
        (
            session_id,
            result["answer"],
            json.dumps(result["sources"]),
            result["confidence"],
            1 if result["in_scope"] else 0,
            result["latency_ms"],
        ),
    )
    return {
        "session_id": session_id,
        "session_title": session["title"],
        "message_id": message_id,
        "answer": result["answer"],
        "sources": result["sources"],
        "confidence": result["confidence"],
        "in_scope": result["in_scope"],
        "kind": result["kind"],
        "latency_ms": result["latency_ms"],
    }


@router.get("/sessions", summary="List my chat sessions")
def list_sessions(user: dict = Depends(get_current_user)):
    return database.query(
        "SELECT s.id, s.title, s.created_at, "
        "  (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id) AS message_count "
        "FROM chat_sessions s WHERE s.user_id = ? ORDER BY s.id DESC",
        (user["id"],),
    )


@router.get("/sessions/{session_id}/messages", summary="Get the full history of a session")
def get_messages(session_id: int, user: dict = Depends(get_current_user)):
    session = database.query_one(
        "SELECT * FROM chat_sessions WHERE id = ? AND user_id = ?",
        (session_id, user["id"]),
    )
    if session is None:
        raise HTTPException(404, "Chat session not found.")
    messages = database.query(
        "SELECT id, role, content, sources_json, confidence, in_scope, latency_ms, created_at "
        "FROM messages WHERE session_id = ? ORDER BY id",
        (session_id,),
    )
    for message in messages:
        message["sources"] = json.loads(message.pop("sources_json") or "[]")
        message["in_scope"] = bool(message["in_scope"])
    return {"session": session, "messages": messages}


@router.delete("/sessions/{session_id}", summary="Delete one of my chat sessions")
def delete_session(session_id: int, user: dict = Depends(get_current_user)):
    session = database.query_one(
        "SELECT id FROM chat_sessions WHERE id = ? AND user_id = ?",
        (session_id, user["id"]),
    )
    if session is None:
        raise HTTPException(404, "Chat session not found.")
    database.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    database.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
    return {"deleted": True}


@router.get("/capabilities", summary="What does the bot know? (suggestions for the UI)")
def capabilities(user: dict = Depends(get_current_user)):
    documents = database.query(
        "SELECT filename, num_chunks FROM documents WHERE status = 'ready' ORDER BY filename"
    )
    from ..services.vectorstore import vector_store

    return {
        "documents": [d["filename"] for d in documents],
        "num_documents": len(documents),
        "num_chunks": vector_store.count(),
        "suggested_questions": chatbot.suggested_questions(),
    }
