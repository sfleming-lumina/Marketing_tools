ALTER TABLE `lumina-lakehouse.marketing_tool_ops.dashboard_notes`
ADD COLUMN IF NOT EXISTS action_status STRING;

ALTER TABLE `lumina-lakehouse.marketing_tool_ops.dashboard_notes`
ADD COLUMN IF NOT EXISTS action_taken STRING;

ALTER TABLE `lumina-lakehouse.marketing_tool_ops.dashboard_notes`
ADD COLUMN IF NOT EXISTS actioned_at TIMESTAMP;

ALTER TABLE `lumina-lakehouse.marketing_tool_ops.dashboard_notes`
ADD COLUMN IF NOT EXISTS actioned_by STRING;

UPDATE `lumina-lakehouse.marketing_tool_ops.dashboard_notes`
SET action_status = 'Open'
WHERE action_status IS NULL;
