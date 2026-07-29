-- Most recent BigQuery jobs that materialized the upstream marketing facts.
SELECT
  destination_table.table_id AS destination_table_name,
  creation_time,
  user_email,
  statement_type,
  query
FROM `region-us`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
WHERE destination_table.project_id = 'lumina-lakehouse'
  AND destination_table.dataset_id IN ('analytics_fact', 'analytics_stg', 'analytics_dim')
  AND destination_table.table_id IN (
    'fact_lead_funnel_attributed',
    'fact_marketing_cohort_member_outcome',
    'fact_marketing_spend',
    'fact_marketing_spend_allocated',
    'fact_lead_funnel',
    'stg_marketing_spend_salesforce',
    'dim_campaign',
    'dim_zip_ahj_best',
    'dim_campaign_reporting_hierarchy',
    'dim_marketing_cohort_benchmark'
  )
  AND state = 'DONE'
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY destination_table_name
  ORDER BY creation_time DESC
) = 1
ORDER BY destination_table_name;
