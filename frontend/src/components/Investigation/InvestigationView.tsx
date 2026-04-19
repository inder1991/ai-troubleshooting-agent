import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import type { V4Session, V4Findings, V4SessionStatus, ChatMessage, TaskEvent, DiagnosticPhase, TokenUsage, AttestationGateData } from '../../types';
import { getFindings, getSessionStatus, sendChatMessage } from '../../services/api';
import { useChatUI, useInvestigationContext } from '../../contexts/ChatContext';
import { useCampaignContext } from '../../contexts/CampaignContext';
import Investigator from './Investigator';
import EvidenceFindings from './EvidenceFindings';
import Navigator from './Navigator';
import RemediationProgressBar from './RemediationProgressBar';
import AttestationGateUI from '../Remediation/AttestationGateUI';
import ChatDrawer from '../Chat/ChatDrawer';
import LedgerTriggerTab from '../Chat/LedgerTriggerTab';
import SurgicalTelescope from './SurgicalTelescope';
import { TopologySelectionProvider } from '../../contexts/TopologySelectionContext';
import { TelescopeProvider } from '../../contexts/TelescopeContext';
import { IncidentLifecycleProvider } from '../../contexts/IncidentLifecycleContext';
import { AppControlProvider } from '../../contexts/AppControlContext';
import { RegionPortalsProvider, useRegionPortals } from '../../contexts/RegionPortalsContext';
import TelescopeDrawerV2 from './TelescopeDrawerV2';
import BannerRegion from '../banner/BannerRegion';

const RELEVANT_EVENT_TYPES = new Set<string>(['summary', 'finding', 'phase_change']);

interface InvestigationViewProps {
  session: V4Session;
  events: TaskEvent[];
  wsConnected: boolean;
  phase: DiagnosticPhase | null;
  confidence: number;
  tokenUsage: TokenUsage[];
  attestationGate?: AttestationGateData | null;
  onAttestationDecision?: (decision: string) => void;
  onNavigateToDossier?: () => void;
}

