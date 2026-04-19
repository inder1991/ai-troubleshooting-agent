import { create } from 'zustand';

/**
 * pinStore — shared source of truth for pinned evidence cards.
 *
 * Today the EvidenceFindings column pins items via local state AND
 * renders the card twice (once inline, once in AssemblyWorkbench).
 * That duplicates content and lets the two renderings drift out of
 * sync (click expand on the pin, inline version stays collapsed).
 *
 * This store centralises the pinned set + metadata so:
 *   · The inline slot can render a PinnedGhost placeholder while the
 *     full card renders exclusively in AssemblyWorkbench.
 *   · Clicking the ghost scrolls up to the pinned full card.
 *   · Unpinning from either surface syncs both.
 *
 * The store is small on purpose — pinned IDs + a tiny metadata
 * record for labels. Card content is still derived from findings
 * props; we never duplicate the payload.
 */

export interface PinnedItem {
  /** Stable section ID — e.g. 'root-cause', 'metrics', 'cascading'. */
  id: string;
  /** Human-readable label for ghost / hover preview. */
  label: string;
  /** Agent single-letter code for color bar. */
  agentCode: string;
}

interface PinStoreState {
  pinned: Map<string, PinnedItem>;
  isPinned: (id: string) => boolean;
  pin: (item: PinnedItem) => void;
  unpin: (id: string) => void;
  toggle: (item: PinnedItem) => void;
  clear: () => void;
  count: () => number;
  items: () => PinnedItem[];
}

export const usePinStore = create<PinStoreState>((set, get) => ({
  pinned: new Map<string, PinnedItem>(),

  isPinned: (id) => get().pinned.has(id),

  pin: (item) =>
    set((state) => {
      if (state.pinned.has(item.id)) return state;
      const next = new Map(state.pinned);
      next.set(item.id, item);
      return { pinned: next };
    }),

  unpin: (id) =>
    set((state) => {
      if (!state.pinned.has(id)) return state;
      const next = new Map(state.pinned);
      next.delete(id);
      return { pinned: next };
    }),

  toggle: (item) =>
    set((state) => {
      const next = new Map(state.pinned);
      if (next.has(item.id)) {
        next.delete(item.id);
      } else {
        next.set(item.id, item);
      }
      return { pinned: next };
    }),

  clear: () => set({ pinned: new Map() }),

  count: () => get().pinned.size,

  items: () => Array.from(get().pinned.values()),
}));
