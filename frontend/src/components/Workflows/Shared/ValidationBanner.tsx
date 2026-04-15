import { useState } from 'react';

export type ValidationError = {
  path: string;
  message: string;
  stepId?: string;
  severity?: 'error' | 'warning';
};

interface Props {
  errors: ValidationError[];
  onJump?: (stepId: string) => void;
  title?: string;
}

export function ValidationBanner({ errors, onJump, title }: Props) {
  const [expanded, setExpanded] = useState(false);

  if (errors.length === 0) return null;

  const errorCount = errors.filter((e) => (e.severity ?? 'error') === 'error').length;
  const warnCount = errors.filter((e) => e.severity === 'warning').length;

  // Accent: red if any error, otherwise amber.
  const hasError = errorCount > 0;
  const accentClass = hasError
    ? 'border-wr-status-error text-wr-status-error'
    : 'border-wr-status-warning text-wr-status-warning';

  const summaryParts: string[] = [];
  if (errorCount > 0) summaryParts.push(`${errorCount} ${errorCount === 1 ? 'error' : 'errors'}`);
  if (warnCount > 0) summaryParts.push(`${warnCount} ${warnCount === 1 ? 'warning' : 'warnings'}`);
  const summary = summaryParts.join(' · ');

  return (
    <div
      role="alert"
      className={`w-full rounded-md border bg-wr-surface px-4 py-3 ${accentClass}`}
    >
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between text-left text-sm font-medium"
      >
        <span>
          {title ?? 'Validation issues'}: {summary}
        </span>
        <span className="ml-4 text-xs text-wr-text-muted">
          {expanded ? 'Hide details' : 'Show details'}
        </span>
      </button>
      {expanded && (
        <ul className="mt-3 space-y-2 border-t border-wr-border pt-3">
          {errors.map((e, i) => {
            const sev = e.severity ?? 'error';
            const dotClass =
              sev === 'warning' ? 'bg-wr-status-warning' : 'bg-wr-status-error';
            return (
              <li
                key={`${e.path}-${i}`}
                className="flex items-start gap-3 text-sm text-wr-text"
              >
                <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${dotClass}`} />
                <div className="flex-1 min-w-0">
                  <div className="font-mono text-xs text-wr-text-muted break-all">
                    {e.path}
                  </div>
                  <div>{e.message}</div>
                </div>
                {e.stepId && onJump && (
                  <button
                    type="button"
                    onClick={() => onJump(e.stepId!)}
                    className="shrink-0 text-xs text-wr-accent hover:underline"
                  >
                    Jump to step
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export default ValidationBanner;
