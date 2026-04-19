import React from 'react';
import * as HoverCard from '@radix-ui/react-hover-card';
import type { SignatureMatch } from '../../types';

/**
 * SignatureMatchPill (PR-E)
 *
 * Renders a small editorial pill on the banner when the supervisor's
 * signature library matched a known failure shape. The backend has
 * been computing `state.signature_match` for weeks (Stage H of the
 * run_v5 orchestration swap) but the UI never rendered it, so the
 * matched pattern and its remediation pointer were invisible to
 * operators.
 *
 * Voice: lowercase, editorial-serif, one short clause that terminates
 * in the pattern name. Hover reveals the full summary + remediation
 * hint so the pill doesn't compete with the verdict for attention.
 */

interface Props {
  match: SignatureMatch | null | undefined;
}

function formatConfidence(c: number): string {
  // Backend emits 0..1; render as percentage (rounded) to match the
  // rest of the banner's confidence vocabulary.
  const pct = Math.round(Math.max(0, Math.min(1, c)) * 100);
  return `${pct}%`;
}

const SignatureMatchPill: React.FC<Props> = ({ match }) => {
  if (!match || !match.pattern_name) return null;

  return (
    <HoverCard.Root openDelay={200} closeDelay={150}>
      <HoverCard.Trigger asChild>
        <span
          className="signature-match-pill inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border border-wr-border text-[11px] text-wr-text-muted hover:text-wr-paper hover:border-wr-border-strong transition-colors cursor-help"
          data-testid="signature-match-pill"
          tabIndex={0}
          role="status"
          aria-label={`Known pattern matched: ${match.pattern_name} (${formatConfidence(match.confidence)} confidence)`}
        >
          <span aria-hidden>🔖</span>
          <span className="font-editorial italic">known pattern ·</span>
          <span className="font-mono tabular-nums">{match.pattern_name}</span>
          <span className="text-wr-text-subtle tabular-nums" aria-hidden>
            {formatConfidence(match.confidence)}
          </span>
        </span>
      </HoverCard.Trigger>
      <HoverCard.Portal>
        <HoverCard.Content
          side="bottom"
          align="start"
          sideOffset={6}
          className="signature-match-popover bg-wr-bg border border-wr-border rounded-sm p-3 max-w-[360px] text-[12px] text-wr-paper"
          style={{ zIndex: 'var(--z-tooltip)' }}
          data-testid="signature-match-popover"
        >
          <p className="text-[11px] uppercase tracking-[0.12em] text-wr-text-muted mb-1.5">
            signature match · {formatConfidence(match.confidence)} confidence
          </p>
          {match.summary && (
            <p className="mb-2 leading-[1.4]">{match.summary}</p>
          )}
          {match.remediation && (
            <p className="font-editorial italic text-wr-text-muted leading-[1.4]">
              {match.remediation}
            </p>
          )}
          {!match.summary && !match.remediation && (
            <p className="font-editorial italic text-wr-text-muted">
              Matched pattern in the signature library. No additional detail
              was published with this match.
            </p>
          )}
          <HoverCard.Arrow className="fill-wr-border" />
        </HoverCard.Content>
      </HoverCard.Portal>
    </HoverCard.Root>
  );
};

export default SignatureMatchPill;
