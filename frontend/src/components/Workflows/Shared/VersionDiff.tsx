import type { StepSpec } from '../../../types';

interface VersionDiffProps {
  oldSteps: StepSpec[];
  newSteps: StepSpec[];
}

type DiffKind = 'added' | 'removed' | 'modified' | 'unchanged';

interface DiffEntry {
  stepId: string;
  kind: DiffKind;
  changedFields: string[];
  oldStep?: StepSpec;
  newStep?: StepSpec;
}

const COMPARE_FIELDS: (keyof StepSpec)[] = [
  'agent', 'agent_version', 'on_failure', 'timeout_seconds_override',
];

function shallowEqual(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

function computeDiff(oldSteps: StepSpec[], newSteps: StepSpec[]): DiffEntry[] {
  const oldMap = new Map(oldSteps.map((s) => [s.id, s]));
  const newMap = new Map(newSteps.map((s) => [s.id, s]));
  const allIds = new Set([...oldMap.keys(), ...newMap.keys()]);
  const entries: DiffEntry[] = [];

  for (const id of allIds) {
    const old = oldMap.get(id);
    const curr = newMap.get(id);
    if (!old && curr) {
      entries.push({ stepId: id, kind: 'added', changedFields: [], newStep: curr });
    } else if (old && !curr) {
      entries.push({ stepId: id, kind: 'removed', changedFields: [], oldStep: old });
    } else if (old && curr) {
      const changed: string[] = [];
      for (const field of COMPARE_FIELDS) {
        if (!shallowEqual(old[field], curr[field])) changed.push(field);
      }
      if (!shallowEqual(old.inputs, curr.inputs)) changed.push('inputs');
      if (!shallowEqual(old.when, curr.when)) changed.push('when');
      entries.push({
        stepId: id,
        kind: changed.length > 0 ? 'modified' : 'unchanged',
        changedFields: changed, oldStep: old, newStep: curr,
      });
    }
  }
  return entries;
}

const KIND_STYLES: Record<DiffKind, { bg: string; label: string; labelClass: string }> = {
  added: { bg: 'bg-green-900/20 border-green-700', label: 'Added', labelClass: 'text-green-400' },
  removed: { bg: 'bg-red-900/20 border-red-700', label: 'Removed', labelClass: 'text-red-400' },
  modified: { bg: 'bg-amber-900/20 border-amber-700', label: 'Modified', labelClass: 'text-amber-400' },
  unchanged: { bg: 'opacity-40 border-wr-border', label: '', labelClass: '' },
};

export function VersionDiff({ oldSteps, newSteps }: VersionDiffProps) {
  const diff = computeDiff(oldSteps, newSteps);
  if (diff.length === 0 || !diff.some((d) => d.kind !== 'unchanged')) {
    return <p className="text-sm text-wr-text-muted py-4">No changes between versions.</p>;
  }
  return (
    <div className="space-y-2">
      {diff.map((entry) => {
        const style = KIND_STYLES[entry.kind];
        return (
          <div key={entry.stepId} data-testid={`diff-row-${entry.stepId}`}
            className={`rounded-md border p-3 ${style.bg}`}>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-wr-text">{entry.stepId}</span>
              {style.label && (
                <span className={`text-xs font-semibold ${style.labelClass}`}>{style.label}</span>
              )}
            </div>
            {entry.changedFields.length > 0 && (
              <div className="mt-1 text-xs text-wr-text-muted">
                Changed: {entry.changedFields.join(', ')}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
