import type { DeliveryItem, DeliveryKind } from '../../types';

export interface DeliveryFilterState {
  kinds: Set<DeliveryKind>;
  statuses: Set<string>;
  search: string;
}

interface DeliveryFiltersProps {
  value: DeliveryFilterState;
  onChange: (next: DeliveryFilterState) => void;
}

const KIND_OPTIONS: DeliveryKind[] = ['commit', 'build', 'sync'];
const STATUS_OPTIONS: string[] = ['success', 'failed', 'in_progress', 'healthy', 'degraded'];

const CHIP_BASE =
  'px-2 py-1 rounded-full text-body-xs uppercase border transition-colors';
const CHIP_INACTIVE = 'border-zinc-700 text-zinc-400 hover:text-zinc-200';
const CHIP_ACTIVE = 'border-cyan-400 text-cyan-200 bg-cyan-500/10';

export function matchesDeliveryFilter(
  item: DeliveryItem,
  f: DeliveryFilterState,
): boolean {
  if (f.kinds.size > 0 && !f.kinds.has(item.kind)) return false;
  if (f.statuses.size > 0 && !f.statuses.has(item.status)) return false;
  const term = f.search.trim().toLowerCase();
  if (term !== '') {
    const title = item.title.toLowerCase();
    const repo = (item.git_repo ?? '').toLowerCase();
    if (!title.includes(term) && !repo.includes(term)) return false;
  }
  return true;
}

export default function DeliveryFilters({ value, onChange }: DeliveryFiltersProps) {
  const toggleKind = (k: DeliveryKind) => {
    const next = new Set(value.kinds);
    if (next.has(k)) next.delete(k);
    else next.add(k);
    onChange({ ...value, kinds: next });
  };

  const toggleStatus = (s: string) => {
    const next = new Set(value.statuses);
    if (next.has(s)) next.delete(s);
    else next.add(s);
    onChange({ ...value, statuses: next });
  };

  const hasActive =
    value.kinds.size > 0 || value.statuses.size > 0 || value.search.trim() !== '';

  const clear = () =>
    onChange({ kinds: new Set(), statuses: new Set(), search: '' });

  return (
    <div className="flex flex-wrap items-center gap-2 px-3 py-2 border-b border-zinc-800 bg-zinc-950/50">
      {KIND_OPTIONS.map((k) => {
        const active = value.kinds.has(k);
        return (
          <button
            key={k}
            type="button"
            onClick={() => toggleKind(k)}
            className={`${CHIP_BASE} ${active ? CHIP_ACTIVE : CHIP_INACTIVE}`}
          >
            {k}
          </button>
        );
      })}
      {STATUS_OPTIONS.map((s) => {
        const active = value.statuses.has(s);
        return (
          <button
            key={s}
            type="button"
            onClick={() => toggleStatus(s)}
            className={`${CHIP_BASE} ${active ? CHIP_ACTIVE : CHIP_INACTIVE}`}
          >
            {s}
          </button>
        );
      })}
      <input
        type="text"
        placeholder="Search title or repo…"
        value={value.search}
        onChange={(e) => onChange({ ...value, search: e.target.value })}
        className="ml-auto px-2 py-1 text-xs rounded bg-zinc-900 border border-zinc-700 text-zinc-100 placeholder:text-zinc-500 focus:outline-none focus:border-cyan-400 w-64"
      />
      {hasActive && (
        <button
          type="button"
          onClick={clear}
          className="text-xs text-zinc-500 hover:text-zinc-300"
        >
          Clear
        </button>
      )}
    </div>
  );
}
