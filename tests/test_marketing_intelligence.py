import sys
from datetime import date, datetime, timezone
from http import HTTPStatus
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard_server import (
    DashboardHandler,
    OFFICIAL_REPORT_BENCHMARKS,
    build_marketing_funnel_query,
    build_marketing_filter_options_query,
    build_marketing_geo_query,
    build_marketing_projection_query,
    build_marketing_reconciliation_query,
    shape_marketing_funnel_row,
    shape_marketing_geo_row,
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
        "region": "Maryland",
    }
    for query in (build_marketing_funnel_query(**values), build_marketing_geo_query(**values)):
        assert "rpt_marketing_funnel_analysis_runtime" in query
        for name in ("campaign", "rollup", "state", "county", "ahj", "region"):
            assert f"@{name}" in query
        assert "INTERVAL @months MONTH" in query


def test_operating_footprint_filter_is_explicit_and_requires_no_region_parameter():
    for query in (
        build_marketing_funnel_query(region="Operating footprint"),
        build_marketing_geo_query(region="Operating footprint"),
    ):
        assert "operating_region_group IN ('Maryland', 'Pennsylvania')" in query
        assert "@region" not in query


def test_filter_options_query_returns_complete_campaign_and_ahj_catalog():
    query = build_marketing_filter_options_query(months=7, region="Operating footprint")
    assert "ARRAY_AGG(DISTINCT campaign_name" in query
    assert "final_reporting_jurisdiction_label" in query
    assert "operating_region_group IN ('Maryland', 'Pennsylvania')" in query
    assert "INTERVAL @months MONTH" in query


def test_geo_query_returns_normalized_region_dimensions():
    query = build_marketing_geo_query(region="Pennsylvania")
    assert "operating_region_group AS operatingRegion" in query
    assert "normalized_ops_region AS normalizedOpsRegion" in query
    assert "normalized_operating_state AS normalizedState" in query
    assert "final_reporting_jurisdiction_label AS ahj" in query


def test_geo_shaper_exposes_exact_ahj_for_filter_catalog():
    row = {
        "campaignId": "701-test",
        "campaign": "Summer Search",
        "campaignRollup": "3rd Party Vendors LSR",
        "ahj": "Fairfax County",
        "geography": "Fairfax County",
        "geographyType": "COUNTY",
        "county": "Fairfax",
        "state": "VA",
        "market": "DMV",
        "leads": 20,
        "sets": 8,
        "runs": 6,
        "wins": 3,
        "revenue": 120000,
        "effectiveSpend": 9000,
        "activePipeline": 4,
        "expectedRemainingWins": 1,
        "benchmarkLeadToWinRate": 0.12,
        "benchmarkRows": 1,
        "cohortRows": 1,
        "spendCompleteLeadShare": 1,
        "loadedAt": datetime(2026, 7, 28, tzinfo=timezone.utc),
    }
    shaped = shape_marketing_geo_row(row)
    assert shaped["ahj"] == "Fairfax County"
    assert shaped["costPerWin"] == 3000


def test_lakehouse_regions_follow_operational_md_pa_contract():
    sql_path = Path(__file__).resolve().parents[1] / "lakehouse" / "20260728_marketing_funnel_analysis.sql"
    sql = sql_path.read_text(encoding="utf-8")
    assert "resolved_ops_region" in sql
    assert "END AS normalized_ops_region" in sql
    assert "THEN 'Maryland'" in sql
    assert "'PA/DE'" in sql
    assert "THEN 'DMV'" not in sql


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
        "region": ["Maryland"],
    })
    assert status == HTTPStatus.OK
    assert payload[0]["campaign"] == "Summer Search"
    assert [parameter.name for parameter in fake.last_job_config.query_parameters] == [
        "months",
        "campaign",
        "state",
        "region",
    ]
    status, payload = handler._marketing_funnel({"months": ["0"]})
    assert status == HTTPStatus.BAD_REQUEST
    assert "between 1 and 36" in payload["detail"]


def test_marketing_handler_rejects_unsupported_region(monkeypatch):
    fake = FakeClient([])
    monkeypatch.setattr(DashboardHandler, "_client", fake)
    handler = DashboardHandler.__new__(DashboardHandler)
    status, payload = handler._marketing_funnel({"region": ["New York"]})
    assert status == HTTPStatus.BAD_REQUEST
    assert "supported operating-region filter" in payload["detail"]
    assert fake.last_query is None


def test_operating_footprint_handler_binds_only_months(monkeypatch):
    fake = FakeClient([])
    monkeypatch.setattr(DashboardHandler, "_client", fake)
    handler = DashboardHandler.__new__(DashboardHandler)
    status, _ = handler._marketing_geo({"region": ["Operating footprint"]})
    assert status == HTTPStatus.OK
    assert [parameter.name for parameter in fake.last_job_config.query_parameters] == ["months"]
    assert "operating_region_group IN ('Maryland', 'Pennsylvania')" in fake.last_query


def test_filter_options_handler_returns_arrays_and_region_binding(monkeypatch):
    fake = FakeClient([{
        "campaigns": ["SolarReviews", "EnergySage"],
        "rollups": ["3rd Party Vendors LSR"],
        "ahjs": ["Anne Arundel County (MD)", "Lancaster Township (PA)"],
    }])
    monkeypatch.setattr(DashboardHandler, "_client", fake)
    handler = DashboardHandler.__new__(DashboardHandler)
    status, payload = handler._marketing_filter_options({"months": ["7"], "region": ["Maryland"]})
    assert status == HTTPStatus.OK
    assert payload["campaigns"] == ["SolarReviews", "EnergySage"]
    assert payload["ahjs"][0] == "Anne Arundel County (MD)"
    assert [parameter.name for parameter in fake.last_job_config.query_parameters] == ["months", "region"]


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
