export interface FlowNode {
  id: string;
  name: string;
  detail: string;
  iconLabel: string;
  color: string;
  position: { left: number; top: number };
  minWidth?: number;
  outputText: string;
}

export interface AnimationStep {
  delayMs: number;
  nodeId: string;
  toStatus: 'hidden' | 'visible' | 'active' | 'done';
  phaseIndex?: number;
  progress?: number;
  showBracket?: boolean;
}

export const flowNodes: FlowNode[] = [
  {
    id: 'user',
    name: 'User Reports Incident',
    detail: 'checkout-frontend\nnamespace: prod, 2h',
    iconLabel: 'U',
    color: '#94a3b8',
    position: { left: 0, top: 0 },
    outputText: 'Session created',
  },
  {
    id: 'fastapi',
    name: 'FastAPI',
    detail: 'Session + WebSocket',
    iconLabel: 'A',
    color: '#07b6d5',
    position: { left: 0, top: 150 },
    outputText: 'Route: /v4/investigate \u2192 Supervisor',
  },
  {
    id: 'supervisor',
    name: 'Supervisor',
    detail: 'State machine',
    iconLabel: 'S',
    color: '#10b981',
    position: { left: 0, top: 300 },
    outputText: 'Dispatching agents in parallel',
  },
  {
    id: 'log-agent',
    name: 'Log Analyzer',
    detail: 'Direct LLM +\nLogFingerprinter',
    iconLabel: 'L',
    color: '#ef4444',
    position: { left: 215, top: 300 },
    minWidth: 165,
    outputText:
      'Patient Zero: checkout-frontend | Pattern: TimeoutException in CheckoutController.java:87 | Cascade: frontend \u2192 checkout-svc',
  },
  {
    id: 'metrics-agent',
    name: 'Metrics Agent',
    detail: 'Prometheus + MAD',
    iconLabel: 'M',
    color: '#07b6d5',
    position: { left: 275, top: 95 },
    outputText:
      'frontend: latency 10.3s (+2100%) | checkout-svc: 7.18s (+850%) | error_rate: 88.9% spike',
  },
  {
    id: 'k8s-agent',
    name: 'K8s Probe',
    detail: 'Turn-based batch',
    iconLabel: 'K',
    color: '#f97316',
    position: { left: 455, top: 95 },
    outputText:
      'checkout-svc: 2 pods CrashLoop | OOMKill: mem limit 512Mi | HPA: maxed 5 replicas',
  },
  {
    id: 'tracing-agent',
    name: 'Tracing Agent',
    detail: 'Jaeger spans',
    iconLabel: 'T',
    color: '#a78bfa',
    position: { left: 455, top: 225 },
    outputText: 'Slow: checkout\u2192DB 6.9s | Healthy: payment, user, inv',
  },
  {
    id: 'change-agent',
    name: 'Change Intel',
    detail: 'Two-pass commit',
    iconLabel: 'C',
    color: '#10b981',
    position: { left: 660, top: 95 },
    outputText: 'SHA: e7b4a1f | Risk: 0.97 \u2014 N+1 query',
  },
  {
    id: 'code-agent',
    name: 'Code Navigator',
    detail: 'ReAct (15 iter)\nConvergence',
    iconLabel: 'D',
    color: '#3b82f6',
    position: { left: 660, top: 300 },
    minWidth: 165,
    outputText:
      'Root cause: CheckoutService.java:203 | Bug: N+1 query (unbatched) | Impact: 3 files',
  },
  {
    id: 'critic',
    name: 'Critic Agent',
    detail: 'Cross-validation',
    iconLabel: '\u2713',
    color: '#a78bfa',
    position: { left: 880, top: 200 },
    outputText:
      'N+1 query: CONFIRMED | OOM from load: CONFIRMED | Downstream: HEALTHY',
  },
  {
    id: 'human-gate',
    name: 'Human Attestation',
    detail: 'Review + sign-off',
    iconLabel: 'H',
    color: '#eab308',
    position: { left: 880, top: 370 },
    outputText: 'Status: ATTESTED | Audit trail created',
  },
  {
    id: 'fix-gen',
    name: 'Fix Generator',
    detail: 'LLM \u2192 Validate \u2192 Review',
    iconLabel: 'F',
    color: '#10b981',
    position: { left: 1060, top: 115 },
    outputText:
      'Fix: Batch query in CheckoutService | AST \u2713 ruff \u2713 | Risk: LOW',
  },
  {
    id: 'pr',
    name: 'GitHub PR',
    detail: 'Branch \u2192 Commit \u2192 Push',
    iconLabel: 'PR',
    color: '#3b82f6',
    position: { left: 1060, top: 310 },
    outputText: 'Branch: fix/INC-7203-n-plus-1 | PR #512: created \u2713',
  },
];

