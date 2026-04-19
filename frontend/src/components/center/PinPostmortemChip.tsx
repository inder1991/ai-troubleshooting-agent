import React from 'react';
import * as HoverCard from '@radix-ui/react-hover-card';
import type { V4Findings } from '../../types';
import { useIncidentLifecycle } from '../../contexts/IncidentLifecycleContext';

/**
 * PinPostmortemChip — center-panel addition #6 (the user's #6)
 *
 * Surfaces the pin → postmortem flow so users know their pins feed
 * the incident dossier draft. Rendered above the evidence column's
 * anchor bar (inside StickyStack); also visible as a small chip in
 * the banner freshness area (composed by the freshness consumer).
 *
 * Behavior:
 *   · Always-on when findings.evidence_pins.length > 0
 *   · HoverCard preview of pinned items + dossier link
 *   · Click "view dossier draft" → onOpenDossier callback
 *   · Hidden when lifecycle === 'historical' (pinning new items
 *     post-close isn't allowed; read the published postmortem instead)
 */

interface PinPostmortemChipProps {
  findings: V4Findings | null;
  onOpenDossier?: () => void;
}

interface PinPreview {
  id: string;
  label: string;
}

function pinPreviews(findings: V4Findings | null): PinPreview[] {
  const pins = findings?.evidence_pins ?? [];
  return pins.map((p, i) => {
    // EvidencePinV2 has a variety of shapes — fall back through common
    // fields so we always show something readable.
    const rec = p as unknown as Record<string, unknown>;
    const label =
      (rec.label as string) ??
      (rec.title as string) ??
      (rec.summary as string) ??
      (rec.kind as string) ??
      `pin ${i + 1}`;
    const id = (rec.id as string) ?? (rec.pin_id as string) ?? String(i);
    return { id, label };
  });
}

export const PinPostmortemChip: React.FC<PinPostmortemChipProps> = ({
  findings,
  onOpenDossier,
}) => {
  const { lifecycle } = useIncidentLifecycle();
  const previews = pinPreviews(findings);
  const count = previews.length;

  if (count === 0) return null;
  if (lifecycle === 'historical') return null;

  return (
    <HoverCard.Root openDelay={200} closeDelay={200}>
      <HoverCard.Trigger asChild>
        <button
          type="button"
          onClick={onOpenDossier}
          className="pin-postmortem-chip inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border border-wr-border text-[11px] text-wr-text-muted hover:text-wr-paper hover:border-wr-border-strong focus-visible:outline focus-visible:outline-1 focus-visible:outline-wr-text-muted transition-colors"
          data-testid="pin-postmortem-chip"
          aria-label={`${count} pinned — open dossier draft`}
        >
          <span aria-hidden>📌</span>
          <span>{count} pinned</span>
          <span
            className="text-wr-text-subtle"
            aria-hidden
          >
            ·
          </span>
          <span className="font-editorial italic">view dossier draft</span>
        </button>
      </HoverCard.Trigger>
      <HoverCard.Portal>
        <HoverCard.Content
          side="bottom"
          align="end"
          sideOffset={6}
          className="pin-postmortem-preview bg-wr-bg border border-wr-border rounded-sm p-3 max-w-[360px]"
          style={{ zIndex: 'var(--z-tooltip)' }}
          data-testid="pin-postmortem-preview"
        >
          <p className="text-[11px] uppercase tracking-[0.12em] text-wr-text-muted mb-1.5">
            will appear in the dossier
          </p>
          <ul className="space-y-1 text-[12px] text-wr-paper">
            {previews.slice(0, 6).map((p) => (
              <li key={p.id} className="leading-[1.35]">
                <span className="text-wr-text-subtle mr-1.5">·</span>
                {p.label}
              </li>
            ))}
            {previews.length > 6 && (
              <li className="text-wr-text-subtle italic">
                + {previews.length - 6} more
              </li>
            )}
          </ul>
          <HoverCard.Arrow className="fill-wr-border" />
        </HoverCard.Content>
      </HoverCard.Portal>
    </HoverCard.Root>
  );
};

export default PinPostmortemChip;
