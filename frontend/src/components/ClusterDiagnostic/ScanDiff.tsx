import React from 'react';

interface ScanDiffProps {
  delta?: {
    new_risks: string[];
    resolved_risks: string[];
    worsened: string[];
    improved: string[];
    previous_scan_id?: string;
    previous_scanned_at?: string;
  };
}

const ScanDiff: React.FC<ScanDiffProps> = ({ delta }) => {
  if (!delta) return null;

  const { new_risks, resolved_risks, worsened, improved } = delta;
  const hasChanges = new_risks.length + resolved_risks.length + worsened.length + improved.length > 0;

  if (!hasChanges) {
    return (
      <div className="bg-wr-inset rounded border border-wr-border-subtle p-3">
        <span className="text-body-xs font-semibold uppercase tracking-wider text-slate-500">Scan Delta</span>
        <p className="text-xs text-slate-500 mt-2">No changes since previous scan</p>
      </div>
    );
  }

  return (
    <div className="bg-wr-inset rounded border border-wr-border-subtle p-3 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-body-xs font-semibold uppercase tracking-wider text-slate-500">Scan Delta</span>
        {delta.previous_scanned_at && (
          <span className="text-body-xs text-slate-600">vs {delta.previous_scanned_at}</span>
        )}
      </div>

      {new_risks.length > 0 && (
        <div>
          <span className="text-body-xs font-semibold text-red-400 uppercase">New Risks ({new_risks.length})</span>
          {new_risks.map((r, i) => (
            <div key={i} className="text-body-xs text-red-300 pl-2 py-0.5 border-l-2 border-red-500/30 mt-1">{r}</div>
          ))}
        </div>
      )}

      {resolved_risks.length > 0 && (
        <div>
          <span className="text-body-xs font-semibold text-emerald-400 uppercase">Resolved ({resolved_risks.length})</span>
          {resolved_risks.map((r, i) => (
            <div key={i} className="text-body-xs text-emerald-300 pl-2 py-0.5 border-l-2 border-emerald-500/30 mt-1 line-through opacity-60">{r}</div>
          ))}
        </div>
      )}

      {worsened.length > 0 && (
        <div>
          <span className="text-body-xs font-semibold text-amber-400 uppercase">Worsened ({worsened.length})</span>
          {worsened.map((r, i) => (
            <div key={i} className="text-body-xs text-amber-300 pl-2 py-0.5 border-l-2 border-amber-500/30 mt-1">{r}</div>
          ))}
        </div>
      )}

      {improved.length > 0 && (
        <div>
          <span className="text-body-xs font-semibold text-blue-400 uppercase">Improved ({improved.length})</span>
          {improved.map((r, i) => (
            <div key={i} className="text-body-xs text-blue-300 pl-2 py-0.5 border-l-2 border-blue-500/30 mt-1">{r}</div>
          ))}
        </div>
      )}
    </div>
  );
};

export default ScanDiff;
