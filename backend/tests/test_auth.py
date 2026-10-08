"""Authentication & authorization tests."""


def test_register_new_user(client):
    response = client.post(
        "/api/auth/register", json={"username": "newstudent", "password": "secret123"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["role"] == "user"
    assert body["username"] == "newstudent"


def test_register_duplicate_username(client):
    response = client.post(
        "/api/auth/register", json={"username": "newstudent", "password": "secret123"}
    )
    assert response.status_code == 400
    assert "already taken" in response.json()["detail"]


def test_register_invalid_username(client):
    response = client.post(
        "/api/auth/register", json={"username": "a", "password": "secret123"}
    )
    assert response.status_code in (400, 422)


def test_login_success(client):
    response = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin123"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "admin"
    assert body["access_token"]


def test_login_wrong_password(client):
    response = client.post(
        "/api/auth/login", json={"username": "admin", "password": "wrong"}
    )
    assert response.status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_returns_profile(client, user_headers):
    response = client.get("/api/auth/me", headers=user_headers)
    assert response.status_code == 200
    assert response.json()["username"] == "user"
    assert response.json()["role"] == "user"


def test_admin_endpoint_forbidden_for_user(client, user_headers):
    response = client.get("/api/kb/documents", headers=user_headers)
    assert response.status_code == 403


def test_admin_endpoint_allowed_for_admin(client, admin_headers):
    response = client.get("/api/kb/documents", headers=admin_headers)
    assert response.status_code == 200
