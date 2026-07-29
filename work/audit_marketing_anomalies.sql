-- Read-only anomaly drill-down for operating-region, test-data, and duplicate review.

-- Outside-footprint and unresolved activity by campaign.
SELECT
  COALESCE(NULLIF(TRIM(UPPER(resolved_state)), ''), 'UNRESOLVED') AS raw_state,
  campaign_name,
  campaign_reporting_rollup_name,
  final_ahj_resolution_method,
  final_ahj_resolution_confidence,
  SUM(lead_count) AS leads,
  SUM(set_count) AS sets,
  SUM(run_count) AS runs,
  SUM(win_count) AS wins,
  SUM(win_revenue) AS revenue,
  SUM(effective_spend_amount) AS effective_spend
FROM `lumina-lakehouse.marketing_tool_ops.rpt_marketing_funnel_analysis_runtime`
WHERE cohort_period_grain = 'MONTH'
  AND cohort_period_start_date BETWEEN DATE '2026-01-01' AND DATE '2026-07-31'
  AND (
    NULLIF(TRIM(resolved_state), '') IS NULL
    OR TRIM(UPPER(resolved_state)) NOT IN (
      'DC', 'D.C.', 'DISTRICT OF COLUMBIA',
      'MD', 'MARYLAND',
      'VA', 'VIRGINIA',
      'PA', 'PENNSYLVANIA'
    )
  )
GROUP BY 1, 2, 3, 4, 5
HAVING leads > 0 OR effective_spend > 0
ORDER BY leads DESC, effective_spend DESC
LIMIT 100;

-- Broad test/demo markers on the attributed lead-funnel source.
SELECT
  lead_funnel_sk,
  campaign_member_id,
  lead_or_contact_id,
  selected_opportunity_id,
  campaign_name,
  official_reporting_campaign_name,
  sf_opp_name,
  resolved_state,
  current_funnel_status,
  official_set_count,
  official_run_count,
  official_win_count,
  official_win_revenue
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
  r'(^|[^a-z])(test|testing|demo|sample|training|dummy|fake|sandbox|do not use|qa)([^a-z]|$)'
)
ORDER BY official_win_count DESC, campaign_member_created_date DESC
LIMIT 500;

-- Dimension and mapping uniqueness.
SELECT
  'dim_campaign campaign_sf_id' AS check_name,
  COUNT(*) AS row_count,
  COUNT(DISTINCT campaign_sf_id) AS distinct_keys,
  COUNTIF(campaign_sf_id IS NULL) AS null_keys,
  COUNT(*) - COUNT(DISTINCT campaign_sf_id) - COUNTIF(campaign_sf_id IS NULL) AS duplicate_rows
FROM `lumina-lakehouse.analytics_dim.dim_campaign`
UNION ALL
SELECT
  'dim_campaign_reporting_hierarchy campaign_sf_id',
  COUNT(*),
  COUNT(DISTINCT campaign_sf_id),
  COUNTIF(campaign_sf_id IS NULL),
  COUNT(*) - COUNT(DISTINCT campaign_sf_id) - COUNTIF(campaign_sf_id IS NULL)
FROM `lumina-lakehouse.analytics_dim.dim_campaign_reporting_hierarchy`
UNION ALL
SELECT
  'dim_zip_ahj_best zip5',
  COUNT(*),
  COUNT(DISTINCT zip5),
  COUNTIF(zip5 IS NULL),
  COUNT(*) - COUNT(DISTINCT zip5) - COUNTIF(zip5 IS NULL)
FROM `lumina-lakehouse.analytics_dim.dim_zip_ahj_best`;

-- Exact reliable-benchmark duplicates at the dashboard join grain.
SELECT
  COUNT(*) AS reliable_benchmark_rows,
  COUNT(DISTINCT CONCAT(
    COALESCE(campaign_sf_id, ''), '|',
    COALESCE(final_reporting_jurisdiction_key, ''), '|',
    COALESCE(resolved_zip_code, ''), '|',
    cohort_period_grain, '|',
    CAST(cohort_period_start_date AS STRING)
  )) AS distinct_join_keys,
  COUNT(*) - COUNT(DISTINCT CONCAT(
    COALESCE(campaign_sf_id, ''), '|',
    COALESCE(final_reporting_jurisdiction_key, ''), '|',
    COALESCE(resolved_zip_code, ''), '|',
    cohort_period_grain, '|',
    CAST(cohort_period_start_date AS STRING)
  )) AS duplicate_reliable_rows
FROM `lumina-lakehouse.analytics_rpt.rpt_marketing_cohort_expected_yield`
WHERE is_reliable_for_expected_yield;

