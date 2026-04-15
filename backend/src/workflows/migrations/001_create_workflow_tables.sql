CREATE TABLE IF NOT EXISTS workflows (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  description TEXT,
  created_at TEXT NOT NULL,
  created_by TEXT
);

CREATE TABLE IF NOT EXISTS workflow_versions (
  id TEXT PRIMARY KEY,
  workflow_id TEXT NOT NULL REFERENCES workflows(id),
  version INTEGER NOT NULL,
  dag_json TEXT NOT NULL,
  compiled_json TEXT NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  UNIQUE(workflow_id, version)
);

CREATE TABLE IF NOT EXISTS workflow_runs (
  id TEXT PRIMARY KEY,
  workflow_version_id TEXT NOT NULL REFERENCES workflow_versions(id),
  status TEXT NOT NULL,
  started_at TEXT,
  ended_at TEXT,
  inputs_json TEXT NOT NULL,
  error_json TEXT,
  idempotency_key TEXT,
  run_mode TEXT NOT NULL DEFAULT 'workflow',
  UNIQUE(workflow_version_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS workflow_step_runs (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES workflow_runs(id),
  step_id TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TEXT,
  ended_at TEXT,
  inputs_json TEXT,
  output_json TEXT,
  attempt INTEGER NOT NULL DEFAULT 1,
  duration_ms INTEGER,
  error_json TEXT
);

CREATE TABLE IF NOT EXISTS workflow_run_events (
  event_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES workflow_runs(id),
  sequence INTEGER NOT NULL,
  timestamp TEXT NOT NULL,
  type TEXT NOT NULL,
  node_id TEXT,
  attempt INTEGER,
  duration_ms INTEGER,
  error_class TEXT,
  error_message TEXT,
  parent_node_id TEXT,
  payload_json TEXT,
  UNIQUE(run_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_version ON workflow_runs(workflow_version_id);
CREATE INDEX IF NOT EXISTS idx_workflow_step_runs_run ON workflow_step_runs(run_id);
CREATE INDEX IF NOT EXISTS idx_workflow_run_events_run_seq ON workflow_run_events(run_id, sequence);
