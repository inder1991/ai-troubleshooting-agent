import React, { useMemo } from 'react';
import type { V4Findings, V4SessionStatus, TaskEvent, AttestationGateData } from '../../types';
import { scheduleSignals, Signal } from './signalScheduler';
import BannerRow from './BannerRow';
import FreshnessRow from './FreshnessRow';
import { useIncidentLifecycle } from '../../contexts/IncidentLifecycleContext';
import { useAppControl } from '../../contexts/AppControlContext';

/**
 * BannerRegion — owns the War Room banner grid area (.wr-region-banner).
 *
 * Assembles:
 *   · BannerRow (conditional, Mode 3) — highest-severity signal + Popover for the rest
 *   · FreshnessRow (always-on) — status + tokens + cost + phase narrative
 *
 * Drives the data-banner-mode attribute on the grid shell so the CSS
 * grid-row transition animates the region's height change when signals
 * appear/disappear. Pure CSS transition — no JS height measurement,
 * no layout jank.
 */

interface BannerRegionProps {
  findings: V4Findings | null;
  status: V4SessionStatus | null;
  events: TaskEvent[];
  lastFetchAgoSec: number;
  wsConnected: boolean;
  fetchFailCount: number;
  fetchErrorDismissed: boolean;
  attestationGate?: AttestationGateData | null;
  /** Fired when the user clicks the banner's action button. */
  onBannerAction?: (signal: Signal) => void;
  /** Fired when the user clicks the Retry button on a fetch-fail banner. */
  onRetryFetch?: () => void;
}

export const BannerRegion: React.FC<BannerRegionProps> = ({
  findings,
  status,
  events,
  lastFetchAgoSec,
  wsConnected,
  fetchFailCount,
  fetchErrorDismissed,
  attestationGate,
  onBannerAction,
  onRetryFetch,
}) => {
  const { lifecycle } = useIncidentLifecycle();
  const { isManualOverride } = useAppControl();

  const schedule = useMemo(
    () =>
      scheduleSignals({
        fetchFailCount,
        fetchErrorDismissed,
        wsConnected,
        phase: status?.phase ?? null,
        attestationGate: attestationGate
          ? { title: attestationGate.proposed_action ?? undefined }
          : null,
        budget: status?.budget ?? null,
        isHistorical: lifecycle === 'historical',
      }),
    [
      fetchFailCount,
      fetchErrorDismissed,
      wsConnected,
      status?.phase,
      attestationGate,
      status?.budget,
      lifecycle,
    ],
  );

  // Publish banner-mode on the grid shell so the CSS grid-row
  // transition animates the height change.
  React.useEffect(() => {
    const grid = document.querySelector('.warroom-grid') as HTMLElement | null;
    if (!grid) return;
    grid.setAttribute(
      'data-banner-mode',
      schedule.top ? 'action' : 'healthy',
    );
    return () => {
      grid.removeAttribute('data-banner-mode');
    };
  }, [schedule.top]);

  const handleAction = (signal: Signal) => {
    if (signal.kind === 'fetch-fail' && onRetryFetch) {
      onRetryFetch();
      return;
    }
    onBannerAction?.(signal);
  };

  // Historical + manual-override = banner scheduler generally returns
  // nothing; freshness row still renders with lifecycle-aware copy.
  const _ = isManualOverride; // reserved for future: suppress some signals when overriden

  return (
    <div className="wr-region-banner" data-testid="banner-region">
      <BannerRow schedule={schedule} onAction={handleAction} />
      <FreshnessRow
        findings={findings}
        status={status}
        events={events}
        lastFetchAgoSec={lastFetchAgoSec}
        wsConnected={wsConnected}
      />
    </div>
  );
};

export default BannerRegion;
