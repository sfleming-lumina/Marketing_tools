import json
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib import error as urlerror
from urllib import request as urlrequest

from google.cloud import bigquery


ROOT = Path(__file__).parent / "outputs"
PROJECT_ID = os.environ.get("BQ_PROJECT_ID", "lumina-lakehouse")
DATASET = os.environ.get("BQ_DATASET", "marketing_tool_ops")
TABLE = os.environ.get("BQ_TABLE", "dashboard_notes")
TABLE_REF = f"{PROJECT_ID}.{DATASET}.{TABLE}"
DECISIONS_TABLE_REF = f"{PROJECT_ID}.{DATASET}.marketing_decisions"
AHJ_TABLE_REF = f"{PROJECT_ID}.analytics_rpt.rpt_marketing_campaign_ahj_performance"
FUNNEL_TABLE_REF = f"{PROJECT_ID}.marketing_tool_ops.rpt_marketing_funnel_analysis_runtime"
PROJECTION_TABLE_REF = f"{PROJECT_ID}.marketing_tool_ops.rpt_marketing_period_projection_runtime"
ACTIVE_LEAD_TABLE_REF = f"{PROJECT_ID}.marketing_tool_ops.rpt_marketing_active_lead_inventory_runtime"
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5").strip()
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"

SOURCE_OBJECTS = [
    "analytics_rpt.rpt_marketing_lead_cohort_performance",
    "analytics_rpt.rpt_marketing_cohort_expected_yield",
    "analytics_rpt.rpt_marketing_period_projection",
    "marketing_tool_ops.rpt_marketing_funnel_analysis_runtime",
    "marketing_tool_ops.rpt_marketing_period_projection_runtime",
    "marketing_tool_ops.rpt_marketing_active_lead_inventory_runtime",
    "analytics_rpt.rpt_marketing_campaign_ahj_performance",
    "analytics_rpt.rpt_campaign_ahj_performance",
    "analytics_rpt.rpt_pipeline_funnel",
    "analytics_rpt.rpt_sales_growth_summary",
    "analytics_rpt.rpt_project_product_mix_summary",
    "analytics_rpt.rpt_opportunity_product_mix_summary",
    "analytics_rpt.rpt_current_performance_bq_columns_v1",
    "analytics_rpt.rpt_residential_cost_project_detail",
    "analytics_rpt.rpt_sales_to_survey_capacity",
    "analytics_rpt.rpt_survey_performance_by_surveyor",
    "analytics_rpt.rpt_survey_return_reason_trend",
    "analytics_rpt.rpt_forecast_capacity_plan_v1",
    "analytics_rpt.rpt_forecast_leadership_simulation_v1",
    "analytics_rpt.rpt_forecast_priority_queue_v1",
    "analytics_rpt.rpt_forecast_model_decision_recommendation_v1",
]

OFFICIAL_REPORT_BENCHMARKS = {
    "3rd Party Vendors LSR": {
        "leads": 8759,
        "sets": 1117,
        "runs": 848,
        "wins": 198,
        "revenue": 8048213.92,
        "spend": 937555.0,
    },
    "Internal Marketing LSR": {
        "leads": 2792,
        "sets": 1230,
        "runs": 1047,
        "wins": 305,
        "revenue": 12282543.79,
        "spend": 417217.48,
    },
    "Pay Per Install LSR": {
        "leads": 492,
        "sets": 525,
        "runs": 388,
        "wins": 202,
        "revenue": 7434743.13,
        "spend": 132500.0,
    },
    "Co-op": {
        "leads": 87,
        "sets": 74,
        "runs": 73,
        "wins": 37,
        "revenue": 1350381.79,
        "spend": 80467.2,
    },
}


def build_ahj_performance_query(months=6, campaign=None, market=None):
    conditions = ["campaign_name IS NOT NULL", "reporting_market_label IS NOT NULL"]
    if campaign:
        conditions.append("campaign_name = @campaign")
    if market:
        conditions.append("reporting_market_label = @market")
    where_clause = " AND ".join(conditions)
    return f"""
        WITH bounds AS (
            SELECT MAX(period_start_date) AS latest_start
            FROM `{AHJ_TABLE_REF}`
            WHERE period_grain = 'MONTH'
        )
        SELECT
            reporting_market_label AS market,
            campaign_name AS campaign,
            SUM(lead_count) AS leads,
            SUM(win_count) AS wins,
            SUM(allocated_spend_amount) AS spend,
            SUM(win_revenue) AS revenue
        FROM `{AHJ_TABLE_REF}`, bounds
        WHERE period_grain = 'MONTH'
            AND period_start_date > DATE_SUB(bounds.latest_start, INTERVAL @months MONTH)
            AND {where_clause}
        GROUP BY market, campaign
        HAVING SUM(allocated_spend_amount) > 0 OR SUM(lead_count) > 0
        ORDER BY leads DESC, spend DESC
        LIMIT 500
    """


def shape_ahj_row(row):
    leads = row["leads"] or 0
    wins = row["wins"] or 0
    spend = row["spend"] or 0
    revenue = row["revenue"] or 0
    if leads == 0 and wins == 0:
        sample_size_bucket = "No Same-Period Sample"
    elif leads < 20 and wins < 3:
        sample_size_bucket = "Low Sample"
    else:
        sample_size_bucket = "Sufficient Sample"
    return {
        "market": row["market"],
        "campaign": row["campaign"],
        "leads": leads,
        "wins": wins,
        "spend": spend,
        "revenue": revenue,
        "cpw": (spend / wins) if wins else None,
        "revenuePerSpend": (revenue / spend) if spend else None,
        "leadToWinRate": (wins / leads) if leads else None,
        "sampleSizeBucket": sample_size_bucket,
    }


def build_campaign_performance_query(months=6, campaign=None):
    conditions = ["campaign_name IS NOT NULL"]
    if campaign:
        conditions.append("campaign_name = @campaign")
    where_clause = " AND ".join(conditions)
    return f"""
        WITH bounds AS (
            SELECT MAX(period_start_date) AS latest_start
            FROM `{AHJ_TABLE_REF}`
            WHERE period_grain = 'MONTH'
        )
        SELECT
            campaign_name AS campaign,
            campaign_reporting_rollup_name AS campaignRollup,
            period_start_date AS month,
            SUM(lead_count) AS leads,
            SUM(win_count) AS wins,
            SUM(allocated_spend_amount) AS spend,
            SUM(win_revenue) AS revenue
        FROM `{AHJ_TABLE_REF}`, bounds
        WHERE period_grain = 'MONTH'
            AND period_start_date > DATE_SUB(bounds.latest_start, INTERVAL @months MONTH)
            AND {where_clause}
        GROUP BY campaign, campaignRollup, month
        HAVING SUM(allocated_spend_amount) > 0 OR SUM(lead_count) > 0
        ORDER BY month, leads DESC, spend DESC
        LIMIT 2000
    """


def shape_campaign_row(row):
    leads = row["leads"] or 0
    wins = row["wins"] or 0
    spend = row["spend"] or 0
    revenue = row["revenue"] or 0
    if leads == 0 and wins == 0:
        sample_size_bucket = "No Same-Period Sample"
    elif leads < 20 and wins < 3:
        sample_size_bucket = "Low Sample"
    else:
        sample_size_bucket = "Sufficient Sample"
    return {
        "campaign": row["campaign"],
        "campaignRollup": row["campaignRollup"],
        "month": row["month"].isoformat(),
        "leads": leads,
        "wins": wins,
        "spend": spend,
        "revenue": revenue,
        "cpw": (spend / wins) if wins else None,
        "revenuePerSpend": (revenue / spend) if spend else None,
        "leadToWinRate": (wins / leads) if leads else None,
        "sampleSizeBucket": sample_size_bucket,
    }


OPERATING_REGION_FILTERS = {
    "Maryland",
    "Pennsylvania",
    "Outside operating footprint",
    "Unresolved",
    "Operating footprint",
}
MARKETING_WINDOWS = {"30d"}


def _marketing_portfolio_state_sql():
    return (
        "COALESCE("
        "NULLIF(TRIM(normalized_operating_state), ''), "
        "NULLIF(TRIM(resolved_state), ''), "
        "NULLIF(TRIM(reporting_market_state), ''), "
        "'Unresolved'"
        ")"
    )


def _marketing_portfolio_geography_sql():
    state_sql = _marketing_portfolio_state_sql()
    return (
        "COALESCE("
        "NULLIF(TRIM(resolved_county), ''), "
        "IF("
        "NULLIF(TRIM(reporting_market_county), '') IS NOT NULL, "
        f"CONCAT(TRIM(reporting_market_county), IF({state_sql} = 'Unresolved', '', CONCAT(' (', {state_sql}, ')'))), "
        "NULL"
        "), "
        "NULLIF(TRIM(reporting_market_label), ''), "
        "'Unresolved'"
        ")"
    )


