import { useState } from 'react';

/**
 * LineageDrawer — shows the provenance of a single evidence pin.
 *
 * Design choice: rather than retrofitting ``TelescopeDrawerV2`` (which is
 * context-driven and wired to live cluster state) with a polymorphic
 * ``mode`` prop, we ship a sibling drawer component scoped to the pin-
 * lineage use-case from Task 4.18. Both drawers can coexist; callers
 * pick whichever matches their intent.
 */
export interface LineagePayload {
  tool_name: string;
  query: string;
  query_timestamp: string;
  raw_value: string;
}

export interface LineageDrawerProps {
  open: boolean;
  payload: LineagePayload | null;
  onClose: () => void;
  rerun?: (payload: LineagePayload) => Promise<{ raw_value: string }>;
}

export function LineageDrawer({
  open,
  payload,
  onClose,
  rerun,
}: LineageDrawerProps) {
  const [latest, setLatest] = useState<string | null>(null);
  const [rerunning, setRerunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open || !payload) return null;

  const handleRerun = async () => {
    if (!rerun) return;
    setRerunning(true);
    setError(null);
    try {
      const res = await rerun(payload);
      setLatest(res.raw_value);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to re-run.');
    } finally {
      setRerunning(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-label="lineage"
      className="fixed right-0 top-0 bottom-0 w-[450px] z-[100] bg-[#0a1a1f] border-l border-wr-border-strong/50 shadow-2xl flex flex-col"
    >
      <div className="flex items-center justify-between px-4 py-3 border-b border-wr-border/50">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-wr-amber" aria-hidden />
          <span className="text-body-xs font-bold text-slate-300 tracking-wider uppercase">
            Lineage
          </span>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded hover:bg-wr-surface transition-colors"
          aria-label="close lineage drawer"
        >
          <span className="material-symbols-outlined text-slate-400 text-[18px]">
            close
          </span>
        </button>
      </div>

      <div className="flex-1 overflow-auto p-4 text-sm space-y-3">
        <table className="w-full text-body-xs">
          <tbody className="divide-y divide-wr-border/30">
            <tr>
              <th className="text-left py-1.5 pr-3 text-slate-400 uppercase tracking-wider font-mono">
                Tool
              </th>
              <td className="py-1.5 font-mono text-slate-200">{payload.tool_name}</td>
            </tr>
            <tr>
              <th className="text-left py-1.5 pr-3 text-slate-400 uppercase tracking-wider font-mono">
                Query
              </th>
              <td className="py-1.5 font-mono text-slate-200 break-all">
                {payload.query}
              </td>
            </tr>
            <tr>
              <th className="text-left py-1.5 pr-3 text-slate-400 uppercase tracking-wider font-mono">
                At
              </th>
              <td className="py-1.5 font-mono text-slate-200">
                {payload.query_timestamp}
              </td>
            </tr>
            <tr>
              <th className="text-left py-1.5 pr-3 text-slate-400 uppercase tracking-wider font-mono">
                Raw
              </th>
              <td className="py-1.5 font-mono text-slate-200 break-all">
                {latest === null
                  ? payload.raw_value
                  : (
                    <>
                      <div>Latest: {latest}</div>
                      <div className="text-slate-500 text-xs mt-1">
                        Original: {payload.raw_value}
                      </div>
                    </>
                  )}
              </td>
            </tr>
          </tbody>
        </table>

        {rerun && (
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleRerun}
              disabled={rerunning}
              className="px-3 py-1 rounded border border-wr-amber/60 bg-wr-amber/10 text-wr-amber text-xs disabled:opacity-40"
            >
              {rerunning ? 'Re-running…' : 'Re-run query'}
            </button>
            <span className="text-xs text-slate-500">
              Counts against the investigation budget.
            </span>
          </div>
        )}
        {error && (
          <div className="text-xs text-wr-red" role="alert">
            {error}
          </div>
        )}
      </div>
    </div>
  );
}
