-- Read-only workbook-to-lakehouse validation.

-- Candidate campaign-member date definitions compared with workbook lead totals.
WITH member_base AS (
  SELECT
    cm.id AS campaign_member_id,
    COALESCE(cm.lead_id, cm.contact_id, cm.lead_or_contact_id) AS related_record_id,
    cm.campaign_id,
    ch.campaign_reporting_rollup_name AS campaign_rollup,
    DATE(cm.created_date) AS created_date,
    DATE(cm.last_modified_date) AS last_modified_date,
    DATE(cm.first_responded_date) AS first_responded_date,
    DATE(cm.campaign_member_created_date_c) AS formula_created_date,
    DATE(cm.related_record_created_date_c) AS related_record_created_date,
    cm.most_recent_c,
    cm.is_deleted,
    cm._fivetran_deleted
  FROM `lumina-lakehouse.salesforce.campaign_member` cm
  LEFT JOIN `lumina-lakehouse.analytics_dim.dim_campaign_reporting_hierarchy` ch
    ON cm.campaign_id = ch.campaign_sf_id
)
SELECT
  date_definition,
  campaign_rollup,
  COUNT(*) AS leads
FROM member_base
UNPIVOT (
  activity_date FOR date_definition IN (
    created_date,
    last_modified_date,
    first_responded_date,
    formula_created_date,
    related_record_created_date
  )
)
WHERE activity_date BETWEEN DATE '2026-01-01' AND DATE '2026-07-14'
  AND campaign_rollup IN (
    '3rd Party Vendors LSR',
    'Internal Marketing LSR',
    'Pay Per Install LSR',
    'Co-op'
  )
  AND COALESCE(is_deleted, FALSE) = FALSE
  AND COALESCE(_fivetran_deleted, FALSE) = FALSE
GROUP BY 1, 2
ORDER BY date_definition, campaign_rollup;

-- Event-date outcomes aligned to the workbook's Set, SV, and Close month fields.
SELECT
  campaign_rollup,
  SUM(IF(set_anchor_date BETWEEN DATE '2026-01-01' AND DATE '2026-07-13', official_set_count, 0)) AS sets,
  SUM(IF(run_anchor_date BETWEEN DATE '2026-01-01' AND DATE '2026-07-13', official_run_count, 0)) AS runs,
  SUM(IF(official_win_date BETWEEN DATE '2026-01-01' AND DATE '2026-07-14', official_win_count, 0)) AS wins,
  SUM(IF(official_win_date BETWEEN DATE '2026-01-01' AND DATE '2026-07-14', official_win_revenue, 0)) AS revenue
FROM (
  SELECT
    COALESCE(ch.campaign_reporting_rollup_name, flfa.official_reporting_campaign_name, 'Unclassified Campaign') AS campaign_rollup,
    flfa.set_anchor_date,
    flfa.run_anchor_date,
    flfa.official_win_date,
    flfa.official_set_count,
    flfa.official_run_count,
    flfa.official_win_count,
    SAFE_CAST(flfa.official_win_revenue AS FLOAT64) AS official_win_revenue
  FROM `lumina-lakehouse.analytics_fact.fact_lead_funnel_attributed` flfa
  LEFT JOIN `lumina-lakehouse.analytics_dim.dim_campaign_reporting_hierarchy` ch
    ON flfa.official_reporting_campaign_sf_id = ch.campaign_sf_id
  WHERE NOT REGEXP_CONTAINS(
    LOWER(CONCAT(
      COALESCE(flfa.campaign_name, ''), ' ',
      COALESCE(flfa.parent_campaign_name, ''), ' ',
      COALESCE(flfa.grandparent_campaign_name, ''), ' ',
      COALESCE(flfa.official_reporting_campaign_name, ''), ' ',
      COALESCE(flfa.touchpoint_campaign_name, ''), ' ',
      COALESCE(flfa.sf_opp_name, ''), ' ',
      COALESCE(flfa.lead_source_name, ''), ' ',
      COALESCE(flfa.lead_utm_campaign, ''), ' ',
      COALESCE(flfa.opportunity_utm_campaign, '')
    )),
    r'(^|[^a-z])(test|testing|demo|sample|training|dummy|fake|sandbox|do not use|qa)([^a-z]|$)'
  )
)
WHERE campaign_rollup IN (
  '3rd Party Vendors LSR',
  'Internal Marketing LSR',
  'Pay Per Install LSR',
  'Co-op'
)
GROUP BY campaign_rollup
ORDER BY campaign_rollup;

-- Spend parity with the workbook's raw campaign-spend export.
SELECT
  ch.campaign_reporting_rollup_name AS campaign_rollup,
  SUM(SAFE_CAST(fms.spend_amount AS FLOAT64)) AS spend
FROM `lumina-lakehouse.analytics_fact.fact_marketing_spend` fms
LEFT JOIN `lumina-lakehouse.analytics_dim.dim_campaign_reporting_hierarchy` ch
  ON fms.campaign_sf_id = ch.campaign_sf_id
WHERE fms.spend_date BETWEEN DATE '2026-01-01' AND DATE '2026-06-10'
  AND ch.campaign_reporting_rollup_name IN (
    '3rd Party Vendors LSR',
    'Internal Marketing LSR',
    'Pay Per Install LSR',
    'Co-op'
  )
GROUP BY campaign_rollup
ORDER BY campaign_rollup;
