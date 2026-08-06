-- Calendar-period marketing activity, intentionally separate from fixed lead cohorts.
-- Each event is dated by Marketing's Salesforce definition:
--   Lead: Lead.Updated_Campaign_Member__c
--   Set: Opportunity.CreatedDate
--   Run: completed sales-visit event, dated by the opportunity SV start timestamp
--   Win: qualifying Opportunity.StageName, dated by CloseDate
-- Spend is the governed daily allocation and is included for pacing context.

CREATE OR REPLACE TABLE
  `lumina-lakehouse.marketing_tool_ops.rpt_marketing_activity_daily_runtime`
PARTITION BY event_date
CLUSTER BY event_type, campaign_sf_id, operating_region_group
OPTIONS (
  description = 'Runtime-safe daily marketing activity for rolling and calendar-period trends. Event-period metrics are not cohort conversion metrics.'
)
AS
WITH attribution_base AS (
  SELECT
    lead_id,
    campaign_member_id,
    selected_opportunity_id,
    source_most_recent_campaign_member,
    is_official_opportunity_credit_row,
    official_opportunity_credit_rank,
    campaign_member_created_timestamp,
    fact_loaded_at,
    COALESCE(official_reporting_campaign_sf_id, campaign_sf_id) AS campaign_sf_id,
    COALESCE(official_reporting_campaign_name, campaign_name) AS campaign_name,
    resolved_county,
    resolved_state,
    resolved_ops_region
  FROM `lumina-lakehouse.marketing_tool_ops.fact_lead_funnel_attributed_clean`
),
lead_attribution AS (
  SELECT
    a.lead_id,
    a.campaign_sf_id,
    COALESCE(a.campaign_name, h.campaign_name, 'Unattributed lead') AS campaign_name,
    h.campaign_reporting_rollup_name,
    h.campaign_sub_rollup_name,
    a.resolved_county,
    a.resolved_state,
    a.resolved_ops_region
  FROM attribution_base a
  LEFT JOIN `lumina-lakehouse.analytics_dim.dim_campaign_reporting_hierarchy` h
    ON h.campaign_sf_id = a.campaign_sf_id
  WHERE a.lead_id IS NOT NULL
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY a.lead_id
    ORDER BY
      COALESCE(a.source_most_recent_campaign_member, FALSE) DESC,
      a.campaign_member_created_timestamp DESC,
      a.fact_loaded_at DESC
  ) = 1
),
opportunity_attribution AS (
  SELECT
    a.selected_opportunity_id AS opportunity_sf_id,
    a.campaign_sf_id,
    COALESCE(a.campaign_name, h.campaign_name, 'Unattributed opportunity') AS campaign_name,
    h.campaign_reporting_rollup_name,
    h.campaign_sub_rollup_name,
    a.resolved_county,
    a.resolved_state,
    a.resolved_ops_region
  FROM attribution_base a
  LEFT JOIN `lumina-lakehouse.analytics_dim.dim_campaign_reporting_hierarchy` h
    ON h.campaign_sf_id = a.campaign_sf_id
  WHERE a.selected_opportunity_id IS NOT NULL
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY a.selected_opportunity_id
    ORDER BY
      COALESCE(a.is_official_opportunity_credit_row, FALSE) DESC,
      COALESCE(a.official_opportunity_credit_rank, 999999) ASC,
      a.fact_loaded_at DESC
  ) = 1
),
opportunity_events AS (
  SELECT
    o.id AS opportunity_sf_id,
    COALESCE(a.campaign_sf_id, p.opportunity_primary_campaign_sf_id) AS campaign_sf_id,
    COALESCE(a.campaign_name, h.campaign_name, 'Unattributed opportunity') AS campaign_name,
    COALESCE(a.campaign_reporting_rollup_name, h.campaign_reporting_rollup_name) AS campaign_reporting_rollup_name,
    COALESCE(a.campaign_sub_rollup_name, h.campaign_sub_rollup_name) AS campaign_sub_rollup_name,
    COALESCE(a.resolved_county, p.county) AS resolved_county,
    COALESCE(a.resolved_state, p.state) AS resolved_state,
    COALESCE(a.resolved_ops_region, p.ops_region) AS resolved_ops_region,
    DATE(o.created_date, 'America/New_York') AS set_date,
    IF(
      UPPER(TRIM(o.stage_name)) IN ('PENDING REVIEW', 'CHANGE ORDER', 'CLOSED WON', 'CONTRACT CANCELLED'),
      o.close_date,
      NULL
    ) AS win_date,
    IF(
      UPPER(TRIM(o.stage_name)) IN ('PENDING REVIEW', 'CHANGE ORDER', 'CLOSED WON', 'CONTRACT CANCELLED'),
      CAST(COALESCE(o.amount, 0) AS FLOAT64),
      0
    ) AS win_value
  FROM `lumina-lakehouse.salesforce.opportunity` o
  LEFT JOIN opportunity_attribution a
    ON a.opportunity_sf_id = o.id
  LEFT JOIN `lumina-lakehouse.analytics_dim.dim_project` p
    ON p.opportunity_sf_id = o.id
  LEFT JOIN `lumina-lakehouse.analytics_dim.dim_campaign_reporting_hierarchy` h
    ON h.campaign_sf_id = COALESCE(a.campaign_sf_id, p.opportunity_primary_campaign_sf_id)
  WHERE NOT COALESCE(o.is_deleted, FALSE)
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY o.id
    ORDER BY p.project_created_date DESC NULLS LAST, p.created_date DESC NULLS LAST
  ) = 1
),
events AS (
  SELECT
    DATE(l.updated_campaign_member_c, 'America/New_York') AS event_date,
    'Lead' AS event_type,
    a.campaign_sf_id,
    a.campaign_name,
    a.campaign_reporting_rollup_name,
    a.campaign_sub_rollup_name,
    a.resolved_county,
    a.resolved_state,
    a.resolved_ops_region,
    1 AS event_count,
    CAST(0 AS FLOAT64) AS event_value
  FROM `lumina-lakehouse.salesforce.lead` l
  LEFT JOIN lead_attribution a
    ON a.lead_id = l.id
  WHERE NOT COALESCE(l.is_deleted, FALSE)
    AND l.updated_campaign_member_c IS NOT NULL

  UNION ALL

  SELECT
    set_date,
    'Set',
    campaign_sf_id,
    campaign_name,
    campaign_reporting_rollup_name,
    campaign_sub_rollup_name,
    resolved_county,
    resolved_state,
    resolved_ops_region,
    1,
    CAST(0 AS FLOAT64)
  FROM opportunity_events
  WHERE set_date IS NOT NULL

  UNION ALL

  SELECT
    DATE(v.opp_sv_start_c, 'America/New_York'),
    'Run',
    o.campaign_sf_id,
    o.campaign_name,
    o.campaign_reporting_rollup_name,
    o.campaign_sub_rollup_name,
    o.resolved_county,
    o.resolved_state,
    o.resolved_ops_region,
    1,
    CAST(0 AS FLOAT64)
  FROM `lumina-lakehouse.analytics_fact.fact_sales_visit` v
  JOIN opportunity_events o
    ON o.opportunity_sf_id = v.opportunity_sf_id
  WHERE v.source_table = 'event'
    AND UPPER(TRIM(v.source_status)) = 'COMPLETE'
    AND v.opp_sv_start_c IS NOT NULL
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY v.opportunity_sf_id, DATE(v.opp_sv_start_c, 'America/New_York')
    ORDER BY v.source_synced_at DESC
  ) = 1

  UNION ALL

  SELECT
    win_date,
    'Win',
    campaign_sf_id,
    campaign_name,
    campaign_reporting_rollup_name,
    campaign_sub_rollup_name,
    resolved_county,
    resolved_state,
    resolved_ops_region,
    1,
    win_value
  FROM opportunity_events
  WHERE win_date IS NOT NULL

  UNION ALL

  SELECT
    spend_allocation_date,
    'Spend',
    campaign_sf_id,
    COALESCE(campaign_name, 'Unattributed spend'),
    campaign_reporting_rollup_name,
    campaign_sub_rollup_name,
    CAST(NULL AS STRING),
    spend_territory,
    spend_territory,
    0,
    CAST(COALESCE(allocated_daily_spend_amount, 0) AS FLOAT64)
  FROM `lumina-lakehouse.analytics_fact.fact_marketing_spend_allocated`
  WHERE spend_allocation_date IS NOT NULL
)
SELECT
  event_date,
  event_type,
  campaign_sf_id,
  campaign_name,
  campaign_reporting_rollup_name,
  campaign_sub_rollup_name,
  COALESCE(NULLIF(TRIM(resolved_county), ''), 'Unresolved') AS resolved_county,
  COALESCE(NULLIF(TRIM(resolved_state), ''), 'Unresolved') AS resolved_state,
  CASE
    WHEN UPPER(TRIM(resolved_ops_region)) IN ('MD', 'MARYLAND', 'MD OPS', 'MD OPS REGION', 'MD/DC/VA') THEN 'Maryland'
    WHEN UPPER(TRIM(resolved_ops_region)) IN ('PA', 'PENNSYLVANIA', 'PA OPS', 'PA OPS REGION', 'PA/DE') THEN 'Pennsylvania'
    WHEN UPPER(TRIM(resolved_state)) IN ('MD', 'MARYLAND', 'VA', 'VIRGINIA', 'DC', 'D.C.', 'DISTRICT OF COLUMBIA') THEN 'Maryland'
    WHEN UPPER(TRIM(resolved_state)) IN ('PA', 'PENNSYLVANIA', 'DE', 'DELAWARE') THEN 'Pennsylvania'
    WHEN NULLIF(TRIM(resolved_ops_region), '') IS NULL AND NULLIF(TRIM(resolved_state), '') IS NULL THEN 'Unresolved'
    ELSE 'Outside operating footprint'
  END AS operating_region_group,
  SUM(event_count) AS event_count,
  SUM(event_value) AS event_value,
  CURRENT_TIMESTAMP() AS loaded_at
FROM events
WHERE event_date BETWEEN DATE_SUB(DATE_TRUNC(CURRENT_DATE('America/New_York'), YEAR), INTERVAL 1 YEAR)
  AND CURRENT_DATE('America/New_York')
  AND NOT REGEXP_CONTAINS(LOWER(COALESCE(campaign_name, '')), r'jonathan\s+bissell')
GROUP BY
  event_date,
  event_type,
  campaign_sf_id,
  campaign_name,
  campaign_reporting_rollup_name,
  campaign_sub_rollup_name,
  resolved_county,
  resolved_state,
  operating_region_group;

ASSERT (
  SELECT COUNT(*) > 0
  FROM `lumina-lakehouse.marketing_tool_ops.rpt_marketing_activity_daily_runtime`
) AS 'Calendar activity runtime table is empty';

ASSERT (
  SELECT COUNTIF(event_date > CURRENT_DATE('America/New_York')) = 0
  FROM `lumina-lakehouse.marketing_tool_ops.rpt_marketing_activity_daily_runtime`
) AS 'Calendar activity runtime table contains future events';
