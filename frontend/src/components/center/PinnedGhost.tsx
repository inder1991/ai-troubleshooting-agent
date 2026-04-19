import React, { useCallback } from 'react';
import { usePinStore } from '../../stores/pinStore';

/**
 * PinnedGhost (PR 6)
 *
 * Renders in the inline scroll stack where a FullCard would have
 * rendered, when that section is currently pinned. Fixes the
 * content-duplication bug: pinned sections no longer render twice.
 *
 * Click jumps up to the pinned full render in AssemblyWorkbench
 * (jump-target is the element with data-pin-anchor={id}).
 * Unpin button removes it from the pin store, which re-flips the
 * inline slot back to rendering the FullCard.
 */

interface PinnedGhostProps {
  id: string;
  label: string;
  agentCode: string;
}

const AGENT_BORDER: Record<string, string> = {
  L: 'border-l-red-500',
  M: 'border-l-amber-500',
  K: 'border-l-orange-500',
  T: 'border-l-violet-500',
  N: 'border-l-blue-500',
  C: 'border-l-emerald-500',
};

export const PinnedGhost: React.FC<PinnedGhostProps> = ({ id, label, agentCode }) => {
  const unpin = usePinStore((s) => s.unpin);

  const jumpToPin = useCallback(() => {
    const el = document.querySelector(
      `[data-pin-anchor="${id}"]`,
    ) as HTMLElement | null;
    if (el) {
      const reduce =
        typeof window !== 'undefined' &&
        typeof window.matchMedia === 'function' &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      el.scrollIntoView({
        behavior: reduce ? 'auto' : 'smooth',
        block: 'start',
      });
    }
  }, [id]);

  const border = AGENT_BORDER[agentCode] ?? 'border-l-slate-500';

  return (
    <div
      className={`pinned-ghost flex items-center gap-3 border-l-2 ${border} pl-3 py-1.5 my-1 rounded-r bg-wr-bg/40`}
      data-testid={`pinned-ghost-${id}`}
    >
      <span aria-hidden className="text-[12px]">📌</span>
      <button
        type="button"
        onClick={jumpToPin}
        className="flex-1 min-w-0 text-left text-[12px] text-wr-text-muted hover:text-wr-paper focus-visible:text-wr-paper focus:outline-none transition-colors truncate"
        data-testid={`pinned-ghost-jump-${id}`}
      >
        <span className="font-editorial italic">pinned above ·</span>{' '}
        <span className="truncate">{label}</span>
      </button>
      <button
        type="button"
        onClick={() => unpin(id)}
        className="shrink-0 text-[11px] text-wr-text-muted hover:text-wr-paper underline-offset-4 hover:underline focus-visible:underline focus:outline-none transition-colors"
        aria-label={`Unpin ${label}`}
        data-testid={`pinned-ghost-unpin-${id}`}
      >
        unpin
      </button>
    </div>
  );
};

export default PinnedGhost;
