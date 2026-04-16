import type { StepSpec } from '../../../types';
import type { ValidationError } from './builderTypes';
import { humanTriggerSummary } from './humanTriggerSummary';

interface Props {
  step: StepSpec;
  index: number;
  active: boolean;
  onSelect: () => void;
  errors?: ValidationError[];
}

function onFailureLabel(step: StepSpec): { icon: string; text: string } | null {
  const of = step.on_failure;
  if (!of || of === 'fail') return null;
  if (of === 'continue') return { icon: '↺', text: 'continue' };
  if (of === 'fallback') {
    const target = step.fallback_step_id ?? '?';
    return { icon: '⤳', text: `fallback:${target}` };
  }
  return null;
}

export function StepSummaryRow({
  step,
  index,
  active,
  onSelect,
  errors,
}: Props) {
  const trigger = humanTriggerSummary(step.when);
  const fail = onFailureLabel(step);
  const errCount = errors?.length ?? 0;

  const baseClasses =
    'group flex w-full items-center gap-2 rounded-md border px-2 py-2 text-left text-sm transition-colors';
  const activeClasses = active
    ? 'border-wr-accent bg-wr-accent/10 text-wr-text'
    : 'border-wr-border bg-wr-surface text-wr-text hover:bg-wr-elevated';

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={active ? 'true' : undefined}
      className={`${baseClasses} ${activeClasses}`}
    >
      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-wr-elevated text-xs font-mono text-wr-text-muted">
        {index + 1}
      </span>
      <span className="font-mono text-xs text-wr-text">{step.id}</span>
      <span className="text-xs text-wr-text-muted">
        {step.agent}@{step.agent_version}
      </span>

      {trigger && (
        <span className="truncate font-mono text-xs text-wr-text-muted">
          {trigger}
        </span>
      )}

      {fail && (
        <span
          className="ml-auto flex shrink-0 items-center gap-1 rounded border border-wr-border bg-wr-elevated px-1.5 py-0.5 text-xs text-wr-text-muted"
          aria-label={`on failure: ${fail.text}`}
        >
          <span aria-hidden="true">{fail.icon}</span>
          <span>{fail.text}</span>
        </span>
      )}

      {step.concurrency_group && (
        <span
          className={
            (fail ? '' : 'ml-auto ') +
            'shrink-0 rounded-full border border-wr-border bg-wr-elevated px-2 py-0.5 text-xs text-wr-text-muted'
          }
        >
          {step.concurrency_group}
        </span>
      )}

      {typeof step.timeout_seconds_override === 'number' && (
        <span
          className={
            (fail || step.concurrency_group ? '' : 'ml-auto ') +
            'shrink-0 rounded-full border border-wr-border bg-wr-elevated px-2 py-0.5 text-xs text-wr-text-muted'
          }
        >
          {step.timeout_seconds_override}s
        </span>
      )}

      {errCount > 0 && (
        <span
          aria-label={errCount === 1 ? '1 error' : `${errCount} errors`}
          className="shrink-0 rounded-full bg-red-500/20 px-2 py-0.5 text-xs font-medium text-red-400"
        >
          {errCount}
        </span>
      )}
    </button>
  );
}

export default StepSummaryRow;
