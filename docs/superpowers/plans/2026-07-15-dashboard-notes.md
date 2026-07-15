# Dashboard Element Notes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the marketing team click a small "notes" icon on any dashboard element (metric, chart panel, campaign card, decision item, BQ object row) to read and add feedback, centralized in BigQuery so the whole team and the tool maintainer see the same notes.

**Architecture:** A new standalone `notes-api` Cloud Run service (Python/FastAPI) backed by a new append-only BigQuery table (`lumina-lakehouse.marketing_tool_ops.dashboard_notes`) handles storage. The only change to the existing static dashboard is to `outputs/marketing_decision_tool.html`: it gets a small notes client (fetch/post), a reusable "note chip" affordance wired onto every annotatable element via stable, data-derived keys, a slide-in notes drawer, and a new "Feedback" view that lists every note in one place.

**Tech Stack:** Python 3.12 + FastAPI + google-cloud-bigquery (backend); vanilla JS/HTML/CSS, no build step or framework (frontend, matching the existing file); pytest (backend tests); Node.js DOM-faking scripts under `work/` (frontend tests, matching the existing `work/verify_marketing_tool.js` pattern).

## Global Constraints

- No authentication/login for the notes feature — attribution is a self-reported display name stored in the browser's `localStorage`, matching the design spec's non-goals.
- Notes are append-only: no `PATCH`/`DELETE` endpoints, no edit/delete UI. Corrections happen as new notes.
- No real-time sync (no websockets/polling loop). Notes refresh on page load and immediately after a successful submit.
- BigQuery project is `lumina-lakehouse`; new dataset `marketing_tool_ops`; new table `dashboard_notes`.
- The frontend is a single static HTML file with inline `<style>`/`<script>` and no bundler — new frontend code must follow that same pattern (no imports, no npm frontend dependencies).
- Frontend automated tests follow the existing convention in `work/verify_marketing_tool.js`: a plain Node script that fakes just enough of `document`/`window`/`localStorage` to `new Function()`-evaluate the dashboard's inline `<script>` and assert on rendered HTML strings.

---

## Part 1 — Backend: `notes-api` service

### Task 1: Notes data models, in-memory store, and FastAPI skeleton

**Files:**
- Create: `notes-api/models.py`
- Create: `notes-api/storage.py`
- Create: `notes-api/main.py`
- Create: `notes-api/requirements.txt`
- Create: `notes-api/requirements-dev.txt`
- Test: `notes-api/tests/test_api.py`

**Interfaces:**
- Produces: `NoteIn` (pydantic model: `view`, `element_key`, `element_label`, `note_text`, `author_name`, `context`), `Note` (adds `note_id`, `created_at`), `NotesStore` abstract base with `list_notes(view: str | None) -> list[Note]` and `create_note(note: NoteIn) -> Note`, `InMemoryNotesStore`, FastAPI `app` with `GET /health`, `GET /notes`, `POST /notes`, and dependency function `get_store()`.
- Consumes: nothing yet (first task).

- [ ] **Step 1: Write the failing tests**

Create `notes-api/tests/test_api.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd notes-api && python -m pip install -r requirements.txt -r requirements-dev.txt && python -m pytest tests/test_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'main'` (or similar import error, since none of the source files exist yet).

- [ ] **Step 3: Write the models**

Create `notes-api/models.py`:

```python
from typing import Literal

from pydantic import BaseModel, Field

DashboardView = Literal["overview", "cohorts", "campaigns", "scenario", "objects"]


class NoteIn(BaseModel):
    view: DashboardView
    element_key: str = Field(min_length=1, max_length=200)
    element_label: str = Field(min_length=1, max_length=300)
    note_text: str = Field(min_length=1, max_length=4000)
    author_name: str = Field(min_length=1, max_length=120)
    context: dict = Field(default_factory=dict)


class Note(NoteIn):
    note_id: str
    created_at: str
```

- [ ] **Step 4: Write the storage interface and in-memory implementation**

Create `notes-api/storage.py`:

```python
from __future__ import annotations

import abc
import uuid
from datetime import datetime, timezone
from typing import Optional

from models import Note, NoteIn


class NotesStore(abc.ABC):
    @abc.abstractmethod
    def list_notes(self, view: Optional[str] = None) -> list[Note]:
        raise NotImplementedError

    @abc.abstractmethod
    def create_note(self, note: NoteIn) -> Note:
        raise NotImplementedError


class InMemoryNotesStore(NotesStore):
    def __init__(self) -> None:
        self._notes: list[Note] = []

    def list_notes(self, view: Optional[str] = None) -> list[Note]:
        notes = [n for n in self._notes if view is None or n.view == view]
        return sorted(notes, key=lambda n: n.created_at, reverse=True)

    def create_note(self, note: NoteIn) -> Note:
        created = Note(
            note_id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc).isoformat(),
            **note.model_dump(),
        )
        self._notes.append(created)
        return created
```

- [ ] **Step 5: Write the FastAPI app**

Create `notes-api/main.py`:

```python
import os
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from models import Note, NoteIn
from storage import InMemoryNotesStore, NotesStore

ALLOWED_ORIGINS = [origin.strip() for origin in os.environ.get("ALLOWED_ORIGINS", "*").split(",")]

app = FastAPI(title="Lumina Marketing Dashboard Notes API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_default_store = InMemoryNotesStore()


def get_store() -> NotesStore:
    return _default_store


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/notes", response_model=list[Note])
def list_notes(view: Optional[str] = None, store: NotesStore = Depends(get_store)) -> list[Note]:
    return store.list_notes(view)


@app.post("/notes", response_model=Note, status_code=201)
def create_note(note: NoteIn, store: NotesStore = Depends(get_store)) -> Note:
    try:
        return store.create_note(note)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
```

- [ ] **Step 6: Write the requirements files**

Create `notes-api/requirements.txt`:

```
fastapi>=0.115
uvicorn[standard]>=0.30
pydantic>=2.7
```

Create `notes-api/requirements-dev.txt`:

```
pytest>=8.0
httpx>=0.27
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd notes-api && python -m pytest tests/test_api.py -v`
Expected: `3 passed`

- [ ] **Step 8: Commit**

```bash
git add notes-api/models.py notes-api/storage.py notes-api/main.py notes-api/requirements.txt notes-api/requirements-dev.txt notes-api/tests/test_api.py
git commit -m "feat: add notes-api FastAPI skeleton with in-memory store"
```

---

### Task 2: BigQuery-backed store

**Files:**
- Create: `notes-api/bigquery_store.py`
- Modify: `notes-api/main.py` (swap default store to BigQuery-backed)
- Modify: `notes-api/requirements.txt` (add `google-cloud-bigquery`)
- Test: `notes-api/tests/test_bigquery_store.py`

**Interfaces:**
- Consumes: `NotesStore`, `Note`, `NoteIn` from Task 1.
- Produces: `BigQueryNotesStore(project_id: str, dataset: str, table: str)` implementing `NotesStore`.

- [ ] **Step 1: Write the failing tests**

Create `notes-api/tests/test_bigquery_store.py`:

```python
import json
from unittest.mock import MagicMock, patch

from bigquery_store import BigQueryNotesStore
from models import NoteIn


@patch("bigquery_store.bigquery.Client")
def test_create_note_inserts_json_row_with_serialized_context(mock_client_cls):
    mock_client = MagicMock()
    mock_client.insert_rows_json.return_value = []
    mock_client_cls.return_value = mock_client

    store = BigQueryNotesStore(project_id="proj", dataset="ds", table="tbl")
    note_in = NoteIn(
        view="overview",
        element_key="metric:a",
        element_label="A",
        note_text="hello",
        author_name="Jane",
        context={"region": "All markets"},
    )
    created = store.create_note(note_in)

    assert created.note_id
    mock_client.insert_rows_json.assert_called_once()
    table_ref_arg, rows_arg = mock_client.insert_rows_json.call_args[0]
    assert table_ref_arg == "proj.ds.tbl"
    assert rows_arg[0]["note_id"] == created.note_id
    assert json.loads(rows_arg[0]["context"]) == {"region": "All markets"}


@patch("bigquery_store.bigquery.Client")
def test_create_note_raises_on_bigquery_errors(mock_client_cls):
    mock_client = MagicMock()
    mock_client.insert_rows_json.return_value = [{"index": 0, "errors": ["boom"]}]
    mock_client_cls.return_value = mock_client

    store = BigQueryNotesStore(project_id="proj", dataset="ds", table="tbl")
    note_in = NoteIn(
        view="overview", element_key="metric:a", element_label="A",
        note_text="hello", author_name="Jane", context={},
    )
    try:
        store.create_note(note_in)
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "boom" in str(exc)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd notes-api && python -m pytest tests/test_bigquery_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bigquery_store'`

