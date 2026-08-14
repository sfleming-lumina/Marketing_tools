BEGIN
  DECLARE existing_object_type STRING DEFAULT (
    SELECT table_type
    FROM `lumina-lakehouse.marketing_tool_ops.INFORMATION_SCHEMA.TABLES`
    WHERE table_name = 'rpt_marketing_buyer_journey_runtime'
  );

  IF existing_object_type = 'VIEW' THEN
    DROP VIEW `lumina-lakehouse.marketing_tool_ops.rpt_marketing_buyer_journey_runtime`;
  END IF;
END;

CREATE OR REPLACE TABLE
  `lumina-lakehouse.marketing_tool_ops.rpt_marketing_buyer_journey_runtime`
OPTIONS (
  description = 'PII-free materialized marketing buyer-journey event durations for governed dashboard percentile analysis. Materialized so the runtime service account does not require analytics_dim access.'
)
AS

SELECT
  COALESCE(source.official_reporting_campaign_sf_id, source.campaign_sf_id) AS campaign_sf_id,
  COALESCE(hierarchy.campaign_name, source.official_reporting_campaign_name, source.campaign_name) AS campaign_name,
  hierarchy.campaign_reporting_rollup_name,
  hierarchy.campaign_sub_rollup_name,
  source.resolved_county,
  source.resolved_state,
  source.resolved_ops_region,
  source.final_reporting_jurisdiction_label AS reporting_market_label,
  source.resolved_county AS reporting_market_county,
  source.resolved_state AS reporting_market_state,
  source.final_reporting_jurisdiction_label,
  source.campaign_member_created_date,
  source.campaign_member_created_week_start_date,
  source.campaign_member_created_month_start_date,
  CASE
    WHEN UPPER(TRIM(resolved_state)) IN ('MD', 'MARYLAND') THEN 'MD'
    WHEN UPPER(TRIM(resolved_state)) IN ('VA', 'VIRGINIA') THEN 'VA'
    WHEN UPPER(TRIM(resolved_state)) IN ('DC', 'D.C.', 'DISTRICT OF COLUMBIA', 'WASHINGTON DC', 'WASHINGTON, DC') THEN 'DC'
    WHEN UPPER(TRIM(resolved_state)) IN ('PA', 'PENNSYLVANIA') THEN 'PA'
    WHEN UPPER(TRIM(resolved_state)) IN ('DE', 'DELAWARE') THEN 'DE'
    WHEN NULLIF(TRIM(resolved_state), '') IS NULL THEN NULL
    ELSE UPPER(TRIM(resolved_state))
  END AS normalized_operating_state,
  CASE
    WHEN UPPER(TRIM(resolved_ops_region)) IN ('MD', 'MARYLAND', 'MD OPS', 'MD OPS REGION', 'MD/DC/VA') THEN 'MD'
    WHEN UPPER(TRIM(resolved_ops_region)) IN ('PA', 'PENNSYLVANIA', 'PA OPS', 'PA OPS REGION', 'PA/DE') THEN 'PA'
    WHEN NULLIF(TRIM(resolved_ops_region), '') IS NULL
      AND UPPER(TRIM(resolved_state)) IN ('MD', 'MARYLAND', 'VA', 'VIRGINIA', 'DC', 'D.C.', 'DISTRICT OF COLUMBIA', 'WASHINGTON DC', 'WASHINGTON, DC') THEN 'MD'
    WHEN NULLIF(TRIM(resolved_ops_region), '') IS NULL
      AND UPPER(TRIM(resolved_state)) IN ('PA', 'PENNSYLVANIA', 'DE', 'DELAWARE') THEN 'PA'
    ELSE NULL
  END AS normalized_ops_region,
  CASE
    WHEN UPPER(TRIM(resolved_ops_region)) IN ('MD', 'MARYLAND', 'MD OPS', 'MD OPS REGION', 'MD/DC/VA') THEN 'Maryland'
    WHEN UPPER(TRIM(resolved_ops_region)) IN ('PA', 'PENNSYLVANIA', 'PA OPS', 'PA OPS REGION', 'PA/DE') THEN 'Pennsylvania'
    WHEN NULLIF(TRIM(resolved_ops_region), '') IS NULL
      AND UPPER(TRIM(resolved_state)) IN ('MD', 'MARYLAND', 'VA', 'VIRGINIA', 'DC', 'D.C.', 'DISTRICT OF COLUMBIA', 'WASHINGTON DC', 'WASHINGTON, DC') THEN 'Maryland'
    WHEN NULLIF(TRIM(resolved_ops_region), '') IS NULL
      AND UPPER(TRIM(resolved_state)) IN ('PA', 'PENNSYLVANIA', 'DE', 'DELAWARE') THEN 'Pennsylvania'
    WHEN NULLIF(TRIM(resolved_ops_region), '') IS NULL AND NULLIF(TRIM(resolved_state), '') IS NULL THEN 'Unresolved'
    ELSE 'Outside operating footprint'
  END AS operating_region_group,
  IF(source.has_invalid_funnel_date_sequence, NULL, source.lead_to_set_days_clean) AS lead_to_set_days,
  IF(source.has_invalid_funnel_date_sequence, NULL, source.set_to_run_days_clean) AS set_to_run_days,
  IF(source.has_invalid_funnel_date_sequence, NULL, source.run_to_win_days_clean) AS run_to_win_days,
  IF(source.has_invalid_funnel_date_sequence, NULL, source.lead_to_win_days_clean) AS lead_to_win_days,
  source.has_invalid_funnel_date_sequence,
  source.win_count
FROM `lumina-lakehouse.marketing_tool_ops.fact_lead_funnel_attributed_clean` AS source
LEFT JOIN `lumina-lakehouse.analytics_dim.dim_campaign_reporting_hierarchy` AS hierarchy
  ON hierarchy.campaign_sf_id = COALESCE(source.official_reporting_campaign_sf_id, source.campaign_sf_id)
WHERE source.campaign_member_created_date IS NOT NULL
  AND COALESCE(hierarchy.campaign_name, source.official_reporting_campaign_name, source.campaign_name) IS NOT NULL;