def _marketing_identity_exclusions(include_subrollup=True):
    fields = ["campaign_name", "campaign_reporting_rollup_name"]
    if include_subrollup:
        fields.append("campaign_sub_rollup_name")
    return [
        f"NOT REGEXP_CONTAINS(LOWER(COALESCE({field}, '')), r'jonathan\\s+bissell')"
        for field in fields
    ]


def _marketing_filter_conditions(
    campaign=None,
    source=None,
    rollup=None,
    state=None,
    county=None,
    ahj=None,
    region=None,
):
    conditions = ["campaign_name IS NOT NULL", *_marketing_identity_exclusions()]
    portfolio_geography_sql = _marketing_portfolio_geography_sql()
    if campaign:
        conditions.append("campaign_name = @campaign")
    if source:
        conditions.append("campaign_name = @source")
    if rollup:
        conditions.append("campaign_reporting_rollup_name = @rollup")
    if state:
        conditions.append("resolved_state = @state")
    if county:
        conditions.append(f"{portfolio_geography_sql} = @county")
    if ahj:
        # The dashboard's portfolio geography selector intentionally uses a
        # stable county/operating-market grain. The source's jurisdiction label
        # splits lead attribution and downstream outcomes into separate rows.
        conditions.append(f"{portfolio_geography_sql} = @ahj")
    if region == "Operating footprint":
        conditions.append("operating_region_group IN ('Maryland', 'Pennsylvania')")
    elif region:
        conditions.append("operating_region_group = @region")
    return conditions


def _marketing_period_sql(window=None):
    if window == "30d":
        return (
            "WEEK",
            "cohort_period_start_date >= DATE_SUB(bounds.latest_start, INTERVAL 28 DAY)",
        )
    return (
        "MONTH",
        "cohort_period_start_date > DATE_SUB(bounds.latest_start, INTERVAL @months MONTH)",
    )


def build_marketing_funnel_query(
    months=7,
    window=None,
    campaign=None,
    source=None,
    rollup=None,
    state=None,
    county=None,
    ahj=None,
    region=None,
):
    conditions = _marketing_filter_conditions(campaign, source, rollup, state, county, ahj, region)
    where_clause = " AND ".join(conditions)
    period_grain, period_predicate = _marketing_period_sql(window)
    return f"""
        WITH bounds AS (
            SELECT MAX(cohort_period_start_date) AS latest_start
            FROM `{FUNNEL_TABLE_REF}`
            WHERE cohort_period_grain = '{period_grain}'
        )
        SELECT
            cohort_period_start_date AS month,
            campaign_sf_id AS campaignId,
            campaign_name AS campaign,
            campaign_reporting_rollup_name AS campaignRollup,
            campaign_sub_rollup_name AS campaignSubrollup,
            SUM(lead_count) AS leads,
            SUM(set_count) AS sets,
            SUM(run_count) AS runs,
            SUM(win_count) AS wins,
            SUM(lost_count) AS losses,
            SUM(open_no_set_30_plus_count) AS openNoSet30Plus,
            SUM(set_no_run_30_plus_count) AS setNoRun30Plus,
            SUM(run_no_win_60_plus_count) AS runNoWin60Plus,
            SUM(win_revenue) AS revenue,
            SUM(allocated_spend_amount) AS recordedSpend,
            SUM(effective_spend_amount) AS effectiveSpend,
            SUM(active_pipeline_candidate_count) AS activePipeline,
            SUM(active_pipeline_candidate_revenue) AS activePipelineRevenue,
            SUM(expected_remaining_win_count) AS expectedRemainingWins,
            SUM(expected_remaining_revenue) AS expectedRemainingRevenue,
            SAFE_DIVIDE(
                SUM(IF(has_reliable_benchmark, benchmark_lead_to_win_rate * lead_count, 0)),
                SUM(IF(has_reliable_benchmark, lead_count, 0))
            ) AS benchmarkLeadToWinRate,
            SAFE_DIVIDE(
                SUM(IF(spend_is_complete, lead_count, 0)),
                NULLIF(SUM(lead_count), 0)
            ) AS spendCompleteLeadShare,
            COUNTIF(spend_coverage_status = 'Recorded') AS recordedSpendRows,
            COUNTIF(spend_coverage_status = 'Derived payout') AS derivedSpendRows,
            COUNTIF(spend_coverage_status = 'Zero payout') AS zeroPayoutRows,
            COUNTIF(spend_coverage_status = 'Known incomplete') AS knownIncompleteRows,
            COUNTIF(spend_coverage_status = 'Lead-only') AS leadOnlyRows,
            COUNTIF(has_reliable_benchmark) AS benchmarkRows,
            COUNT(*) AS cohortRows,
            MAX(spend_coverage_note) AS spendCoverageNote,
            MAX(rpt_loaded_at) AS loadedAt
        FROM `{FUNNEL_TABLE_REF}`, bounds
        WHERE cohort_period_grain = '{period_grain}'
            AND {period_predicate}
            AND {where_clause}
        GROUP BY month, campaignId, campaign, campaignRollup, campaignSubrollup
        HAVING SUM(lead_count) > 0 OR SUM(effective_spend_amount) > 0
        ORDER BY month, leads DESC
        LIMIT 5000
    """


def build_marketing_geo_query(
    months=7,
    window=None,
    campaign=None,
    source=None,
    rollup=None,
    state=None,
    county=None,
    ahj=None,
    region=None,
):
    conditions = _marketing_filter_conditions(campaign, source, rollup, state, county, ahj, region)
    where_clause = " AND ".join(conditions)
    period_grain, period_predicate = _marketing_period_sql(window)
    portfolio_geography_sql = _marketing_portfolio_geography_sql()
    portfolio_state_sql = _marketing_portfolio_state_sql()
    return f"""
        WITH bounds AS (
            SELECT MAX(cohort_period_start_date) AS latest_start
            FROM `{FUNNEL_TABLE_REF}`
            WHERE cohort_period_grain = '{period_grain}'
        )
        SELECT
            campaign_sf_id AS campaignId,
            campaign_name AS campaign,
            campaign_reporting_rollup_name AS campaignRollup,
            operating_region_group AS operatingRegion,
            normalized_ops_region AS normalizedOpsRegion,
            {portfolio_state_sql} AS normalizedState,
            {portfolio_geography_sql} AS ahj,
            {portfolio_geography_sql} AS geography,
            'County / operating market' AS geographyType,
            {portfolio_geography_sql} AS county,
            {portfolio_state_sql} AS state,
            {portfolio_geography_sql} AS market,
            COUNT(DISTINCT IF(
                NULLIF(final_reporting_jurisdiction_label, 'Unknown') IS NOT NULL
                    AND NOT STARTS_WITH(final_reporting_jurisdiction_label, 'CO - '),
                final_reporting_jurisdiction_label,
                NULL
            )) AS resolvedAhjCount,
            ARRAY_AGG(DISTINCT IF(
                NULLIF(final_reporting_jurisdiction_label, 'Unknown') IS NOT NULL
                    AND NOT STARTS_WITH(final_reporting_jurisdiction_label, 'CO - '),
                final_reporting_jurisdiction_label,
                NULL
            ) IGNORE NULLS ORDER BY IF(
                NULLIF(final_reporting_jurisdiction_label, 'Unknown') IS NOT NULL
                    AND NOT STARTS_WITH(final_reporting_jurisdiction_label, 'CO - '),
                final_reporting_jurisdiction_label,
                NULL
            ) LIMIT 3) AS resolvedAhjExamples,
            SUM(lead_count) AS leads,
            SUM(set_count) AS sets,
            SUM(run_count) AS runs,
            SUM(win_count) AS wins,
            SUM(win_revenue) AS revenue,
            SUM(effective_spend_amount) AS effectiveSpend,
            SUM(active_pipeline_candidate_count) AS activePipeline,
            SUM(expected_remaining_win_count) AS expectedRemainingWins,
            SAFE_DIVIDE(
                SUM(IF(has_reliable_benchmark, benchmark_lead_to_win_rate * lead_count, 0)),
                SUM(IF(has_reliable_benchmark, lead_count, 0))
            ) AS benchmarkLeadToWinRate,
            SAFE_DIVIDE(
                SUM(IF(has_reliable_benchmark, lead_count, 0)),
                NULLIF(SUM(lead_count), 0)
            ) AS benchmarkLeadShare,
            SAFE_DIVIDE(
                SUM(IF(spend_is_complete, lead_count, 0)),
                NULLIF(SUM(lead_count), 0)
            ) AS spendCompleteLeadShare,
            COUNTIF(has_reliable_benchmark) AS benchmarkRows,
            COUNT(*) AS cohortRows,
            MAX(rpt_loaded_at) AS loadedAt
        FROM `{FUNNEL_TABLE_REF}`, bounds
        WHERE cohort_period_grain = '{period_grain}'
            AND {period_predicate}
            AND {where_clause}
        GROUP BY campaignId, campaign, campaignRollup, operatingRegion, normalizedOpsRegion, normalizedState, ahj, geography, geographyType, county, state, market
        HAVING SUM(lead_count) > 0
        ORDER BY leads DESC, wins DESC
        LIMIT 2000
    """


