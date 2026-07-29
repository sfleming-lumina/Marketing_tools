CREATE OR REPLACE VIEW
  `lumina-lakehouse.marketing_tool_ops.rpt_marketing_test_record_exclusions`
AS

SELECT
  lead_funnel_sk,
  campaign_member_id,
  selected_opportunity_id,
  campaign_name,
  official_reporting_campaign_name,
  sf_opp_name,
  campaign_member_created_date,
  resolved_state,
  'Explicit test/demo marker in campaign or opportunity metadata' AS exclusion_reason,
  fact_loaded_at AS source_loaded_at
FROM `lumina-lakehouse.analytics_fact.fact_lead_funnel_attributed`
WHERE REGEXP_CONTAINS(
  LOWER(CONCAT(
    COALESCE(campaign_name, ''), ' ',
    COALESCE(parent_campaign_name, ''), ' ',
    COALESCE(grandparent_campaign_name, ''), ' ',
    COALESCE(official_reporting_campaign_name, ''), ' ',
    COALESCE(touchpoint_campaign_name, ''), ' ',
    COALESCE(sf_opp_name, ''), ' ',
    COALESCE(lead_source_name, ''), ' ',
    COALESCE(lead_utm_campaign, ''), ' ',
    COALESCE(opportunity_utm_campaign, '')
  )),
  r'(^|[^a-z])(test|testing|demo|training|dummy|fake|sandbox|do not use)([^a-z]|$)'
);

CREATE OR REPLACE VIEW
  `lumina-lakehouse.marketing_tool_ops.fact_lead_funnel_attributed_clean`
AS

SELECT source_fact.*
FROM `lumina-lakehouse.analytics_fact.fact_lead_funnel_attributed` source_fact
LEFT JOIN `lumina-lakehouse.marketing_tool_ops.rpt_marketing_test_record_exclusions` exclusions
  ON exclusions.lead_funnel_sk = source_fact.lead_funnel_sk
WHERE exclusions.lead_funnel_sk IS NULL;

BEGIN
  DECLARE upstream_cohort_sql STRING;

  SET upstream_cohort_sql = (
    SELECT view_definition
    FROM `lumina-lakehouse.analytics_rpt.INFORMATION_SCHEMA.VIEWS`
    WHERE table_name = 'rpt_marketing_lead_cohort_performance'
  );

  ASSERT upstream_cohort_sql IS NOT NULL
    AS 'Unable to read analytics_rpt.rpt_marketing_lead_cohort_performance definition';

  SET upstream_cohort_sql = REPLACE(
    upstream_cohort_sql,
    '`lumina-lakehouse.analytics_fact.fact_lead_funnel_attributed` flfa',
    '`lumina-lakehouse.marketing_tool_ops.fact_lead_funnel_attributed_clean` flfa'
  );

  EXECUTE IMMEDIATE
    'CREATE OR REPLACE VIEW `lumina-lakehouse.marketing_tool_ops.rpt_marketing_lead_cohort_performance_clean` AS '
    || upstream_cohort_sql;
END;

CREATE OR REPLACE VIEW
  `lumina-lakehouse.marketing_tool_ops.rpt_marketing_cohort_performance_with_yield`
AS

WITH yield_selected AS (
  SELECT *
  FROM `lumina-lakehouse.analytics_rpt.rpt_marketing_cohort_expected_yield`
  WHERE is_reliable_for_expected_yield
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY
      campaign_sf_id,
      final_reporting_jurisdiction_key,
      resolved_zip_code,
      cohort_period_grain,
      cohort_period_start_date
    ORDER BY
      benchmark_candidate_priority ASC,
      benchmark_confidence_score DESC,
      benchmark_level ASC,
      benchmark_lead_to_win_rate DESC,
      benchmark_revenue_per_win DESC
  ) = 1
)

