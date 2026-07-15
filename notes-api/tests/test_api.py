from fastapi.testclient import TestClient

from auth import VerifiedUser, require_google_user
from main import app, get_store
from storage import InMemoryNotesStore


def make_client():
    store = InMemoryNotesStore()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[require_google_user] = lambda: VerifiedUser(email="jane@luminasolar.com", name="Jane Doe")
    return TestClient(app), store


def test_create_note_returns_generated_id_and_timestamp():
    client, _ = make_client()
    payload = {
        "view": "overview",
        "element_key": "metric:projected-revenue",
        "element_label": "Projected revenue",
        "target_type": "metric",
        "feedback_type": "tweak",
        "note_text": "This number confuses the team.",
        "context": {"region": "All markets", "source": "All sources", "range": 12},
    }
    response = client.post("/notes", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["note_id"]
    assert body["created_at"]
    assert body["element_key"] == "metric:projected-revenue"
    assert body["target_type"] == "metric"
    assert body["feedback_type"] == "tweak"
    assert body["author_name"] == "Jane Doe"
    app.dependency_overrides.clear()


def test_create_note_defaults_target_and_feedback_type_for_old_clients():
    client, _ = make_client()
    response = client.post("/notes", json={
        "view": "overview",
        "element_key": "panel:source-efficiency",
        "element_label": "Source efficiency",
        "note_text": "Useful, but needs more explanation.",
        "context": {},
    })
    assert response.status_code == 201
    body = response.json()
    assert body["target_type"] == "tile"
    assert body["feedback_type"] == "tweak"
    app.dependency_overrides.clear()


def test_list_notes_filters_by_view():
    client, _ = make_client()
    client.post("/notes", json={
        "view": "overview", "element_key": "metric:a", "element_label": "A",
        "note_text": "note a", "context": {},
    })
    client.post("/notes", json={
        "view": "campaigns", "element_key": "campaign:x", "element_label": "X",
        "note_text": "note b", "context": {},
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
        "note_text": "hello", "context": {},
    })
    assert response.status_code == 422
    app.dependency_overrides.clear()


def test_create_note_rejects_invalid_feedback_type():
    client, _ = make_client()
    response = client.post("/notes", json={
        "view": "overview", "element_key": "metric:a", "element_label": "A",
        "feedback_type": "maybe", "note_text": "hello", "context": {},
    })
    assert response.status_code == 422
    app.dependency_overrides.clear()


def test_requests_without_valid_google_identity_are_rejected():
    store = InMemoryNotesStore()
    app.dependency_overrides[get_store] = lambda: store
    client = TestClient(app)
    response = client.get("/notes")
    assert response.status_code == 401
    app.dependency_overrides.clear()
