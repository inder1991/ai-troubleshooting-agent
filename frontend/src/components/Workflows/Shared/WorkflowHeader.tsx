import type { WorkflowDetail, VersionSummary } from '../../../types';
import { VersionSwitcher } from './VersionSwitcher';

// TODO(phase4): add inline rename once backend exposes PATCH /api/v4/workflows/{id}.
// As of Phase 3 backend (routes_workflows.py) no rename endpoint exists, so
// name is rendered read-only here.

interface Props {
  workflow: WorkflowDetail;
  versions: VersionSummary[];
  activeVersion?: number;
  selectedVersion?: number;
  baseVersion?: number;
  canSave: boolean;
  onSelectVersion: (v: number) => void;
  onForkVersion: (v: number) => void;
  onSave: () => void;
  onRun: () => void;
  saving?: boolean;
}

export function WorkflowHeader({
  workflow,
  versions,
  activeVersion,
  selectedVersion,
  baseVersion,
  canSave,
  onSelectVersion,
  onForkVersion,
  onSave,
  onRun,
  saving,
}: Props) {
  const saveDisabled = !canSave || !!saving;

  return (
    <header className="flex flex-col gap-3 border-b border-wr-border bg-wr-bg px-6 py-4">
      <div>
        <h1 className="text-xl font-display font-semibold text-wr-text">
          {workflow.name}
        </h1>
        {workflow.description && (
          <p className="mt-1 text-sm text-wr-text-muted">{workflow.description}</p>
        )}
      </div>
      <div className="flex items-center justify-between gap-4">
        <VersionSwitcher
          versions={versions}
          activeVersion={activeVersion}
          selectedVersion={selectedVersion}
          baseVersion={baseVersion}
          onSelect={onSelectVersion}
          onFork={onForkVersion}
        />
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onSave}
            disabled={saveDisabled}
            className="inline-flex items-center gap-2 rounded-md border border-wr-border bg-wr-surface px-3 py-1.5 text-sm text-wr-text hover:bg-wr-elevated disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving && (
              <span
                data-testid="save-spinner"
                aria-hidden="true"
                className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-wr-border border-t-wr-accent"
              />
            )}
            Save as new version
          </button>
          <button
            type="button"
            onClick={onRun}
            className="rounded-md border border-wr-border bg-wr-accent px-3 py-1.5 text-sm text-wr-on-accent hover:bg-wr-accent-hover"
          >
            Run
          </button>
        </div>
      </div>
    </header>
  );
}

export default WorkflowHeader;
