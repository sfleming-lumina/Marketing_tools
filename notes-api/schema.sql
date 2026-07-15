CREATE SCHEMA IF NOT EXISTS `lumina-lakehouse.marketing_tool_ops`
OPTIONS (location = 'US');

CREATE TABLE IF NOT EXISTS `lumina-lakehouse.marketing_tool_ops.dashboard_notes` (
  note_id STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  author_name STRING NOT NULL,
  view STRING NOT NULL,
  element_key STRING NOT NULL,
  element_label STRING NOT NULL,
  target_type STRING NOT NULL,
  feedback_type STRING NOT NULL,
  note_text STRING NOT NULL,
  context STRING
)
PARTITION BY DATE(created_at);