const InvestigationView: React.FC<InvestigationViewProps> = ({
  session,
  events,
  wsConnected,
  phase,
  confidence,
  tokenUsage,
  attestationGate,
  onAttestationDecision,
  onNavigateToDossier,
}) => {
  // ── Single source of truth for findings + status ──────────────────────
  const [findings, setFindings] = useState<V4Findings | null>(null);
  const [sessionStatus, setSessionStatus] = useState<V4SessionStatus | null>(null);
  const [fetchFailCount, setFetchFailCount] = useState(0);
  const [fetchErrorDismissed, setFetchErrorDismissed] = useState(false);
  const [lastFetchTime, setLastFetchTime] = useState<number | null>(null);
  const [lastFetchAgo, setLastFetchAgo] = useState(0);
  const agoIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Chat state now managed by ChatContext
  const { addMessage: onNewMessage, openDrawer: openChatDrawer } = useChatUI();
  const { setCampaign } = useCampaignContext();

  // Sync campaign data from findings into CampaignContext — keyed to avoid object-identity thrash
  const campaignKey = findings?.campaign
    ? `${(findings.campaign as { id?: string }).id ?? ''}:${(findings.campaign as { updated_at?: string }).updated_at ?? ''}`
    : '';
  useEffect(() => {
    if (findings?.campaign) setCampaign(findings.campaign);
  }, [campaignKey, findings?.campaign, setCampaign]);

  // Sync investigation context (namespace/service/pod) into ChatContext for QuickActionToolbar
  const { setInvestigationContext } = useInvestigationContext();
  useEffect(() => {
    const namespace = findings?.pod_statuses?.[0]?.namespace ?? null;
    const service = findings?.target_service ?? session.service_name ?? null;
    const pod = findings?.pod_statuses?.[0]?.pod_name ?? null;
    setInvestigationContext({ namespace, service, pod, cluster: null });
  }, [findings?.target_service, findings?.pod_statuses, session.service_name, setInvestigationContext]);

  // Tick "last updated X s ago" every second
  useEffect(() => {
    agoIntervalRef.current = setInterval(() => {
      if (lastFetchTime) setLastFetchAgo(Math.floor((Date.now() - lastFetchTime) / 1000));
    }, 1000);
    return () => { if (agoIntervalRef.current) clearInterval(agoIntervalRef.current); };
  }, [lastFetchTime]);

  const abortRef = useRef<AbortController | null>(null);
  const fetchSharedData = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const [f, s] = await Promise.all([
        getFindings(session.session_id, { signal: controller.signal }),
        getSessionStatus(session.session_id, { signal: controller.signal }),
      ]);
      if (controller.signal.aborted) return;
      setFindings(f);
      setSessionStatus(s);
      setFetchFailCount(0);
      setFetchErrorDismissed(false);
      setLastFetchTime(Date.now());
    } catch (err) {
      if ((err as Error)?.name === 'AbortError') return;
      setFetchFailCount((c) => c + 1);
    }
  }, [session.session_id]);
  useEffect(() => () => abortRef.current?.abort(), []);

  // Backoff poll interval — stretches from 5s to 30s after repeated failures
  const pollIntervalMs = useMemo(() => {
    if (fetchFailCount === 0) return 5000;
    return Math.min(30000, 5000 * 2 ** Math.min(fetchFailCount, 3));
  }, [fetchFailCount]);

  useEffect(() => {
    fetchSharedData();
    const interval = setInterval(fetchSharedData, pollIntervalMs);
    return () => clearInterval(interval);
  }, [fetchSharedData, pollIntervalMs]);

  // Re-fetch on relevant WebSocket events — ref-based to avoid derived recompute on every render
  const seenRelevantRef = useRef(0);
  useEffect(() => {
    let relevant = 0;
    for (const e of events) {
      if (RELEVANT_EVENT_TYPES.has(e.event_type)) relevant++;
    }
    if (relevant > seenRelevantRef.current) {
      seenRelevantRef.current = relevant;
      fetchSharedData();
    }
  }, [events, fetchSharedData]);

  // Freshness indicator color
  const freshnessColor = lastFetchAgo <= 10 ? 'bg-green-500' : lastFetchAgo <= 30 ? 'bg-amber-500' : 'bg-red-500';

  // Attach repo handler — sends "confirm" through chat.
  // PR-B: auto-open the chat drawer so the user sees the response
  // (SDET audit C2). Previously the response landed in a collapsed
  // drawer and users thought the click had no effect.
  const handleAttachRepo = useCallback(() => {
    if (!session.session_id) return;
    openChatDrawer();
    const userMsg: ChatMessage = { role: 'user', content: 'confirm', timestamp: new Date().toISOString() };
    onNewMessage(userMsg);
    sendChatMessage(session.session_id, 'confirm').then((resp) => {
      if (resp?.content) onNewMessage(resp);
    }).catch(() => {});
  }, [session.session_id, onNewMessage, openChatDrawer]);

  return (
    <AppControlProvider>
      <IncidentLifecycleProvider status={sessionStatus}>
        <RegionPortalsProvider>
          <WarRoomGrid
            session={session}
            events={events}
            wsConnected={wsConnected}
            phase={phase}
            confidence={confidence}
            tokenUsage={tokenUsage}
            attestationGate={attestationGate}
            onAttestationDecision={onAttestationDecision}
            onNavigateToDossier={onNavigateToDossier}
            findings={findings}
            sessionStatus={sessionStatus}
            lastFetchAgo={lastFetchAgo}
            fetchFailCount={fetchFailCount}
            fetchErrorDismissed={fetchErrorDismissed}
            fetchSharedData={fetchSharedData}
            handleAttachRepo={handleAttachRepo}
          />
        </RegionPortalsProvider>
      </IncidentLifecycleProvider>
    </AppControlProvider>
  );
};

// Inner grid component — consumes useRegionPortals() to wire region
// refs that PR 3 drawers use as their pane-portal mount targets.
interface WarRoomGridProps {
  session: V4Session;
  events: TaskEvent[];
  wsConnected: boolean;
  phase: DiagnosticPhase | null;
  confidence: number;
  tokenUsage: TokenUsage[];
  attestationGate?: AttestationGateData | null;
  onAttestationDecision?: (decision: string) => void;
  onNavigateToDossier?: () => void;
  findings: V4Findings | null;
  sessionStatus: V4SessionStatus | null;
  lastFetchAgo: number;
  fetchFailCount: number;
  fetchErrorDismissed: boolean;
  fetchSharedData: () => void;
  handleAttachRepo: () => void;
}

