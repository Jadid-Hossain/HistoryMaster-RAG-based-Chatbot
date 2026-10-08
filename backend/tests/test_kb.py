"""Knowledge base management tests: upload, list, delete, incremental updates."""
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


def _test_doc_id(client, admin_headers, filename: str) -> int:
    docs = client.get("/api/kb/documents", headers=admin_headers).json()
    return next(d["id"] for d in docs if d["filename"] == filename)


def test_upload_txt_document(client, admin_headers):
    content = (
        "The Alpha Valley chess club meets every Friday at 5 PM in the Student Center. "
        "The club president is Sofia Rahman and the faculty advisor is Professor Ian Miles. "
        "Membership is free for all enrolled students."
    ).encode("utf-8")
    response = client.post(
        "/api/kb/documents",
        headers=admin_headers,
        files={"files": ("test_chess_club.txt", content, "text/plain")},
    )
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["status"] == "ready", result
    assert result["num_chunks"] >= 1


def test_upload_rejects_unsupported_type(client, admin_headers):
    response = client.post(
        "/api/kb/documents",
        headers=admin_headers,
        files={"files": ("virus.exe", b"MZ...", "application/octet-stream")},
    )
    assert response.status_code == 400


def test_document_list_and_delete(client, admin_headers):
    docs = client.get("/api/kb/documents", headers=admin_headers).json()
    assert any(d["filename"] == "test_university.txt" for d in docs)

    doc_id = _test_doc_id(client, admin_headers, "test_chess_club.txt")
    response = client.delete(f"/api/kb/documents/{doc_id}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["deleted"] is True

    docs_after = client.get("/api/kb/documents", headers=admin_headers).json()
    assert all(d["id"] != doc_id for d in docs_after)


def test_incremental_update_no_retrain(client, admin_headers):
    """Upload a brand-new fact and query it immediately - no retraining step.

    With the fake LLM the *content* of the answer is scripted, so we verify
    the RAG wiring: the new document must be retrievable (cited in sources)
    and the pipeline must answer in-scope right after the upload.
    """
    content = (
        "The Alpha Valley planetarium opens in November 2026 on the top floor of the "
        "Science Building. Entry is free for university students on Wednesdays."
    ).encode("utf-8")
    upload = client.post(
        "/api/kb/documents",
        headers=admin_headers,
        files={"files": ("test_planetarium.txt", content, "text/plain")},
    )
    assert upload.status_code == 200, upload.text

    answer = client.post(
        "/api/chat/ask",
        headers=admin_headers,
        json={"message": "When is entry to the planetarium free for students?"},
    )
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["in_scope"] is True
    source_docs = [s["document"] for s in body["sources"]]
    assert "test_planetarium.txt" in source_docs


def test_url_ingest_from_local_server(client, admin_headers):
    html = (
        "<html><head><title>Alpha Valley News</title></head><body>"
        "<h1>Alpha Valley News</h1>"
        "<p>The new campus swimming pool opens on 5 March 2027 next to the sports complex. "
        "The pool will be free for students every weekday morning from 6 AM to 8 AM.</p>"
        "</body></html>"
    ).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(html)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        response = client.post(
            "/api/kb/url",
            headers=admin_headers,
            json={"url": f"http://127.0.0.1:{server.server_port}/news"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["num_chunks"] >= 1
    finally:
        server.shutdown()
