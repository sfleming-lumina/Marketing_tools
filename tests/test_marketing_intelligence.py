import sys
from datetime import date, datetime, timezone
from http import HTTPStatus
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard_server import (
    DashboardHandler,
    OFFICIAL_REPORT_BENCHMARKS,
    build_marketing_funnel_query,
    build_marketing_geo_query,
    build_marketing_projection_query,
    build_marketing_reconciliation_query,
    shape_marketing_funnel_row,
)


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def result(self):
        return self.rows


class FakeClient:
    def __init__(self, rows):
        self.rows = rows
        self.last_query = None
        self.last_job_config = None

    def query(self, query, job_config=None):
        self.last_query = query
        self.last_job_config = job_config
        return FakeResult(self.rows)


class ExplodingClient:
    def query(self, query, job_config=None):
        raise RuntimeError("warehouse offline")


def funnel_row(**overrides):
    row = {
        "month": date(2026, 7, 1),
        "campaignId": "701-test",
        "campaign": "Summer Search",
        "campaignRollup": "3rd Party Vendors LSR",
        "campaignSubrollup": "Paid Search",
        "leads": 100,
        "sets": 40,
        "runs": 30,
        "wins": 10,
        "losses": 20,
        "revenue": 500000,
        "recordedSpend": 20000,
        "effectiveSpend": 20000,
        "activePipeline": 25,
        "activePipelineRevenue": 800000,
        "expectedRemainingWins": 5,
        "expectedRemainingRevenue": 250000,
        "benchmarkLeadToWinRate": 0.09,
        "spendCompleteLeadShare": 1.0,
        "recordedSpendRows": 1,
        "derivedSpendRows": 0,
        "zeroPayoutRows": 0,
        "knownIncompleteRows": 0,
        "leadOnlyRows": 0,
        "benchmarkRows": 1,
        "cohortRows": 1,
        "spendCoverageNote": "Recorded spend",
        "loadedAt": datetime(2026, 7, 28, tzinfo=timezone.utc),
    }
    row.update(overrides)
    return row


def test_funnel_and_geo_queries_bind_all_optional_filters():
    values = {
        "months": 7,
        "campaign": "Summer Search",
        "rollup": "3rd Party Vendors LSR",
        "state": "VA",
        "county": "Fairfax",
        "ahj": "Fairfax County",
    }
    for query in (build_marketing_funnel_query(**values), build_marketing_geo_query(**values)):
        assert "rpt_marketing_funnel_analysis_runtime" in query
        for name in ("campaign", "rollup", "state", "county", "ahj"):
            assert f"@{name}" in query
        assert "INTERVAL @months MONTH" in query


def test_projection_query_uses_confidence_and_current_month():
    query = build_marketing_projection_query(campaign="Summer Search")
    assert "rpt_marketing_period_projection_runtime" in query
    assert "MAX(projection_confidence)" in query
    assert "projection_period_start_date = latest.latest_start" in query
    assert "campaign_name = @campaign" in query


def test_funnel_shaper_uses_spend_when_complete():
    shaped = shape_marketing_funnel_row(funnel_row())
    assert shaped["spendCoverageStatus"] == "Complete"
    assert shaped["costPerLead"] == 200
    assert shaped["costPerWin"] == 2000
    assert shaped["leadToWinRate"] == 0.1
    assert shaped["benchmarkCoverage"] == 1


def test_funnel_shaper_forces_lead_first_for_known_incomplete_spend():
    shaped = shape_marketing_funnel_row(
        funnel_row(
            effectiveSpend=0,
            recordedSpend=0,
            spendCompleteLeadShare=0,
            knownIncompleteRows=1,
        )
    )
    assert shaped["spendCoverageStatus"] == "Known incomplete"
    assert shaped["costPerLead"] is None
    assert shaped["costPerWin"] is None


def test_funnel_handler_validates_range_and_binds_parameters(monkeypatch):
    fake = FakeClient([funnel_row()])
    monkeypatch.setattr(DashboardHandler, "_client", fake)
    handler = DashboardHandler.__new__(DashboardHandler)
    status, payload = handler._marketing_funnel({
        "months": ["12"],
        "campaign": ["Summer Search"],
        "state": ["VA"],
    })
    assert status == HTTPStatus.OK
    assert payload[0]["campaign"] == "Summer Search"
    assert [parameter.name for parameter in fake.last_job_config.query_parameters] == [
        "months",
        "campaign",
        "state",
    ]
    status, payload = handler._marketing_funnel({"months": ["0"]})
    assert status == HTTPStatus.BAD_REQUEST
    assert "between 1 and 36" in payload["detail"]


def test_marketing_query_errors_are_returned_as_bad_gateway(monkeypatch):
    monkeypatch.setattr(DashboardHandler, "_client", ExplodingClient())
    handler = DashboardHandler.__new__(DashboardHandler)
    status, payload = handler._marketing_geo({})
    assert status == HTTPStatus.BAD_GATEWAY
    assert "warehouse offline" in payload["detail"]


def test_reconciliation_contract_and_deltas(monkeypatch):
    rows = []
    for rollup, official in OFFICIAL_REPORT_BENCHMARKS.items():
        rows.append({
            "campaignRollup": rollup,
            **official,
            "spendCompleteLeadShare": 1,
            "loadedAt": datetime(2026, 7, 28, tzinfo=timezone.utc),
        })
    fake = FakeClient(rows)
    monkeypatch.setattr(DashboardHandler, "_client", fake)
    handler = DashboardHandler.__new__(DashboardHandler)
    status, payload = handler._marketing_reconciliation()
    assert status == HTTPStatus.OK
    assert len(payload["comparisons"]) == 4
    assert all(item["leadParityStatus"] == "Aligned" for item in payload["comparisons"])
    assert all(item["deltas"]["leads"] == 0 for item in payload["comparisons"])
    assert "fixed lead cohort" in payload["definitions"]["funnelMetrics"]
    assert "2026-07-31" in build_marketing_reconciliation_query()
