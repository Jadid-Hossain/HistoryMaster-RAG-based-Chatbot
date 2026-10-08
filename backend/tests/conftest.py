"""Pytest fixtures: isolated data dir, fake LLM, small seeded KB, API clients."""
import os
import tempfile
from pathlib import Path

# Must run BEFORE any app import: isolate storage and force the fake LLM.
_TMP = Path(tempfile.mkdtemp(prefix="knowbot_test_"))
os.environ["KB_DATA_DIR"] = str(_TMP)
os.environ["LLM_PROVIDER"] = "fake"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import database  # noqa: E402
from app.logger import setup_logging  # noqa: E402
from app.main import app  # noqa: E402
from app.services import ingest  # noqa: E402
from app.services.embeddings import embedder  # noqa: E402
from app.services.vectorstore import vector_store  # noqa: E402

setup_logging()

TEST_DOCS = {
    "test_university.txt": (
        "Alpha Valley University was founded in 2001 in the city of Alpha Valley. "
        "The university has 5,200 students and 300 faculty members. "
        "The Vice-Chancellor is Professor Maria Santos. "
        "The Computer Science department is led by Dr. John Baker, whose office is Room 210 "
        "in the Science Building. The university library holds 80,000 books and opens at 8 AM. "
        "Students may borrow up to 4 books for 14 days. The annual tuition fee is 3,000 dollars "
        "per semester. The Robotics Lab is located in Room 402 of the Science Building."
    ),
    "test_hostel.txt": (
        "Alpha Valley University has three hostels: River Hall, Mountain Hall and Forest Hall. "
        "The hostel fee is 600 dollars per semester including meals. "
        "The warden of River Hall is Mr. David Kim. Hostel rooms are shared by two students. "
        "Wi-Fi is available in all hostels and hot water runs 24 hours a day."
    ),
}


@pytest.fixture(scope="session", autouse=True)
def seeded_kb():
    """Load embeddings + vector store and ingest two small test documents."""
    embedder.load()
    vector_store.load()
    for filename, text in TEST_DOCS.items():
        from langchain_core.documents import Document

        database.init_db()
        ingest.ingest_documents(
            filename, "txt", [Document(page_content=text, metadata={"source": filename})],
            "tester",
        )
    yield


@pytest.fixture(scope="session")
def client(seeded_kb):
    with TestClient(app) as c:  # context manager runs the lifespan (LLM etc.)
        yield c


def _login(c: TestClient, username: str, password: str) -> dict:
    response = c.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture(scope="session")
def admin_headers(client):
    return _login(client, "admin", "admin123")


@pytest.fixture(scope="session")
def user_headers(client):
    return _login(client, "user", "user123")
