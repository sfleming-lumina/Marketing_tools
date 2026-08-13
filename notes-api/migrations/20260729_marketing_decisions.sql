CREATE TABLE IF NOT EXISTS `lumina-lakehouse.marketing_tool_ops.marketing_decisions` (
  decision_id STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  created_by_email STRING NOT NULL,
  created_by_name STRING NOT NULL,
  decision_type STRING NOT NULL,
  question STRING NOT NULL,
  action STRING NOT NULL,
  status STRING NOT NULL,
  source_view STRING NOT NULL,
  campaign STRING,
  campaign_rollup STRING,
  ahj STRING,
  decision_market STRING,
  operating_region STRING,
  months INT64 NOT NULL,
  temporal_window STRING,
  primary_metric STRING NOT NULL,
  review_after DATE NOT NULL,
  baseline STRING NOT NULL,
  scenario STRING NOT NULL,
  expected STRING NOT NULL,
  evidence STRING NOT NULL,
  data_confidence STRING NOT NULL
)
PARTITION BY DATE(created_at)
CLUSTER BY status, operating_region, campaign, ahj;

ALTER TABLE `lumina-lakehouse.marketing_tool_ops.marketing_decisions`
ADD COLUMN IF NOT EXISTS decision_market STRING;
