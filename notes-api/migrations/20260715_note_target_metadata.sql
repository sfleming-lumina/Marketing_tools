ALTER TABLE `lumina-lakehouse.marketing_tool_ops.dashboard_notes`
ADD COLUMN IF NOT EXISTS target_type STRING;

ALTER TABLE `lumina-lakehouse.marketing_tool_ops.dashboard_notes`
ADD COLUMN IF NOT EXISTS feedback_type STRING;