- [ ] **Step 3: Write the BigQuery-backed store**

Create `notes-api/bigquery_store.py`:

```python
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from google.cloud import bigquery

from models import Note, NoteIn
from storage import NotesStore


class BigQueryNotesStore(NotesStore):
    def __init__(self, project_id: str, dataset: str, table: str) -> None:
        self._client = bigquery.Client(project=project_id)
        self._table_ref = f"{project_id}.{dataset}.{table}"

    def list_notes(self, view: Optional[str] = None) -> list[Note]:
        query = f"""
            SELECT note_id, created_at, author_name, view, element_key, element_label, note_text, context
            FROM `{self._table_ref}`
            {"WHERE view = @view" if view else ""}
            ORDER BY created_at DESC
        """
        job_config = bigquery.QueryJobConfig()
        if view:
            job_config.query_parameters = [bigquery.ScalarQueryParameter("view", "STRING", view)]
        rows = self._client.query(query, job_config=job_config).result()
        return [
            Note(
                note_id=row["note_id"],
                created_at=row["created_at"].isoformat(),
                author_name=row["author_name"],
                view=row["view"],
                element_key=row["element_key"],
                element_label=row["element_label"],
                note_text=row["note_text"],
                context=json.loads(row["context"]) if row["context"] else {},
            )
            for row in rows
        ]

    def create_note(self, note: NoteIn) -> Note:
        created = Note(
            note_id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc).isoformat(),
            **note.model_dump(),
        )
        row = created.model_dump()
        row["context"] = json.dumps(row["context"])
        errors = self._client.insert_rows_json(self._table_ref, [row])
        if errors:
            raise RuntimeError(f"BigQuery insert failed: {errors}")
        return created
```

- [ ] **Step 4: Wire it in as the default store**

Modify `notes-api/main.py` — replace the `_default_store`/`get_store` block:

```python
import os
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from bigquery_store import BigQueryNotesStore
from models import Note, NoteIn
from storage import NotesStore

ALLOWED_ORIGINS = [origin.strip() for origin in os.environ.get("ALLOWED_ORIGINS", "*").split(",")]

app = FastAPI(title="Lumina Marketing Dashboard Notes API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_store_instance: Optional[NotesStore] = None


def get_store() -> NotesStore:
    global _store_instance
    if _store_instance is None:
        _store_instance = BigQueryNotesStore(
            project_id=os.environ.get("BQ_PROJECT_ID", "lumina-lakehouse"),
            dataset=os.environ.get("BQ_DATASET", "marketing_tool_ops"),
            table=os.environ.get("BQ_TABLE", "dashboard_notes"),
        )
    return _store_instance


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/notes", response_model=list[Note])
def list_notes(view: Optional[str] = None, store: NotesStore = Depends(get_store)) -> list[Note]:
    return store.list_notes(view)


@app.post("/notes", response_model=Note, status_code=201)
def create_note(note: NoteIn, store: NotesStore = Depends(get_store)) -> Note:
    try:
        return store.create_note(note)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
```

Note: `notes-api/tests/test_api.py` still passes unmodified — it overrides the `get_store` dependency directly, so it never touches `BigQueryNotesStore`.

- [ ] **Step 5: Add the BigQuery client dependency**

Modify `notes-api/requirements.txt`, add a line:

```
google-cloud-bigquery>=3.25
```

- [ ] **Step 6: Run all tests to verify they pass**

Run: `cd notes-api && python -m pip install -r requirements.txt && python -m pytest -v`
Expected: `5 passed`

- [ ] **Step 7: Commit**

```bash
git add notes-api/bigquery_store.py notes-api/main.py notes-api/requirements.txt notes-api/tests/test_bigquery_store.py
git commit -m "feat: back notes-api with BigQuery storage"
```

---

### Task 3: Containerize the service

**Files:**
- Create: `notes-api/Dockerfile`
- Create: `notes-api/.dockerignore`

