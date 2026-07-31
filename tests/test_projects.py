from fastapi.testclient import TestClient


def test_create_project(client: TestClient) -> None:
    user = client.post("/users", json={"name": "Ada", "email": "ada@example.com"}).json()

    response = client.post(
        "/projects",
        json={"name": "Analytical Engine", "description": "A plan", "owner_id": user["id"]},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Analytical Engine"
    assert body["description"] == "A plan"
    assert body["owner_id"] == user["id"]


def test_create_project_with_invalid_owner_returns_404(client: TestClient) -> None:
    response = client.post("/projects", json={"name": "Orphan", "owner_id": 999999})

    assert response.status_code == 404
