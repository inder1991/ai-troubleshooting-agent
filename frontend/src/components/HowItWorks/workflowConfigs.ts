import type { DuckVariant } from './DuckAvatar';

// ─── Design System Colors ───
export const WF_COLORS = {
  // Backgrounds
  pageBg: '#1a1814',
  panelBg: '#161310',
  cardBg: '#252118',
  border: '#3d3528',
  // Accents
  amber: '#e09f3e',
  green: '#10b981',
  // Node status
  activeFill: '#2a2010',
  activeStroke: '#e09f3e',
  completeFill: '#0c2d1f',
  completeStroke: '#10b981',
  pendingFill: '#252118',
  pendingStroke: '#3d3528',
  // Text
  mutedText: '#8a7e6b',
  labelText: '#e2e8f0',
  dimText: '#5a5347',
  // Agent edge colors
  agentRed: '#ef4444',
  agentBlue: '#38bdf8',
  agentOrange: '#f59e0b',
  agentPurple: '#a78bfa',
  agentEmerald: '#10b981',
} as const;

export type NodeTier = 'landmark' | 'agent' | 'pipeline';

export interface WorkflowNode {
  id: string;
  label: string;
  duck: DuckVariant;
  x: number;
  y: number;
  tier: NodeTier;
  subtitle?: string;
  badge?: string;
  accentColor?: string;
  outputLabels?: string[];
}

export interface WorkflowEdge {
  from: string;
  to: string;
  color?: string;
}

export interface WorkflowPhase {
  name: string;
  description: string;
  startTime: number;
  duration: number;
  activateNodes: string[];
  activateEdges: [string, string][];
  parallel?: boolean;
  phaseColumn?: number;
}

export interface WorkflowConfig {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  phases: WorkflowPhase[];
  totalDuration: number;
  viewBoxWidth: number;
  viewBoxHeight: number;
}

// ═══════════════════════════════════════════════════════════════
// CLUSTER DIAGNOSTICS (35 seconds)
// ═══════════════════════════════════════════════════════════════

