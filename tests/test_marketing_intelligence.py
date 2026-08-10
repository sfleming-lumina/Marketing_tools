import sys
from datetime import date, datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard_server import (
    DashboardHandler,
    OFFICIAL_REPORT_BENCHMARKS,
    build_marketing_capacity_query,
    build_marketing_funnel_query,
    build_marketing_filter_options_query,
    build_marketing_geo_query,
    build_marketing_projection_query,
    build_marketing_reconciliation_query,
    build_marketing_trends_query,
    marketing_trend_period_bounds,
    normalize_workbook_detail,
    normalize_workbook_forecast,
    normalize_workbook_summary,
    official_workbook_credentials,
    shape_marketing_funnel_row,
    shape_marketing_geo_row,
    shape_marketing_capacity_row,
    summarize_marketing_activity,
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
        "cohortAgeDays": 40,
        "cohortMaturityBucket": "Maturing: 30-59 days",
        "leads": 100,
        "sets": 40,
        "runs": 30,
        "wins": 10,
        "losses": 20,
        "openNoSet30Plus": 5,
        "setNoRun30Plus": 4,
        "runNoWin60Plus": 3,
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
        "source": "EnergySage",
        "rollup": "3rd Party Vendors LSR",
        "state": "VA",
        "county": "Fairfax",
        "ahj": "Fairfax County",
        "region": "Maryland",
    }
    for query in (build_marketing_funnel_query(**values), build_marketing_geo_query(**values)):
        assert "rpt_marketing_funnel_analysis_runtime" in query
        for name in ("campaign", "source", "rollup", "state", "county", "ahj", "region"):
            assert f"@{name}" in query
        assert "INTERVAL @months MONTH" in query


def test_physical_state_filter_uses_governed_portfolio_state_fallback():
    for query in (build_marketing_funnel_query(state="VA"), build_marketing_geo_query(state="VA")):
        assert "COALESCE(NULLIF(TRIM(normalized_operating_state), ''), NULLIF(TRIM(resolved_state), ''), NULLIF(TRIM(reporting_market_state), ''), 'Unresolved') = @state" in query


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
    assert "rpt_marketing_active_campaign_catalog_runtime" in query
    assert "WHERE is_active" in query
    assert "resolved_county" in query
    assert "reporting_market_county" in query
    assert "operating_region_group IN ('Maryland', 'Pennsylvania')" in query
    assert "INTERVAL @months MONTH" in query


def test_active_campaign_catalog_uses_governed_status_not_current_leads():
    sql_path = Path(__file__).resolve().parents[1] / "lakehouse" / "20260728_marketing_funnel_analysis.sql"
    sql = sql_path.read_text(encoding="utf-8")
    catalog_sql = sql.split(
        "`lumina-lakehouse.marketing_tool_ops.rpt_marketing_active_campaign_catalog_runtime`",
        1,
    )[1].split(
        "`lumina-lakehouse.marketing_tool_ops.rpt_marketing_active_lead_inventory_runtime`",
        1,
    )[0]
    assert "FROM `lumina-lakehouse.marketing_tool_ops.rpt_marketing_funnel_analysis_runtime`" in catalog_sql
    assert "UPPER(campaign_status) IN ('PLANNED', 'IN PROGRESS')" in catalog_sql
    assert "jonathan\\s+bissell" in catalog_sql
    assert "fact_lead_funnel_attributed_clean" not in catalog_sql
    assert "salesforce.campaign" not in catalog_sql


def test_capacity_query_uses_current_active_salesforce_inventory():
    query = build_marketing_capacity_query(
        source="EnergySage",
        region="Operating footprint",
    )
    assert "rpt_marketing_active_lead_inventory_runtime" in query
    assert "is_currently_open" in query
    assert "has_active_campaign" in query
    assert "campaign_source = @source" in query
    assert "operating_region_group IN ('Maryland', 'Pennsylvania')" in query
    assert "inside_rep_bucket" in query
    assert "outside_rep_bucket" in query


