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
