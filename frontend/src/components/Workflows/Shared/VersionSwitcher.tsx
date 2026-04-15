import type { VersionSummary } from '../../../types';

interface Props {
  versions: VersionSummary[];
  activeVersion?: number;
  selectedVersion?: number;
  baseVersion?: number;
  onSelect: (version: number) => void;
  onFork: (version: number) => void;
  disabled?: boolean;
}

function formatCreatedAt(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  } catch {
    return iso;
  }
}

export function VersionSwitcher({
  versions,
  activeVersion,
  selectedVersion,
  baseVersion,
  onSelect,
  onFork,
  disabled,
}: Props) {
  if (versions.length === 0) {
    return (
      <div className="text-sm text-wr-text-muted" role="status">
        No versions yet
      </div>
    );
  }

  const sorted = [...versions].sort((a, b) => b.version - a.version);

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <select
          aria-label="Workflow version"
          className="rounded-md border border-wr-border bg-wr-surface px-2 py-1 text-sm text-wr-text focus:outline focus:outline-2 focus:outline-wr-accent"
          value={selectedVersion ?? sorted[0].version}
          onChange={(e) => onSelect(Number(e.target.value))}
        >
          {sorted.map((v) => {
            const isActive = v.version === activeVersion;
            const label = `v${v.version} · ${formatCreatedAt(v.created_at)}${
              isActive ? ' · Active' : ''
            }`;
            return (
              <option key={v.version_id} value={v.version}>
                {label}
              </option>
            );
          })}
        </select>
        <button
          type="button"
          disabled={disabled}
          onClick={() => selectedVersion !== undefined && onSelect(selectedVersion)}
          className="rounded-md border border-wr-border bg-wr-surface px-3 py-1 text-sm text-wr-text hover:bg-wr-elevated disabled:cursor-not-allowed disabled:opacity-50"
        >
          View
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() => selectedVersion !== undefined && onFork(selectedVersion)}
          className="rounded-md border border-wr-border bg-wr-accent px-3 py-1 text-sm text-wr-on-accent hover:bg-wr-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
        >
          Edit
        </button>
      </div>
      {baseVersion !== undefined && (
        <div className="text-xs text-wr-text-muted">
          Editing new version (based on v{baseVersion})
        </div>
      )}
    </div>
  );
}

export default VersionSwitcher;