def build_marketing_filter_options_query(months=7, window=None, region=None):
    conditions = _marketing_filter_conditions(region=region)
    where_clause = " AND ".join(conditions)
    period_grain, period_predicate = _marketing_period_sql(window)
    portfolio_geography_sql = _marketing_portfolio_geography_sql()
    return f"""
        WITH bounds AS (
            SELECT MAX(cohort_period_start_date) AS latest_start
            FROM `{FUNNEL_TABLE_REF}`
            WHERE cohort_period_grain = '{period_grain}'
        )
        SELECT
            ARRAY_AGG(DISTINCT campaign_name IGNORE NULLS ORDER BY campaign_name) AS campaigns,
            ARRAY_AGG(DISTINCT campaign_reporting_rollup_name IGNORE NULLS ORDER BY campaign_reporting_rollup_name) AS rollups,
            ARRAY_AGG(
                DISTINCT NULLIF({portfolio_geography_sql}, 'Unresolved')
                IGNORE NULLS
                ORDER BY NULLIF({portfolio_geography_sql}, 'Unresolved')
            ) AS ahjs
        FROM `{FUNNEL_TABLE_REF}`, bounds
        WHERE cohort_period_grain = '{period_grain}'
            AND {period_predicate}
            AND {where_clause}
    """


def _active_lead_conditions(source=None, region=None, active_only=False):
    conditions = ["is_currently_open", "NOT is_test_record"]
    if active_only:
        conditions.append("has_active_campaign")
    if source:
        conditions.append("campaign_source = @source")
    if region == "Operating footprint":
        conditions.append("operating_region_group IN ('Maryland', 'Pennsylvania')")
    elif region:
        conditions.append("operating_region_group = @region")
    return conditions


def build_marketing_capacity_query(source=None, region=None):
    all_open_where = " AND ".join(_active_lead_conditions(source, region))
    active_where = " AND ".join(_active_lead_conditions(source, region, active_only=True))
    return f"""
        WITH all_open AS (
            SELECT *
            FROM `{ACTIVE_LEAD_TABLE_REF}`
            WHERE {all_open_where}
        ),
        active_open AS (
            SELECT *
            FROM `{ACTIVE_LEAD_TABLE_REF}`
            WHERE {active_where}
        ),
        summary AS (
            SELECT
                (SELECT COUNT(*) FROM all_open) AS salesforceOpen,
                COUNT(*) AS activeCampaignOpen,
                COUNTIF(lead_age_days BETWEEN 0 AND 7) AS age0To7,
                COUNTIF(lead_age_days BETWEEN 8 AND 30) AS age8To30,
                COUNTIF(lead_age_days BETWEEN 31 AND 60) AS age31To60,
                COUNTIF(lead_age_days >= 61) AS age61Plus,
                MAX(loaded_at) AS loadedAt
            FROM active_open
        ),
        sources AS (
            SELECT ARRAY_AGG(campaign_source ORDER BY campaign_source) AS sourceOptions
            FROM (
                SELECT DISTINCT campaign_source
                FROM `{ACTIVE_LEAD_TABLE_REF}`
                WHERE {" AND ".join(_active_lead_conditions(region=region, active_only=True))}
                  AND campaign_source IS NOT NULL
            )
        ),
        inside_load AS (
            SELECT ARRAY_AGG(STRUCT(rep, activeLeads) ORDER BY activeLeads DESC, rep) AS insideLoads
            FROM (
                SELECT inside_rep_bucket AS rep, COUNT(*) AS activeLeads
                FROM active_open
                GROUP BY rep
            )
        ),
        outside_load AS (
            SELECT ARRAY_AGG(STRUCT(rep, activeLeads) ORDER BY activeLeads DESC, rep) AS outsideLoads
            FROM (
                SELECT outside_rep_bucket AS rep, COUNT(*) AS activeLeads
                FROM active_open
                GROUP BY rep
            )
        )
        SELECT summary.*, sources.sourceOptions, inside_load.insideLoads, outside_load.outsideLoads
        FROM summary
        CROSS JOIN sources
        CROSS JOIN inside_load
        CROSS JOIN outside_load
    """


def shape_marketing_capacity_row(row):
    def loads(name):
        return [
            {"rep": item["rep"], "activeLeads": item["activeLeads"] or 0}
            for item in (row[name] or [])
        ]

    return {
        "salesforceOpen": row["salesforceOpen"] or 0,
        "activeCampaignOpen": row["activeCampaignOpen"] or 0,
        "ageBands": {
            "0To7": row["age0To7"] or 0,
            "8To30": row["age8To30"] or 0,
            "31To60": row["age31To60"] or 0,
            "61Plus": row["age61Plus"] or 0,
        },
        "sourceOptions": list(row["sourceOptions"] or []),
        "insideLoads": loads("insideLoads"),
        "outsideLoads": loads("outsideLoads"),
        "loadedAt": row["loadedAt"].isoformat() if row["loadedAt"] else None,
        "definitions": {
            "salesforceOpen": "IS_Open__c = TRUE and IsConverted = FALSE.",
            "activeCampaignOpen": "Salesforce open leads whose Active_Campaign__c is TRUE.",
            "capacity": "Advisory scenario only; no Salesforce assignments are changed.",
            "insideAssignment": "The governed lead-funnel contract does not yet expose IS_Lead_Owner__c; inside assignments are labeled unavailable instead of inferred.",
        },
    }


def build_marketing_projection_query(campaign=None, rollup=None):
    conditions = [
        "projection_period_grain = 'MONTH'",
        *_marketing_identity_exclusions(include_subrollup=False),
    ]
    if campaign:
        conditions.append("campaign_name = @campaign")
    if rollup:
        conditions.append("campaign_reporting_rollup_name = @rollup")
    where_clause = " AND ".join(conditions)
    return f"""
        WITH latest AS (
            SELECT MAX(projection_period_start_date) AS latest_start
            FROM `{PROJECTION_TABLE_REF}`
            WHERE projection_period_grain = 'MONTH'
        )
        SELECT
            projection_period_start_date AS month,
            campaign_sf_id AS campaignId,
            campaign_name AS campaign,
            campaign_reporting_rollup_name AS campaignRollup,
            SUM(IF(metric_name = 'Leads', actual_to_date, 0)) AS actualLeads,
            SUM(IF(metric_name = 'Leads', recommended_projection, 0)) AS projectedLeads,
            SUM(IF(metric_name = 'Sets', actual_to_date, 0)) AS actualSets,
            SUM(IF(metric_name = 'Sets', recommended_projection, 0)) AS projectedSets,
            SUM(IF(metric_name = 'Runs', actual_to_date, 0)) AS actualRuns,
            SUM(IF(metric_name = 'Runs', recommended_projection, 0)) AS projectedRuns,
            SUM(IF(metric_name = 'Wins', actual_to_date, 0)) AS actualWins,
            SUM(IF(metric_name = 'Wins', recommended_projection, 0)) AS projectedWins,
            SUM(IF(metric_name = 'Revenue', actual_to_date, 0)) AS actualRevenue,
            SUM(IF(metric_name = 'Revenue', recommended_projection, 0)) AS projectedRevenue,
            SUM(IF(metric_name = 'Spend - Week Assigned', actual_to_date, 0)) AS actualSpend,
            SUM(IF(metric_name = 'Spend - Week Assigned', recommended_projection, 0)) AS projectedSpend,
            MAX(projection_confidence) AS projectionConfidence,
            MAX(projection_as_of_date) AS projectionAsOfDate,
            MAX(rpt_loaded_at) AS loadedAt
        FROM `{PROJECTION_TABLE_REF}`, latest
        WHERE projection_period_start_date = latest.latest_start
            AND {where_clause}
        GROUP BY month, campaignId, campaign, campaignRollup
        HAVING projectedLeads > 0 OR projectedWins > 0 OR projectedRevenue > 0 OR projectedSpend > 0
        ORDER BY projectedRevenue DESC, projectedLeads DESC
        LIMIT 1000
    """


