"""Chat pipeline tests: grounded answers, fallback, memory, sessions.

The LLM is the FakeListChatModel (LLM_PROVIDER=fake) so these run
hermetically - they verify the pipeline wiring, retrieval, fallback and
persistence rather than the language quality. LLM refusal and API-error
paths are exercised with small patches instead of a live model.
"""
from unittest import mock

from app.services import memory


def test_ask_in_scope_question(client, user_headers):
    response = client.post(
        "/api/chat/ask",
        headers=user_headers,
        json={"message": "When was Alpha Valley University founded?"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["in_scope"] is True
    assert body["answer"]
    assert body["sources"], "grounded answers must cite sources"
    assert body["session_id"] and body["session_title"]


def test_ask_out_of_scope_gives_fallback(client, user_headers):
    """Nothing relevant found -> the retrieval floor short-circuits to the fallback."""
    from app.services import chatbot as cb

    with mock.patch.object(cb.vector_store, "search", return_value=[]):
        response = client.post(
            "/api/chat/ask",
            headers=user_headers,
            json={"message": "What is the airspeed velocity of an unladen swallow on Mars?"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["in_scope"] is False
    assert "knowledge base" in body["answer"].lower()
    assert body["sources"] == []


def test_llm_refusal_becomes_graceful_fallback(client, user_headers):
    """The LLM says the context lacks the answer -> polite fallback (no hallucination)."""
    from app.services import chatbot as cb

    with mock.patch.object(cb.rag, "generate_answer", return_value=None):
        response = client.post(
            "/api/chat/ask",
            headers=user_headers,
            json={"message": "How many floors does the library building have?"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["in_scope"] is False
    assert body["kind"] == "fallback"
    assert body["sources"] == []


def test_llm_api_error_is_handled_gracefully(client, user_headers):
    """A 429/network error must become a friendly message, not a 500 crash."""
    from app.services import chatbot as cb

    with mock.patch.object(cb.rag, "generate_answer", side_effect=RuntimeError("429 quota")):
        response = client.post(
            "/api/chat/ask",
            headers=user_headers,
            json={"message": "When was Alpha Valley University founded?"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "llm_error"
    assert "temporarily unavailable" in body["answer"]
    assert body["sources"], "retrieved sources are still shown for transparency"


def test_greeting_is_canned(client, user_headers):
    response = client.post(
        "/api/chat/ask", headers=user_headers, json={"message": "hello"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "greeting"
    assert "Hello" in body["answer"] or "hello" in body["answer"]


def test_capabilities_question(client, user_headers):
    response = client.post(
        "/api/chat/ask", headers=user_headers, json={"message": "What can you do?"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "capabilities"


def test_empty_message_rejected(client, user_headers):
    response = client.post("/api/chat/ask", headers=user_headers, json={"message": "   "})
    assert response.status_code in (400, 422)


def test_session_history_roundtrip(client, user_headers):
    ask = client.post(
        "/api/chat/ask",
        headers=user_headers,
        json={"message": "How many books can students borrow from the library?"},
    ).json()
    session_id = ask["session_id"]

    history = client.get(
        f"/api/chat/sessions/{session_id}/messages", headers=user_headers
    ).json()
    assert history["session"]["id"] == session_id
    roles = [m["role"] for m in history["messages"]]
    assert roles == ["user", "assistant"]
    assert "borrow" in history["messages"][0]["content"]


def test_sessions_listed_and_deletable(client, user_headers):
    ask = client.post(
        "/api/chat/ask", headers=user_headers, json={"message": "Who is the warden of River Hall?"}
    ).json()
    sessions = client.get("/api/chat/sessions", headers=user_headers).json()
    assert any(s["id"] == ask["session_id"] for s in sessions)

    response = client.delete(f"/api/chat/sessions/{ask['session_id']}", headers=user_headers)
    assert response.status_code == 200

    sessions = client.get("/api/chat/sessions", headers=user_headers).json()
    assert all(s["id"] != ask["session_id"] for s in sessions)


def test_cannot_access_other_users_session(client, user_headers, admin_headers):
    ask = client.post(
        "/api/chat/ask", headers=user_headers, json={"message": "Where is the Robotics Lab?"}
    ).json()
    response = client.get(
        f"/api/chat/sessions/{ask['session_id']}/messages", headers=admin_headers
    )
    assert response.status_code == 404


def test_memory_rewrites_followup_queries():
    history = [
        {"role": "user", "content": "Who leads the robotics lab?"},
        {"role": "assistant", "content": "Dr. John Baker leads the robotics lab."},
    ]
    combined = memory.build_search_query("Where is his office?", history)
    assert "robotics lab" in combined.lower()
    assert "office" in combined.lower()

    standalone = memory.build_search_query(
        "What is the tuition fee?", history
    )
    assert standalone == "What is the tuition fee?"


def test_capabilities_endpoint(client, user_headers):
    response = client.get("/api/chat/capabilities", headers=user_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["num_documents"] >= 2
    # Suggestions are KB-specific and empty unless the loaded KB defines them.
    assert isinstance(body["suggested_questions"], list)


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["embeddings"] is True
    assert body["vector_db"] is True
    assert body["llm_ready"] is True  # fake provider in tests