export const clusterConfig: WorkflowConfig = {
  totalDuration: 35,
  viewBoxWidth: 2400,
  viewBoxHeight: 600,
  nodes: [
    // Col 1: Pre-flight (x=200)
    { id: 'form',     label: 'Mission Deployed', duck: 'supervisor', x: 200, y: 80,  tier: 'landmark', subtitle: 'Form submitted' },
    { id: 'rbac',     label: 'RBAC Check',       duck: 'rbac',       x: 200, y: 160, tier: 'pipeline', subtitle: 'Checking permissions...' },
    { id: 'topo',     label: 'Topology Scan',    duck: 'network',    x: 200, y: 240, tier: 'pipeline', subtitle: 'Mapping cluster...' },
    { id: 'alerts',   label: 'Alert Correlation', duck: 'metrics',   x: 200, y: 320, tier: 'pipeline', subtitle: 'Grouping alerts...' },
    { id: 'firewall', label: 'Causal Firewall',  duck: 'critic',     x: 200, y: 400, tier: 'pipeline', subtitle: 'Pruning links...' },
    { id: 'dispatch', label: 'Dispatch Router',  duck: 'supervisor', x: 200, y: 480, tier: 'pipeline', subtitle: 'Routing to agents...' },

    // Col 2: Domain agents (x=700)
    { id: 'ctrl',    label: 'Control Plane',  duck: 'ctrl_plane', x: 700, y: 80,  tier: 'agent', accentColor: '#ef4444', subtitle: 'Analyzing operators...', badge: '4 anomalies' },
    { id: 'compute', label: 'Compute',        duck: 'compute',    x: 700, y: 180, tier: 'agent', accentColor: '#38bdf8', subtitle: 'Checking nodes...',       badge: '6 anomalies' },
    { id: 'net',     label: 'Network',        duck: 'network',    x: 700, y: 280, tier: 'agent', accentColor: '#f59e0b', subtitle: 'DNS & ingress...',        badge: '5 anomalies' },
    { id: 'stor',    label: 'Storage',        duck: 'storage',    x: 700, y: 380, tier: 'agent', accentColor: '#a78bfa', subtitle: 'PVC health...',           badge: '3 anomalies' },
    { id: 'rbac_a',  label: 'RBAC',           duck: 'rbac',       x: 700, y: 480, tier: 'agent', accentColor: '#10b981', subtitle: 'Security audit...',       badge: '2 anomalies' },

    // Col 3: Intelligence pipeline (x=1200)
    { id: 'signal',  label: 'Signal Normalizer',  duck: 'generic', x: 1200, y: 80,  tier: 'pipeline', subtitle: 'Extracting signals...' },
    { id: 'pattern', label: 'Pattern Matcher',     duck: 'generic', x: 1200, y: 170, tier: 'pipeline', subtitle: 'Matching failure patterns...' },
    { id: 'temporal',label: 'Temporal Analyzer',   duck: 'generic', x: 1200, y: 260, tier: 'pipeline', subtitle: 'Restart velocity...' },
    { id: 'graph',   label: 'Evidence Graph',      duck: 'generic', x: 1200, y: 350, tier: 'pipeline', subtitle: 'Building causal graph...' },
    { id: 'hypo',    label: 'Hypothesis Engine',   duck: 'generic', x: 1200, y: 440, tier: 'pipeline', subtitle: 'Ranking root causes...' },
    { id: 'critic',  label: 'Critic Validator',    duck: 'critic',  x: 1200, y: 530, tier: 'pipeline', subtitle: '6-layer validation...' },

    // Col 4: Synthesis (x=1700)
    { id: 'synth',    label: 'Synthesize',        duck: 'supervisor', x: 1700, y: 200, tier: 'pipeline', subtitle: 'Building diagnosis...' },
    { id: 'solution', label: 'Solution Validator', duck: 'critic',    x: 1700, y: 340, tier: 'pipeline', subtitle: 'Validating remediation...' },
    { id: 'impact',   label: 'Impact Analysis',   duck: 'generic',   x: 1700, y: 480, tier: 'pipeline', subtitle: 'Blast radius...' },

    // Col 5: Report (x=2200)
    { id: 'report', label: 'Health Report', duck: 'supervisor', x: 2200, y: 300, tier: 'landmark', badge: 'Diagnosis Complete', outputLabels: ['Causal Chains', 'Blast Radius', 'Remediation Steps'] },
  ],

  edges: [
    { from: 'form', to: 'rbac' },
    { from: 'rbac', to: 'topo' },
    { from: 'topo', to: 'alerts' },
    { from: 'alerts', to: 'firewall' },
    { from: 'firewall', to: 'dispatch' },
    { from: 'dispatch', to: 'ctrl',    color: '#ef4444' },
    { from: 'dispatch', to: 'compute', color: '#38bdf8' },
    { from: 'dispatch', to: 'net',     color: '#f59e0b' },
    { from: 'dispatch', to: 'stor',    color: '#a78bfa' },
    { from: 'dispatch', to: 'rbac_a',  color: '#10b981' },
    { from: 'ctrl',    to: 'signal', color: '#ef4444' },
    { from: 'compute', to: 'signal', color: '#38bdf8' },
    { from: 'net',     to: 'signal', color: '#f59e0b' },
    { from: 'stor',    to: 'signal', color: '#a78bfa' },
    { from: 'rbac_a',  to: 'signal', color: '#10b981' },
    { from: 'signal', to: 'pattern' },
    { from: 'pattern', to: 'temporal' },
    { from: 'temporal', to: 'graph' },
    { from: 'graph', to: 'hypo' },
    { from: 'hypo', to: 'critic' },
    { from: 'critic', to: 'synth' },
    { from: 'synth', to: 'solution' },
    { from: 'solution', to: 'impact' },
    { from: 'impact', to: 'report' },
  ],

  phases: [
    {
      name: 'Pre-flight',
      description: 'Checking permissions, mapping topology, correlating alerts',
      startTime: 0, duration: 5,
      activateNodes: ['form', 'rbac', 'topo', 'alerts', 'firewall', 'dispatch'],
      activateEdges: [['form','rbac'], ['rbac','topo'], ['topo','alerts'], ['alerts','firewall'], ['firewall','dispatch']],
      phaseColumn: 200,
    },
    {
      name: 'Domain Agents',
      description: '5 specialized agents analyze the cluster in parallel',
      startTime: 5, duration: 10,
      activateNodes: ['ctrl', 'compute', 'net', 'stor', 'rbac_a'],
      activateEdges: [['dispatch','ctrl'], ['dispatch','compute'], ['dispatch','net'], ['dispatch','stor'], ['dispatch','rbac_a']],
      parallel: true,
      phaseColumn: 700,
    },
    {
      name: 'Intelligence',
      description: 'Normalizing signals, matching patterns, building evidence graph',
      startTime: 15, duration: 10,
      activateNodes: ['signal', 'pattern', 'temporal', 'graph', 'hypo', 'critic'],
      activateEdges: [['ctrl','signal'], ['compute','signal'], ['net','signal'], ['stor','signal'], ['rbac_a','signal'],
                      ['signal','pattern'], ['pattern','temporal'], ['temporal','graph'], ['graph','hypo'], ['hypo','critic']],
      phaseColumn: 1200,
    },
    {
      name: 'Synthesis',
      description: 'Generating root cause analysis, remediation plan, and health report',
      startTime: 25, duration: 7,
      activateNodes: ['synth', 'solution', 'impact', 'report'],
      activateEdges: [['critic','synth'], ['synth','solution'], ['solution','impact'], ['impact','report']],
      phaseColumn: 1700,
    },
    {
      name: 'Diagnosis Complete',
      description: 'Causal chains, blast radius, and remediation steps ready',
      startTime: 32, duration: 3,
      activateNodes: [],
      activateEdges: [],
      phaseColumn: 2200,
    },
  ],
};

// ═══════════════════════════════════════════════════════════════
// APP DIAGNOSTICS (40 seconds)
// ═══════════════════════════════════════════════════════════════