def test_capacity_shaper_preserves_reconciliation_and_rep_loads():
    shaped = shape_marketing_capacity_row({
        "governedOpen": 3471,
        "activeCampaignOpen": 3104,
        "age0To7": 238,
        "age8To30": 561,
        "age31To60": 392,
        "age61Plus": 3574,
        "sourceOptions": ["EnergySage", "SolarReviews"],
        "insideLoads": [
            {"rep": "Needs reassignment", "activeLeads": 2839},
            {"rep": "Angelo Nauls", "activeLeads": 206},
        ],
        "outsideLoads": [{"rep": "Kelly Stelmack", "activeLeads": 1235}],
        "loadedAt": datetime(2026, 7, 30, tzinfo=timezone.utc),
    })
    assert shaped["governedOpen"] == 3471
    assert shaped["activeCampaignOpen"] == 3104
    assert shaped["salesforceValidation"]["openLeads"] == 6472
    assert shaped["ageBands"]["61Plus"] == 3574
    assert shaped["insideLoads"][0]["rep"] == "Needs reassignment"
    assert "Jonathan Bissell" not in str(shaped)


def test_active_inventory_sql_uses_salesforce_open_contract_and_hides_excluded_owner():
    sql_path = Path(__file__).resolve().parents[1] / "lakehouse" / "20260728_marketing_funnel_analysis.sql"
    sql = sql_path.read_text(encoding="utf-8")
    inventory_sql = sql.split(
        "`lumina-lakehouse.marketing_tool_ops.rpt_marketing_active_lead_inventory_runtime`",
        1,
    )[1]
    assert "COALESCE(l.lead_is_open, FALSE)" in inventory_sql
    assert "NOT COALESCE(l.lead_is_converted, FALSE)" in inventory_sql
    assert "COALESCE(l.lead_active_campaign_flag, FALSE)" in inventory_sql
    assert "THEN 'Needs reassignment'" in inventory_sql
    assert "Inside assignment unavailable" in inventory_sql
    assert "marketing_tool_ops.rpt_marketing_funnel_analysis_runtime" in inventory_sql
    assert "marketing_tool_ops.fact_lead_funnel_attributed_clean" in inventory_sql
    assert "salesforce.lead" not in inventory_sql
    assert "salesforce.campaign" not in inventory_sql


def test_marketing_queries_exclude_jonathan_bissell_from_data_and_filters():
    for query in (
        build_marketing_funnel_query(),
        build_marketing_geo_query(),
        build_marketing_filter_options_query(),
        build_marketing_projection_query(),
    ):
        lowered = query.lower()
        assert "jonathan\\s+bissell" in lowered
        assert "campaign_name" in lowered
        assert "campaign_reporting_rollup_name" in lowered


def test_last_30d_uses_five_weekly_cohort_starts_without_month_parameter():
    for query in (
        build_marketing_funnel_query(window="30d"),
        build_marketing_geo_query(window="30d"),
        build_marketing_filter_options_query(window="30d"),
    ):
        assert "cohort_period_grain = 'WEEK'" in query
        assert "INTERVAL 28 DAY" in query
        assert "@months" not in query


def test_geo_query_returns_normalized_region_dimensions():
    query = build_marketing_geo_query(region="Pennsylvania")
    assert "operating_region_group AS operatingRegion" in query
    assert "normalized_ops_region AS normalizedOpsRegion" in query
    assert "normalized_operating_state" in query
    assert "AS normalizedState" in query
    assert "resolved_county" in query
    assert "AS ahj" in query
    assert "'County / operating market' AS geographyType" in query


def test_geo_query_recombines_split_jurisdiction_labels_at_county_grain():
    query = build_marketing_geo_query(campaign="SolarReviews", ahj="Baltimore (MD)")
    # The defective source can hold lead-only "CO - Baltimore, MD" and
    # outcome-bearing "Baltimore County (MD)" rows for the same county.
    # Neither source jurisdiction label may remain in the GROUP BY grain.
    group_by = query.split("GROUP BY", 1)[1].split("HAVING", 1)[0]
    assert "final_reporting_jurisdiction_label" not in group_by
    assert "resolved_county" in query
    assert "= @ahj" in query
    assert "resolvedAhjCount" in query
    assert "benchmarkLeadShare" in query


