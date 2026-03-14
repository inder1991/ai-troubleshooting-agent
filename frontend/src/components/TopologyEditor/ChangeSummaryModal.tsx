import type { DesignDiff } from '../../types';

interface ChangeSummaryModalProps {
  diff: DesignDiff;
  designName: string;
  onConfirm: () => void;
  onCancel: () => void;
  applying: boolean;
}

export default function ChangeSummaryModal({
  diff,
  designName,
  onConfirm,
  onCancel,
  applying,
}: ChangeSummaryModalProps) {
  const hasConflicts = diff.conflicts.length > 0;
  const hasEdgeErrors = diff.edge_errors.length > 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div
        className="rounded-xl border shadow-2xl w-full max-w-2xl max-h-[80vh] overflow-y-auto"
        style={{ background: '#1a1814', borderColor: 'rgba(224,159,62,0.2)' }}
      >
        {/* Header */}
        <div className="flex items-center gap-2 px-6 py-4 border-b" style={{ borderColor: 'rgba(224,159,62,0.1)' }}>
          <span className="material-symbols-outlined text-amber-400" style={{ fontSize: 20 }}>difference</span>
          <h2 className="text-lg font-semibold text-white">Change Summary — {designName}</h2>
        </div>

        <div className="px-6 py-4 space-y-4">
          {/* Conflicts */}
          {hasConflicts && (
            <section>
              <div className="flex items-center gap-2 mb-2">
                <span className="material-symbols-outlined text-red-400" style={{ fontSize: 16 }}>error</span>
                <h3 className="text-sm font-semibold text-red-400">Conflicts ({diff.conflicts.length})</h3>
              </div>
              <div className="rounded-lg p-3 space-y-1.5" style={{ background: 'rgba(239,68,68,0.08)' }}>
                {diff.conflicts.map((c, i) => (
                  <div key={i} className="text-xs text-red-300 flex items-start gap-2">
                    <span className="material-symbols-outlined mt-0.5" style={{ fontSize: 12 }}>warning</span>
                    <span>
                      {c.type === 'ip_conflict' && `IP ${c.ip} on "${c.planned_device}" conflicts with "${c.conflicts_with}"`}
                      {c.type === 'hostname_conflict' && `Name "${c.planned_device}" already exists in live inventory`}
                      {c.type === 'id_conflict' && `ID "${c.planned_device}" conflicts with "${c.conflicts_with}"`}
                      {c.type === 'subnet_overlap' && `Subnet ${c.planned_subnet} overlaps with "${c.conflicts_with}"`}
                      {c.type === 'vlan_conflict' && `VLAN ${c.vlan_id} in zone "${c.zone}" conflicts with "${c.conflicts_with}"`}
                    </span>
                  </div>
                ))}
              </div>
              <div className="mt-2 px-3 py-1.5 rounded text-xs text-red-300 font-medium" style={{ background: 'rgba(239,68,68,0.12)' }}>
                Resolve all conflicts before applying
              </div>
            </section>
          )}

          {/* Edge Errors */}
          {hasEdgeErrors && (
            <section>
              <div className="flex items-center gap-2 mb-2">
                <span className="material-symbols-outlined text-amber-400" style={{ fontSize: 16 }}>link_off</span>
                <h3 className="text-sm font-semibold text-amber-400">Edge Errors ({diff.edge_errors.length})</h3>
              </div>
              <div className="rounded-lg p-3 space-y-1.5" style={{ background: 'rgba(245,158,11,0.08)' }}>
                {diff.edge_errors.map((e, i) => (
                  <div key={i} className="text-xs text-amber-300 flex items-start gap-2">
                    <span className="material-symbols-outlined mt-0.5" style={{ fontSize: 12 }}>warning</span>
                    <span>Edge {e.edge_id}: {e.reason}</span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* New Devices */}
          {diff.added.length > 0 && (
            <section>
              <div className="flex items-center gap-2 mb-2">
                <span className="material-symbols-outlined text-green-400" style={{ fontSize: 16 }}>add_circle</span>
                <h3 className="text-sm font-semibold text-green-400">New Devices ({diff.added.length})</h3>
              </div>
              <div className="rounded-lg overflow-hidden" style={{ background: 'rgba(34,197,94,0.06)' }}>
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-green-400/70">
                      <th className="px-3 py-1.5">Name</th>
                      <th className="px-3 py-1.5">Type</th>
                      <th className="px-3 py-1.5">IP</th>
                      <th className="px-3 py-1.5">Vendor</th>
                    </tr>
                  </thead>
                  <tbody>
                    {diff.added.map((n: any, i: number) => (
                      <tr key={i} className="border-t" style={{ borderColor: 'rgba(34,197,94,0.1)' }}>
                        <td className="px-3 py-1.5 text-green-200">{n.data?.label || n.id}</td>
                        <td className="px-3 py-1.5 text-green-300/60">{n.data?.deviceType || '—'}</td>
                        <td className="px-3 py-1.5 text-green-300/60 font-mono">{n.data?.ip || '—'}</td>
                        <td className="px-3 py-1.5 text-green-300/60">{n.data?.vendor || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {/* New Connections */}
          {diff.new_edges.length > 0 && (
            <section>
              <div className="flex items-center gap-2 mb-2">
                <span className="material-symbols-outlined text-blue-400" style={{ fontSize: 16 }}>cable</span>
                <h3 className="text-sm font-semibold text-blue-400">New Connections ({diff.new_edges.length})</h3>
              </div>
              <div className="rounded-lg overflow-hidden" style={{ background: 'rgba(59,130,246,0.06)' }}>
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-blue-400/70">
                      <th className="px-3 py-1.5">Source</th>
                      <th className="px-3 py-1.5">Target</th>
                      <th className="px-3 py-1.5">Type</th>
                    </tr>
                  </thead>
                  <tbody>
                    {diff.new_edges.map((e: any, i: number) => (
                      <tr key={i} className="border-t" style={{ borderColor: 'rgba(59,130,246,0.1)' }}>
                        <td className="px-3 py-1.5 text-blue-200">{e.source}</td>
                        <td className="px-3 py-1.5 text-blue-200">{e.target}</td>
                        <td className="px-3 py-1.5 text-blue-300/60">{e.data?.label || 'connected_to'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {/* Existing Infrastructure */}
          <section className="flex items-center gap-2 px-3 py-2 rounded-lg" style={{ background: 'rgba(100,116,139,0.08)' }}>
            <span className="material-symbols-outlined text-gray-500" style={{ fontSize: 16 }}>dns</span>
            <span className="text-xs text-gray-400">{diff.live_count} live devices remain unchanged</span>
          </section>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t" style={{ borderColor: 'rgba(224,159,62,0.1)' }}>
          <button
            onClick={onCancel}
            className="px-4 py-2 rounded-lg text-sm text-gray-400 hover:text-white transition-colors"
            style={{ background: 'rgba(100,116,139,0.15)' }}
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={!diff.can_apply || applying}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all"
            style={{
              background: diff.can_apply && !applying ? 'rgba(34,197,94,0.2)' : 'rgba(100,116,139,0.1)',
              color: diff.can_apply && !applying ? '#4ade80' : '#475569',
              cursor: diff.can_apply && !applying ? 'pointer' : 'not-allowed',
            }}
          >
            {applying ? (
              <>
                <span className="material-symbols-outlined animate-spin" style={{ fontSize: 16 }}>progress_activity</span>
                Applying...
              </>
            ) : (
              <>
                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>rocket_launch</span>
                Apply Changes
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