-- Ties at the selected benchmark priority (would make QUALIFY nondeterministic).
WITH ranked AS (
  SELECT
    campaign_sf_id,
    final_reporting_jurisdiction_key,
    resolved_zip_code,
    cohort_period_grain,
    cohort_period_start_date,
    benchmark_candidate_priority,
    MIN(benchmark_candidate_priority) OVER (
      PARTITION BY
        campaign_sf_id,
        final_reporting_jurisdiction_key,
        resolved_zip_code,
        cohort_period_grain,
        cohort_period_start_date
    ) AS min_priority
  FROM `lumina-lakehouse.analytics_rpt.rpt_marketing_cohort_expected_yield`
  WHERE is_reliable_for_expected_yield
),
selected_ties AS (
  SELECT
    campaign_sf_id,
    final_reporting_jurisdiction_key,
    resolved_zip_code,
    cohort_period_grain,
    cohort_period_start_date,
    COUNT(*) AS selected_rows
  FROM ranked
  WHERE benchmark_candidate_priority = min_priority
  GROUP BY 1, 2, 3, 4, 5
  HAVING COUNT(*) > 1
)
SELECT
  COUNT(*) AS tied_join_keys,
  SUM(selected_rows) AS tied_rows
FROM selected_ties;

WITH ranked AS (
  SELECT
    *,
    MIN(benchmark_candidate_priority) OVER (
      PARTITION BY
        campaign_sf_id,
        final_reporting_jurisdiction_key,
        resolved_zip_code,
        cohort_period_grain,
        cohort_period_start_date
    ) AS min_priority
  FROM `lumina-lakehouse.analytics_rpt.rpt_marketing_cohort_expected_yield`
  WHERE is_reliable_for_expected_yield
),
selected_variation AS (
  SELECT
    campaign_sf_id,
    final_reporting_jurisdiction_key,
    resolved_zip_code,
    cohort_period_grain,
    cohort_period_start_date,
    COUNT(*) AS selected_rows,
    COUNT(DISTINCT TO_JSON_STRING(STRUCT(
      benchmark_level,
      benchmark_confidence,
      benchmark_confidence_score,
      benchmark_lead_to_win_rate,
      benchmark_revenue_per_win
    ))) AS distinct_benchmark_values
  FROM ranked
  WHERE benchmark_candidate_priority = min_priority
  GROUP BY 1, 2, 3, 4, 5
)
SELECT
  COUNTIF(selected_rows > 1) AS tied_join_keys,
  COUNTIF(selected_rows > 1 AND distinct_benchmark_values > 1) AS ties_with_different_values,
  MAX(distinct_benchmark_values) AS max_distinct_values_per_key
FROM selected_variation;

-- Spend multi-entry groups for duplicate adjudication.
SELECT
  campaign_sf_id,
  campaign_name,
  spend_date,
  spend_territory,
  COUNT(*) AS row_count,
  COUNT(DISTINCT campaign_spend_sf_id) AS distinct_source_ids,
  COUNT(DISTINCT CAST(spend_amount AS STRING)) AS distinct_amounts,
  SUM(spend_amount) AS spend
FROM `lumina-lakehouse.analytics_fact.fact_marketing_spend`
GROUP BY 1, 2, 3, 4
HAVING COUNT(*) > 1
ORDER BY spend DESC
LIMIT 100;

-- Test/demo candidates by cohort period and current dashboard impact.
WITH exclusions AS (
  SELECT DISTINCT campaign_member_id, selected_opportunity_id
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
    r'(^|[^a-z])(test|testing|demo|sample|training|dummy|fake|sandbox|do not use|qa)([^a-z]|$)'
  )
)
SELECT
  DATE_TRUNC(c.cohort_lead_created_date, MONTH) AS cohort_month,
  c.campaign_reporting_rollup_name,
  c.campaign_name,
  c.resolved_state,
  COUNT(*) AS excluded_rows,
  SUM(c.lead_count) AS leads,
  SUM(c.set_count) AS sets,
  SUM(c.run_count) AS runs,
  SUM(c.win_count) AS wins,
  SUM(c.official_win_revenue) AS revenue
FROM `lumina-lakehouse.analytics_fact.fact_marketing_cohort_member_outcome` c
JOIN exclusions e
  ON e.campaign_member_id = c.campaign_member_id
  AND e.selected_opportunity_id = c.selected_opportunity_id
GROUP BY 1, 2, 3, 4
ORDER BY cohort_month DESC, excluded_rows DESC;