export const phaseLabels: string[] = [
  'Session',
  'Log Analysis',
  'Telemetry',
  'Reasoning',
  'Code Analysis',
  'Validation',
  'Attestation',
  'Fix & PR',
];

// Total animation time at 1x speed: ~22,200ms
// Progress values are proportional across the full sequence.
//
// Phase 0 (Session):        0ms–2700ms     → progress 0–12
// Phase 1 (Log Analysis):   2700ms–5500ms  → progress 12–25
// Phase 2 (Telemetry):      5500ms–10000ms → progress 25–45
// Phase 3 (Reasoning):      10000ms–12000ms→ progress 45–54
// Phase 4 (Code Analysis):  12000ms–16000ms→ progress 54–72
// Phase 5 (Validation):     16000ms–18400ms→ progress 72–83
// Phase 6 (Attestation):    18400ms–20800ms→ progress 83–94
// Phase 7 (Fix & PR):       20800ms–22200ms→ progress 94–100

export const animationSequence: AnimationStep[] = [
  // ── Phase 0: Session ──────────────────────────────────────────────
  // user active → 1100ms → user done, fastapi active → 900ms → fastapi done, supervisor active → 700ms → supervisor done
  { delayMs: 0, nodeId: 'user', toStatus: 'active', phaseIndex: 0, progress: 0 },
  { delayMs: 1100, nodeId: 'user', toStatus: 'done', progress: 5 },
  { delayMs: 0, nodeId: 'fastapi', toStatus: 'active', progress: 5 },
  { delayMs: 900, nodeId: 'fastapi', toStatus: 'done', progress: 9 },
  { delayMs: 0, nodeId: 'supervisor', toStatus: 'active', progress: 9 },
  { delayMs: 700, nodeId: 'supervisor', toStatus: 'done', progress: 12 },

  // ── Phase 1: Log Analysis ─────────────────────────────────────────
  // log-agent active → 1400ms → 1000ms → log-agent done → 400ms
  { delayMs: 0, nodeId: 'log-agent', toStatus: 'active', phaseIndex: 1, progress: 12 },
  { delayMs: 1400, nodeId: 'log-agent', toStatus: 'active', progress: 19 },
  { delayMs: 1000, nodeId: 'log-agent', toStatus: 'done', progress: 23 },
  { delayMs: 400, nodeId: 'log-agent', toStatus: 'done', progress: 25 },

  // ── Phase 2: Parallel Telemetry ───────────────────────────────────
  // show bracket → 300ms
  // metrics, k8s, tracing, change all active → 1800ms → 1200ms
  // staggered done: metrics → 400ms → k8s → 300ms → tracing → 400ms → change
  // hide bracket → 500ms
  { delayMs: 0, nodeId: 'metrics-agent', toStatus: 'visible', phaseIndex: 2, progress: 25, showBracket: true },
  { delayMs: 300, nodeId: 'metrics-agent', toStatus: 'active', progress: 26 },
  { delayMs: 0, nodeId: 'k8s-agent', toStatus: 'active', progress: 26 },
  { delayMs: 0, nodeId: 'tracing-agent', toStatus: 'active', progress: 26 },
  { delayMs: 0, nodeId: 'change-agent', toStatus: 'active', progress: 26 },
  { delayMs: 1800, nodeId: 'metrics-agent', toStatus: 'active', progress: 34 },
  { delayMs: 1200, nodeId: 'metrics-agent', toStatus: 'done', progress: 39 },
  { delayMs: 400, nodeId: 'k8s-agent', toStatus: 'done', progress: 41 },
  { delayMs: 300, nodeId: 'tracing-agent', toStatus: 'done', progress: 42 },
  { delayMs: 400, nodeId: 'change-agent', toStatus: 'done', progress: 44 },
  { delayMs: 500, nodeId: 'change-agent', toStatus: 'done', progress: 45, showBracket: false },

  // ── Phase 3: Reasoning ────────────────────────────────────────────
  // supervisor active → 1600ms → supervisor done → 400ms
  { delayMs: 0, nodeId: 'supervisor', toStatus: 'active', phaseIndex: 3, progress: 45 },
  { delayMs: 1600, nodeId: 'supervisor', toStatus: 'done', progress: 52 },
  { delayMs: 400, nodeId: 'supervisor', toStatus: 'done', progress: 54 },

  // ── Phase 4: Code Analysis ────────────────────────────────────────
  // code-agent active → 1500ms → 1200ms → 900ms → code-agent done → 400ms
  { delayMs: 0, nodeId: 'code-agent', toStatus: 'active', phaseIndex: 4, progress: 54 },
  { delayMs: 1500, nodeId: 'code-agent', toStatus: 'active', progress: 61 },
  { delayMs: 1200, nodeId: 'code-agent', toStatus: 'active', progress: 66 },
  { delayMs: 900, nodeId: 'code-agent', toStatus: 'done', progress: 70 },
  { delayMs: 400, nodeId: 'code-agent', toStatus: 'done', progress: 72 },

  // ── Phase 5: Validation ───────────────────────────────────────────
  // critic active → 1200ms → 800ms → critic done → 400ms
  { delayMs: 0, nodeId: 'critic', toStatus: 'active', phaseIndex: 5, progress: 72 },
  { delayMs: 1200, nodeId: 'critic', toStatus: 'active', progress: 77 },
  { delayMs: 800, nodeId: 'critic', toStatus: 'done', progress: 81 },
  { delayMs: 400, nodeId: 'critic', toStatus: 'done', progress: 83 },

  // ── Phase 6: Attestation ──────────────────────────────────────────
  // human-gate active → 2000ms → human-gate done → 400ms
  { delayMs: 0, nodeId: 'human-gate', toStatus: 'active', phaseIndex: 6, progress: 83 },
  { delayMs: 2000, nodeId: 'human-gate', toStatus: 'done', progress: 92 },
  { delayMs: 400, nodeId: 'human-gate', toStatus: 'done', progress: 94 },

  // ── Phase 7: Fix & PR ─────────────────────────────────────────────
  // fix-gen active → 1500ms → 1000ms → fix-gen done → 500ms
  // pr active → 1200ms → 700ms → pr done → 300ms → progress 100%
  { delayMs: 0, nodeId: 'fix-gen', toStatus: 'active', phaseIndex: 7, progress: 94 },
  { delayMs: 1500, nodeId: 'fix-gen', toStatus: 'active', progress: 95 },
  { delayMs: 1000, nodeId: 'fix-gen', toStatus: 'done', progress: 96 },
  { delayMs: 500, nodeId: 'pr', toStatus: 'active', progress: 97 },
  { delayMs: 1200, nodeId: 'pr', toStatus: 'active', progress: 98 },
  { delayMs: 700, nodeId: 'pr', toStatus: 'done', progress: 99 },
  { delayMs: 300, nodeId: 'pr', toStatus: 'done', progress: 100 },
];
