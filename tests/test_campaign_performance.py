import sys
from datetime import date
from http import HTTPStatus
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard_server import (
    DashboardHandler,
    build_campaign_performance_query,
    shape_campaign_row,
)


class FakeQueryResult:
    def __init__(self, rows):
        self._rows = rows

    def result(self):
        return self._rows


class FakeClient:
    def __init__(self, rows):
        self._rows = rows
        self.last_query = None
        self.last_job_config = None

    def query(self, query, job_config=None):
        self.last_query = query
        self.last_job_config = job_config
        return FakeQueryResult(self._rows)


class ExplodingClient:
    def query(self, query, job_config=None):
        raise RuntimeError("BigQuery is unavailable")


def fixture_row():
    return {
        "campaign": "Solar Reviews",
        "campaignRollup": "Partner",
        "month": date(2026, 6, 1),
        "leads": 100,
        "wins": 10,
        "spend": 10000,
        "revenue": 50000,
    }


def test_query_groups_campaigns_by_month():
    query = build_campaign_performance_query(months=6)
    assert "INTERVAL @months MONTH" in query
    assert "period_grain = 'MONTH'" in query
    assert "period_start_date AS month" in query
    assert "campaign_reporting_rollup_name AS campaignRollup" in query
    assert "GROUP BY campaign, campaignRollup, month" in query


def test_query_only_filters_campaign_when_provided():
    assert "campaign_name = @campaign" not in build_campaign_performance_query()
    assert "campaign_name = @campaign" in build_campaign_performance_query(campaign="Solar Reviews")


def test_shape_campaign_row_serializes_month_and_ratios():
    shaped = shape_campaign_row(fixture_row())
    assert shaped["month"] == "2026-06-01"
    assert shaped["campaignRollup"] == "Partner"
    assert shaped["cpw"] == 1000
    assert shaped["revenuePerSpend"] == 5
    assert shaped["leadToWinRate"] == 0.1
    assert shaped["sampleSizeBucket"] == "Sufficient Sample"


def test_shape_campaign_row_handles_no_sample():
    row = fixture_row()
    row.update(leads=0, wins=0, spend=0, revenue=0)
    shaped = shape_campaign_row(row)
    assert shaped["cpw"] is None
    assert shaped["revenuePerSpend"] is None
    assert shaped["leadToWinRate"] is None
    assert shaped["sampleSizeBucket"] == "No Same-Period Sample"


def test_campaign_handler_shapes_rows_and_binds_params(monkeypatch):
    fake_client = FakeClient([fixture_row()])
    monkeypatch.setattr(DashboardHandler, "_client", fake_client)
    handler = DashboardHandler.__new__(DashboardHandler)
    status, result = handler._campaign_performance({"months": ["3"], "campaign": ["Solar Reviews"]})
    assert status == HTTPStatus.OK
    assert result[0]["month"] == "2026-06-01"
    assert [param.name for param in fake_client.last_job_config.query_parameters] == ["months", "campaign"]


def test_campaign_handler_rejects_invalid_months(monkeypatch):
    monkeypatch.setattr(DashboardHandler, "_client", FakeClient([]))
    handler = DashboardHandler.__new__(DashboardHandler)
    status, result = handler._campaign_performance({"months": ["nope"]})
    assert status == HTTPStatus.BAD_REQUEST
    assert "detail" in result


def test_campaign_handler_reports_bigquery_failure(monkeypatch):
    monkeypatch.setattr(DashboardHandler, "_client", ExplodingClient())
    handler = DashboardHandler.__new__(DashboardHandler)
    status, result = handler._campaign_performance({})
    assert status == HTTPStatus.BAD_GATEWAY
    assert "detail" in result
