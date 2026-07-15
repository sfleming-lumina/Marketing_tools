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
