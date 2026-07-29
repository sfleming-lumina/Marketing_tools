-- Candidate campaign-member lead definitions at the workbook cutoff.
WITH member_base AS (
  SELECT
    cm.id AS campaign_member_id,
    COALESCE(cm.lead_id, cm.contact_id, cm.lead_or_contact_id) AS related_record_id,
    ch.campaign_reporting_rollup_name AS campaign_rollup,
    DATE(cm.created_date) AS activity_date,
    cm.most_recent_c,
    cm.is_deleted,
    cm._fivetran_deleted
  FROM `lumina-lakehouse.salesforce.campaign_member` cm
  LEFT JOIN `lumina-lakehouse.analytics_dim.dim_campaign_reporting_hierarchy` ch
    ON cm.campaign_id = ch.campaign_sf_id
)
SELECT
  campaign_rollup,
  COUNT(*) AS campaign_members,
  COUNT(DISTINCT campaign_member_id) AS distinct_campaign_members,
  COUNT(DISTINCT related_record_id) AS distinct_people,
  COUNTIF(most_recent_c) AS most_recent_members,
  COUNT(DISTINCT IF(most_recent_c, related_record_id, NULL)) AS most_recent_people
FROM member_base
WHERE activity_date BETWEEN DATE '2026-01-01' AND DATE '2026-07-14'
  AND campaign_rollup IN (
    '3rd Party Vendors LSR',
    'Internal Marketing LSR',
    'Pay Per Install LSR',
    'Co-op'
  )
  AND COALESCE(is_deleted, FALSE) = FALSE
  AND COALESCE(_fivetran_deleted, FALSE) = FALSE
GROUP BY campaign_rollup
ORDER BY campaign_rollup;
