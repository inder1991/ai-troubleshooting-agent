ALTER TABLE workflows ADD COLUMN deleted_at TEXT;

CREATE INDEX IF NOT EXISTS idx_workflow_runs_status_created
  ON workflow_runs(status, started_at);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_created
  ON workflow_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_workflows_deleted
  ON workflows(deleted_at);
