from fastapi.testclient import TestClient


def test_create_user(client: TestClient) -> None:
    response = client.post("/users", json={"name": "Anahit", "email": "anahit@example.com"})

    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["name"] == "Anahit"
    assert body["email"] == "anahit@example.com"


def test_duplicate_email_returns_409(client: TestClient) -> None:
    client.post("/users", json={"name": "Anahit", "email": "anahit@example.com"})

    response = client.post("/users", json={"name": "Impostor", "email": "anahit@example.com"})

    assert response.status_code == 409


def test_invalid_email_returns_422(client: TestClient) -> None:
    response = client.post("/users", json={"name": "Anahit", "email": "not-an-email"})

    assert response.status_code == 422


def test_blank_name_returns_422(client: TestClient) -> None:
    response = client.post("/users", json={"name": "", "email": "valid@example.com"})

    assert response.status_code == 422


def test_list_users_pagination(client: TestClient) -> None:
    for index in range(5):
        client.post("/users", json={"name": f"User {index}", "email": f"u{index}@example.com"})

    response = client.get("/users", params={"limit": 2, "offset": 1})

    assert response.status_code == 200
    emails = [user["email"] for user in response.json()]
    assert emails == ["u1@example.com", "u2@example.com"]


def test_delete_user_cascades_projects(client: TestClient) -> None:
    user = client.post("/users", json={"name": "Anahit", "email": "anahit@example.com"}).json()
    first = client.post("/projects", json={"name": "First", "owner_id": user["id"]}).json()
    second = client.post("/projects", json={"name": "Second", "owner_id": user["id"]}).json()

    assert client.delete(f"/users/{user['id']}").status_code == 204

    assert client.get(f"/users/{user['id']}").status_code == 404
    assert client.get(f"/projects/{first['id']}").status_code == 404
    assert client.get(f"/projects/{second['id']}").status_code == 404
