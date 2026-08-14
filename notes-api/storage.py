from __future__ import annotations

import abc
import uuid
from datetime import datetime, timezone
from typing import Optional

from models import Note, NoteActionIn, NoteIn


class NotesStore(abc.ABC):
    @abc.abstractmethod
    def list_notes(self, view: Optional[str] = None) -> list[Note]:
        raise NotImplementedError

    @abc.abstractmethod
    def create_note(self, note: NoteIn, author_name: str) -> Note:
        raise NotImplementedError

    @abc.abstractmethod
    def update_note_action(self, note_id: str, action: NoteActionIn, author_name: str) -> Note:
        raise NotImplementedError

    @abc.abstractmethod
    def source_freshness(self, object_ids: list[str]) -> dict:
        raise NotImplementedError


class InMemoryNotesStore(NotesStore):
    def __init__(self) -> None:
        self._notes: list[Note] = []

    def list_notes(self, view: Optional[str] = None) -> list[Note]:
        notes = [n for n in self._notes if view is None or n.view == view]
        return sorted(notes, key=lambda n: n.created_at, reverse=True)

    def create_note(self, note: NoteIn, author_name: str) -> Note:
        created = Note(
            note_id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc).isoformat(),
            author_name=author_name,
            **note.model_dump(),
        )
        self._notes.append(created)
        return created

    def update_note_action(self, note_id: str, action: NoteActionIn, author_name: str) -> Note:
        for index, note in enumerate(self._notes):
            if note.note_id != note_id:
                continue
            updated = note.model_copy(update={
                "action_status": action.action_status,
                "action_taken": action.action_taken,
                "actioned_at": datetime.now(timezone.utc).isoformat(),
                "actioned_by": author_name,
            })
            self._notes[index] = updated
            return updated
        raise KeyError(note_id)

    def source_freshness(self, object_ids: list[str]) -> dict:
        checked_at = datetime.now(timezone.utc).isoformat()
        return {
            "checked_at": checked_at,
            "latest_modified_at": checked_at,
            "objects_checked": len(object_ids),
            "objects_found": len(object_ids),
            "missing_objects": [],
            "objects": [
                {"object_id": object_id, "type": "TABLE", "modified_at": checked_at}
                for object_id in object_ids
            ],
        }
