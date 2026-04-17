/**
 * InfraPills — horizontal flex of small infra-health pills for Navigator.
 *
 * Data comes from the Phase-3 K8s additions (Task 3.8 tools) — but the
 * component accepts any subset, so the Navigator can render whatever
 * data the backend currently emits.
 */
export interface NodeCondition {
  node: string;
  type: string;
  status: 'True' | 'False' | 'Unknown';
}

export interface InfraPillsProps {
  nodeConditions?: NodeCondition[];
  pvcPending?: number;
  pdbViolations?: number;
  hpaSaturated?: string[];
}

interface Pill {
  label: string;
  tone: 'neutral' | 'amber' | 'red';
  key: string;
}

function buildPills(p: InfraPillsProps): Pill[] {
  const out: Pill[] = [];
  const trueConditions = (p.nodeConditions || []).filter(
    (c) => c.status === 'True',
  );
  for (const c of trueConditions) {
    out.push({
      key: `node-${c.node}-${c.type}`,
      label: `${c.type} · ${c.node}`,
      tone: c.type.includes('Pressure') ? 'amber' : 'red',
    });
  }
  if ((p.pvcPending || 0) > 0) {
    out.push({
      key: 'pvc',
      label: `PVC pending: ${p.pvcPending}`,
      tone: 'amber',
    });
  }
  if ((p.pdbViolations || 0) > 0) {
    out.push({
      key: 'pdb',
      label: `PDB violations: ${p.pdbViolations}`,
      tone: 'red',
    });
  }
  for (const hpa of p.hpaSaturated || []) {
    out.push({
      key: `hpa-${hpa}`,
      label: `HPA saturated · ${hpa}`,
      tone: 'amber',
    });
  }
  return out;
}

const TONE: Record<Pill['tone'], string> = {
  neutral: 'border-wr-border/60 text-wr-text bg-wr-bg/40',
  amber: 'border-wr-amber/60 text-wr-amber bg-wr-amber/10',
  red: 'border-wr-red/60 text-wr-red bg-wr-red/10',
};

export function InfraPills(props: InfraPillsProps) {
  const pills = buildPills(props);
  if (pills.length === 0) return null;
  return (
    <div
      data-testid="infra-pills"
      className="flex flex-wrap items-center gap-1.5"
    >
      {pills.map((p) => (
        <span
          key={p.key}
          data-testid={`pill-${p.key}`}
          className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-mono ${TONE[p.tone]}`}
        >
          {p.label}
        </span>
      ))}
    </div>
  );
}
