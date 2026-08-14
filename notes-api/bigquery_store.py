import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from google.cloud import bigquery

from models import Note, NoteActionIn, NoteIn
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
                context,
                COALESCE(action_status, 'Open') AS action_status,
                action_taken,
                actioned_at,
                actioned_by
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
                action_status=row["action_status"],
                action_taken=row["action_taken"],
                actioned_at=row["actioned_at"].isoformat() if row["actioned_at"] else None,
                actioned_by=row["actioned_by"],
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

    def update_note_action(self, note_id: str, action: NoteActionIn, author_name: str) -> Note:
        query = f"""
            UPDATE `{self._table_ref}`
            SET
                action_status = @action_status,
                action_taken = @action_taken,
                actioned_at = CURRENT_TIMESTAMP(),
                actioned_by = @actioned_by
            WHERE note_id = @note_id
        """
        job_config = bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("action_status", "STRING", action.action_status),
            bigquery.ScalarQueryParameter("action_taken", "STRING", action.action_taken),
            bigquery.ScalarQueryParameter("actioned_by", "STRING", author_name),
            bigquery.ScalarQueryParameter("note_id", "STRING", note_id),
        ])
        result = self._client.query(query, job_config=job_config).result()
        if result.num_dml_affected_rows != 1:
            raise KeyError(note_id)
        return next(note for note in self.list_notes() if note.note_id == note_id)

    def source_freshness(self, object_ids: list[str]) -> dict:
        checked_at = datetime.now(timezone.utc).isoformat()
        objects = []
        missing = []
        for object_id in object_ids:
            table_id = f"{self._client.project}.{object_id}"
            try:
                table = self._client.get_table(table_id)
            except Exception:
                missing.append(object_id)
                continue
            modified = table.modified.isoformat() if table.modified else None
            objects.append({
                "object_id": object_id,
                "type": table.table_type,
                "modified_at": modified,
            })
        latest = max((item["modified_at"] for item in objects if item["modified_at"]), default=None)
        return {
            "checked_at": checked_at,
            "latest_modified_at": latest,
            "objects_checked": len(object_ids),
            "objects_found": len(objects),
            "missing_objects": missing,
            "objects": objects,
        }
