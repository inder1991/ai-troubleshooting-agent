import { useState } from 'react';

/**
 * CoverageGapsBanner — surfaces agents that didn't run (Task 1.14 data).
 *
 * Each entry in ``gaps`` is a pre-formatted "<agent>: <reason>" string
 * emitted by the backend's ``coverage_gaps`` field. Collapsed by default;
 * user clicks "show" to see the reasons. Renders nothing when the list
 * is empty so it takes zero visual space on healthy runs.
 */
export interface CoverageGapsBannerProps {
  gaps: string[];
}

export function CoverageGapsBanner({ gaps }: CoverageGapsBannerProps) {
  const [expanded, setExpanded] = useState(false);

  if (!gaps || gaps.length === 0) return null;

  const n = gaps.length;
  const noun = n === 1 ? 'check' : 'checks';

  return (
    <div
      data-testid="coverage-gaps-banner"
      className="w-full border border-wr-amber/40 bg-wr-amber/10 text-wr-amber px-3 py-2 rounded-md flex items-start gap-2 text-sm"
    >
      <span
        className="material-symbols-outlined text-base leading-5"
        aria-hidden
      >
        info
      </span>
      <div className="flex-1">
        <div className="flex items-center gap-2">
          <span className="font-medium">
            {n} {noun} skipped
          </span>
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="text-xs underline underline-offset-2 hover:no-underline"
            aria-expanded={expanded}
          >
            {expanded ? 'hide' : 'show'}
          </button>
        </div>
        {expanded && (
          <ul className="mt-1 list-disc list-inside space-y-0.5 text-wr-amber/90">
            {gaps.map((gap, i) => (
              <li key={i} className="font-mono text-xs">
                {gap}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
