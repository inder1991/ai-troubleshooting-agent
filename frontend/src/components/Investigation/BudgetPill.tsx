/**
 * BudgetPill — compact budget telemetry for the Investigator header.
 *
 * Two segments: tool-call ratio and LLM-USD ratio. Color is driven by the
 * worse of the two axes so a single overshoot is obvious.
 * - < 80%  neutral
 * - 80-99% wr-amber
 * - ≥ 100% wr-red
 */
export interface BudgetPillProps {
  toolCalls: { used: number; max: number } | null;
  llmUsd: { used: number; max: number } | null;
}

function ratio(used: number, max: number): number {
  if (max <= 0) return 0;
  return used / max;
}

function toneFor(r: number): 'neutral' | 'amber' | 'red' {
  if (r >= 1.0) return 'red';
  if (r >= 0.8) return 'amber';
  return 'neutral';
}

const TONE_CLASS: Record<'neutral' | 'amber' | 'red', string> = {
  neutral: 'border-wr-border/60 text-wr-text bg-wr-bg/40',
  amber: 'border-wr-amber/60 text-wr-amber bg-wr-amber/10',
  red: 'border-wr-red/60 text-wr-red bg-wr-red/10',
};

export function BudgetPill({ toolCalls, llmUsd }: BudgetPillProps) {
  if (!toolCalls && !llmUsd) return null;

  const tcRatio = toolCalls ? ratio(toolCalls.used, toolCalls.max) : 0;
  const usdRatio = llmUsd ? ratio(llmUsd.used, llmUsd.max) : 0;
  const worst = Math.max(tcRatio, usdRatio);
  const tone = toneFor(worst);

  return (
    <span
      data-testid="budget-pill"
      className={`inline-flex items-center gap-2 rounded-full border px-2.5 py-0.5 text-xs font-mono ${TONE_CLASS[tone]}`}
      title="Tool calls / LLM spend for this investigation"
    >
      {toolCalls && (
        <span>
          {toolCalls.used}/{toolCalls.max} calls
        </span>
      )}
      {toolCalls && llmUsd && <span className="opacity-50">·</span>}
      {llmUsd && (
        <span>
          ${llmUsd.used.toFixed(2)} / ${llmUsd.max.toFixed(2)}
        </span>
      )}
    </span>
  );
}