const WarRoomGrid: React.FC<WarRoomGridProps> = ({
  session,
  events,
  wsConnected,
  phase,
  confidence,
  tokenUsage,
  attestationGate,
  onAttestationDecision,
  onNavigateToDossier,
  findings,
  sessionStatus,
  lastFetchAgo,
  fetchFailCount,
  fetchErrorDismissed,
  fetchSharedData,
  handleAttachRepo,
}) => {
  const {
    setInvestigatorEl,
    setEvidenceEl,
    setNavigatorEl,
    setGutterEl,
  } = useRegionPortals();

  return (
    <div className="warroom-grid">
      {/* Banner region — top grid row */}
      <BannerRegion
        findings={findings}
        status={sessionStatus}
        events={events}
        lastFetchAgoSec={lastFetchAgo}
        wsConnected={wsConnected}
        fetchFailCount={fetchFailCount}
        fetchErrorDismissed={fetchErrorDismissed}
        attestationGate={attestationGate ?? null}
        onRetryFetch={fetchSharedData}
        sessionId={session.session_id}
      />

      {/* Main grid — 3 columns (+ gutter) */}
      <TelescopeProvider>
        <TopologySelectionProvider>
          {/* Left: Investigator */}
          <div
            ref={setInvestigatorEl}
            className="wr-region-investigator overflow-hidden relative"
          >
            <Investigator
              sessionId={session.session_id}
              events={events}
              wsConnected={wsConnected}
              findings={findings}
              status={sessionStatus}
              onAttachRepo={handleAttachRepo}
            />
          </div>

          {/* Center: Evidence (hosts TelescopeDrawerV2 + SurgicalTelescope
              PaneDrawers via RegionPortalsContext) */}
          <div
            ref={setEvidenceEl}
            className="wr-region-evidence overflow-hidden relative"
          >
            <EvidenceFindings
              findings={findings}
              status={sessionStatus}
              events={events}
              sessionId={session.session_id}
              phase={phase}
              onRefresh={fetchSharedData}
              onNavigateToDossier={onNavigateToDossier}
            />
          </div>

          {/* Right: Navigator (hosts ChatDrawer via RegionPortalsContext) */}
          <div
            ref={setNavigatorEl}
            className="wr-region-navigator overflow-hidden relative"
          >
            <Navigator findings={findings} status={sessionStatus} events={events} />
          </div>

          {/* Gutter rail — hosts LedgerTriggerTab */}
          <div
            ref={setGutterEl}
            className="wr-region-gutter flex flex-col items-center pt-[45vh] relative"
            data-testid="gutter-rail"
          />

          {/* Resource telescopes mount into Evidence region */}
          <TelescopeDrawerV2 />
          <SurgicalTelescope />
        </TopologySelectionProvider>
      </TelescopeProvider>

      {/* Footer */}
      <div className="wr-region-footer">
        <RemediationProgressBar
          phase={phase}
          confidence={confidence}
          tokenUsage={tokenUsage}
          wsConnected={wsConnected}
          budget={sessionStatus?.budget ?? null}
          selfConsistency={sessionStatus?.self_consistency ?? null}
          findings={findings}
          onResolve={onNavigateToDossier}
        />
      </div>

      {/* Attestation Gate Modal — true modal, not a pane drawer */}
      {attestationGate && onAttestationDecision && (
        <AttestationGateUI
          gate={attestationGate}
          evidencePins={[]}
          onDecision={(decision, _notes) => onAttestationDecision(decision)}
          onClose={() => onAttestationDecision('dismiss')}
        />
      )}

      {/* ChatDrawer mounts into Navigator via PaneDrawer; LedgerTab
          mounts into the gutter rail. Both read refs from
          RegionPortalsContext. Rendered here so their internal state
          is scoped to the WarRoomGrid lifetime. */}
      <ChatDrawer />
      <LedgerTriggerTab />
    </div>
  );
};

export default InvestigationView;
