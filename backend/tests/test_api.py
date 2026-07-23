def test_source_status_and_initial_sync(client):
    status = client.get("/api/v1/source/status")
    assert status.status_code == 200
    assert status.json()["status"] == "ready"

    response = client.post("/api/v1/sync", json={"account_id": "dev-account", "mode": "initial"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["inserted_count"] == 5


def test_idempotent_import_and_search_context(client):
    counts = []
    for _ in range(3):
        response = client.post("/api/v1/sync", json={"account_id": "dev-account", "mode": "initial"})
        counts.append((response.json()["inserted_count"], response.json()["duplicate_count"]))
    assert counts[0] == (5, 0)
    assert counts[1] == (0, 5)
    assert counts[2] == (0, 5)

    search = client.get("/api/v1/messages/search", params={"account_id": "dev-account", "q": "离线部署"})
    assert search.status_code == 200
    assert len(search.json()) == 1
    assert "离线部署" in search.json()[0]["text_content"]

    message_id = search.json()[0]["id"]
    context = client.get(f"/api/v1/messages/{message_id}/context", params={"radius": 2})
    assert context.status_code == 200
    assert context.json()["anchor_id"] == message_id
    assert len(context.json()["messages"]) >= 2


def test_contact_search_and_account_isolation(client):
    client.post("/api/v1/sync", json={"account_id": "dev-account", "mode": "initial"})
    contacts = client.get("/api/v1/contacts", params={"account_id": "dev-account", "query": "张"})
    assert contacts.status_code == 200
    assert [item["display_name"] for item in contacts.json()] == ["张工"]

    other = client.get("/api/v1/contacts", params={"account_id": "another-account"})
    assert other.status_code == 200
    assert other.json() == []
