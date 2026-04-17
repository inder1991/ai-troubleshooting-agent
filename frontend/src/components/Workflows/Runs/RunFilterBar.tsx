const ALL_STATUSES = [
  { value: 'success', label: 'Success', activeClass: 'bg-emerald-600 text-white' },
  { value: 'failed', label: 'Failed', activeClass: 'bg-red-600 text-white' },
  { value: 'running', label: 'Running', activeClass: 'bg-amber-600 text-white' },
  { value: 'pending', label: 'Pending', activeClass: 'bg-neutral-600 text-white' },
  { value: 'cancelled', label: 'Cancelled', activeClass: 'bg-slate-600 text-white' },
] as const;

interface RunFilterBarProps {
  statuses: string[];
  onStatusToggle: (status: string) => void;
  sortBy: 'started_at' | 'duration';
  sortOrder: 'asc' | 'desc';
  onSortChange: (sort: 'started_at' | 'duration', order: 'asc' | 'desc') => void;
  fromDate: string;
  toDate: string;
  onDateChange: (from: string, to: string) => void;
}

export function RunFilterBar({
  statuses, onStatusToggle, sortBy, sortOrder, onSortChange,
  fromDate, toDate, onDateChange,
}: RunFilterBarProps) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="flex flex-wrap gap-1.5">
        {ALL_STATUSES.map((s) => {
          const active = statuses.includes(s.value);
          return (
            <button key={s.value} type="button" onClick={() => onStatusToggle(s.value)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                active ? s.activeClass : 'bg-wr-surface text-wr-text-muted border border-wr-border hover:bg-wr-elevated'
              }`}>
              {s.label}
            </button>
          );
        })}
      </div>
      <div className="flex items-center gap-2">
        <label htmlFor="run-from" className="text-xs text-wr-text-muted">From</label>
        <input
          id="run-from"
          type="date"
          aria-label="From date"
          value={fromDate}
          onChange={(e) => onDateChange(e.target.value, toDate)}
          className="rounded-md border border-wr-border bg-wr-bg px-2 py-1 text-xs text-wr-text"
        />
        <label htmlFor="run-to" className="text-xs text-wr-text-muted">To</label>
        <input
          id="run-to"
          type="date"
          aria-label="To date"
          value={toDate}
          onChange={(e) => onDateChange(fromDate, e.target.value)}
          className="rounded-md border border-wr-border bg-wr-bg px-2 py-1 text-xs text-wr-text"
        />
      </div>
      <div className="ml-auto flex items-center gap-2">
        <label htmlFor="run-sort" className="text-xs text-wr-text-muted">Sort</label>
        <select id="run-sort" aria-label="Sort"
          value={`${sortBy}-${sortOrder}`}
          onChange={(e) => {
            const [sort, order] = e.target.value.split('-') as ['started_at' | 'duration', 'asc' | 'desc'];
            onSortChange(sort, order);
          }}
          className="rounded-md border border-wr-border bg-wr-bg px-2 py-1 text-xs text-wr-text">
          <option value="started_at-desc">Newest first</option>
          <option value="started_at-asc">Oldest first</option>
        </select>
      </div>
    </div>
  );
}