export const appConfig: WorkflowConfig = {
  totalDuration: 40,
  viewBoxWidth: 1800,
  viewBoxHeight: 500,
  nodes: [
    { id: 'form',       label: 'Mission Deployed',  duck: 'supervisor', x: 150, y: 180, tier: 'landmark', subtitle: 'Form submitted' },
    { id: 'supervisor', label: 'Supervisor',         duck: 'supervisor', x: 150, y: 320, tier: 'agent', accentColor: '#e09f3e', subtitle: 'Orchestrating...' },
    { id: 'log', label: 'Log Agent', duck: 'log', x: 400, y: 250, tier: 'agent', accentColor: '#fbbf24', subtitle: 'Scanning error patterns...', badge: '3 patterns' },
    { id: 'metrics', label: 'Metrics Agent', duck: 'metrics', x: 650, y: 160, tier: 'agent', accentColor: '#10b981', subtitle: 'Querying Prometheus...', badge: '5 anomalies' },
    { id: 'k8s',     label: 'K8s Agent',     duck: 'k8s',     x: 650, y: 340, tier: 'agent', accentColor: '#f59e0b', subtitle: 'Checking pod health...', badge: '2 issues' },
    { id: 'code', label: 'Code Agent', duck: 'code', x: 900, y: 250, tier: 'agent', accentColor: '#60a5fa', subtitle: 'Tracing to source code...', badge: '4 files' },
    { id: 'change', label: 'Change Agent', duck: 'change', x: 1150, y: 250, tier: 'agent', accentColor: '#c084fc', subtitle: 'Correlating deployments...', badge: '1 commit' },
    { id: 'critic', label: 'Critic Agent', duck: 'critic', x: 1400, y: 250, tier: 'agent', accentColor: '#f87171', subtitle: 'Cross-validating findings...' },
    { id: 'impact', label: 'Impact Analysis', duck: 'generic',    x: 1650, y: 140, tier: 'pipeline', subtitle: 'Blast radius estimation...' },
    { id: 'synth',  label: 'Synthesis',       duck: 'supervisor', x: 1650, y: 250, tier: 'pipeline', subtitle: 'Building final report...' },
    { id: 'report', label: 'Diagnosis Report', duck: 'supervisor', x: 1650, y: 380, tier: 'landmark', badge: 'Diagnosis Complete', outputLabels: ['Root Cause', 'Blast Radius', 'Remediation', 'Past Incidents'] },
  ],

  edges: [
    { from: 'form', to: 'supervisor' },
    { from: 'supervisor', to: 'log' },
    { from: 'log', to: 'metrics', color: '#10b981' },
    { from: 'log', to: 'k8s',     color: '#f59e0b' },
    { from: 'metrics', to: 'code', color: '#10b981' },
    { from: 'k8s',     to: 'code', color: '#f59e0b' },
    { from: 'code', to: 'change' },
    { from: 'change', to: 'critic' },
    { from: 'critic', to: 'impact' },
    { from: 'impact', to: 'synth' },
    { from: 'synth', to: 'report' },
  ],

  phases: [
    {
      name: 'Dispatch',
      description: 'Supervisor receives the mission and plans agent execution',
      startTime: 0, duration: 3,
      activateNodes: ['form', 'supervisor'],
      activateEdges: [['form', 'supervisor']],
      phaseColumn: 150,
    },
    {
      name: 'Log Analysis',
      description: 'Scanning logs for error patterns and reconstructing service flow',
      startTime: 3, duration: 6,
      activateNodes: ['log'],
      activateEdges: [['supervisor', 'log']],
      phaseColumn: 400,
    },
    {
      name: 'Parallel Analysis',
      description: 'Metrics and K8s agents analyze simultaneously',
      startTime: 9, duration: 8,
      activateNodes: ['metrics', 'k8s'],
      activateEdges: [['log', 'metrics'], ['log', 'k8s']],
      parallel: true,
      phaseColumn: 650,
    },
    {
      name: 'Code Analysis',
      description: 'Tracing stack frames to source code',
      startTime: 17, duration: 6,
      activateNodes: ['code'],
      activateEdges: [['metrics', 'code'], ['k8s', 'code']],
      phaseColumn: 900,
    },
    {
      name: 'Change Correlation',
      description: 'Correlating recent deployments with the incident',
      startTime: 23, duration: 5,
      activateNodes: ['change'],
      activateEdges: [['code', 'change']],
      phaseColumn: 1150,
    },
    {
      name: 'Validation',
      description: 'Cross-validating all findings for contradictions',
      startTime: 28, duration: 5,
      activateNodes: ['critic'],
      activateEdges: [['change', 'critic']],
      phaseColumn: 1400,
    },
    {
      name: 'Synthesis & Output',
      description: 'Estimating blast radius and generating final diagnosis',
      startTime: 33, duration: 5,
      activateNodes: ['impact', 'synth', 'report'],
      activateEdges: [['critic', 'impact'], ['impact', 'synth'], ['synth', 'report']],
      phaseColumn: 1650,
    },
    {
      name: 'Diagnosis Complete',
      description: 'Root cause, blast radius, and remediation ready',
      startTime: 38, duration: 2,
      activateNodes: [],
      activateEdges: [],
    },
  ],
};
