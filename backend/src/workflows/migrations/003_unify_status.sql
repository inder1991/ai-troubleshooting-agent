UPDATE workflow_runs SET status = 'success' WHERE status = 'succeeded';
UPDATE workflow_step_runs SET status = 'success' WHERE status = 'succeeded';