def build_marketing_reconciliation_query():
    rollups = ", ".join(f"'{name}'" for name in OFFICIAL_REPORT_BENCHMARKS)
    return f"""
        SELECT
            campaign_reporting_rollup_name AS campaignRollup,
            SUM(lead_count) AS leads,
            SUM(set_count) AS sets,
            SUM(run_count) AS runs,
            SUM(win_count) AS wins,
            SUM(win_revenue) AS revenue,
            SUM(effective_spend_amount) AS spend,
            SAFE_DIVIDE(
                SUM(IF(spend_is_complete, lead_count, 0)),
                NULLIF(SUM(lead_count), 0)
            ) AS spendCompleteLeadShare,
            MAX(rpt_loaded_at) AS loadedAt
        FROM `{FUNNEL_TABLE_REF}`
        WHERE cohort_period_grain = 'MONTH'
            AND cohort_period_start_date BETWEEN DATE '2026-01-01' AND DATE '2026-07-31'
            AND campaign_reporting_rollup_name IN ({rollups})
        GROUP BY campaignRollup
        ORDER BY campaignRollup
    """


def shape_marketing_funnel_row(row):
    leads = row["leads"] or 0
    sets = row["sets"] or 0
    runs = row["runs"] or 0
    wins = row["wins"] or 0
    revenue = row["revenue"] or 0
    effective_spend = row["effectiveSpend"] or 0
    completeness = row["spendCompleteLeadShare"] or 0
    if row["knownIncompleteRows"]:
        coverage_status = "Known incomplete"
    elif effective_spend <= 0:
        coverage_status = "Lead-first"
    elif completeness >= 0.85:
        coverage_status = "Complete"
    else:
        coverage_status = "Partial"
    return {
        "month": row["month"].isoformat(),
        "campaignId": row["campaignId"],
        "campaign": row["campaign"],
        "campaignRollup": row["campaignRollup"],
        "campaignSubrollup": row["campaignSubrollup"],
        "leads": leads,
        "sets": sets,
        "runs": runs,
        "wins": wins,
        "losses": row["losses"] or 0,
        "openNoSet30Plus": row["openNoSet30Plus"] or 0,
        "setNoRun30Plus": row["setNoRun30Plus"] or 0,
        "runNoWin60Plus": row["runNoWin60Plus"] or 0,
        "revenue": revenue,
        "recordedSpend": row["recordedSpend"] or 0,
        "effectiveSpend": effective_spend,
        "activePipeline": row["activePipeline"] or 0,
        "activePipelineRevenue": row["activePipelineRevenue"] or 0,
        "expectedRemainingWins": row["expectedRemainingWins"] or 0,
        "expectedRemainingRevenue": row["expectedRemainingRevenue"] or 0,
        "benchmarkLeadToWinRate": row["benchmarkLeadToWinRate"],
        "spendCompleteLeadShare": completeness,
        "spendCoverageStatus": coverage_status,
        "spendCoverageNote": row["spendCoverageNote"],
        "recordedSpendRows": row["recordedSpendRows"] or 0,
        "derivedSpendRows": row["derivedSpendRows"] or 0,
        "zeroPayoutRows": row["zeroPayoutRows"] or 0,
        "knownIncompleteRows": row["knownIncompleteRows"] or 0,
        "leadOnlyRows": row["leadOnlyRows"] or 0,
        "benchmarkCoverage": (row["benchmarkRows"] or 0) / max(1, row["cohortRows"] or 0),
        "setRate": sets / leads if leads else None,
        "runRateFromSets": runs / sets if sets else None,
        "winRateFromRuns": wins / runs if runs else None,
        "leadToWinRate": wins / leads if leads else None,
        "costPerLead": effective_spend / leads if leads and effective_spend else None,
        "costPerWin": effective_spend / wins if wins and effective_spend else None,
        "revenuePerSpend": revenue / effective_spend if effective_spend else None,
        "revenuePerWin": revenue / wins if wins else None,
        "loadedAt": row["loadedAt"].isoformat() if row["loadedAt"] else None,
    }


def shape_marketing_geo_row(row):
    leads = row["leads"] or 0
    sets = row["sets"] or 0
    runs = row["runs"] or 0
    wins = row["wins"] or 0
    revenue = row["revenue"] or 0
    spend = row["effectiveSpend"] or 0
    lead_to_win = wins / leads if leads else 0
    benchmark = row["benchmarkLeadToWinRate"] or 0
    sample_rank = 2 if leads >= 50 and wins >= 5 else 1 if leads >= 15 else 0
    opportunity_score = (
        min(45, lead_to_win * 300)
        + min(25, (revenue / spend if spend else 0) * 1.5)
        + min(20, sample_rank * 10)
        + min(10, (row["expectedRemainingWins"] or 0) * 1.5)
    )
    return {
        "campaignId": row["campaignId"],
        "campaign": row["campaign"],
        "campaignRollup": row["campaignRollup"],
        "ahj": row["ahj"],
        "geography": row["geography"],
        "geographyType": row["geographyType"],
        "county": row["county"],
        "state": row["state"],
        "market": row["market"],
        "resolvedAhjCount": row.get("resolvedAhjCount", 0) or 0,
        "resolvedAhjExamples": list(row.get("resolvedAhjExamples", []) or []),
        "leads": leads,
        "sets": sets,
        "runs": runs,
        "wins": wins,
        "revenue": revenue,
        "effectiveSpend": spend,
        "activePipeline": row["activePipeline"] or 0,
        "expectedRemainingWins": row["expectedRemainingWins"] or 0,
        "benchmarkLeadToWinRate": row["benchmarkLeadToWinRate"],
        "benchmarkCoverage": (
            row.get("benchmarkLeadShare")
            if row.get("benchmarkLeadShare") is not None
            else (row["benchmarkRows"] or 0) / max(1, row["cohortRows"] or 0)
        ),
        "spendCompleteLeadShare": row["spendCompleteLeadShare"] or 0,
        "setRate": sets / leads if leads else None,
        "runRateFromSets": runs / sets if sets else None,
        "winRateFromRuns": wins / runs if runs else None,
        "leadToWinRate": lead_to_win,
        "costPerWin": spend / wins if spend and wins else None,
        "revenuePerSpend": revenue / spend if spend else None,
        "sampleSizeBucket": "Sufficient Sample" if sample_rank == 2 else "Low Sample" if sample_rank == 1 else "No Same-Period Sample",
        "opportunityScore": round(opportunity_score, 1),
        "conversionDeltaVsBenchmark": lead_to_win - benchmark if benchmark else None,
        "loadedAt": row["loadedAt"].isoformat() if row["loadedAt"] else None,
    }


def shape_marketing_projection_row(row):
    return {
        "month": row["month"].isoformat(),
        "campaignId": row["campaignId"],
        "campaign": row["campaign"],
        "campaignRollup": row["campaignRollup"],
        "actualLeads": row["actualLeads"] or 0,
        "projectedLeads": row["projectedLeads"] or 0,
        "actualSets": row["actualSets"] or 0,
        "projectedSets": row["projectedSets"] or 0,
        "actualRuns": row["actualRuns"] or 0,
        "projectedRuns": row["projectedRuns"] or 0,
        "actualWins": row["actualWins"] or 0,
        "projectedWins": row["projectedWins"] or 0,
        "actualRevenue": row["actualRevenue"] or 0,
        "projectedRevenue": row["projectedRevenue"] or 0,
        "actualSpend": row["actualSpend"] or 0,
        "projectedSpend": row["projectedSpend"] or 0,
        "projectionConfidence": row["projectionConfidence"],
        "projectionAsOfDate": row["projectionAsOfDate"].isoformat() if row["projectionAsOfDate"] else None,
        "loadedAt": row["loadedAt"].isoformat() if row["loadedAt"] else None,
    }


def aggregate_marketing_funnel_rows(rows):
    leads = sum(float(row.get("leads") or 0) for row in rows)
    sets = sum(float(row.get("sets") or 0) for row in rows)
    runs = sum(float(row.get("runs") or 0) for row in rows)
    wins = sum(float(row.get("wins") or 0) for row in rows)
    revenue = sum(float(row.get("revenue") or 0) for row in rows)
    spend = sum(float(row.get("effectiveSpend") or 0) for row in rows)
    return {
        "leads": leads,
        "sets": sets,
        "runs": runs,
        "wins": wins,
        "revenue": revenue,
        "spend": spend,
        "setRate": sets / leads if leads else 0,
        "runRate": runs / sets if sets else 0,
        "winRate": wins / runs if runs else 0,
        "leadToWin": wins / leads if leads else 0,
        "cpl": spend / leads if spend and leads else None,
        "cpw": spend / wins if spend and wins else None,
    }


