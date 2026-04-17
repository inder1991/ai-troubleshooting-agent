/**
 * CausalForestView — repurposed in Phase 4 Task 4.21 as the typed-edge
 * legend for ServiceTopologySVG. The old "causal forest" rendering was
 * unused dead code; the file survives as a legend so imports don't
 * churn and the Navigator panel keeps its existing layout hook.
 */

interface LegendRow {
  type: 'causes' | 'precedes' | 'correlates' | 'contradicts' | 'supports';
  label: string;
  stroke: string;
  dasharray: string;
  description: string;
}

const ROWS: LegendRow[] = [
  {
    type: 'causes',
    label: 'causes',
    stroke: 'var(--wr-red)',
    dasharray: '',
    description: 'Certified cause→effect (solid red)',
  },
  {
    type: 'precedes',
    label: 'precedes',
    stroke: 'var(--wr-amber)',
    dasharray: '6,3',
    description: 'Temporal precedence only (amber dashed)',
  },
  {
    type: 'correlates',
    label: 'correlates',
    stroke: '#94a3b8',
    dasharray: '2,3',
    description: 'Observed together (gray dotted)',
  },
  {
    type: 'contradicts',
    label: 'contradicts',
    stroke: 'var(--wr-red)',
    dasharray: '2,3',
    description: 'Contradicted by evidence (red dotted)',
  },
  {
    type: 'supports',
    label: 'supports',
    stroke: 'var(--wr-emerald)',
    dasharray: '2,3',
    description: 'Consistent with (emerald dotted)',
  },
];

export default function CausalForestView() {
  return (
    <div
      data-testid="topology-edge-legend"
      className="border border-wr-border/40 bg-wr-bg/40 rounded-md p-3 text-xs"
    >
      <div className="uppercase tracking-wider text-body-xs font-bold text-slate-400 mb-2">
        Edge types
      </div>
      <ul className="space-y-1.5">
        {ROWS.map((row) => (
          <li
            key={row.type}
            className="flex items-center gap-3"
            data-testid={`legend-${row.type}`}
          >
            <svg width="40" height="10" aria-hidden>
              <line
                x1="0"
                y1="5"
                x2="40"
                y2="5"
                stroke={row.stroke}
                strokeWidth={2}
                strokeDasharray={row.dasharray || undefined}
              />
            </svg>
            <span className="font-mono text-slate-200 min-w-[90px]">{row.label}</span>
            <span className="text-slate-400 truncate">{row.description}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
