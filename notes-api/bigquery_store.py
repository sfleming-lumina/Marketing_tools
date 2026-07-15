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
            SELECT
                note_id,
                created_at,
                author_name,
                view,
                element_key,
                element_label,
                COALESCE(target_type, 'tile') AS target_type,
                COALESCE(feedback_type, 'tweak') AS feedback_type,
                note_text,
                context
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
                target_type=row["target_type"],
                feedback_type=row["feedback_type"],
                note_text=row["note_text"],
                context=json.loads(row["context"]) if row["context"] else {},
            )
            for row in rows
        ]

    def create_note(self, note: NoteIn, author_name: str) -> Note:
        created = Note(
            note_id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc).isoformat(),
            author_name=author_name,
            **note.model_dump(),
        )
        row = created.model_dump()
        row["context"] = json.dumps(row["context"])
        errors = self._client.insert_rows_json(self._table_ref, [row])
        if errors:
            raise RuntimeError(f"BigQuery insert failed: {errors}")
        return created
