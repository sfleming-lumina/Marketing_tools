-- Read-only marketing lineage and reconciliation audit.

-- 1. Exact state values and operating-footprint classification.
SELECT
  COALESCE(NULLIF(TRIM(UPPER(resolved_state)), ''), 'UNRESOLVED') AS raw_state,
  CASE
    WHEN TRIM(UPPER(resolved_state)) IN ('DC', 'D.C.', 'DISTRICT OF COLUMBIA', 'MD', 'MARYLAND', 'VA', 'VIRGINIA')
      THEN 'DMV'
    WHEN TRIM(UPPER(resolved_state)) IN ('PA', 'PENNSYLVANIA')
      THEN 'Pennsylvania'
    WHEN NULLIF(TRIM(resolved_state), '') IS NULL
      THEN 'Unresolved'
    ELSE 'Outside operating footprint'
  END AS proposed_operating_region,
  SUM(lead_count) AS leads,
  SUM(set_count) AS sets,
  SUM(run_count) AS runs,
  SUM(win_count) AS wins,
  SUM(win_revenue) AS revenue,
  SUM(effective_spend_amount) AS effective_spend
FROM `lumina-lakehouse.marketing_tool_ops.rpt_marketing_funnel_analysis_runtime`
WHERE cohort_period_grain = 'MONTH'
  AND cohort_period_start_date BETWEEN DATE '2026-01-01' AND DATE '2026-07-31'
GROUP BY raw_state, proposed_operating_region
ORDER BY leads DESC;

-- 2. Campaigns with explicit test/demo/training naming.
SELECT
  campaign_sf_id,
  campaign_name,
  parent_campaign_name,
  grandparent_campaign_name,
  campaign_reporting_rollup_name,
  SUM(lead_count) AS leads,
  SUM(win_count) AS wins,
  SUM(win_revenue) AS revenue,
  SUM(effective_spend_amount) AS effective_spend
FROM `lumina-lakehouse.marketing_tool_ops.rpt_marketing_funnel_analysis_runtime`
WHERE cohort_period_grain = 'MONTH'
  AND cohort_period_start_date BETWEEN DATE '2026-01-01' AND DATE '2026-07-31'
  AND REGEXP_CONTAINS(
    LOWER(CONCAT(
      COALESCE(campaign_name, ''), ' ',
      COALESCE(parent_campaign_name, ''), ' ',
      COALESCE(grandparent_campaign_name, '')
    )),
    r'(^|[^a-z])(test|demo|sample|training|dummy|fake|sandbox|do not use|qa)([^a-z]|$)'
  )
GROUP BY 1, 2, 3, 4, 5
ORDER BY leads DESC;

-- 3. Source-fact key uniqueness and outcome integrity.
SELECT
  COUNT(*) AS fact_rows,
  COUNT(DISTINCT lead_funnel_sk) AS distinct_lead_funnel_keys,
  COUNTIF(lead_funnel_sk IS NULL) AS null_lead_funnel_keys,
  COUNTIF(has_invalid_funnel_date_sequence) AS invalid_date_sequences,
  COUNTIF(official_run_count > official_set_count) AS run_without_set_count_mismatch,
  COUNTIF(official_win_count > official_run_count) AS win_without_run_count_mismatch,
  COUNTIF(is_duplicate_win_credit_suppressed) AS duplicate_win_credit_suppressed_rows
FROM `lumina-lakehouse.analytics_fact.fact_lead_funnel_attributed`;

-- 4. Cohort-member key uniqueness and invariant exceptions.
SELECT
  COUNT(*) AS cohort_member_rows,
  COUNT(DISTINCT CONCAT(
    COALESCE(campaign_member_id, ''), '|',
    COALESCE(campaign_sf_id, ''), '|',
    COALESCE(final_reporting_jurisdiction_key, ''), '|',
    COALESCE(resolved_zip_code, '')
  )) AS distinct_member_campaign_geo_keys,
  COUNTIF(lead_count != 1) AS non_unit_lead_rows,
  COUNTIF(set_count > lead_count) AS set_gt_lead_rows,
  COUNTIF(run_count > set_count) AS run_gt_set_rows,
  COUNTIF(win_count > run_count) AS win_gt_run_rows,
  COUNTIF(has_run_without_set) AS flagged_run_without_set_rows,
  COUNTIF(has_win_without_run) AS flagged_win_without_run_rows,
  COUNTIF(has_negative_days_to_set OR has_negative_days_to_run OR has_negative_days_to_win) AS negative_duration_rows
FROM `lumina-lakehouse.analytics_fact.fact_marketing_cohort_member_outcome`;

-- 5. Aggregated cohort invariant exceptions.
SELECT
  COUNT(*) AS cohort_rows,
  COUNTIF(set_count > lead_count) AS set_gt_lead_rows,
  COUNTIF(run_count > set_count) AS run_gt_set_rows,
  COUNTIF(win_count > run_count) AS win_gt_run_rows,
  SUM(IF(set_count > lead_count, set_count - lead_count, 0)) AS excess_sets,
  SUM(IF(run_count > set_count, run_count - set_count, 0)) AS excess_runs,
  SUM(IF(win_count > run_count, win_count - run_count, 0)) AS excess_wins
FROM `lumina-lakehouse.analytics_rpt.rpt_marketing_lead_cohort_performance`
WHERE cohort_period_grain = 'MONTH';

-- 6. Spend duplicates and multi-entry handling.
SELECT
  COUNT(*) AS spend_rows,
  COUNT(DISTINCT marketing_spend_sk) AS distinct_spend_keys,
  COUNTIF(marketing_spend_sk IS NULL) AS null_spend_keys,
  COUNTIF(is_same_campaign_date_territory_multi_entry) AS multi_entry_rows,
  SUM(IF(is_same_campaign_date_territory_multi_entry, spend_amount, 0)) AS multi_entry_spend,
  COUNTIF(spend_amount < 0) AS negative_spend_rows,
  SUM(IF(spend_amount < 0, spend_amount, 0)) AS negative_spend
FROM `lumina-lakehouse.analytics_fact.fact_marketing_spend`;

-- 7. Jan-Jul dashboard cohort totals used for workbook reconciliation.
SELECT
  campaign_reporting_rollup_name AS campaign_rollup,
  SUM(lead_count) AS leads,
  SUM(set_count) AS sets,
  SUM(run_count) AS runs,
  SUM(win_count) AS wins,
  SUM(win_revenue) AS revenue,
  SUM(effective_spend_amount) AS effective_spend,
  SUM(allocated_spend_amount) AS recorded_spend
FROM `lumina-lakehouse.marketing_tool_ops.rpt_marketing_funnel_analysis_runtime`
WHERE cohort_period_grain = 'MONTH'
  AND cohort_period_start_date BETWEEN DATE '2026-01-01' AND DATE '2026-07-31'
  AND campaign_reporting_rollup_name IN (
    '3rd Party Vendors LSR',
    'Internal Marketing LSR',
    'Pay Per Install LSR',
    'Co-op'
  )
GROUP BY campaign_rollup
ORDER BY campaign_rollup;