def test_geo_shaper_exposes_canonical_county_and_underlying_ahj_context():
    row = {
        "campaignId": "701-test",
        "campaign": "Summer Search",
        "campaignRollup": "3rd Party Vendors LSR",
        "ahj": "Fairfax County (VA)",
        "geography": "Fairfax County (VA)",
        "geographyType": "County / operating market",
        "county": "Fairfax County (VA)",
        "state": "VA",
        "market": "Fairfax County (VA)",
        "resolvedAhjCount": 2,
        "resolvedAhjExamples": ["Fairfax County (VA)", "Town of Vienna - Fairfax County (VA)"],
        "leads": 20,
        "sets": 8,
        "runs": 6,
        "wins": 3,
        "revenue": 120000,
        "effectiveSpend": 9000,
        "activePipeline": 4,
        "expectedRemainingWins": 1,
        "benchmarkLeadToWinRate": 0.12,
        "benchmarkLeadShare": 0.75,
        "benchmarkRows": 1,
        "cohortRows": 1,
        "spendCompleteLeadShare": 1,
        "loadedAt": datetime(2026, 7, 28, tzinfo=timezone.utc),
    }
    shaped = shape_marketing_geo_row(row)
    assert shaped["ahj"] == "Fairfax County (VA)"
    assert shaped["resolvedAhjCount"] == 2
    assert shaped["resolvedAhjExamples"][1].startswith("Town of Vienna")
    assert shaped["benchmarkCoverage"] == 0.75
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
    assert shaped["cohortAgeDays"] == 40
    assert shaped["cohortMaturityBucket"] == "Maturing: 30-59 days"
    assert shaped["openNoSet30Plus"] == 5
    assert shaped["setNoRun30Plus"] == 4
    assert shaped["runNoWin60Plus"] == 3


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


def test_last_30d_handler_uses_weekly_window_and_binds_no_months(monkeypatch):
    fake = FakeClient([funnel_row()])
    monkeypatch.setattr(DashboardHandler, "_client", fake)
    handler = DashboardHandler.__new__(DashboardHandler)
    status, payload = handler._marketing_funnel({"window": ["30d"]})
    assert status == HTTPStatus.OK
    assert payload[0]["sets"] == 40
    assert "cohort_period_grain = 'WEEK'" in fake.last_query
    assert fake.last_job_config.query_parameters == []


def test_marketing_handler_rejects_unsupported_temporal_window(monkeypatch):
    fake = FakeClient([])
    monkeypatch.setattr(DashboardHandler, "_client", fake)
    handler = DashboardHandler.__new__(DashboardHandler)
    status, payload = handler._marketing_funnel({"window": ["90d"]})
    assert status == HTTPStatus.BAD_REQUEST
    assert "supported temporal filter" in payload["detail"]
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


def test_capacity_handler_binds_source_and_returns_current_inventory(monkeypatch):
    fake = FakeClient([{
        "governedOpen": 3000,
        "activeCampaignOpen": 2500,
        "age0To7": 100,
        "age8To30": 400,
        "age31To60": 300,
        "age61Plus": 3270,
        "sourceOptions": ["EnergySage", "SolarReviews"],
        "insideLoads": [{"rep": "Needs reassignment", "activeLeads": 2500}],
        "outsideLoads": [{"rep": "Kelly Stelmack", "activeLeads": 1000}],
        "loadedAt": datetime(2026, 7, 30, tzinfo=timezone.utc),
    }])
    monkeypatch.setattr(DashboardHandler, "_client", fake)
    handler = DashboardHandler.__new__(DashboardHandler)
    status, payload = handler._marketing_capacity({
        "source": ["EnergySage"],
        "region": ["Operating footprint"],
    })
    assert status == HTTPStatus.OK
    assert payload["activeCampaignOpen"] == 2500
    assert payload["salesforceValidation"]["activeCampaignOpenLeads"] == 4765
    assert [parameter.name for parameter in fake.last_job_config.query_parameters] == ["source"]


def test_dashboard_shell_disables_browser_caching():
    handler = object.__new__(DashboardHandler)
    handler.path = "/marketing_decision_tool.html"
    headers = []
    handler.send_header = lambda name, value: headers.append((name, value))
    with patch.object(SimpleHTTPRequestHandler, "end_headers"):
        handler.end_headers()
    assert ("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0") in headers
    assert ("Pragma", "no-cache") in headers


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


