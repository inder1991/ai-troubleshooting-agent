import type { DuckVariant } from './DuckAvatar';

export interface WorkflowNode {
  id: string;
  label: string;
  duck: DuckVariant;
  x: number;
  y: number;
  subtitle?: string;  // shown when active
  badge?: string;     // shown when complete
}

export interface WorkflowEdge {
  from: string;
  to: string;
  color?: string;
}

export interface WorkflowPhase {
  name: string;
  description: string;
  startTime: number;    // seconds
  duration: number;     // seconds
  activateNodes: string[];
  activateEdges: [string, string][]; // [fromId, toId] pairs
  parallel?: boolean;
}

export interface WorkflowConfig {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  phases: WorkflowPhase[];
  totalDuration: number;
}

// ─── Layout constants ───
const CX = 450; // center X of canvas
const FAN_SPREAD = 130; // horizontal spread for fan-out nodes

// ═══════════════════════════════════════════════════════════════
// CLUSTER DIAGNOSTICS (35 seconds)
// ═══════════════════════════════════════════════════════════════

export const clusterConfig: WorkflowConfig = {
  totalDuration: 35,
  nodes: [
    // Pre-flight chain
    { id: 'form',     label: 'Mission Deployed', duck: 'supervisor', x: CX, y: 40, subtitle: 'Form submitted' },
    { id: 'rbac',     label: 'RBAC Check',       duck: 'rbac',       x: CX, y: 110, subtitle: 'Checking permissions...' },
    { id: 'topo',     label: 'Topology Scan',    duck: 'network',    x: CX, y: 180, subtitle: 'Mapping cluster...' },
    { id: 'alerts',   label: 'Alert Correlation', duck: 'metrics',   x: CX, y: 250, subtitle: 'Grouping alerts...' },
    { id: 'firewall', label: 'Causal Firewall',  duck: 'critic',     x: CX, y: 320, subtitle: 'Pruning links...' },
    { id: 'dispatch', label: 'Dispatch Router',  duck: 'supervisor', x: CX, y: 390, subtitle: 'Routing to agents...' },

    // Domain agents (fan-out)
    { id: 'ctrl',    label: 'Control Plane',  duck: 'ctrl_plane', x: CX - 2 * FAN_SPREAD, y: 490, subtitle: 'Analyzing operators...', badge: '4 anomalies' },
    { id: 'compute', label: 'Compute',        duck: 'compute',    x: CX - FAN_SPREAD,     y: 490, subtitle: 'Checking nodes...',       badge: '6 anomalies' },
    { id: 'net',     label: 'Network',        duck: 'network',    x: CX,                  y: 490, subtitle: 'DNS & ingress...',        badge: '5 anomalies' },
    { id: 'stor',    label: 'Storage',        duck: 'storage',    x: CX + FAN_SPREAD,     y: 490, subtitle: 'PVC health...',           badge: '3 anomalies' },
    { id: 'rbac_a',  label: 'RBAC',           duck: 'rbac',       x: CX + 2 * FAN_SPREAD, y: 490, subtitle: 'Security audit...',       badge: '2 anomalies' },

    // Intelligence pipeline
    { id: 'signal',  label: 'Signal Normalizer',  duck: 'generic', x: CX, y: 580, subtitle: 'Extracting signals...' },
    { id: 'pattern', label: 'Pattern Matcher',     duck: 'generic', x: CX, y: 640, subtitle: 'Matching failure patterns...' },
    { id: 'temporal',label: 'Temporal Analyzer',   duck: 'generic', x: CX, y: 700, subtitle: 'Restart velocity...' },
    { id: 'graph',   label: 'Evidence Graph',      duck: 'generic', x: CX, y: 760, subtitle: 'Building causal graph...' },
    { id: 'hypo',    label: 'Hypothesis Engine',   duck: 'generic', x: CX, y: 820, subtitle: 'Ranking root causes...' },
    { id: 'critic',  label: 'Critic Validator',    duck: 'critic',  x: CX, y: 880, subtitle: '6-layer validation...' },

    // Synthesis
    { id: 'synth',   label: 'Synthesize',       duck: 'supervisor', x: CX, y: 960, subtitle: 'Building diagnosis...' },
    { id: 'solution',label: 'Solution Validator', duck: 'critic',   x: CX, y: 1030, subtitle: 'Validating remediation...' },
    { id: 'report',  label: 'Health Report',     duck: 'supervisor', x: CX, y: 1110, badge: 'Diagnosis Complete' },
  ],

  edges: [
    // Pre-flight
    { from: 'form', to: 'rbac' },
    { from: 'rbac', to: 'topo' },
    { from: 'topo', to: 'alerts' },
    { from: 'alerts', to: 'firewall' },
    { from: 'firewall', to: 'dispatch' },

    // Fan-out
    { from: 'dispatch', to: 'ctrl',   color: '#ef4444' },
    { from: 'dispatch', to: 'compute',color: '#38bdf8' },
    { from: 'dispatch', to: 'net',    color: '#f59e0b' },
    { from: 'dispatch', to: 'stor',   color: '#a78bfa' },
    { from: 'dispatch', to: 'rbac_a', color: '#10b981' },

    // Fan-in
    { from: 'ctrl',   to: 'signal', color: '#ef4444' },
    { from: 'compute',to: 'signal', color: '#38bdf8' },
    { from: 'net',    to: 'signal', color: '#f59e0b' },
    { from: 'stor',   to: 'signal', color: '#a78bfa' },
    { from: 'rbac_a', to: 'signal', color: '#10b981' },

    // Pipeline
    { from: 'signal', to: 'pattern' },
    { from: 'pattern', to: 'temporal' },
    { from: 'temporal', to: 'graph' },
    { from: 'graph', to: 'hypo' },
    { from: 'hypo', to: 'critic' },

    // Synthesis
    { from: 'critic', to: 'synth' },
    { from: 'synth', to: 'solution' },
    { from: 'solution', to: 'report' },
  ],

  phases: [
    {
      name: 'Pre-flight',
      description: 'Checking permissions, mapping topology, correlating alerts',
      startTime: 0, duration: 5,
      activateNodes: ['form', 'rbac', 'topo', 'alerts', 'firewall', 'dispatch'],
      activateEdges: [['form','rbac'], ['rbac','topo'], ['topo','alerts'], ['alerts','firewall'], ['firewall','dispatch']],
    },
    {
      name: 'Domain Agent Fan-out',
      description: '5 specialized agents analyze the cluster in parallel',
      startTime: 5, duration: 10,
      activateNodes: ['ctrl', 'compute', 'net', 'stor', 'rbac_a'],
      activateEdges: [['dispatch','ctrl'], ['dispatch','compute'], ['dispatch','net'], ['dispatch','stor'], ['dispatch','rbac_a']],
      parallel: true,
    },
    {
      name: 'Intelligence Pipeline',
      description: 'Normalizing signals, matching patterns, building evidence graph',
      startTime: 15, duration: 10,
      activateNodes: ['signal', 'pattern', 'temporal', 'graph', 'hypo', 'critic'],
      activateEdges: [['ctrl','signal'], ['compute','signal'], ['net','signal'], ['stor','signal'], ['rbac_a','signal'],
                      ['signal','pattern'], ['pattern','temporal'], ['temporal','graph'], ['graph','hypo'], ['hypo','critic']],
    },
    {
      name: 'Synthesis & Output',
      description: 'Generating root cause analysis, remediation plan, and health report',
      startTime: 25, duration: 7,
      activateNodes: ['synth', 'solution', 'report'],
      activateEdges: [['critic','synth'], ['synth','solution'], ['solution','report']],
    },
    {
      name: 'Diagnosis Complete',
      description: 'Causal chains, blast radius, and remediation steps ready',
      startTime: 32, duration: 3,
      activateNodes: [],
      activateEdges: [],
    },
  ],
};