SELECT
  p.campaign_sf_id,
  p.campaign_sk,
  p.campaign_name,
  p.parent_campaign_name,
  p.grandparent_campaign_name,
  p.campaign_reporting_rollup_name,
  p.campaign_sub_rollup_name,
  p.campaign_hierarchy_path,
  p.campaign_type,
  p.campaign_status,
  p.campaign_stage,
  p.inferred_campaign_channel,
  p.campaign_group,
  p.final_reporting_jurisdiction_key,
  p.final_reporting_jurisdiction_type,
  p.final_reporting_jurisdiction_label,
  p.final_reporting_ahj_sf_id,
  p.final_reporting_ahj_name,
  p.final_ahj_resolution_method,
  p.final_ahj_resolution_confidence,
  p.resolved_county,
  p.resolved_state,
  p.resolved_zip_code,
  p.resolved_ops_region,
  p.reporting_market_label,
  p.reporting_market_county,
  p.reporting_market_state,
  p.cohort_period_grain,
  p.cohort_period_start_date,
  p.cohort_period_end_date,
  p.cohort_age_days,
  p.cohort_maturity_bucket,
  p.sample_size_bucket,
  p.lead_count,
  p.distinct_campaign_members,
  p.distinct_people,
  p.set_count,
  p.run_count,
  p.win_count,
  p.lost_count,
  p.win_revenue,
  p.win_kw,
  p.set_no_run_30_plus_count,
  p.run_no_win_60_plus_count,
  p.open_no_set_30_plus_count,
  p.active_pipeline_candidate_count,
  p.active_pipeline_candidate_revenue,
  p.cohort_row_set_rate,
  p.cohort_row_run_rate_from_sets,
  p.cohort_row_win_rate_from_runs,
  p.cohort_row_lead_to_win_rate,
  p.allocated_spend_amount,
  p.spend_allocation_method,
  p.cost_per_lead,
  p.cost_per_set,
  p.cost_per_run,
  p.cost_per_win,
  p.revenue_per_spend,
  p.revenue_per_win,
  y.benchmark_level AS applied_benchmark_level,
  y.benchmark_candidate_priority AS applied_benchmark_priority,
  y.benchmark_confidence,
  y.benchmark_confidence_score,
  y.benchmark_data_quality_status,
  y.benchmark_lead_to_win_rate,
  y.benchmark_revenue_per_win,
  y.expected_mature_win_count,
  y.expected_mature_revenue,
  y.expected_remaining_win_count,
  y.expected_remaining_revenue,
  y.win_attainment_vs_expected,
  y.revenue_attainment_vs_expected,
  y.expected_yield_category,
  y.expected_yield_usability,
  y.campaign_sf_id IS NOT NULL AS has_reliable_benchmark,
  p.rpt_loaded_at
FROM `lumina-lakehouse.marketing_tool_ops.rpt_marketing_lead_cohort_performance_clean` p
LEFT JOIN yield_selected y
  ON y.campaign_sf_id = p.campaign_sf_id
  AND y.final_reporting_jurisdiction_key = p.final_reporting_jurisdiction_key
  AND IFNULL(y.resolved_zip_code, '') = IFNULL(p.resolved_zip_code, '')
  AND y.cohort_period_grain = p.cohort_period_grain
  AND y.cohort_period_start_date = p.cohort_period_start_date;


CREATE OR REPLACE VIEW
  `lumina-lakehouse.marketing_tool_ops.rpt_marketing_funnel_analysis`
AS