def evaluate_marketing_decision_progress(decision, current, now=None):
    now = now or datetime.now(timezone.utc)
    baseline = decision.get("baseline") or {}
    expected = decision.get("expected") or {}
    metric = decision.get("primary_metric") or "wins"
    inverse = metric in {"cpl", "cpw"}
    baseline_value = baseline.get(metric)
    target_value = expected.get(metric)
    current_value = current.get(metric)
    progress = None
    if all(value is not None for value in (baseline_value, target_value, current_value)):
        target_delta = float(target_value) - float(baseline_value)
        current_delta = float(current_value) - float(baseline_value)
        if inverse:
            target_delta *= -1
            current_delta *= -1
        if abs(target_delta) > 1e-9:
            progress = current_delta / target_delta
    created_at = datetime.fromisoformat(str(decision["created_at"]).replace("Z", "+00:00"))
    age_days = max(0, (now - created_at).days)
    if age_days < 7:
        status = "Maturing"
    elif progress is None:
        status = "Monitoring"
    elif progress >= 1:
        status = "Target reached"
    elif progress >= 0.25:
        status = "Improving"
    elif progress <= -0.2:
        status = "Needs attention"
    else:
        status = "Monitoring"
    budget_change = float((decision.get("scenario") or {}).get("budget") or 0) / 100
    baseline_spend = float(baseline.get("spend") or 0)
    current_spend = float(current.get("spend") or 0)
    spend_change = (current_spend / baseline_spend - 1) if baseline_spend else None
    matching_spend_change = (
        spend_change is not None
        and abs(budget_change) >= 0.05
        and abs(spend_change) >= 0.05
        and (budget_change > 0) == (spend_change > 0)
    )
    implementation_signal = (
        "Spend change detected"
        if matching_spend_change
        else "No spend change detected"
        if abs(budget_change) >= 0.05
        else "Outcome monitoring"
    )
    return {
        "decisionId": decision["decision_id"],
        "status": status,
        "implementationSignal": implementation_signal,
        "primaryMetric": metric,
        "progressToTarget": progress,
        "ageDays": age_days,
        "baseline": baseline,
        "current": current,
        "expected": expected,
        "evaluatedAt": now.isoformat(),
    }


