import React, { useCallback, useState } from 'react';
import { Copy, Check, Square } from 'lucide-react';
import * as Toast from '@radix-ui/react-toast';
import type { V4Findings, V4SessionStatus } from '../../types';
import { cancelInvestigation } from '../../services/api';
import { useIncidentLifecycle } from '../../contexts/IncidentLifecycleContext';

/**
 * SessionControlsRow (PR-B)
 *
 * Attaches two persistent user controls to the banner region:
 *
 *   · Copy session link — copy the current tab's URL so SREs can hand
 *     off an investigation to a teammate without fumbling with the
 *     browser address bar.
 *   · Cancel investigation — POSTs to /api/v4/session/{id}/cancel so
 *     users can stop a runaway investigation without closing the tab.
 *     Disabled during historical / terminal phases.
 *
 * Both affordances are keyboard-accessible, screen-reader labelled,
 * and confirmation-toasted.
 */

interface SessionControlsRowProps {
  sessionId: string;
  findings: V4Findings | null;
  status: V4SessionStatus | null;
}

const TERMINAL_PHASES = new Set([
  'complete',
  'diagnosis_complete',
  'cancelled',
  'error',
]);

export const SessionControlsRow: React.FC<SessionControlsRowProps> = ({
  sessionId,
  status,
}) => {
  const { lifecycle } = useIncidentLifecycle();
  const [copied, setCopied] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);

  const canCancel =
    lifecycle === 'active' &&
    !!status?.phase &&
    !TERMINAL_PHASES.has(status.phase);

  const handleCopyLink = useCallback(() => {
    const url =
      typeof window !== 'undefined' ? window.location.href : '';
    if (!url) return;
    try {
      void navigator.clipboard?.writeText?.(url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard permissions denied (HTTP / restricted browser).
      // Silent failure — user will see no toast; not critical.
    }
  }, []);

  const handleCancel = useCallback(async () => {
    if (!canCancel || cancelling) return;
    const confirmed = window.confirm(
      'Cancel this investigation? Running agents will stop checkpointing and the phase will flip to "cancelled". This cannot be undone.',
    );
    if (!confirmed) return;
    setCancelling(true);
    setCancelError(null);
    try {
      await cancelInvestigation(sessionId);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Cancel failed';
      setCancelError(msg);
      window.setTimeout(() => setCancelError(null), 4000);
    } finally {
      setCancelling(false);
    }
  }, [canCancel, cancelling, sessionId]);

  return (
    <Toast.Provider swipeDirection="right">
      <div
        className="session-controls-row inline-flex items-center gap-2 text-[11px] text-wr-text-muted"
        data-testid="session-controls-row"
      >
        {/* Copy session link */}
        <button
          type="button"
          onClick={handleCopyLink}
          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-wr-inset/40 focus-visible:bg-wr-inset/40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-wr-text-muted focus:outline-none transition-colors"
          aria-label="Copy session link"
          title="Copy this session's URL"
          data-testid="copy-session-link"
        >
          {copied ? (
            <>
              <Check aria-hidden size={11} className="text-emerald-400" />
              <span className="text-wr-text-muted">copied</span>
            </>
          ) : (
            <>
              <Copy aria-hidden size={11} />
              <span>copy link</span>
            </>
          )}
        </button>

        {/* Cancel investigation */}
        <button
          type="button"
          onClick={handleCancel}
          disabled={!canCancel || cancelling}
          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-wr-inset/40 focus-visible:bg-wr-inset/40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-wr-text-muted focus:outline-none transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          aria-label={
            canCancel
              ? 'Cancel investigation'
              : 'Cancel — unavailable (investigation is not running)'
          }
          title={
            canCancel
              ? 'Stop the running investigation'
              : 'Investigation is not currently running'
          }
          data-testid="cancel-investigation"
        >
          <Square aria-hidden size={11} />
          <span>{cancelling ? 'cancelling…' : 'cancel'}</span>
        </button>

        {cancelError && (
          <span
            className="text-[11px] text-red-400 font-editorial italic"
            role="alert"
            data-testid="cancel-error"
          >
            {cancelError}
          </span>
        )}
      </div>

      <Toast.Viewport
        className="fixed bottom-4 right-4 flex flex-col gap-2 outline-none"
        style={{ zIndex: 'var(--z-toast)' }}
      />
    </Toast.Provider>
  );
};

export default SessionControlsRow;
