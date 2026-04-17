/**
 * MetricEntry — one row in the Navigator metrics dock, with baseline strip.
 *
 * If baselineValue + baselineDeltaPct are supplied, renders a small strip
 * below the value: "within 3% of 24h baseline" (emerald when near), or
 * "+45% vs 24h baseline" (amber/red at distance). Otherwise renders just
 * the name+value pair.
 */
export interface MetricEntryProps {
  name: string;
  value: number | string;
  baselineValue?: number;
  baselineDeltaPct?: number;
}

function baselineLine(delta: number): { text: string; tone: string } {
  const abs = Math.abs(delta);
  if (abs < 3) {
    return {
      text: `within ${abs.toFixed(1)}% of 24h baseline`,
      tone: 'text-wr-emerald',
    };
  }
  if (abs < 15) {
    return {
      text: `${delta >= 0 ? '+' : ''}${delta.toFixed(1)}% vs 24h baseline`,
      tone: 'text-wr-emerald',
    };
  }
  if (abs < 50) {
    return {
      text: `${delta >= 0 ? '+' : ''}${delta.toFixed(1)}% vs 24h baseline`,
      tone: 'text-wr-amber',
    };
  }
  return {
    text: `${delta >= 0 ? '+' : ''}${delta.toFixed(1)}% vs 24h baseline`,
    tone: 'text-wr-red',
  };
}

export function MetricEntry({
  name,
  value,
  baselineValue,
  baselineDeltaPct,
}: MetricEntryProps) {
  const hasBaseline =
    baselineValue !== undefined && baselineDeltaPct !== undefined;
  return (
    <div
      data-testid={`metric-entry-${name}`}
      className="flex flex-col gap-0.5 py-1 border-b border-wr-border/20 last:border-0"
    >
      <div className="flex items-center justify-between">
        <span className="text-body-xs text-slate-400 uppercase tracking-wider font-mono">
          {name}
        </span>
        <span className="text-xs text-slate-200 font-mono">{value}</span>
      </div>
      {hasBaseline && (
        <div
          data-testid={`baseline-strip-${name}`}
          className={`text-[10px] font-mono ${baselineLine(baselineDeltaPct!).tone}`}
        >
          {baselineLine(baselineDeltaPct!).text}
        </div>
      )}
    </div>
  );
}