def test_official_workbook_credentials_use_scoped_short_lived_impersonation(monkeypatch):
    source_credentials = object()
    scoped_credentials = object()
    monkeypatch.setattr(
        "dashboard_server.OFFICIAL_WORKBOOK_ACCESS_SERVICE_ACCOUNT",
        "marketing-tools-runtime@lumina-lakehouse.iam.gserviceaccount.com",
    )
    monkeypatch.setattr("dashboard_server.google.auth.default", lambda: (source_credentials, "lumina-lakehouse"))

    with patch("dashboard_server.impersonated_credentials.Credentials", return_value=scoped_credentials) as factory:
        credentials = official_workbook_credentials()

    assert credentials is scoped_credentials
    factory.assert_called_once_with(
        source_credentials=source_credentials,
        target_principal="marketing-tools-runtime@lumina-lakehouse.iam.gserviceaccount.com",
        target_scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
        lifetime=3600,
    )


def test_official_workbook_ranges_normalize_into_dashboard_records():
    summary = normalize_workbook_summary([
        ["Category", "State", "Metric", "Jan", "Feb", "Mar"],
        [None, None, None, "1", "2", "3"],
        ["Internal Marketing", "MD", "Net Revenue", 100, 250, 300, 0, 0, 0, 0, 0, 0, 0, 0, 0, 650],
    ])
    detail = normalize_workbook_detail([
        ["Category", "Resource", "State", "Metric", "Jan", "Feb"],
        [None, None, None, None, "1", "2"],
        ["Internal Marketing", "Google Ads LSR", "MD", "Leads", 10, 15, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 25],
    ])
    forecast = normalize_workbook_forecast([
        [None, None, None, "Jan", "Feb"],
        [None, None, "Total"],
        [None, "Revenue", "3rd Party Vendors", 1000, 1100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2100],
        [None, None, "Internal Marketing", 2000, 2200, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 4200],
    ])
    assert summary == [{"category": "Internal Marketing", "state": "MD", "metric": "Net Revenue", "months": [100, 250, 300, 0, 0, 0, 0, 0, 0, 0, 0, 0], "total": 650}]
    assert detail[0]["resource"] == "Google Ads LSR" and detail[0]["months"][:2] == [10, 15]
    assert [record["metric"] for record in forecast] == ["Revenue", "Revenue"]
    assert forecast[1]["category"] == "Internal Marketing" and forecast[1]["total"] == 4200


def test_calendar_trend_periods_use_honest_equal_or_elapsed_comparisons():
    today = date(2026, 8, 6)
    rolling = marketing_trend_period_bounds("7d", today)
    assert rolling["current_start"] == date(2026, 7, 31)
    assert rolling["current_end"] == today
    assert rolling["comparison_start"] == date(2026, 7, 24)
    assert rolling["comparison_end"] == date(2026, 7, 30)

    month_to_date = marketing_trend_period_bounds("mtd", today)
    assert month_to_date["current_start"] == date(2026, 8, 1)
    assert month_to_date["comparison_start"] == date(2026, 7, 1)
    assert month_to_date["comparison_end"] == date(2026, 7, 6)

    last_quarter = marketing_trend_period_bounds("last_quarter", today)
    assert last_quarter["current_start"] == date(2026, 4, 1)
    assert last_quarter["current_end"] == date(2026, 6, 30)
    assert last_quarter["comparison_start"] == date(2026, 1, 1)
    assert last_quarter["comparison_end"] == date(2026, 3, 31)


def test_calendar_trend_query_and_summary_remain_event_period_metrics():
    sql = build_marketing_trends_query(
        campaign="Campaign A", rollup="Internal Marketing", region="Operating footprint"
    )
    assert "rpt_marketing_activity_daily_runtime" in sql
    assert "campaign_name = @campaign" in sql
    assert "campaign_reporting_rollup_name = @rollup" in sql
    assert "operating_region_group IN ('Maryland', 'Pennsylvania')" in sql
    summary = summarize_marketing_activity(
        [
            {"leads": 10, "sets": 4, "runs": 3, "wins": 2, "winValue": 1000, "spend": 200},
            {"leads": 5, "sets": 2, "runs": 1, "wins": 1, "winValue": 500, "spend": 100},
        ]
    )
    assert summary["leads"] == 15
    assert summary["setsPerLead"] == 0.4
    assert summary["costPerWin"] == 100
