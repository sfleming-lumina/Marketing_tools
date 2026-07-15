from fastapi.testclient import TestClient

from main import app, get_store
from storage import InMemoryNotesStore


def make_client():
    store = InMemoryNotesStore()
    app.dependency_overrides[get_store] = lambda: store
    return TestClient(app), store


def test_create_note_returns_generated_id_and_timestamp():
    client, _ = make_client()
    payload = {
        "view": "overview",
        "element_key": "metric:projected-revenue",
        "element_label": "Projected revenue",
        "note_text": "This number confuses the team.",
        "author_name": "Jane Doe",
        "context": {"region": "All markets", "source": "All sources", "range": 12},
    }
    response = client.post("/notes", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["note_id"]
    assert body["created_at"]
    assert body["element_key"] == "metric:projected-revenue"
    app.dependency_overrides.clear()


def test_list_notes_filters_by_view():
    client, _ = make_client()
    client.post("/notes", json={
        "view": "overview", "element_key": "metric:a", "element_label": "A",
        "note_text": "note a", "author_name": "Jane", "context": {},
    })
    client.post("/notes", json={
        "view": "campaigns", "element_key": "campaign:x", "element_label": "X",
        "note_text": "note b", "author_name": "Jane", "context": {},
    })
    response = client.get("/notes", params={"view": "campaigns"})
    assert response.status_code == 200
    notes = response.json()
    assert len(notes) == 1
    assert notes[0]["view"] == "campaigns"
    app.dependency_overrides.clear()


def test_create_note_rejects_invalid_view():
    client, _ = make_client()
    response = client.post("/notes", json={
        "view": "not-a-real-view", "element_key": "metric:a", "element_label": "A",
        "note_text": "hello", "author_name": "Jane", "context": {},
    })
    assert response.status_code == 422
    app.dependency_overrides.clear()
