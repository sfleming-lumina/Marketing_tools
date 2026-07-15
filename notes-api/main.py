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