class DashboardHandler(SimpleHTTPRequestHandler):
    _client = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    @property
    def client(self):
        if DashboardHandler._client is None:
            DashboardHandler._client = bigquery.Client(project=PROJECT_ID)
        return DashboardHandler._client

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length > 120_000:
            raise ValueError("Request body is too large.")
        return json.loads(self.rfile.read(length).decode("utf-8") or "{}")

    def _iap_user(self):
        raw = self.headers.get("X-Goog-Authenticated-User-Email", "")
        if raw.startswith("accounts.google.com:"):
            raw = raw.split(":", 1)[1]
        return raw or "iap-user@luminasolar.com"

    def _author_name(self):
        email = self._iap_user()
        return email.split("@", 1)[0].replace(".", " ").title() if "@" in email else email

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._send_json(HTTPStatus.OK, {"status": "ok"})
            return
        if parsed.path == "/api/notes":
            params = parse_qs(parsed.query)
            self._send_json(HTTPStatus.OK, self._list_notes(params.get("view", [None])[0]))
            return
        if parsed.path == "/api/marketing-decisions":
            status, result = self._list_marketing_decisions(parse_qs(parsed.query))
            self._send_json(status, result)
            return
        if parsed.path == "/api/marketing-decision-progress":
            status, result = self._marketing_decision_progress(parse_qs(parsed.query))
            self._send_json(status, result)
            return
        if parsed.path == "/api/freshness":
            self._send_json(HTTPStatus.OK, self._source_freshness())
            return
        if parsed.path == "/api/ahj-performance":
            params = parse_qs(parsed.query)
            status, result = self._ahj_performance(params)
            self._send_json(status, result)
            return
        if parsed.path == "/api/campaign-performance":
            params = parse_qs(parsed.query)
            status, result = self._campaign_performance(params)
            self._send_json(status, result)
            return
        if parsed.path == "/api/marketing-funnel":
            status, result = self._marketing_funnel(parse_qs(parsed.query))
            self._send_json(status, result)
            return
        if parsed.path == "/api/marketing-geo":
            status, result = self._marketing_geo(parse_qs(parsed.query))
            self._send_json(status, result)
            return
        if parsed.path == "/api/marketing-filter-options":
            status, result = self._marketing_filter_options(parse_qs(parsed.query))
            self._send_json(status, result)
            return
        if parsed.path == "/api/marketing-capacity":
            status, result = self._marketing_capacity(parse_qs(parsed.query))
            self._send_json(status, result)
            return
        if parsed.path == "/api/marketing-projection":
            status, result = self._marketing_projection(parse_qs(parsed.query))
            self._send_json(status, result)
            return
        if parsed.path == "/api/marketing-reconciliation":
            status, result = self._marketing_reconciliation()
            self._send_json(status, result)
            return
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/notes":
            payload = self._read_json_body()
            self._send_json(HTTPStatus.CREATED, self._create_note(payload))
            return
        if parsed.path == "/api/marketing-decisions":
            status, result = self._create_marketing_decision(self._read_json_body())
            self._send_json(status, result)
            return
        if parsed.path == "/api/freshness/refresh":
            result = self._source_freshness()
            result["refresh_mode"] = "metadata_check"
            self._send_json(HTTPStatus.OK, result)
            return
        if parsed.path == "/api/ask-claude":
            try:
                status, result = self._ask_claude(self._read_json_body())
            except ValueError as exc:
                status, result = HTTPStatus.BAD_REQUEST, {"detail": str(exc)}
            self._send_json(status, result)
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"detail": "Not found"})

    def _list_notes(self, view):
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
            FROM `{TABLE_REF}`
            {"WHERE view = @view" if view else ""}
            ORDER BY created_at DESC
        """
        job_config = bigquery.QueryJobConfig()
        if view:
            job_config.query_parameters = [bigquery.ScalarQueryParameter("view", "STRING", view)]
        rows = self.client.query(query, job_config=job_config).result()
        return [
            {
                "note_id": row["note_id"],
                "created_at": row["created_at"].isoformat(),
                "author_name": row["author_name"],
                "view": row["view"],
                "element_key": row["element_key"],
                "element_label": row["element_label"],
                "target_type": row["target_type"],
                "feedback_type": row["feedback_type"],
                "note_text": row["note_text"],
                "context": json.loads(row["context"]) if row["context"] else {},
            }
            for row in rows
        ]

    def _create_note(self, payload):
        created = {
            "note_id": str(uuid.uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "author_name": self._author_name(),
            "view": payload["view"],
            "element_key": payload["element_key"],
            "element_label": payload["element_label"],
            "target_type": payload.get("target_type", "tile"),
            "feedback_type": payload.get("feedback_type", "tweak"),
            "note_text": payload["note_text"],
            "context": payload.get("context", {}),
        }
        row = dict(created)
        row["context"] = json.dumps(row["context"])
        errors = self.client.insert_rows_json(TABLE_REF, [row])
        if errors:
            self._send_json(HTTPStatus.BAD_GATEWAY, {"detail": f"BigQuery insert failed: {errors}"})
            return
        return created

    @staticmethod
    def _shape_marketing_decision(row):
        def parsed_json(name, fallback):
            value = row[name]
            if not value:
                return fallback
            return json.loads(value) if isinstance(value, str) else value

        return {
            "decision_id": row["decision_id"],
            "created_at": row["created_at"].isoformat(),
            "created_by_email": row["created_by_email"],
            "created_by_name": row["created_by_name"],
            "decision_type": row["decision_type"],
            "question": row["question"],
            "action": row["action"],
            "status": row["status"],
            "source_view": row["source_view"],
            "campaign": row["campaign"] or "",
            "rollup": row["campaign_rollup"] or "",
            "ahj": row["ahj"] or "",
            "operating_region": row["operating_region"] or "",
            "months": row["months"] or 7,
            "window": row["temporal_window"] or "",
            "primary_metric": row["primary_metric"],
            "review_after": row["review_after"].isoformat(),
            "baseline": parsed_json("baseline", {}),
            "scenario": parsed_json("scenario", {}),
            "expected": parsed_json("expected", {}),
            "evidence": parsed_json("evidence", []),
            "data_confidence": row["data_confidence"] or "Developing",
        }

    def _list_marketing_decisions(self, params):
        try:
            limit = min(100, max(1, int((params.get("limit", ["30"])[0]) or "30")))
        except ValueError:
            return HTTPStatus.BAD_REQUEST, {"detail": "limit must be an integer."}
        query = f"""
            SELECT *
            FROM `{DECISIONS_TABLE_REF}`
            ORDER BY created_at DESC
            LIMIT @limit
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("limit", "INT64", limit)]
        )
        try:
            rows = self.client.query(query, job_config=job_config).result()
        except Exception as exc:
            return HTTPStatus.BAD_GATEWAY, {"detail": f"Decision ledger query failed: {exc}"}
        return HTTPStatus.OK, [self._shape_marketing_decision(row) for row in rows]

    def _create_marketing_decision(self, payload):
        question = str(payload.get("question") or "").strip()
        if not question:
            return HTTPStatus.BAD_REQUEST, {"detail": "question is required."}
        primary_metric = str(payload.get("primaryMetric") or "wins")
        if primary_metric not in {"leads", "wins", "revenue", "spend", "setRate", "runRate", "winRate", "leadToWin", "cpl", "cpw"}:
            return HTTPStatus.BAD_REQUEST, {"detail": "primaryMetric is not supported."}
        filters = payload.get("filters") or {}
        baseline = payload.get("baseline") or {}
        scenario = payload.get("scenario") or {}
        expected = payload.get("expected") or {}
        evidence = payload.get("evidence") or []
        if not isinstance(baseline, dict) or not isinstance(scenario, dict) or not isinstance(expected, dict):
            return HTTPStatus.BAD_REQUEST, {"detail": "baseline, scenario, and expected must be objects."}
        if not isinstance(evidence, list):
            return HTTPStatus.BAD_REQUEST, {"detail": "evidence must be an array."}
        now = datetime.now(timezone.utc)
        try:
            horizon_days = min(120, max(7, int(payload.get("horizonDays") or 30)))
            months = min(36, max(1, int(filters.get("months") or 7)))
        except (TypeError, ValueError):
            return HTTPStatus.BAD_REQUEST, {"detail": "horizonDays and filters.months must be integers."}
        created = {
            "decision_id": str(uuid.uuid4()),
            "created_at": now.isoformat(),
            "created_by_email": self._iap_user(),
            "created_by_name": self._author_name(),
            "decision_type": str(payload.get("decisionType") or "Test")[:50],
            "question": question[:500],
            "action": str(payload.get("action") or question)[:1000],
            "status": "Monitoring",
            "source_view": str(payload.get("sourceView") or "scenario")[:50],
            "campaign": str(filters.get("campaign") or "")[:500],
            "campaign_rollup": str(filters.get("rollup") or "")[:500],
            "ahj": str(filters.get("ahj") or "")[:500],
            "operating_region": str(filters.get("operatingRegion") or "")[:100],
            "months": months,
            "temporal_window": str(filters.get("window") or "")[:20],
            "primary_metric": primary_metric,
            "review_after": (now + timedelta(days=horizon_days)).date().isoformat(),
            "baseline": json.dumps(baseline),
            "scenario": json.dumps(scenario),
            "expected": json.dumps(expected),
            "evidence": json.dumps([str(item)[:1000] for item in evidence[:20]]),
            "data_confidence": str(payload.get("dataConfidence") or "Developing")[:50],
        }
        try:
            errors = self.client.insert_rows_json(DECISIONS_TABLE_REF, [created])
        except Exception as exc:
            return HTTPStatus.BAD_GATEWAY, {"detail": f"Decision ledger insert failed: {exc}"}
        if errors:
            return HTTPStatus.BAD_GATEWAY, {"detail": f"Decision ledger insert failed: {errors}"}
        response = dict(created)
        for name in ("baseline", "scenario", "expected", "evidence"):
            response[name] = json.loads(response[name])
        response["rollup"] = response.pop("campaign_rollup")
        response["window"] = response.pop("temporal_window")
        return HTTPStatus.CREATED, response

    def _get_marketing_decision(self, decision_id):
        query = f"""
            SELECT *
            FROM `{DECISIONS_TABLE_REF}`
            WHERE decision_id = @decision_id
            LIMIT 1
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("decision_id", "STRING", decision_id)]
        )
        row = next(iter(self.client.query(query, job_config=job_config).result()), None)
        return self._shape_marketing_decision(row) if row else None

    def _marketing_decision_progress(self, params):
        decision_id = str((params.get("id", [""])[0]) or "").strip()
        if not decision_id:
            return HTTPStatus.BAD_REQUEST, {"detail": "id is required."}
        try:
            decision = self._get_marketing_decision(decision_id)
        except Exception as exc:
            return HTTPStatus.BAD_GATEWAY, {"detail": f"Decision lookup failed: {exc}"}
        if not decision:
            return HTTPStatus.NOT_FOUND, {"detail": "Decision not found."}
        filter_params = {"months": [str(decision["months"])]}
        for key, value in (
            ("window", decision["window"]),
            ("campaign", decision["campaign"]),
            ("rollup", decision["rollup"]),
            ("ahj", decision["ahj"]),
            ("region", decision["operating_region"]),
        ):
            if value:
                filter_params[key] = [value]
        status, rows = self._marketing_funnel(filter_params)
        if status != HTTPStatus.OK:
            return status, rows
        current = aggregate_marketing_funnel_rows(rows)
        return HTTPStatus.OK, evaluate_marketing_decision_progress(decision, current)

    def _ahj_performance(self, params):
        # campaign/market filters are supported and tested here, but the current
        # frontend fetches this endpoint once per session with no query string
        # (two-tier fetch: fetch all rows, then filter/render client-side), so
        # they are never invoked in production today.
        try:
            months = int((params.get("months", ["6"])[0]) or "6")
        except ValueError:
            return HTTPStatus.BAD_REQUEST, {"detail": "months must be an integer."}
        campaign = (params.get("campaign", [None])[0] or None)
        market = (params.get("market", [None])[0] or None)
        query = build_ahj_performance_query(months=months, campaign=campaign, market=market)
        query_parameters = [bigquery.ScalarQueryParameter("months", "INT64", months)]
        if campaign:
            query_parameters.append(bigquery.ScalarQueryParameter("campaign", "STRING", campaign))
        if market:
            query_parameters.append(bigquery.ScalarQueryParameter("market", "STRING", market))
        job_config = bigquery.QueryJobConfig(query_parameters=query_parameters)
        try:
            rows = self.client.query(query, job_config=job_config).result()
        except Exception as exc:
            return HTTPStatus.BAD_GATEWAY, {"detail": f"AHJ performance query failed: {exc}"}
        return HTTPStatus.OK, [shape_ahj_row(row) for row in rows]

    def _campaign_performance(self, params):
        try:
            months = int((params.get("months", ["6"])[0]) or "6")
        except ValueError:
            return HTTPStatus.BAD_REQUEST, {"detail": "months must be an integer."}
        campaign = (params.get("campaign", [None])[0] or None)
        query = build_campaign_performance_query(months=months, campaign=campaign)
        query_parameters = [bigquery.ScalarQueryParameter("months", "INT64", months)]
        if campaign:
            query_parameters.append(bigquery.ScalarQueryParameter("campaign", "STRING", campaign))
        job_config = bigquery.QueryJobConfig(query_parameters=query_parameters)
        try:
            rows = self.client.query(query, job_config=job_config).result()
        except Exception as exc:
            return HTTPStatus.BAD_GATEWAY, {"detail": f"Campaign performance query failed: {exc}"}
        return HTTPStatus.OK, [shape_campaign_row(row) for row in rows]

    @staticmethod
    def _marketing_params(params, include_geo=True):
        window = params.get("window", [None])[0] or None
        if window and window not in MARKETING_WINDOWS:
            raise ValueError("window is not a supported temporal filter.")
        try:
            months = int((params.get("months", ["7"])[0]) or "7")
        except ValueError as exc:
            raise ValueError("months must be an integer.") from exc
        if months < 1 or months > 36:
            raise ValueError("months must be between 1 and 36.")
        values = {
            "months": months,
            "window": window,
            "campaign": params.get("campaign", [None])[0] or None,
            "source": params.get("source", [None])[0] or None,
            "rollup": params.get("rollup", [None])[0] or None,
        }
        if include_geo:
            values.update({
                "state": params.get("state", [None])[0] or None,
                "county": params.get("county", [None])[0] or None,
                "ahj": params.get("ahj", [None])[0] or None,
                "region": params.get("region", [None])[0] or None,
            })
        if values.get("region") and values["region"] not in OPERATING_REGION_FILTERS:
            raise ValueError("region is not a supported operating-region filter.")
        return values

    @staticmethod
    def _marketing_query_parameters(values, include_months=True):
        parameters = []
        if include_months and values.get("window") != "30d":
            parameters.append(bigquery.ScalarQueryParameter("months", "INT64", values["months"]))
        for name in ("campaign", "source", "rollup", "state", "county", "ahj", "region"):
            if name == "region" and values.get(name) == "Operating footprint":
                continue
            if values.get(name):
                parameters.append(bigquery.ScalarQueryParameter(name, "STRING", values[name]))
        return parameters

    def _run_marketing_query(self, query, values, shaper, label, include_months=True):
        job_config = bigquery.QueryJobConfig(
            query_parameters=self._marketing_query_parameters(values, include_months=include_months)
        )
        try:
            rows = self.client.query(query, job_config=job_config).result()
        except Exception as exc:
            return HTTPStatus.BAD_GATEWAY, {"detail": f"{label} query failed: {exc}"}
        return HTTPStatus.OK, [shaper(row) for row in rows]

    def _marketing_funnel(self, params):
        try:
            values = self._marketing_params(params)
        except ValueError as exc:
            return HTTPStatus.BAD_REQUEST, {"detail": str(exc)}
        query = build_marketing_funnel_query(**values)
        return self._run_marketing_query(query, values, shape_marketing_funnel_row, "Marketing funnel")

    def _marketing_geo(self, params):
        try:
            values = self._marketing_params(params)
        except ValueError as exc:
            return HTTPStatus.BAD_REQUEST, {"detail": str(exc)}
        query = build_marketing_geo_query(**values)
        return self._run_marketing_query(query, values, shape_marketing_geo_row, "Marketing geography")

    def _marketing_filter_options(self, params):
        try:
            values = self._marketing_params(params)
        except ValueError as exc:
            return HTTPStatus.BAD_REQUEST, {"detail": str(exc)}
        values = {"months": values["months"], "window": values["window"], "region": values["region"]}
        query = build_marketing_filter_options_query(**values)
        job_config = bigquery.QueryJobConfig(
            query_parameters=self._marketing_query_parameters(values)
        )
        try:
            row = next(iter(self.client.query(query, job_config=job_config).result()), None)
        except Exception as exc:
            return HTTPStatus.BAD_GATEWAY, {"detail": f"Marketing filter options query failed: {exc}"}
        return HTTPStatus.OK, {
            "campaigns": list(row["campaigns"] or []) if row else [],
            "rollups": list(row["rollups"] or []) if row else [],
            "ahjs": list(row["ahjs"] or []) if row else [],
        }

    def _marketing_capacity(self, params):
        try:
            values = self._marketing_params(params)
        except ValueError as exc:
            return HTTPStatus.BAD_REQUEST, {"detail": str(exc)}
        query_values = {
            "source": values["source"],
            "region": values["region"],
        }
        query = build_marketing_capacity_query(**query_values)
        job_config = bigquery.QueryJobConfig(
            query_parameters=self._marketing_query_parameters(
                query_values,
                include_months=False,
            )
        )
        try:
            row = next(iter(self.client.query(query, job_config=job_config).result()), None)
        except Exception as exc:
            return HTTPStatus.BAD_GATEWAY, {"detail": f"Marketing capacity query failed: {exc}"}
        if not row:
            return HTTPStatus.OK, {
                "salesforceOpen": 0,
                "activeCampaignOpen": 0,
                "ageBands": {"0To7": 0, "8To30": 0, "31To60": 0, "61Plus": 0},
                "sourceOptions": [],
                "insideLoads": [],
                "outsideLoads": [],
                "loadedAt": None,
            }
        return HTTPStatus.OK, shape_marketing_capacity_row(row)

    def _marketing_projection(self, params):
        try:
            values = self._marketing_params(params, include_geo=False)
        except ValueError as exc:
            return HTTPStatus.BAD_REQUEST, {"detail": str(exc)}
        query_values = {key: values[key] for key in ("campaign", "rollup")}
        query = build_marketing_projection_query(**query_values)
        return self._run_marketing_query(
            query,
            query_values,
            shape_marketing_projection_row,
            "Marketing projection",
            include_months=False,
        )

    def _marketing_reconciliation(self):
        try:
            rows = self.client.query(build_marketing_reconciliation_query()).result()
        except Exception as exc:
            return HTTPStatus.BAD_GATEWAY, {"detail": f"Marketing reconciliation query failed: {exc}"}
        lakehouse_rows = {row["campaignRollup"]: row for row in rows}
        comparisons = []
        for rollup, official in OFFICIAL_REPORT_BENCHMARKS.items():
            row = lakehouse_rows.get(rollup, {})
            lakehouse = {
                metric: (row.get(metric) or 0) if hasattr(row, "get") else (row[metric] or 0)
                for metric in ("leads", "sets", "runs", "wins", "revenue", "spend")
            }
            deltas = {
                metric: lakehouse[metric] - official[metric]
                for metric in official
            }
            comparisons.append({
                "campaignRollup": rollup,
                "officialReport": official,
                "lakehouseCohort": lakehouse,
                "deltas": deltas,
                "leadParityStatus": "Aligned" if abs(deltas["leads"]) <= max(10, official["leads"] * 0.03) else "Review",
                "spendParityStatus": "Aligned" if abs(deltas["spend"]) <= max(1000, official["spend"] * 0.03) else "Review",
                "spendCompleteLeadShare": (
                    (row.get("spendCompleteLeadShare") or 0)
                    if hasattr(row, "get")
                    else (row["spendCompleteLeadShare"] or 0)
                ),
            })
        return HTTPStatus.OK, {
            "period": "2026-01-01 through 2026-07-31",
            "workbook": "Marketing Report 2026_Official.xlsx",
            "comparisons": comparisons,
            "definitions": {
                "parityMetrics": "Leads and spend are direct source reconciliation checks.",
                "funnelMetrics": "Lakehouse sets, runs, wins, and revenue follow the fixed lead cohort; workbook figures are event-date actuals. Differences are expected and are shown for context.",
                "spend": "PPI referral payout is derived from the workbook rule. Co-op is marked known incomplete and remains lead-first.",
            },
        }

    def _source_freshness(self):
        checked_at = datetime.now(timezone.utc).isoformat()
        objects = []
        missing = []
        for object_id in SOURCE_OBJECTS:
            try:
                table = self.client.get_table(f"{PROJECT_ID}.{object_id}")
            except Exception:
                missing.append(object_id)
                continue
            objects.append({
                "object_id": object_id,
                "type": table.table_type,
                "modified_at": table.modified.isoformat() if table.modified else None,
            })
        latest = max((item["modified_at"] for item in objects if item["modified_at"]), default=None)
        return {
            "checked_at": checked_at,
            "latest_modified_at": latest,
            "objects_checked": len(SOURCE_OBJECTS),
            "objects_found": len(objects),
            "missing_objects": missing,
            "objects": objects,
        }

    def _extract_claude_answer(self, result):
        parts = []

        def collect(value):
            if isinstance(value, str):
                if value.strip():
                    parts.append(value.strip())
                return
            if isinstance(value, list):
                for item in value:
                    collect(item)
                return
            if not isinstance(value, dict):
                return
            text = value.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
            nested = value.get("content")
            if nested is not None:
                collect(nested)

        collect(result.get("content", []))
        legacy_completion = result.get("completion")
        if isinstance(legacy_completion, str) and legacy_completion.strip():
            parts.append(legacy_completion.strip())
        return "\n".join(parts).strip()

    def _parse_claude_insights(self, answer):
        try:
            return json.loads(answer)
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{[\s\S]*\}", answer)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    def _fallback_insights(self, question, context, reason):
        planner = context.get("campaign_planner", {}) if isinstance(context, dict) else {}
        top_rows = planner.get("top_recommendations", []) if isinstance(planner, dict) else []
        top_rows = [row for row in top_rows if isinstance(row, dict)]
        summary = context.get("summary_metrics", {}) if isinstance(context, dict) else {}
        filters = context.get("filters", {}) if isinstance(context, dict) else {}
        total_spend = sum(self._num(row.get("spend")) for row in top_rows) or self._num(summary.get("spend"))
        total_wins = sum(self._num(row.get("wins")) for row in top_rows)
        blended_cpw = total_spend / total_wins if total_wins else self._num(summary.get("cost_per_win"))
        risk_rows = [row for row in top_rows if row.get("decision") in {"Hold", "Avoid"}]
        highest_cpw = max(
            (row for row in (risk_rows or top_rows) if self._num(row.get("cost_per_win")) > 0),
            key=lambda row: self._num(row.get("cost_per_win")),
            default={},
        )
        best_efficiency = max(
            top_rows,
            key=lambda row: self._num(row.get("revenue_per_spend")),
            default={},
        )

        weak_spots = []
        if highest_cpw:
            weak_spots.append({
                "name": self._label(highest_cpw),
                "metric": f"{highest_cpw.get('decision', 'Review')} campaign cost per win",
                "evidence": (
                    f"{self._label(highest_cpw)} shows cost per win of "
                    f"{self._currency(highest_cpw.get('cost_per_win'))} versus blended CPW of "
                    f"{self._currency(blended_cpw)}."
                ),
                "why_it_matters": (
                    f"Lead-to-win is {self._percent(highest_cpw.get('lead_to_win_rate'))} with "
                    f"{highest_cpw.get('sample_size_bucket', 'unknown')} confidence."
                ),
                "severity": "high" if highest_cpw.get("decision") == "Avoid" else "medium",
            })

        recommendations = []
        if highest_cpw:
            recommendations.append({
                "action": f"Keep {self._label(highest_cpw)} in {highest_cpw.get('decision', 'review')}",
                "rationale": "Its live cost-per-win and conversion gates do not support scaling yet.",
                "expected_impact": "Protects budget while the campaign builds a stronger same-period sample.",
                "confidence": "medium",
            })
        if best_efficiency:
            recommendations.append({
                "action": f"Prioritize the next review of {self._label(best_efficiency)}",
                "rationale": (
                    f"It has stronger revenue per spend at {self._num(best_efficiency.get('revenue_per_spend')):.1f}x "
                    f"and is currently gated as {best_efficiency.get('decision', 'Review')}."
                ),
                "expected_impact": "Focuses decision time on the strongest evidence-backed campaign.",
                "confidence": "medium",
            })
        recommendations.append({
            "action": "Review Scale, Test, Hold, and Avoid gates in the next planning meeting",
            "rationale": "The campaign ranking combines live CPW, lead-to-win rate, and same-period sample confidence.",
            "expected_impact": "Keeps spend decisions tied to observed performance rather than synthetic allocations.",
            "confidence": "high",
        })

        return {
            "headline": "Live campaign gates identify the next decisions",
            "executive_summary": (
                f"For {filters.get('market', 'the selected market')} / {filters.get('source', 'the selected source')}, "
                f"the ranked live campaign rows show {self._currency(total_spend)} in actual spend and blended CPW of "
                f"{self._currency(blended_cpw)}. Scale and Test recommendations require both efficient CPW and credible conversion."
            ),
            "weak_spots": weak_spots,
            "recommendations": recommendations,
            "watchouts": [
                "These recommendations use the dashboard context supplied to the assistant, not an open-ended BigQuery query.",
                f"Fallback insight mode was used because Claude returned no usable structured text: {reason}.",
            ],
            "next_actions": [
                "Open Campaign Performance and compare the weak spot against the highest-ranked campaign.",
                "Add a note on any campaign whose CPW looks directionally wrong so the data team can validate source data.",
                "Use the next budget review to decide whether each campaign should scale, test, hold, or avoid.",
            ],
        }

    def _num(self, value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _label(self, row):
        return str(row.get("campaign") or row.get("source") or row.get("name") or "Selected campaign")

    def _currency(self, value):
        amount = self._num(value)
        if abs(amount) >= 1_000_000:
            return f"${amount / 1_000_000:.1f}M"
        if abs(amount) >= 1_000:
            return f"${amount / 1_000:.0f}K"
        return f"${amount:,.0f}"

    def _percent(self, value):
        return f"{self._num(value) * 100:.1f}%"

    def _retry_delay(self, exc, attempt):
        retry_after = exc.headers.get("retry-after") if exc.headers else None
        try:
            return min(5.0, max(0.5, float(retry_after)))
        except (TypeError, ValueError):
            return 0.8 * (attempt + 1)

    def _is_retryable_claude_error(self, status, detail):
        text = str(detail or "").lower()
        return status in {429, 500, 502, 503, 529} or "overload" in text or "rate" in text

    def _ask_claude(self, payload):
        if not ANTHROPIC_API_KEY:
            return HTTPStatus.SERVICE_UNAVAILABLE, {"detail": "Claude is not configured for this environment."}

        question = str(payload.get("question", "")).strip()
        if not question:
            raise ValueError("Question is required.")

        context = payload.get("context", {})
        context_json = json.dumps(context, indent=2, default=str)[:20_000]
        body = {
            "model": ANTHROPIC_MODEL,
            "max_tokens": 1600,
            "system": (
                "You are Claude helping Lumina Solar's marketing team interpret an internal "
                "performance dashboard. Give executives and marketing operators decision-grade "
                "insights, not generic commentary. Use the supplied dashboard context only, call "
                "out exact evidence, compare against blended benchmarks, and convert findings "
                "into actions. Return JSON only with this shape: "
                '{"headline": string, "executive_summary": string, '
                '"weak_spots": [{"name": string, "metric": string, "evidence": string, '
                '"why_it_matters": string, "severity": "high"|"medium"|"low"}], '
                '"recommendations": [{"action": string, "rationale": string, '
                '"expected_impact": string, "confidence": "high"|"medium"|"low"}], '
                '"watchouts": [string], "next_actions": [string]}. '
                "Keep each string concise. If the evidence is directional/demo-mode, say so."
            ),
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"Dashboard context:\n{context_json}\n\n"
                        f"Marketing user's question:\n{question}"
                    ),
                }
            ],
        }
        request = urlrequest.Request(
            ANTHROPIC_MESSAGES_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
                "x-api-key": ANTHROPIC_API_KEY,
            },
            method="POST",
        )
        result = None
        for attempt in range(3):
            try:
                with urlrequest.urlopen(request, timeout=45) as response:
                    result = json.loads(response.read().decode("utf-8"))
                break
            except urlerror.HTTPError as exc:
                detail = "Claude request failed. Check the configured Anthropic key and model."
                try:
                    error_payload = json.loads(exc.read().decode("utf-8"))
                    detail = error_payload.get("error", {}).get("message", detail)
                except Exception:
                    pass
                if self._is_retryable_claude_error(exc.code, detail):
                    if attempt < 2:
                        time.sleep(self._retry_delay(exc, attempt))
                        continue
                    insights = self._fallback_insights(question, context, f"Claude temporarily unavailable: {detail}")
                    return HTTPStatus.OK, {
                        "answer": insights["executive_summary"],
                        "insights": insights,
                        "model": ANTHROPIC_MODEL,
                        "fallback": True,
                    }
                return HTTPStatus.BAD_GATEWAY, {"detail": detail, "status": exc.code}
            except Exception:
                if attempt < 2:
                    time.sleep(0.8 * (attempt + 1))
                    continue
                insights = self._fallback_insights(question, context, "Claude request failed after retries")
                return HTTPStatus.OK, {
                    "answer": insights["executive_summary"],
                    "insights": insights,
                    "model": ANTHROPIC_MODEL,
                    "fallback": True,
                }

        if result is None:
            insights = self._fallback_insights(question, context, "Claude returned no response")
            return HTTPStatus.OK, {
                "answer": insights["executive_summary"],
                "insights": insights,
                "model": ANTHROPIC_MODEL,
                "fallback": True,
            }

        answer = self._extract_claude_answer(result)
        if not answer:
            reason = f"stop_reason={result.get('stop_reason')}; content_types={','.join([
                block.get("type", type(block).__name__) if isinstance(block, dict) else type(block).__name__
                for block in result.get("content", [])
            ]) or 'none'}"
            insights = self._fallback_insights(question, context, reason)
            return HTTPStatus.OK, {
                "answer": insights["executive_summary"],
                "insights": insights,
                "model": result.get("model", ANTHROPIC_MODEL),
                "fallback": True,
            }
        insights = self._parse_claude_insights(answer)
        if insights is None:
            insights = self._fallback_insights(question, context, "unstructured Claude response")
            insights["watchouts"].insert(0, "Claude returned text, but not in the structured format needed for the insight panel.")
        return HTTPStatus.OK, {
            "answer": answer,
            "insights": insights,
            "model": result.get("model", ANTHROPIC_MODEL),
        }


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    ThreadingHTTPServer(("0.0.0.0", port), DashboardHandler).serve_forever()