**Interfaces:**
- Consumes: `notes-api/main.py` (Task 1/2), `notes-api/requirements.txt`.
- Produces: a runnable container image listening on `$PORT` (Cloud Run's convention).

- [ ] **Step 1: Write the Dockerfile**

Create `notes-api/Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY models.py storage.py bigquery_store.py main.py ./

ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
```

- [ ] **Step 2: Write the dockerignore**

Create `notes-api/.dockerignore`:

```
tests/
requirements-dev.txt
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 3: Build the image**

Run: `cd notes-api && docker build -t notes-api:local .`
Expected: build completes with `Successfully tagged notes-api:local` (or equivalent final `naming to docker.io/library/notes-api:local` line).

- [ ] **Step 4: Run the container and smoke-test the health endpoint**

Run:
```bash
docker run -d --name notes-api-smoke -p 8080:8080 notes-api:local
sleep 2
curl -s http://127.0.0.1:8080/health
docker stop notes-api-smoke && docker rm notes-api-smoke
```
Expected: `{"status":"ok"}`

Note: `/notes` will fail in this smoke test because the container has no BigQuery credentials or table yet — that's expected until Task 4. `/health` never touches BigQuery, which is why it's the right smoke check here.

- [ ] **Step 5: Commit**

```bash
git add notes-api/Dockerfile notes-api/.dockerignore
git commit -m "feat: containerize notes-api for Cloud Run"
```

---

### Task 4: Provision BigQuery table and deploy to Cloud Run

**Files:**
- Create: `notes-api/schema.sql`

**Interfaces:**
- Consumes: the container image from Task 3.
- Produces: a deployed Cloud Run service reachable at a URL the frontend will call in Part 2.

- [ ] **Step 1: Write the BigQuery DDL**

Create `notes-api/schema.sql`:

```sql
CREATE SCHEMA IF NOT EXISTS `lumina-lakehouse.marketing_tool_ops`
OPTIONS (location = 'US');

CREATE TABLE IF NOT EXISTS `lumina-lakehouse.marketing_tool_ops.dashboard_notes` (
  note_id STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  author_name STRING NOT NULL,
  view STRING NOT NULL,
  element_key STRING NOT NULL,
  element_label STRING NOT NULL,
  note_text STRING NOT NULL,
  context STRING
)
PARTITION BY DATE(created_at);
```

- [ ] **Step 2: Apply the DDL**

`gcloud auth` is currently expired in this environment (confirmed during design — the dashboard itself shows "Live BQ query was blocked by expired `gcloud` auth on 2026-07-13"), so refresh it first:

Run: `gcloud auth login`

Then apply the schema:

Run: `bq query --use_legacy_sql=false < notes-api/schema.sql`
Expected: query completes with no errors; confirm with `bq show lumina-lakehouse:marketing_tool_ops.dashboard_notes`.

- [ ] **Step 3: Look up the existing dashboard's Cloud Run region**

Run: `gcloud run services list --platform=managed --format="table(SERVICE,REGION,URL)"`
Expected: a row for the existing marketing-dashboard service. Note its `REGION` value — use the same region below so both services have comparable latency, and note its `URL` — that's the origin to allow via CORS.

- [ ] **Step 4: Deploy notes-api to Cloud Run**

Run (replace `$REGION` with the region from Step 3, and `$DASHBOARD_ORIGIN` with the existing dashboard's URL, scheme+host only, no trailing path):

```bash
cd notes-api
gcloud run deploy notes-api \
  --source=. \
  --region=$REGION \
  --allow-unauthenticated \
  --set-env-vars=BQ_PROJECT_ID=lumina-lakehouse,BQ_DATASET=marketing_tool_ops,BQ_TABLE=dashboard_notes,ALLOWED_ORIGINS=$DASHBOARD_ORIGIN
```
Expected: deployment succeeds and prints a `Service URL`. Record this URL — it's `NOTES_API_BASE` for Part 2.

- [ ] **Step 5: Grant the service's runtime account BigQuery access**

Run: `gcloud run services describe notes-api --region=$REGION --format='value(spec.template.spec.serviceAccountName)'`

If that prints a service account email, use it below. If it prints nothing, the service runs as the project's default compute service account (`gcloud iam service-accounts list` to find `PROJECT_NUMBER-compute@developer.gserviceaccount.com`).

Run (replace `$RUNTIME_SA` with that email):
```bash
gcloud projects add-iam-policy-binding lumina-lakehouse \
  --member="serviceAccount:$RUNTIME_SA" \
  --role="roles/bigquery.dataEditor" \
  --condition=None
gcloud projects add-iam-policy-binding lumina-lakehouse \
  --member="serviceAccount:$RUNTIME_SA" \
  --role="roles/bigquery.jobUser" \
  --condition=None
```

- [ ] **Step 6: Verify the deployed service end-to-end**

Run (replace `$SERVICE_URL` with the URL from Step 4):
```bash
curl -s $SERVICE_URL/health
curl -s -X POST $SERVICE_URL/notes -H "Content-Type: application/json" -d '{"view":"overview","element_key":"metric:test","element_label":"Test metric","note_text":"deployment smoke test","author_name":"Deploy Check","context":{}}'
curl -s $SERVICE_URL/notes
```
Expected: `/health` returns `{"status":"ok"}`; the `POST` returns `201` with a generated `note_id`/`created_at`; the final `GET` includes that note in its JSON array.

- [ ] **Step 7: Commit**

```bash
git add notes-api/schema.sql
git commit -m "feat: add BigQuery schema for dashboard notes"
```

---

## Part 2 — Frontend: `outputs/marketing_decision_tool.html`

### Task 5: Notes API client (fetch, post, offline queue, author identity)

**Files:**
- Modify: `outputs/marketing_decision_tool.html`

**Interfaces:**
- Consumes: the deployed `notes-api` service URL from Task 4 (`NOTES_API_BASE`).
- Produces: `allNotes` (array, module-level state), `notesForKey(key)`, `fetchNotes()`, `postNote(payload, opts)`, `getAuthorName()`, `setAuthorName(name)`. These are consumed by Tasks 6–8.

- [ ] **Step 1: Add the notes client code**

In `outputs/marketing_decision_tool.html`, insert immediately after the line `const rawData = generateData();` (just before the existing `let state = {...}` block):

```js
    const NOTES_API_BASE = (typeof window !== "undefined" && window.LUMINA_NOTES_API_BASE) || "https://notes-api-REPLACE_ME.a.run.app";
    const NOTES_AUTHOR_KEY = "luminaMarketingNotesAuthor";
    const NOTES_QUEUE_KEY = "luminaMarketingNotesQueue";
    let allNotes = [];

    function getAuthorName() {
      try {
        return localStorage.getItem(NOTES_AUTHOR_KEY) || "";
      } catch (error) {
        return "";
      }
    }

    function setAuthorName(name) {
      try {
        localStorage.setItem(NOTES_AUTHOR_KEY, name);
      } catch (error) {}
    }

    function readQueuedNotes() {
      try {
        return JSON.parse(localStorage.getItem(NOTES_QUEUE_KEY) || "[]");
      } catch (error) {
        return [];
      }
    }

    function writeQueuedNotes(queue) {
      try {
        localStorage.setItem(NOTES_QUEUE_KEY, JSON.stringify(queue));
      } catch (error) {}
    }

    function notesForKey(key) {
      return allNotes.filter(note => note.element_key === key);
    }

    async function postNote(payload, options = {}) {
      const queueOnFailure = options.queueOnFailure !== false;
      const response = await fetch(`${NOTES_API_BASE}/notes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!response.ok) {
        if (queueOnFailure) {
          const queue = readQueuedNotes();
          queue.push(payload);
          writeQueuedNotes(queue);
        }
        throw new Error(`Note save failed: ${response.status}`);
      }
      return response.json();
    }

    async function flushQueuedNotes() {
      const queue = readQueuedNotes();
      if (!queue.length) return;
      const remaining = [];
      for (const pending of queue) {
        try {
          const saved = await postNote(pending, { queueOnFailure: false });
          allNotes.unshift(saved);
        } catch (error) {
          remaining.push(pending);
        }
      }
      writeQueuedNotes(remaining);
    }

    async function fetchNotes() {
      try {
        const response = await fetch(`${NOTES_API_BASE}/notes`);
        if (!response.ok) throw new Error(`Notes fetch failed: ${response.status}`);
        allNotes = await response.json();
      } catch (error) {
        allNotes = allNotes || [];
      }
      await flushQueuedNotes();
    }
```

Replace `https://notes-api-REPLACE_ME.a.run.app` with the actual `Service URL` recorded in Task 4 Step 4 before this ships.

- [ ] **Step 2: Manually verify the client layer loads without errors**

Run: `cd "C:\Users\sflem\Documents\Codex\2026-07-13\i" && node -e "require('./work/dom_fake.js')" 2>&1 || echo "dom_fake.js not created yet — that's expected, created in Task 9"`

This step is just a placeholder sanity check that the HTML file is still syntactically valid JS; the real automated coverage for this layer lands in Task 9, once the shared test harness exists. For now, open `outputs/marketing_decision_tool.html` directly in a browser (`file://` URL) and confirm the page still renders with no console errors (the notes fetch will fail against the placeholder URL — that's expected and handled by the try/catch).

- [ ] **Step 3: Commit**

```bash
git add outputs/marketing_decision_tool.html
git commit -m "feat: add notes-api client layer to dashboard"
```

---

### Task 6: Note chips, stable entity keys, and the note drawer

**Files:**
- Modify: `outputs/marketing_decision_tool.html`

**Interfaces:**
- Consumes: `notesForKey(key)`, `getAuthorName()`, `setAuthorName(name)`, `postNote(payload, opts)` (Task 5).
- Produces: `slugify(text)`, `noteChip(key, label)`, `metricCardHtml([label, value, delta, tone])`, `decisionCardHtml({key, title, body, pills, tone})`, `wireNoteChips(scope)`, `openNoteDrawer(key, label)`, `closeNoteDrawer()`, `refreshPanelNoteBadges()`, `addPanelChips()`. Consumed by Task 7 (Feedback view reads `allNotes` directly, not these), Task 8 (init wiring calls `refreshPanelNoteBadges()`), and the Task 9 regression test (asserts on the rendered chip markup).

This is one task rather than two because a note chip with no working drawer behind it isn't a shippable increment — the drawer is what makes the chips do anything.

- [ ] **Step 1: Add CSS for the note chip and badge**

In `outputs/marketing_decision_tool.html`, immediately after the existing `.help-chip:hover, .help-chip:focus-visible { ... }` rule, add:

```css
    .note-chip {
      position: absolute;
      top: 10px;
      right: 38px;
      width: 20px;
      height: 20px;
      border: 1px solid rgba(24, 100, 171, 0.28);
      border-radius: 999px;
      background: rgba(255,255,255,0.7);
      color: #1864ab;
      display: inline-grid;
      place-items: center;
      font-size: 10px;
      font-weight: 800;
      line-height: 1;
      cursor: pointer;
      opacity: 0.6;
      box-shadow: 0 4px 12px rgba(13, 43, 24, 0.08);
      transition: opacity 140ms ease, transform 140ms ease, background 140ms ease;
      z-index: 2;
    }

    .note-chip:hover,
    .note-chip:focus-visible {
      opacity: 1;
      background: #fff;
      transform: translateY(-1px);
      outline: none;
    }

    .note-chip-count {
      position: absolute;
      top: -6px;
      right: -6px;
      min-width: 14px;
      height: 14px;
      padding: 0 3px;
      border-radius: 999px;
      background: #1864ab;
      color: #fff;
      font-size: 9px;
      line-height: 14px;
      text-align: center;
    }

    .decision-card, .object-row, .campaign-card { position: relative; }
    .decision-card .note-chip, .object-row .note-chip, .campaign-card .note-chip { right: 10px; }
```

- [ ] **Step 2: Widen the space reserved for two chips**

Modify the `.metric` rule (currently `padding-right: 42px;`) to:

```css
    .metric {
      padding: 15px;
      padding-right: 68px;
      display: grid;
      gap: 8px;
      min-height: 116px;
      position: relative;
    }
```

Modify the `.panel-head` rule (currently `padding-right: 26px;`) to:

```css
    .panel-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: start;
      padding-right: 54px;
    }
```

- [ ] **Step 3: Add `slugify` and `noteChip`**

In `outputs/marketing_decision_tool.html`, immediately after the existing `function helpChip(label) { ... }` function, add:

```js
    function slugify(text) {
      return String(text).toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
    }

    function noteChip(key, label) {
      const count = notesForKey(key).length;
      const badge = count > 0 ? `<span class="note-chip-count">${count}</span>` : "";
      return `<button type="button" class="note-chip" data-note-key="${escapeAttr(key)}" data-note-label="${escapeAttr(label)}" aria-label="Notes on ${escapeAttr(label)}">N${badge}</button>`;
    }
```

- [ ] **Step 4: Extract the shared metric-card template**

Immediately after `noteChip`, add:

```js
    function metricCardHtml([label, value, delta, tone]) {
      const key = `metric:${slugify(label)}`;
      return `
        <div class="metric">
          ${helpChip(label)}
          ${noteChip(key, label)}
          <span>${label}</span>
          <strong>${value}</strong>
          <span class="delta ${tone}">${delta}</span>
        </div>
      `;
    }
```

Modify `renderMetrics` — replace the `document.getElementById("metrics").innerHTML = ...` block:

```js
      document.getElementById("metrics").innerHTML = data.map(metricCardHtml).join("");
      wireTips(document.getElementById("metrics"));
      wireNoteChips(document.getElementById("metrics"));
```

Modify `renderCampaignMetrics` — replace its `document.getElementById("campaignMetrics").innerHTML = ...` block the same way:

```js
      document.getElementById("campaignMetrics").innerHTML = data.map(metricCardHtml).join("");
      wireTips(document.getElementById("campaignMetrics"));
      wireNoteChips(document.getElementById("campaignMetrics"));
```

`wireNoteChips` itself is defined later in this same task (Step 10) — since every render function below is edited within this one task before it's testable in a browser, forward-referencing it here within the task is fine.

Modify `renderScenario` — replace its `document.getElementById("scenarioMetrics").innerHTML = ...` block the same way:

```js
      document.getElementById("scenarioMetrics").innerHTML = metrics.map(metricCardHtml).join("");
      wireTips(document.getElementById("scenarioMetrics"));
      wireNoteChips(document.getElementById("scenarioMetrics"));
```

- [ ] **Step 5: Extract the shared decision-card template**

Immediately after `metricCardHtml`, add:

```js
    function decisionCardHtml({ key, title, body, pills, tone }) {
      return `
        <div class="decision-card">
          ${noteChip(key, title)}
          <h3>${title}</h3>
          <p>${body}</p>
          <div class="impact">${pills.map(pill => `<span class="pill ${tone}">${pill}</span>`).join("")}</div>
        </div>
      `;
    }
```

Modify `renderDecisions` — give each card a stable `key` and use the shared template:

```js
    function renderDecisions() {
      const rows = filteredRows();
      const bySource = sources.map(source => {
        const subset = rows.filter(row => row.source === source);
        const wins = aggregate(subset, "wins");
        const revenue = aggregate(subset, "revenue");
        const spend = aggregate(subset, "spend");
        const runs = aggregate(subset, "runs");
        const cap = aggregate(subset, "capacity");
        return { source, wins, revenue, spend, cpw: spend / Math.max(1, wins), roi: revenue / Math.max(1, spend), stress: Math.max(0, runs - cap) / Math.max(1, runs) };
      }).sort((a, b) => b.roi - a.roi);
      const cards = [
        {
          key: "decision:overview:top-source",
          title: `Shift incremental budget toward ${bySource[0].source}`,
          body: `${bySource[0].source} has the strongest revenue per spend in the selected cut and a manageable capacity stress signal.`,
          pills: [`${bySource[0].roi.toFixed(1)}x rev/spend`, `${fmtCurrency(bySource[0].cpw)} CPW`, `${pct(bySource[0].stress)} stress`],
          tone: "good"
        },
        {
          key: "decision:overview:capacity-throttle",
          title: "Throttle sources that create survey compression",
          body: "When closed-won inflow outruns scheduled survey capacity, marketing growth converts into rework and aging risk.",
          pills: ["Use sales_to_survey_capacity", "Protect first-pass rate", "Align launch calendar"],
          tone: "warn"
        },
        {
          key: "decision:overview:period-projection",
          title: "Use period projection as the demo close",
          body: "The projection object gives marketing a clean actual-to-date, recommended projection, confidence, and gap-to-quota story.",
          pills: ["Projection ready", "Quota gap", "Confidence band"],
          tone: "good"
        }
      ];
      document.getElementById("decisionList").innerHTML = cards.map(decisionCardHtml).join("");
      wireNoteChips(document.getElementById("decisionList"));
    }
```

Modify `renderDecisionMetricSuite` — give each of its 6 fixed cards a stable `key` and use the shared template:

```js
    function renderDecisionMetricSuite(planRows) {
      const expectedWins = planRows.reduce((sum, row) => sum + row.expectedWins, 0);
      const readiness = marketReadinessScore();
      const top = planRows[0];
      const capAdjustedCpw = planRows.reduce((sum, row) => sum + row.capacityAdjustedCpw * row.expectedWins, 0) / Math.max(1, expectedWins);
      const blendedCpw = state.campaignBudget / Math.max(1, expectedWins);
      const frictionTax = Math.max(0, capAdjustedCpw - blendedCpw);
      const grossMargin = planRows.reduce((sum, row) => sum + row.expectedGrossMargin, 0);
      const marginPerDollar = grossMargin / Math.max(1, state.campaignBudget);
      const productLift = planRows.reduce((sum, row) => sum + row.productMixLift * row.expectedRevenue, 0) / Math.max(1, planRows.reduce((sum, row) => sum + row.expectedRevenue, 0));
      const nextDollar = top ? `${fmtCurrency(top.nextTenKRevenue)} / ${fmtNum(top.nextTenKWins)} wins` : "$0 / 0 wins";
      const cards = [
        {
          key: "decision:metric-suite:market-readiness",
          title: `Market readiness: ${readiness}/100`,
          body: "Blends permit speed, utility fit, crew coverage, survey access, and cancellation risk for the selected DMV/PA market view.",
          pills: [state.region, marketReadinessTone(readiness) === "good" ? "Scale friendly" : "Guardrail needed", "AHJ + capacity"],
          tone: marketReadinessTone(readiness)
        },
        {
          key: "decision:metric-suite:capacity-adjusted-cpw",
          title: `Capacity-adjusted CPW: ${fmtCurrency(capAdjustedCpw)}`,
          body: "Normal cost per win adjusted for survey/install pressure and lower-readiness market friction.",
          pills: [`${fmtCurrency(frictionTax)} friction tax`, "Capacity object", "Campaign AHJ rollup"],
          tone: capAdjustedCpw < 5200 ? "good" : capAdjustedCpw < 6500 ? "warn" : "bad"
        },
        {
          key: "decision:metric-suite:next-10k-efficiency",
          title: `Next $10K efficiency: ${nextDollar}`,
          body: `Shows the expected return from the best incremental spend candidate, currently ${top?.campaign || "n/a"}.`,
          pills: [top ? `${top.nextDollarEfficiency.toFixed(1)}x adjusted ROI` : "0.0x", "Marginal decision", "Spend allocator"],
          tone: top && top.nextDollarEfficiency >= 7 ? "good" : "warn"
        },
        {
          key: "decision:metric-suite:gross-margin-per-dollar",
          title: `Gross margin per $: ${marginPerDollar.toFixed(1)}x`,
          body: "Uses project economics and campaign yield to shift the conversation from revenue to contribution quality.",
          pills: [`${fmtCurrency(grossMargin)} margin`, "Project economics", "Payback view"],
          tone: marginPerDollar >= 1.8 ? "good" : "warn"
        },
        {
          key: "decision:metric-suite:product-mix-lift",
          title: `Product mix lift: +${(productLift * 100).toFixed(1)} pts`,
          body: "Flags campaigns likely to produce richer systems, partner/builder demand, or battery attach upside.",
          pills: ["Battery attach", "System size", "Margin quality"],
          tone: productLift >= 0.07 ? "good" : "warn"
        },
        {
          key: "decision:metric-suite:saturation-guardrail",
          title: "Saturation guardrail",
          body: "Campaigns with high allocation shares are discounted so the recommendation avoids pouring dollars into a market/source already near diminishing returns.",
          pills: ["Diminishing return", "Budget share", "Reallocation ready"],
          tone: "warn"
        }
      ];
      document.getElementById("decisionMetricSuite").innerHTML = cards.map(decisionCardHtml).join("");
      wireNoteChips(document.getElementById("decisionMetricSuite"));
    }
```

Modify `renderCampaignRecommendations` to key each card by the real campaign entity (the same key `renderCampaignCards` in Step 6 uses, so notes show consistently everywhere that campaign appears):

```js
    function renderCampaignRecommendations(planRows) {
      const cards = planRows.slice(0, 4).map(row => {
        const tone = row.decision === "Scale" ? "good" : row.decision === "Cut" ? "bad" : "warn";
        return decisionCardHtml({
          key: `campaign:${row.source}:${row.key}`,
          title: `${row.decision}: ${row.campaign}`,
          body: row.tactic,
          pills: [
            row.source,
            `${fmtCurrency(row.plannedSpend)} planned`,
            `${row.marginalRoi.toFixed(1)}x rev/spend`,
            `${fmtCurrency(row.capacityAdjustedCpw)} cap-adj CPW`,
            `${row.marginPerDollar.toFixed(1)}x margin/$`,
            `${fmtNum(row.expectedWins)} wins`,
            `${pct(row.stress)} stress`
          ],
          tone
        });
      }).join("");
      document.getElementById("campaignRecommendations").innerHTML = cards;
      wireNoteChips(document.getElementById("campaignRecommendations"));
    }
```

Modify `renderCampaignMoves` to key the single-campaign brief by campaign entity, and each move by its rank position:

```js
    function renderCampaignMoves(planRows) {
      if (planRows.length < 2) {
        const row = planRows[0];
        document.getElementById("campaignMoves").innerHTML = row ? decisionCardHtml({
          key: `campaign:${row.source}:${row.key}:brief`,
          title: "Focused campaign brief",
          body: `${row.campaign} is isolated in this view. Use the trend, market heatmap, and decision table to decide whether to scale or hold this campaign.`,
          pills: [
            row.decision,
            `${row.marginalRoi.toFixed(1)}x rev/spend`,
            `${fmtCurrency(row.plannedSpend)} planned`,
            `${pct(row.stress)} stress`
          ],
          tone: row.decision === "Scale" ? "good" : "warn"
        }) : "";
        wireNoteChips(document.getElementById("campaignMoves"));
        return;
      }
      const scalable = planRows.filter(row => row.decision === "Scale" || row.decision === "Test").sort((a, b) => b.score - a.score);
      const weak = planRows.filter(row => row.decision === "Hold" || row.decision === "Cut").sort((a, b) => a.score - b.score);
      const fallbackWeak = [...planRows].sort((a, b) => a.score - b.score);
      const fromRows = weak.length ? weak : fallbackWeak.slice(0, 2);
      const toRows = scalable.length ? scalable : planRows.slice(0, 2);
      const moves = toRows.slice(0, 3).map((to, index) => {
        const from = fromRows[index % fromRows.length] || to;
        const moveAmount = Math.min(50000, Math.max(10000, from.plannedSpend * 0.22));
        const fromWinsPerDollar = from.expectedWins / Math.max(1, from.plannedSpend);
        const toWinsPerDollar = to.expectedWins / Math.max(1, to.plannedSpend);
        const fromRevenuePerDollar = from.expectedRevenue / Math.max(1, from.plannedSpend);
        const toRevenuePerDollar = to.expectedRevenue / Math.max(1, to.plannedSpend);
        const winDelta = Math.max(0, (toWinsPerDollar - fromWinsPerDollar) * moveAmount);
        const revenueDelta = Math.max(0, (toRevenuePerDollar - fromRevenuePerDollar) * moveAmount);
        const tone = revenueDelta > 0 ? "good" : "warn";
        return { from, to, moveAmount, winDelta, revenueDelta, tone };
      });
      document.getElementById("campaignMoves").innerHTML = moves.map((move, index) => decisionCardHtml({
        key: `decision:campaign-moves:${index}`,
        title: `Move ${fmtCurrency(move.moveAmount)} to ${move.to.campaign}`,
        body: `Take budget from ${move.from.campaign} and redeploy it where expected yield and operational fit are stronger.`,
        pills: [
          `+${fmtNum(move.winDelta)} wins`,
          `+${fmtCurrency(move.revenueDelta)} revenue`,
          `${move.to.marginalRoi.toFixed(1)}x target ROI`,
          `${pct(move.to.stress)} stress`
        ],
        tone: move.tone
      })).join("");
      wireNoteChips(document.getElementById("campaignMoves"));
    }
```

- [ ] **Step 6: Add note chips to campaign cards and object rows**

Modify `renderCampaignCards`:

```js
    function renderCampaignCards(planRows) {
      document.getElementById("campaignCards").innerHTML = planRows.map(row => {
        const tone = row.decision === "Scale" ? "good" : row.decision === "Cut" ? "bad" : "warn";
        const key = `campaign:${row.source}:${row.key}`;
        return `
          <div class="campaign-card">
            ${noteChip(key, row.campaign)}
            <div>
              <span class="pill ${tone}">${row.decision}</span>
              <h4>${row.campaign}</h4>
              <p>${row.source} / ${row.rollupLabel}: ${row.tactic}</p>
            </div>
            <div class="campaign-stats">
              <span>Spend <strong>${fmtCurrency(row.plannedSpend)}</strong></span>
              <span>Wins <strong>${fmtNum(row.expectedWins)}</strong></span>
              <span>Next $10K <strong>${fmtNum(row.nextTenKWins)}</strong></span>
            </div>
            <p>${row.guardrail} Cap-adj CPW ${fmtCurrency(row.capacityAdjustedCpw)}, margin payback ${row.paybackMonths.toFixed(1)} months.</p>
          </div>
        `;
      }).join("");
      wireNoteChips(document.getElementById("campaignCards"));
    }
```

Modify `renderObjects`:

```js
    function renderObjects() {
      const rows = objectInventory.filter(row => state.objectDomain === "All" || row[0] === state.objectDomain);
      document.getElementById("objectTable").innerHTML = rows.map(([domain, id, name, purpose, score]) => `
        <div class="object-row">
          ${noteChip(`object:${id}`, name)}
          <div>
            <code>${id}</code>
            <span>${domain}</span>
          </div>
          <strong>${name}</strong>
          <p>${purpose}</p>
          <div>
            <span>Demo fit ${score}</span>
            <div class="scorebar"><div style="width:${score}%"></div></div>
          </div>
        </div>
      `).join("");
      wireNoteChips(document.getElementById("objectTable"));
    }
```

- [ ] **Step 7: Extend the panel-level chip function**

Rename `addPanelHelp` to `addPanelChips` and have it add both chips, keyed by the panel's own heading:

```js
    function addPanelChips() {
      document.querySelectorAll(".panel").forEach(panel => {
        if (panel.__helpAdded) return;
        const heading = panel.querySelector(".panel-head h3");
        if (!heading) return;
        const label = heading.textContent;
        const key = `panel:${slugify(label)}`;
        panel.insertAdjacentHTML("beforeend", helpChip(label));
        panel.insertAdjacentHTML("beforeend", noteChip(key, label));
        panel.__helpAdded = true;
      });
      wireTips(document);
      wireNoteChips(document);
    }
```

Update the one call site near the bottom of the script — change `addPanelHelp();` to `addPanelChips();`.

- [ ] **Step 8: Add the drawer markup**

In `outputs/marketing_decision_tool.html`, immediately after `<div class="tooltip" id="tooltip"></div>`, add:

```html
  <div class="note-drawer-backdrop" id="noteDrawerBackdrop"></div>
  <aside class="note-drawer" id="noteDrawer" aria-hidden="true">
    <div class="note-drawer-head">
      <div>
        <strong id="noteDrawerLabel">Notes</strong>
        <span id="noteDrawerView"></span>
      </div>
      <button type="button" class="note-drawer-close" id="noteDrawerClose" aria-label="Close notes">×</button>
    </div>
    <div class="note-drawer-list" id="noteDrawerList"></div>
    <form class="note-drawer-form" id="noteDrawerForm">
      <textarea id="noteDrawerText" placeholder="Add a note about this..." maxlength="4000" required></textarea>
      <div class="note-drawer-form-row">
        <input id="noteDrawerAuthor" type="text" placeholder="Your name" maxlength="120" required>
        <button type="submit">Add note</button>
      </div>
      <p class="note-drawer-status" id="noteDrawerStatus"></p>
    </form>
  </aside>
```

- [ ] **Step 9: Add the drawer CSS**

Immediately after the `.decision-card .note-chip, .object-row .note-chip, .campaign-card .note-chip { right: 10px; }` rule added earlier in this task (Step 1), add:

```css
    .note-drawer-backdrop {
      position: fixed;
      inset: 0;
      background: rgba(9, 19, 13, 0.32);
      opacity: 0;
      pointer-events: none;
      transition: opacity 180ms ease;
      z-index: 29;
    }

    .note-drawer-backdrop.open { opacity: 1; pointer-events: auto; }

    .note-drawer {
      position: fixed;
      top: 0;
      right: 0;
      height: 100vh;
      width: min(380px, 92vw);
      background: #fff;
      box-shadow: -18px 0 40px rgba(13, 43, 24, 0.18);
      transform: translateX(100%);
      transition: transform 220ms ease;
      z-index: 30;
      display: grid;
      grid-template-rows: auto 1fr auto;
    }

    .note-drawer.open { transform: translateX(0); }

    .note-drawer-head {
      display: flex;
      justify-content: space-between;
      align-items: start;
      gap: 12px;
      padding: 16px;
      border-bottom: 1px solid var(--line);
    }

    .note-drawer-head span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-top: 2px;
    }

    .note-drawer-close {
      border: 0;
      background: transparent;
      font-size: 18px;
      cursor: pointer;
      color: var(--muted);
      line-height: 1;
    }

    .note-drawer-list {
      padding: 12px 16px;
      overflow-y: auto;
      display: grid;
      gap: 10px;
      align-content: start;
    }

    .note-drawer-item {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      font-size: 13px;
    }

    .note-drawer-item-meta {
      color: var(--muted);
      font-size: 11px;
      margin-bottom: 4px;
    }

    .note-drawer-empty {
      color: var(--muted);
      font-size: 13px;
    }

    .note-drawer-form {
      padding: 12px 16px 16px;
      border-top: 1px solid var(--line);
      display: grid;
      gap: 8px;
    }

    .note-drawer-form textarea {
      min-height: 70px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px;
      font: inherit;
      resize: vertical;
    }

    .note-drawer-form-row {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 8px;
    }

    .note-drawer-form-row input {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px;
    }

    .note-drawer-form-row button {
      border: 0;
      border-radius: 8px;
      background: var(--lumina-green);
      color: #06210d;
      font-weight: 700;
      padding: 0 14px;
      cursor: pointer;
    }

    .note-drawer-status {
      margin: 0;
      font-size: 11px;
      color: var(--muted);
      min-height: 14px;
    }
```

- [ ] **Step 10: Add the drawer logic**

Immediately after the `addPanelChips` function from Step 7, add:

```js
    let activeNoteKey = null;
    let activeNoteLabel = null;

    function currentNoteContext() {
      return {
        region: state.region,
        source: state.source,
        range: state.range,
        campaignObjective: state.campaignObjective,
        campaignGrain: state.campaignGrain,
        campaignDetail: state.campaignDetail
      };
    }

    function renderNoteDrawerList() {
      const notes = notesForKey(activeNoteKey);
      const list = document.getElementById("noteDrawerList");
      list.innerHTML = notes.length
        ? notes.map(note => `
            <div class="note-drawer-item">
              <div class="note-drawer-item-meta">${escapeAttr(note.author_name)} &middot; ${new Date(note.created_at).toLocaleString()}</div>
              <div>${escapeAttr(note.note_text)}</div>
            </div>
          `).join("")
        : `<p class="note-drawer-empty">No notes yet on this element.</p>`;
    }

    function openNoteDrawer(key, label) {
      activeNoteKey = key;
      activeNoteLabel = label;
      document.getElementById("noteDrawerLabel").textContent = label;
      document.getElementById("noteDrawerView").textContent = titleMap[state.view][0];
      document.getElementById("noteDrawerAuthor").value = getAuthorName();
      renderNoteDrawerList();
      document.getElementById("noteDrawer").classList.add("open");
      document.getElementById("noteDrawer").setAttribute("aria-hidden", "false");
      document.getElementById("noteDrawerBackdrop").classList.add("open");
    }

    function closeNoteDrawer() {
      document.getElementById("noteDrawer").classList.remove("open");
      document.getElementById("noteDrawer").setAttribute("aria-hidden", "true");
      document.getElementById("noteDrawerBackdrop").classList.remove("open");
      activeNoteKey = null;
    }

    function refreshPanelNoteBadges() {
      document.querySelectorAll(".panel .note-chip").forEach(chip => {
        const key = chip.dataset.noteKey;
        const count = notesForKey(key).length;
        let badge = chip.querySelector(".note-chip-count");
        if (count > 0) {
          if (!badge) {
            badge = document.createElement("span");
            badge.className = "note-chip-count";
            chip.appendChild(badge);
          }
          badge.textContent = String(count);
        } else if (badge) {
          badge.remove();
        }
      });
    }

    function wireNoteChips(scope) {
      scope.querySelectorAll(".note-chip").forEach(chip => {
        if (chip.__noteWired) return;
        chip.__noteWired = true;
        chip.addEventListener("click", () => {
          openNoteDrawer(chip.dataset.noteKey, chip.dataset.noteLabel);
        });
      });
    }
```

- [ ] **Step 11: Wire the drawer's close controls and submit handler**

Immediately after the drawer logic from Step 10, add (this sits alongside the other top-level `document.getElementById(...).addEventListener(...)` calls near the bottom of the script — see Task 8 for exactly where those live):

```js
    document.getElementById("noteDrawerClose").addEventListener("click", closeNoteDrawer);
    document.getElementById("noteDrawerBackdrop").addEventListener("click", closeNoteDrawer);
    document.getElementById("noteDrawerForm").addEventListener("submit", async event => {
      event.preventDefault();
      const text = document.getElementById("noteDrawerText").value.trim();
      const author = document.getElementById("noteDrawerAuthor").value.trim();
      const status = document.getElementById("noteDrawerStatus");
      if (!text || !author || !activeNoteKey) return;
      setAuthorName(author);
      const payload = {
        view: state.view,
        element_key: activeNoteKey,
        element_label: activeNoteLabel,
        note_text: text,
        author_name: author,
        context: currentNoteContext()
      };
      status.textContent = "Saving...";
      try {
        const saved = await postNote(payload);
        allNotes.unshift(saved);
        document.getElementById("noteDrawerText").value = "";
        status.textContent = "Saved.";
        renderNoteDrawerList();
        render();
        refreshPanelNoteBadges();
      } catch (error) {
        status.textContent = "Not saved yet — will retry automatically.";
        renderNoteDrawerList();
      }
    });
```

- [ ] **Step 12: Manually verify in a browser**

Serve the file (`powershell -File outputs/start_lumina_marketing_server.ps1`) and open it. Click a note chip on a metric tile, a panel, a campaign card, and an object row. Confirm the drawer slides in each time with the correct label, the compose form accepts text, and closing via the × button or backdrop click works. (Submitting will fail until `NOTES_API_BASE` points at the real deployed service — the status line should read "Not saved yet — will retry automatically." rather than throwing a JS error.)

- [ ] **Step 13: Commit**

```bash
git add outputs/marketing_decision_tool.html
git commit -m "feat: add note chips, stable entity keys, and the note drawer across the dashboard"
```

---

### Task 7: "Feedback" view

**Files:**
- Modify: `outputs/marketing_decision_tool.html`

**Interfaces:**
- Consumes: `allNotes` (Task 5), `titleMap`, `escapeAttr`.
- Produces: `renderFeedback()`, hooked into `render()` and `switchView`.

- [ ] **Step 1: Add the nav button**

In `outputs/marketing_decision_tool.html`, immediately after the `<button data-view="objects" ...>BQ Objects</button>` nav button, add:

```html
        <button data-view="feedback" data-short="FB"><span>Feedback</span></button>
```

- [ ] **Step 2: Add the section markup**

Immediately after the `</section>` that closes `<section id="objects" ...>` (and before `</main>`), add:

```html
      <section id="feedback" class="view hidden">
        <article class="panel">
          <div class="panel-head">
            <div>
              <h3>Team feedback</h3>
              <p>Every note left across the dashboard, in one place.</p>
            </div>
            <div class="segmented" id="feedbackFilter">
              <button class="active" data-feedback-view="All">All</button>
              <button data-feedback-view="overview">Overview</button>
              <button data-feedback-view="cohorts">Cohorts</button>
              <button data-feedback-view="campaigns">Campaigns</button>
              <button data-feedback-view="scenario">Scenario</button>
              <button data-feedback-view="objects">BQ Objects</button>
            </div>
          </div>
          <table class="table" id="feedbackTable"></table>
        </article>
      </section>
```

- [ ] **Step 3: Register the view's title and state**

Modify `titleMap` to add an entry (after the `objects` entry):

```js
      feedback: ["Team feedback", "Every note left on the dashboard, filterable by section, so the tool can be refined around real usage."]
```

Modify `state` to add a field (after `objectDomain: "All",`):

```js
      feedbackFilter: "All",
```

- [ ] **Step 4: Write `renderFeedback` and hook it into the dispatcher**

Immediately after `renderObjects`, add:

```js
    function renderFeedback() {
      const notes = state.feedbackFilter === "All" ? allNotes : allNotes.filter(note => note.view === state.feedbackFilter);
      document.getElementById("feedbackTable").innerHTML = `
        <thead><tr><th>When</th><th>Section</th><th>Element</th><th>Author</th><th>Note</th></tr></thead>
        <tbody>${notes.length ? notes.map(note => `
          <tr>
            <td>${new Date(note.created_at).toLocaleString()}</td>
            <td>${titleMap[note.view] ? titleMap[note.view][0] : note.view}</td>
            <td>${escapeAttr(note.element_label)}</td>
            <td>${escapeAttr(note.author_name)}</td>
            <td>${escapeAttr(note.note_text)}</td>
          </tr>
        `).join("") : `<tr><td colspan="5">No feedback yet.</td></tr>`}</tbody>
      `;
    }
```

Modify `render()` to add a branch:

```js
    function render() {
      if (state.view === "overview") {
        renderMetrics();
        renderOverviewCharts();
        renderDecisions();
      }
      if (state.view === "cohorts") renderCohorts();
      if (state.view === "campaigns") renderCampaignPlanner();
      if (state.view === "scenario") renderScenario();
      if (state.view === "objects") renderObjects();
      if (state.view === "feedback") renderFeedback();
    }
```

- [ ] **Step 5: Wire the section filter buttons**

Immediately after the existing `document.querySelectorAll("#objectFilter button").forEach(...)` block near the bottom of the script, add:

```js
    document.querySelectorAll("#feedbackFilter button").forEach(btn => {
      btn.addEventListener("click", () => {
        state.feedbackFilter = btn.dataset.feedbackView;
        document.querySelectorAll("#feedbackFilter button").forEach(b => b.classList.toggle("active", b === btn));
        renderFeedback();
      });
    });
```

- [ ] **Step 6: Manually verify in a browser**

Reload the page, click the new "Feedback" nav button, confirm the empty state ("No feedback yet.") renders, then click each filter segment and confirm none of them error.

- [ ] **Step 7: Commit**

```bash
git add outputs/marketing_decision_tool.html
git commit -m "feat: add Feedback view listing all dashboard notes"
```

---

### Task 8: Load notes on page init

**Files:**
- Modify: `outputs/marketing_decision_tool.html`

**Interfaces:**
- Consumes: `fetchNotes()` (Task 5), `refreshPanelNoteBadges()` (Task 6), `render()`.

- [ ] **Step 1: Call `fetchNotes()` after the initial render**

At the very end of the `<script>` block, the existing code reads:

```js
    window.addEventListener("resize", render);
    addPanelChips();
    render();
```

Change the last two lines to:

```js
    window.addEventListener("resize", render);
    addPanelChips();
    render();
    fetchNotes().then(() => {
      refreshPanelNoteBadges();
      render();
    });
```

- [ ] **Step 2: Manually verify in a browser**

With `NOTES_API_BASE` still pointed at the placeholder URL, reload the page and confirm it still renders normally (the failed fetch should be silently swallowed, leaving `allNotes` empty, per Task 5's `fetchNotes` try/catch).

- [ ] **Step 3: Commit**

```bash
git add outputs/marketing_decision_tool.html
git commit -m "feat: load dashboard notes on page init"
```

---

### Task 9: Automated regression test for stable note keys

**Files:**
- Create: `work/dom_fake.js`
- Modify: `work/verify_marketing_tool.js` (use the shared fake instead of its own copy)
- Create: `work/verify_dashboard_notes.js`

**Interfaces:**
- Consumes: the finished `outputs/marketing_decision_tool.html` from Tasks 5–8.
- Produces: `installFakeDom(extraIds)`, `loadDashboardScript()` — a shared harness other frontend verification scripts can reuse.

- [ ] **Step 1: Extract the shared DOM-faking harness**

Create `work/dom_fake.js`:

```js
const fs = require("fs");

class FakeElement {
  constructor(id = "") {
    this.id = id;
    this.value = "";
    this.innerHTML = "";
    this.textContent = "";
    this.disabled = false;
    this.clientWidth = 700;
    this.clientHeight = 280;
    this.firstChild = null;
    this.attributes = {};
    this._classes = new Set();
    this.classList = {
      toggle: (name, force) => {
        const shouldAdd = force == null ? !this._classes.has(name) : Boolean(force);
        if (shouldAdd) this._classes.add(name);
        else this._classes.delete(name);
      },
      contains: name => this._classes.has(name)
    };
  }
  addEventListener() {}
  removeChild() {}
  querySelectorAll() { return []; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] || null; }
}

function installFakeDom(extraIds = []) {
  const elements = new Map();
  function getElement(id) {
    if (!elements.has(id)) elements.set(id, new FakeElement(id));
    return elements.get(id);
  }

  global.document = {
    getElementById: getElement,
    querySelectorAll(selector) {
      if (selector === ".view") return [getElement("overview"), getElement("campaigns")];
      return [];
    },
    querySelector(selector) {
      if (selector.startsWith("#")) return getElement(selector.slice(1));
      return null;
    }
  };
  global.window = { addEventListener() {}, LUMINA_NOTES_API_BASE: "http://fake-notes-api.test" };
  global.localStorage = {
    getItem() { return null; },
    setItem() {}
  };

  [
    "appShell", "sideToggle", "campaignBudget", "campaignObjective", "campaignGrain",
    "campaignDetailSelect", "rangeSelect", "regionSelect", "sourceSelect",
    "noteDrawer", "noteDrawerBackdrop", "noteDrawerClose", "noteDrawerForm",
    "noteDrawerText", "noteDrawerAuthor", "noteDrawerStatus", "noteDrawerLabel", "noteDrawerView",
    ...extraIds
  ].forEach(id => getElement(id));

  return { getElement };
}

function loadDashboardScript() {
  const html = fs.readFileSync("outputs/marketing_decision_tool.html", "utf8");
  return html.match(/<script>([\s\S]*)<\/script>/)[1];
}

module.exports = { FakeElement, installFakeDom, loadDashboardScript };
```

- [ ] **Step 2: Point the existing verify script at the shared harness**

Modify `work/verify_marketing_tool.js` — replace everything from the top of the file through the `const run = new Function(...)` declaration with:

```js
const { installFakeDom, loadDashboardScript } = require("./dom_fake");

installFakeDom();
global.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) });

const script = loadDashboardScript();
const run = new Function(`${script}
state.view = "campaigns";
renderCampaignPlanner();
return {
  heatmap: document.getElementById("campaignHeatmap").innerHTML,
  cards: document.getElementById("campaignCards").innerHTML,
  moves: document.getElementById("campaignMoves").innerHTML,
  suite: document.getElementById("decisionMetricSuite").innerHTML,
  table: document.getElementById("campaignTable").innerHTML,
  metrics: document.getElementById("campaignMetrics").innerHTML,
  trend: document.getElementById("campaignTrendChart").innerHTML
};`);
```

Everything after that (the `const output = run();` line through the end of the file) stays exactly as it is today.

- [ ] **Step 3: Run the existing test to make sure the refactor didn't break it**

Run: `cd "C:\Users\sflem\Documents\Codex\2026-07-13\i" && node work/verify_marketing_tool.js`
Expected: prints the JSON summary object with no errors and exits `0`, same as before this task.

- [ ] **Step 4: Write the new failing test for stable note keys**

Create `work/verify_dashboard_notes.js`:

```js
const { installFakeDom, loadDashboardScript } = require("./dom_fake");

installFakeDom(["feedbackFilter", "feedbackTable"]);
global.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) });

const script = loadDashboardScript();
const run = new Function(`${script}
allNotes = [
  { note_id: "1", created_at: "2026-07-15T10:00:00Z", author_name: "Jane", view: "campaigns", element_key: "campaign:Paid Search:Google Nonbrand Search", element_label: "Google Nonbrand Search", note_text: "Great campaign card", context: {} },
  { note_id: "2", created_at: "2026-07-15T11:00:00Z", author_name: "Sam", view: "overview", element_key: "metric:projected-revenue", element_label: "Projected revenue", note_text: "Confusing metric", context: {} }
];
state.view = "campaigns";
renderCampaignPlanner();
state.view = "overview";
renderMetrics();
renderObjects();
return {
  cards: document.getElementById("campaignCards").innerHTML,
  recommendations: document.getElementById("campaignRecommendations").innerHTML,
  metrics: document.getElementById("metrics").innerHTML,
  objects: document.getElementById("objectTable").innerHTML
};`);

const output = run();

function assert(condition, message) {
  if (!condition) {
    console.error(message);
    process.exit(1);
  }
}

assert(output.cards.includes('data-note-key="campaign:Paid Search:Google Nonbrand Search"'), "Campaign card is missing its note chip key.");
assert(output.cards.includes('<span class="note-chip-count">1</span>'), "Campaign card note badge should show a count of 1.");
assert(output.recommendations.includes('data-note-key="campaign:Paid Search:Google Nonbrand Search"'), "Campaign recommendation should reuse the same entity key as the campaign card.");
assert(output.metrics.includes('data-note-key="metric:projected-revenue"'), "Projected revenue metric is missing its note chip key.");
assert(output.objects.includes('data-note-key="object:analytics_rpt.rpt_marketing_lead_cohort_performance"'), "Object row is missing its note chip key.");

console.log("Dashboard notes key wiring verified OK.");
```

- [ ] **Step 5: Run it to verify it fails (before Tasks 5–8 land) or passes (after)**

Run: `cd "C:\Users\sflem\Documents\Codex\2026-07-13\i" && node work/verify_dashboard_notes.js`

If Tasks 5–8 are already committed (the expected order in this plan), expected output is `Dashboard notes key wiring verified OK.` with exit code `0`. If any assertion fails, it will print the specific message and exit `1` — use that message to find which render function's key wiring is wrong.

- [ ] **Step 6: Commit**

```bash
git add work/dom_fake.js work/verify_marketing_tool.js work/verify_dashboard_notes.js
git commit -m "test: add automated regression coverage for stable note-chip keys"
```

---

### Task 10: End-to-end verification against the deployed service

**Files:** none (verification only)

- [ ] **Step 1: Point the dashboard at the real notes-api URL**

In `outputs/marketing_decision_tool.html`, confirm the `NOTES_API_BASE` fallback (Task 5, Step 1) was updated to the real Cloud Run URL from Task 4. If not done yet, update it now and commit:

```bash
git add outputs/marketing_decision_tool.html
git commit -m "chore: point dashboard at deployed notes-api service"
```

- [ ] **Step 2: Serve the dashboard locally and drive it in a real browser**

Run: `powershell -File "outputs/start_lumina_marketing_server.ps1"`

In the browser that opens:
1. On the Overview view, click the note chip on the "Projected revenue" metric, enter a name and a note, submit. Confirm the drawer shows "Saved." and the chip now shows a badge with count 1.
2. Switch to the Campaign Planner view, click the note chip on any campaign card, add a note.
3. Switch to the BQ Objects view, click the note chip on any object row, add a note.
4. Reload the page fully. Confirm all three note chips still show their badges and the notes are present when you reopen each drawer (proves BigQuery persistence, not just in-page state).
5. Open the new Feedback view and confirm all three notes appear, with correct section/author/text, and that filtering by section works.

- [ ] **Step 3: Confirm centralization from a second browser profile**

Open the same dashboard URL in a different browser (or an incognito/private window, which has its own `localStorage`). Confirm the three notes from Step 2 are visible there too (this is the check that notes are centralized via BigQuery, not just local to one browser).

- [ ] **Step 4: Confirm the offline fallback path**

Temporarily set `NOTES_API_BASE` (via browser devtools console: `window.LUMINA_NOTES_API_BASE = "https://example.invalid"` then reload, or by editing the file's fallback constant to a dead URL and reloading) and confirm: existing badges/notes still load from the last good fetch is not expected (a dead URL means the fetch fails and `allNotes` stays empty per Task 5's catch block) — the actual thing to confirm is that composing a note against the dead URL shows "Not saved yet — will retry automatically." instead of a raw JS error, and that reloading against the real URL afterward successfully flushes it from the queue. Revert the temporary change afterward.

- [ ] **Step 5: Publish the change to the marketing team's live Cloud Run URL**

Everything above verifies the local copy of `outputs/marketing_decision_tool.html`. The marketing team's actual dashboard is a separate, already-deployed Cloud Run service whose build/deploy pipeline is outside this plan (this project has no Dockerfile or deploy script for it — it was deployed some other way). Re-run whatever process currently publishes that static site (redeploy, re-run a build trigger, `gcloud run deploy` from wherever its source actually lives, etc.) so the live URL picks up this file's changes. Once redeployed, repeat Steps 2–3 against the live URL instead of the local server to confirm the feature actually reaches the team.

This task has no code changes of its own — it's the acceptance gate confirming Tasks 1–10 work together as designed.
