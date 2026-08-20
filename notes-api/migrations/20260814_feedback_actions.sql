ALTER TABLE `lumina-lakehouse.marketing_tool_ops.dashboard_notes`
ADD COLUMN IF NOT EXISTS action_status STRING,
ADD COLUMN IF NOT EXISTS action_taken STRING,
ADD COLUMN IF NOT EXISTS actioned_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS actioned_by STRING;

UPDATE `lumina-lakehouse.marketing_tool_ops.dashboard_notes`
SET action_status = 'Open'
WHERE action_status IS NULL;
