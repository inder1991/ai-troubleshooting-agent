import React, { RefObject } from 'react';
import * as Dialog from '@radix-ui/react-dialog';

/**
 * PaneDrawer (PR 1 of the War Room grid-shell migration)
 *
 * Wrapper around Radix Dialog that mounts a drawer INSIDE a caller-
 * provided container (typically a specific column's grid region)
 * rather than floating above the whole viewport. Two invariants it
 * guarantees:
 *
 *   1. Background columns stay interactive — `modal={false}` plus a
 *      refined `onInteractOutside` that only closes the drawer on
 *      clicks inside its owning region, never on clicks in other
 *      columns.
 *   2. The drawer can never grow wider than its owning region — the
 *      caller passes a `maxWidth` CSS value (typically `100cqi` of
 *      the region, or a `min()` expression capped at 640px).
 *
 * Also wires up Esc-to-close + focus-trap + focus-return via Radix —
 * standard Dialog behavior, but constrained so keyboard flows don't
 * leak into other columns.
 *
 * Consumers:
 *   PR 3 adopts this for ChatDrawer, TelescopeDrawerV2, SurgicalTelescope.
 *   PR 1 ships it dormant; it's unused until PR 3 wires it in.
 */

interface PaneDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /**
   * Ref to the element the drawer should mount inside. Typically a
   * column region's DOM node. If the ref is null, the drawer falls
   * back to rendering in `document.body` (development ergonomics —
   * production should always provide a mount target).
   */
  mountInto?: RefObject<HTMLElement | null>;
  /**
   * Maximum inline-size (CSS value). Typically `100cqi` for chat or
   * `min(640px, 100cqi - 24px)` for telescopes. The drawer will never
   * grow past this, so it can't cover columns it doesn't own.
   */
  maxInlineSize: string;
  /**
   * Which edge the drawer slides from. Defaults to 'right' since most
   * War Room drawers are right-edge.
   */
  side?: 'right' | 'left' | 'bottom';
  /**
   * Accessible dialog title. Not rendered visually by default — use a
   * visible heading inside `children` if you want one shown.
   */
  title: string;
  /**
   * Optional description for screen readers.
   */
  description?: string;
  className?: string;
  children: React.ReactNode;
}

export function PaneDrawer({
  open,
  onOpenChange,
  mountInto,
  maxInlineSize,
  side = 'right',
  title,
  description,
  className = '',
  children,
}: PaneDrawerProps) {
  // If the mount target isn't available yet (first render, hydration),
  // fall through to the default portal so the drawer still renders
  // cleanly. In practice this shouldn't happen because consumers pass
  // stable refs created with useRef.
  const container =
    mountInto && mountInto.current ? mountInto.current : undefined;

  const sideClasses =
    side === 'right'
      ? 'right-0 top-0 bottom-0 translate-x-full data-[state=open]:translate-x-0'
      : side === 'left'
      ? 'left-0 top-0 bottom-0 -translate-x-full data-[state=open]:translate-x-0'
      : 'left-0 right-0 bottom-0 translate-y-full data-[state=open]:translate-y-0';

  const containerScope = container ?? undefined;

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange} modal={false}>
      <Dialog.Portal container={containerScope}>
        <Dialog.Content
          className={`pane-drawer absolute ${sideClasses} bg-wr-bg border-l border-wr-border shadow-2xl transition-transform duration-200 ease-[cubic-bezier(0.16,1,0.3,1)] motion-reduce:transition-none ${className}`}
          style={{
            maxInlineSize,
            inlineSize: maxInlineSize,
            zIndex: 'var(--z-drawer)',
          }}
          onInteractOutside={(e) => {
            // Only close on clicks inside the owning container. Clicks
            // in other columns are completely ignored — they don't close
            // and they don't break focus.
            if (!container) return;
            const target = e.target as Node | null;
            if (target && !container.contains(target)) {
              e.preventDefault();
            }
          }}
          aria-describedby={description ? 'pane-drawer-description' : undefined}
        >
          <Dialog.Title className="sr-only">{title}</Dialog.Title>
          {description && (
            <Dialog.Description id="pane-drawer-description" className="sr-only">
              {description}
            </Dialog.Description>
          )}
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export default PaneDrawer;