// ═══════════════════════════════════════════════════════════════
// APP DIAGNOSTICS (40 seconds)
// ═══════════════════════════════════════════════════════════════

export const appConfig: WorkflowConfig = {
  totalDuration: 40,
  nodes: [
    { id: 'form',      label: 'Mission Deployed',  duck: 'supervisor', x: CX, y: 40,  subtitle: 'Form submitted' },
    { id: 'supervisor', label: 'Supervisor',        duck: 'supervisor', x: CX, y: 120, subtitle: 'Orchestrating diagnosis...' },

    // Log agent (sequential)
    { id: 'log',       label: 'Log Agent',         duck: 'log',       x: CX, y: 210, subtitle: 'Scanning error patterns...', badge: '3 patterns' },

    // Parallel: metrics + k8s
    { id: 'metrics',   label: 'Metrics Agent',     duck: 'metrics',   x: CX - FAN_SPREAD, y: 310, subtitle: 'Querying Prometheus...', badge: '5 anomalies' },
    { id: 'k8s',       label: 'K8s Agent',         duck: 'k8s',       x: CX + FAN_SPREAD, y: 310, subtitle: 'Checking pod health...', badge: '2 issues' },

    // Code agent
    { id: 'code',      label: 'Code Agent',        duck: 'code',      x: CX, y: 410, subtitle: 'Tracing to source code...', badge: '4 files' },

    // Change agent
    { id: 'change',    label: 'Change Agent',      duck: 'change',    x: CX, y: 510, subtitle: 'Correlating deployments...', badge: '1 commit' },

    // Critic
    { id: 'critic',    label: 'Critic Agent',      duck: 'critic',    x: CX, y: 610, subtitle: 'Cross-validating findings...' },

    // Synthesis
    { id: 'impact',    label: 'Impact Analysis',   duck: 'generic',   x: CX, y: 700, subtitle: 'Blast radius estimation...' },
    { id: 'synth',     label: 'Synthesis',         duck: 'supervisor', x: CX, y: 790, subtitle: 'Building final report...' },
    { id: 'report',    label: 'Diagnosis Report',  duck: 'supervisor', x: CX, y: 880, badge: 'Diagnosis Complete' },
  ],

  edges: [
    { from: 'form', to: 'supervisor' },
    { from: 'supervisor', to: 'log' },
    // Fan-out
    { from: 'log', to: 'metrics', color: '#10b981' },
    { from: 'log', to: 'k8s',     color: '#f59e0b' },
    // Fan-in
    { from: 'metrics', to: 'code', color: '#10b981' },
    { from: 'k8s',     to: 'code', color: '#f59e0b' },
    // Sequential
    { from: 'code', to: 'change' },
    { from: 'change', to: 'critic' },
    // Connect all agents to critic (visual cross-validation)
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
    },
    {
      name: 'Log Analysis',
      description: 'Scanning logs for error patterns and reconstructing service flow',
      startTime: 3, duration: 6,
      activateNodes: ['log'],
      activateEdges: [['supervisor', 'log']],
    },
    {
      name: 'Parallel Analysis',
      description: 'Metrics and K8s agents analyze the cluster simultaneously',
      startTime: 9, duration: 8,
      activateNodes: ['metrics', 'k8s'],
      activateEdges: [['log', 'metrics'], ['log', 'k8s']],
      parallel: true,
    },
    {
      name: 'Code Analysis',
      description: 'Tracing stack frames to source code and identifying root cause',
      startTime: 17, duration: 6,
      activateNodes: ['code'],
      activateEdges: [['metrics', 'code'], ['k8s', 'code']],
    },
    {
      name: 'Change Correlation',
      description: 'Correlating recent deployments and commits with the incident',
      startTime: 23, duration: 5,
      activateNodes: ['change'],
      activateEdges: [['code', 'change']],
    },
    {
      name: 'Validation',
      description: 'Cross-validating all findings for contradictions',
      startTime: 28, duration: 5,
      activateNodes: ['critic'],
      activateEdges: [['change', 'critic']],
    },
    {
      name: 'Synthesis & Output',
      description: 'Estimating blast radius and generating final diagnosis',
      startTime: 33, duration: 5,
      activateNodes: ['impact', 'synth', 'report'],
      activateEdges: [['critic', 'impact'], ['impact', 'synth'], ['synth', 'report']],
    },
    {
      name: 'Diagnosis Complete',
      description: 'Root cause, blast radius, and remediation steps ready',
      startTime: 38, duration: 2,
      activateNodes: [],
      activateEdges: [],
    },
  ],
};
