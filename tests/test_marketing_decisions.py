import json
import sys
from datetime import date, datetime, timedelta, timezone
from http import HTTPStatus
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard_server import (
    DECISIONS_TABLE_REF,
    DashboardHandler,
    aggregate_marketing_funnel_rows,
    evaluate_marketing_decision_progress,
)


class InsertClient:
    def __init__(self, errors=None):
        self.errors = errors or []
        self.table_ref = None
        self.rows = None

    def insert_rows_json(self, table_ref, rows):
        self.table_ref = table_ref
        self.rows = rows
        return self.errors


class ArchiveClient:
    def __init__(self, affected=1):
        self.num_dml_affected_rows = affected
        self.query_text = ""
        self.job_config = None

    def query(self, query, job_config=None):
        self.query_text = query
        self.job_config = job_config
        return self

    def result(self):
        return []


def decision(created_at, **overrides):
    value = {
        "decision_id": "decision-1",
        "created_at": created_at.isoformat(),
        "baseline": {"wins": 10, "spend": 20000, "cpw": 2000},
        "expected": {"wins": 15, "spend": 25000, "cpw": 1667},
        "scenario": {"budget": 25},
        "primary_metric": "wins",
    }
    value.update(overrides)
    return value


def test_funnel_aggregation_builds_tracking_metrics():
    result = aggregate_marketing_funnel_rows([
        {"leads": 100, "sets": 40, "runs": 30, "wins": 10, "revenue": 500000, "effectiveSpend": 20000},
        {"leads": 50, "sets": 20, "runs": 10, "wins": 5, "revenue": 250000, "effectiveSpend": 10000},
    ])
    assert result["leads"] == 150
    assert result["wins"] == 15
    assert result["setRate"] == 0.4
    assert result["cpw"] == 2000


def test_progress_marks_target_and_observed_spend_change():
    now = datetime(2026, 7, 29, tzinfo=timezone.utc)
    result = evaluate_marketing_decision_progress(
        decision(now - timedelta(days=14)),
        {"wins": 15, "spend": 26000, "cpw": 1733},
        now=now,
    )
    assert result["status"] == "Target reached"
    assert result["implementationSignal"] == "Spend change detected"
    assert result["progressToTarget"] == 1


def test_progress_keeps_new_decisions_in_maturity_window():
    now = datetime(2026, 7, 29, tzinfo=timezone.utc)
    result = evaluate_marketing_decision_progress(
        decision(now - timedelta(days=3)),
        {"wins": 8, "spend": 19000, "cpw": 2375},
        now=now,
    )
    assert result["status"] == "Maturing"


def test_create_decision_captures_identity_scope_and_frozen_snapshots(monkeypatch):
    client = InsertClient()
    monkeypatch.setattr(DashboardHandler, "_client", client)
    handler = DashboardHandler.__new__(DashboardHandler)
    handler._iap_user = lambda: "jane.doe@luminasolar.com"
    payload = {
        "decisionType": "Recover",
        "question": "Can SolarReviews recover lead-to-set in Montgomery County?",
        "action": "Run a 30-day conversion test.",
        "sourceView": "funnel",
        "filters": {
            "campaign": "SolarReviews",
            "ahj": "Montgomery County",
            "operatingRegion": "Maryland",
            "months": 7,
        },
        "primaryMetric": "setRate",
        "horizonDays": 30,
        "baseline": {"leads": 100, "setRate": 0.29},
        "scenario": {"setRate": 20},
        "expected": {"leads": 100, "setRate": 0.35},
        "evidence": ["Lead-to-set trails benchmark."],
        "dataConfidence": "Spend complete",
    }
    status, created = handler._create_marketing_decision(payload)
    assert status == HTTPStatus.CREATED
    assert client.table_ref == DECISIONS_TABLE_REF
    inserted = client.rows[0]
    assert inserted["created_by_email"] == "jane.doe@luminasolar.com"
    assert inserted["created_by_name"] == "Jane Doe"
    assert inserted["campaign"] == "SolarReviews"
    assert inserted["ahj"] == "Montgomery County"
    assert json.loads(inserted["baseline"])["setRate"] == 0.29
    assert date.fromisoformat(inserted["review_after"]) > date.today()
    assert created["evidence"] == ["Lead-to-set trails benchmark."]


def test_create_decision_rejects_invalid_tracking_metric(monkeypatch):
    monkeypatch.setattr(DashboardHandler, "_client", InsertClient())
    handler = DashboardHandler.__new__(DashboardHandler)
    status, payload = handler._create_marketing_decision({
        "question": "Test",
        "primaryMetric": "madeUpMetric",
    })
    assert status == HTTPStatus.BAD_REQUEST
    assert "not supported" in payload["detail"]


def test_archive_decision_is_owner_scoped_and_preserves_ledger(monkeypatch):
    client = ArchiveClient()
    monkeypatch.setattr(DashboardHandler, "_client", client)
    handler = DashboardHandler.__new__(DashboardHandler)
    handler._iap_user = lambda: "jane.doe@luminasolar.com"

    status, payload = handler._archive_marketing_decision({"decisionId": "decision-1"})

    assert status == HTTPStatus.OK
    assert payload == {"decisionId": "decision-1", "status": "Archived"}
    assert "SET status = 'Archived'" in client.query_text
    assert "created_by_email = @created_by_email" in client.query_text
    parameters = {item.name: item.value for item in client.job_config.query_parameters}
    assert parameters == {
        "decision_id": "decision-1",
        "created_by_email": "jane.doe@luminasolar.com",
    }


def test_archive_decision_reports_missing_or_inaccessible_record(monkeypatch):
    monkeypatch.setattr(DashboardHandler, "_client", ArchiveClient(affected=0))
    handler = DashboardHandler.__new__(DashboardHandler)
    handler._iap_user = lambda: "jane.doe@luminasolar.com"

    status, payload = handler._archive_marketing_decision({"decisionId": "decision-1"})

    assert status == HTTPStatus.NOT_FOUND
    assert "another user" in payload["detail"]