SELECT
  c.*,
  CASE
    WHEN UPPER(TRIM(c.resolved_state)) IN ('MD', 'MARYLAND') THEN 'MD'
    WHEN UPPER(TRIM(c.resolved_state)) IN ('VA', 'VIRGINIA') THEN 'VA'
    WHEN UPPER(TRIM(c.resolved_state)) IN (
      'DC',
      'D.C.',
      'DISTRICT OF COLUMBIA',
      'WASHINGTON DC',
      'WASHINGTON, DC'
    ) THEN 'DC'
    WHEN UPPER(TRIM(c.resolved_state)) IN ('PA', 'PENNSYLVANIA') THEN 'PA'
    WHEN UPPER(TRIM(c.resolved_state)) IN ('DE', 'DELAWARE') THEN 'DE'
    WHEN NULLIF(TRIM(c.resolved_state), '') IS NULL THEN NULL
    ELSE UPPER(TRIM(c.resolved_state))
  END AS normalized_operating_state,
  CASE
    WHEN UPPER(TRIM(c.resolved_ops_region)) IN (
      'MD',
      'MARYLAND',
      'MD OPS',
      'MD OPS REGION',
      'MD/DC/VA'
    ) THEN 'MD'
    WHEN UPPER(TRIM(c.resolved_ops_region)) IN (
      'PA',
      'PENNSYLVANIA',
      'PA OPS',
      'PA OPS REGION',
      'PA/DE'
    ) THEN 'PA'
    WHEN NULLIF(TRIM(c.resolved_ops_region), '') IS NULL
      AND UPPER(TRIM(c.resolved_state)) IN (
        'MD', 'MARYLAND', 'VA', 'VIRGINIA', 'DC', 'D.C.',
        'DISTRICT OF COLUMBIA', 'WASHINGTON DC', 'WASHINGTON, DC'
      ) THEN 'MD'
    WHEN NULLIF(TRIM(c.resolved_ops_region), '') IS NULL
      AND UPPER(TRIM(c.resolved_state)) IN (
        'PA', 'PENNSYLVANIA', 'DE', 'DELAWARE'
      ) THEN 'PA'
    ELSE NULL
  END AS normalized_ops_region,
  CASE
    WHEN UPPER(TRIM(c.resolved_ops_region)) IN (
      'MD',
      'MARYLAND',
      'MD OPS',
      'MD OPS REGION',
      'MD/DC/VA'
    ) THEN 'Maryland'
    WHEN UPPER(TRIM(c.resolved_ops_region)) IN (
      'PA',
      'PENNSYLVANIA',
      'PA OPS',
      'PA OPS REGION',
      'PA/DE'
    ) THEN 'Pennsylvania'
    WHEN NULLIF(TRIM(c.resolved_ops_region), '') IS NULL
      AND UPPER(TRIM(c.resolved_state)) IN (
      'MD',
      'MARYLAND',
      'VA',
      'VIRGINIA',
      'DC',
      'D.C.',
      'DISTRICT OF COLUMBIA',
      'WASHINGTON DC',
      'WASHINGTON, DC'
    ) THEN 'Maryland'
    WHEN NULLIF(TRIM(c.resolved_ops_region), '') IS NULL
      AND UPPER(TRIM(c.resolved_state)) IN (
        'PA', 'PENNSYLVANIA', 'DE', 'DELAWARE'
      )
      THEN 'Pennsylvania'
    WHEN NULLIF(TRIM(c.resolved_ops_region), '') IS NULL
      AND NULLIF(TRIM(c.resolved_state), '') IS NULL
      THEN 'Unresolved'
    ELSE 'Outside operating footprint'
  END AS operating_region_group,
  CASE
    WHEN UPPER(TRIM(c.resolved_ops_region)) IN (
      'MD',
      'MARYLAND',
      'MD OPS',
      'MD OPS REGION',
      'MD/DC/VA',
      'PA',
      'PENNSYLVANIA',
      'PA OPS',
      'PA OPS REGION',
      'PA/DE'
    ) THEN TRUE
    WHEN NULLIF(TRIM(c.resolved_ops_region), '') IS NULL
      AND UPPER(TRIM(c.resolved_state)) IN (
      'MD',
      'MARYLAND',
      'VA',
      'VIRGINIA',
      'DC',
      'D.C.',
      'DISTRICT OF COLUMBIA',
      'WASHINGTON DC',
      'WASHINGTON, DC',
      'PA',
      'PENNSYLVANIA',
      'DE',
      'DELAWARE'
    ) THEN TRUE
    ELSE FALSE
  END AS is_operating_footprint,
  CASE
    WHEN c.campaign_reporting_rollup_name = 'Pay Per Install LSR'
      AND c.campaign_sub_rollup_name IN (
        'Customer Referral',
        'Non-Customer Referral',
        'Partner Referral'
      )
      AND c.cohort_period_start_date = DATE '2026-01-01'
      THEN c.win_count * 500
    WHEN c.campaign_reporting_rollup_name = 'Pay Per Install LSR'
      AND c.campaign_sub_rollup_name IN (
        'Customer Referral',
        'Non-Customer Referral',
        'Partner Referral'
      )
      THEN c.win_count * 1000
    ELSE COALESCE(c.allocated_spend_amount, 0)
  END AS effective_spend_amount,
  CASE
    WHEN c.campaign_reporting_rollup_name = 'Pay Per Install LSR'
      AND c.campaign_sub_rollup_name IN (
        'Customer Referral',
        'Non-Customer Referral',
        'Partner Referral'
      )
      THEN 'Derived payout'
    WHEN c.campaign_reporting_rollup_name = 'Pay Per Install LSR'
      AND c.campaign_sub_rollup_name = 'Rep Generated (Rep-Gen)'
      THEN 'Zero payout'
    WHEN c.campaign_reporting_rollup_name = 'Co-op'
      THEN 'Known incomplete'
    WHEN COALESCE(c.allocated_spend_amount, 0) > 0
      THEN 'Recorded'
    WHEN c.lead_count > 0
      THEN 'Lead-only'
    ELSE 'No activity'
  END AS spend_coverage_status,
  CASE
    WHEN c.campaign_reporting_rollup_name = 'Pay Per Install LSR'
      AND c.campaign_sub_rollup_name IN (
        'Customer Referral',
        'Non-Customer Referral',
        'Partner Referral'
      )
      THEN TRUE
    WHEN c.campaign_reporting_rollup_name = 'Pay Per Install LSR'
      AND c.campaign_sub_rollup_name = 'Rep Generated (Rep-Gen)'
      THEN TRUE
    WHEN c.campaign_reporting_rollup_name = 'Co-op'
      THEN FALSE
    WHEN COALESCE(c.allocated_spend_amount, 0) > 0
      THEN TRUE
    ELSE FALSE
  END AS spend_is_complete,
  CASE
    WHEN c.campaign_reporting_rollup_name = 'Pay Per Install LSR'
      AND c.campaign_sub_rollup_name IN (
        'Customer Referral',
        'Non-Customer Referral',
        'Partner Referral'
      )
      THEN 'Workbook payout rule: $500 per January win, $1,000 per February+ win'
    WHEN c.campaign_reporting_rollup_name = 'Pay Per Install LSR'
      AND c.campaign_sub_rollup_name = 'Rep Generated (Rep-Gen)'
      THEN 'Workbook payout rule: rep-generated leads carry a $0 referral payout'
    WHEN c.campaign_reporting_rollup_name = 'Co-op'
      THEN 'Workbook models Co-op cost outside campaign spend; use lead-first funnel'
    WHEN COALESCE(c.allocated_spend_amount, 0) > 0
      THEN c.spend_allocation_method
    ELSE 'No attributable campaign spend; use lead-first funnel'
  END AS spend_coverage_note
FROM
  `lumina-lakehouse.marketing_tool_ops.rpt_marketing_cohort_performance_with_yield` c;

-- Runtime-safe reporting copies.
--
-- The Cloud Run service is intentionally not granted direct access to the
-- analytics_dim or analytics_fact source datasets. These tables expose only
-- the curated reporting contracts needed by the application.
CREATE OR REPLACE TABLE
  `lumina-lakehouse.marketing_tool_ops.rpt_marketing_funnel_analysis_runtime`
OPTIONS (
  description = 'Runtime-safe copy of the marketing cohort funnel. Refresh with this deployment script.'
)
AS
SELECT *
FROM `lumina-lakehouse.marketing_tool_ops.rpt_marketing_funnel_analysis`;

CREATE OR REPLACE TABLE
  `lumina-lakehouse.marketing_tool_ops.rpt_marketing_period_projection_runtime`
OPTIONS (
  description = 'Runtime-safe copy of the current marketing period projections. Refresh with this deployment script.'
)
AS
SELECT *
FROM `lumina-lakehouse.analytics_rpt.rpt_marketing_period_projection`;
