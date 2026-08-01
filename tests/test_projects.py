from fastapi.testclient import TestClient


def test_create_project(client: TestClient) -> None:
    user = client.post("/users", json={"name": "Anahit", "email": "anahit@example.com"}).json()

    response = client.post(
        "/projects",
        json={"name": "Billing Service", "description": "A plan", "owner_id": user["id"]},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Billing Service"
    assert body["description"] == "A plan"
    assert body["owner_id"] == user["id"]


def test_create_project_with_invalid_owner_returns_404(client: TestClient) -> None:
    response = client.post("/projects", json={"name": "Orphan", "owner_id": 999999})

    assert response.status_code == 404


def test_create_project_without_owner_returns_422(client: TestClient) -> None:
    response = client.post("/projects", json={"name": "Nameless"})

    assert response.status_code == 422
