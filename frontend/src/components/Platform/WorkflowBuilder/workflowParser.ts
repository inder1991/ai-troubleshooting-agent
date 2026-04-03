export interface WorkflowStep {
  id: string;
  label?: string;          // human-readable display name
  agent: string;
  depends_on: string[];
  condition?: string;
  gate?: string;
  timeout?: number;        // seconds
  retries?: number;        // 0–5
  retry_delay?: number;    // seconds
  human_gate?: boolean;    // true if gate === 'human_approval'
  skip_if?: string;        // expression string
  parameters?: Record<string, string>;  // custom agent parameters
}

export interface ParsedWorkflow {
  id?: string;
  name?: string;
  version?: string;
  triggers?: string[];
  steps: WorkflowStep[];
  errors: string[];
  dirty?: boolean;
}

export function parseWorkflowYaml(yaml: string): ParsedWorkflow {
  const errors: string[] = [];
  const steps: WorkflowStep[] = [];

  const idMatch = yaml.match(/^id:\s*(.+)$/m);
  const nameMatch = yaml.match(/^name:\s*(.+)$/m);
  const versionMatch = yaml.match(/^version:\s*"?([^"\n]+?)"?\s*$/m);
  const triggersMatch = yaml.match(/^triggers?:\s*\[([^\]]+)\]/m);
  const triggers = triggersMatch
    ? triggersMatch[1].split(',').map(t => t.trim())
    : [];

  const stepsSection = yaml.split(/^steps:\s*$/m)[1] || '';
  const stepBlocks = stepsSection.split(/(?=\n\s{2}-\s)/);

  for (const block of stepBlocks) {
    const idM = block.match(/[-\s]+id:\s*(\S+)/);
    const agentM = block.match(/\s+agent:\s*(\S+)/);
    if (!idM) continue;

    const stepId = idM[1];
    const agent = agentM ? agentM[1] : '';

    if (!agent) errors.push(`Step '${stepId}': missing agent field`);

    const depends_on: string[] = [];
    const depsMatch = block.match(/depends_on:\s*\[([^\]]*)\]/);
    if (depsMatch) {
      depsMatch[1].split(',').forEach(d => {
        const trimmed = d.trim().replace(/['"]/g, '');
        if (trimmed) depends_on.push(trimmed);
      });
    } else {
      const multiLine = block.match(/depends_on:\s*\n((?:\s+-\s+\S+\n?)+)/);
      if (multiLine) {
        const matches = multiLine[1].match(/^\s+-\s+(\S+)/gm);
        matches?.forEach(line => {
          const id = line.replace(/^\s+-\s+/, '').trim();
          if (id) depends_on.push(id);
        });
      }
    }

    const conditionM = block.match(/condition:\s*"(.+)"/);
    const gateM = block.match(/^\s+gate:\s*(\S+)/m);
    const labelM = block.match(/\s+label:\s*"?([^"\n]+?)"?\s*$/m);
    const timeoutM = block.match(/\s+timeout:\s*(\d+)/);
    const retriesM = block.match(/\s+retries:\s*(\d+)/);
    const retryDelayM = block.match(/\s+retry_delay:\s*(\d+)/);
    const skipIfM = block.match(/\s+skip_if:\s*"?([^"\n]+)"?\s*$/m);

    // Parse parameters block
    const parameters: Record<string, string> = {};
    const paramSection = block.match(/\s+parameters:\s*\n((?:\s+[\w-]+:.+\n?)+)/);
    if (paramSection) {
      const paramLines = paramSection[1].match(/\s+([\w-]+):\s*(.+)/g) || [];
      paramLines.forEach(line => {
        const [, k, v] = line.match(/\s+([\w-]+):\s*(.+)/) || [];
        if (k && v) parameters[k.trim()] = v.trim().replace(/^["']|["']$/g, '');
      });
    }

    const humanGate = gateM?.[1] === 'human_approval';

    steps.push({
      id: stepId,
      label: labelM?.[1]?.trim(),
      agent,
      depends_on,
      condition: conditionM?.[1],
      gate: gateM?.[1],
      timeout: timeoutM ? parseInt(timeoutM[1]) : undefined,
      retries: retriesM ? parseInt(retriesM[1]) : undefined,
      retry_delay: retryDelayM ? parseInt(retryDelayM[1]) : undefined,
      human_gate: humanGate || undefined,
      skip_if: skipIfM?.[1]?.trim(),
      parameters: Object.keys(parameters).length > 0 ? parameters : undefined,
    });
  }

  const stepIds = new Set(steps.map(s => s.id));
  steps.forEach(step => {
    step.depends_on.forEach(dep => {
      if (!stepIds.has(dep)) {
        errors.push(`Step '${step.id}': depends_on '${dep}' not found`);
      }
    });
  });

  const visited = new Set<string>();
  const inStack = new Set<string>();
  const hasCycle = (id: string): boolean => {
    if (inStack.has(id)) return true;
    if (visited.has(id)) return false;
    visited.add(id); inStack.add(id);
    const step = steps.find(s => s.id === id);
    for (const dep of step?.depends_on || []) {
      if (hasCycle(dep)) return true;
    }
    inStack.delete(id);
    return false;
  };
  const cycleReported = new Set<string>();
  steps.forEach(s => {
    visited.clear();
    inStack.clear();
    if (hasCycle(s.id) && !cycleReported.has(s.id)) {
      errors.push(`Cycle detected involving step '${s.id}'`);
      cycleReported.add(s.id);
    }
  });

  return {
    id: idMatch?.[1]?.trim(),
    name: nameMatch?.[1]?.trim(),
    version: versionMatch?.[1]?.trim(),
    triggers,
    steps,
    errors,
  };
}

export const APP_DIAGNOSTICS_TEMPLATE = `id: app_diagnostics
name: Application Diagnostics
version: "3.0"
trigger: [api, event]

triggers:
  inputs:
    - name: service_name
      label: "Service Name"
      type: string
      required: true
    - name: time_window
      type: select
      options: ["15m", "1h", "6h", "24h"]
      default: "1h"

steps:
  - id: logs
    agent: log_analysis_agent
    depends_on: []
    input:
      service_name: "{{ trigger.service_name }}"
      time_window: "{{ trigger.time_window }}"

  - id: metrics
    agent: metrics_agent
    depends_on: []
    input:
      service_name: "{{ trigger.service_name }}"

  - id: k8s
    agent: k8s_agent
    depends_on: []
    input:
      namespace: "{{ trigger.namespace | default('default') }}"

  - id: critic
    agent: critic_agent
    depends_on: [logs, metrics, k8s]
    condition: "{{ steps.logs.output.confidence < 0.7 }}"

  - id: fix
    agent: fix_generator
    depends_on: [critic]
    gate: human_approval
    gate_timeout: 30m
`;

export const CLUSTER_DIAGNOSTICS_TEMPLATE = `id: cluster_diagnostics
name: Cluster Diagnostics
version: "1.0"
trigger: [api]

triggers:
  inputs:
    - name: namespace
      label: "Namespace"
      type: string
      default: "default"
    - name: cluster_url
      label: "Cluster URL"
      type: string
      required: true

steps:
  - id: k8s
    agent: k8s_agent
    depends_on: []
    input:
      namespace: "{{ trigger.namespace }}"
      cluster_url: "{{ trigger.cluster_url }}"

  - id: metrics
    agent: metrics_agent
    depends_on: []
    input:
      namespace: "{{ trigger.namespace }}"

  - id: critic
    agent: critic_agent
    depends_on: [k8s, metrics]

  - id: fix
    agent: fix_generator
    depends_on: [critic]
    gate: human_approval
    gate_timeout: 30m
`;

export const NETWORK_DIAGNOSTICS_TEMPLATE = `id: network_diagnostics
name: Network Diagnostics
version: "1.0"
trigger: [api]

triggers:
  inputs:
    - name: src_ip
      label: "Source IP"
      type: string
      required: true
    - name: dst_ip
      label: "Destination IP"
      type: string
      required: true
    - name: port
      label: "Port"
      type: string
      default: "80"

steps:
  - id: connectivity
    agent: network_analysis_agent
    depends_on: []
    input:
      src_ip: "{{ trigger.src_ip }}"
      dst_ip: "{{ trigger.dst_ip }}"
      port: "{{ trigger.port }}"

  - id: routing
    agent: tracing_agent
    depends_on: []
    input:
      src_ip: "{{ trigger.src_ip }}"
      dst_ip: "{{ trigger.dst_ip }}"

  - id: critic
    agent: critic_agent
    depends_on: [connectivity, routing]

  - id: fix
    agent: fix_generator
    depends_on: [critic]
    gate: human_approval
    gate_timeout: 30m
`;

export const DB_DIAGNOSTICS_TEMPLATE = `id: db_diagnostics
name: Database Diagnostics
version: "1.0"
trigger: [api]

triggers:
  inputs:
    - name: database_name
      label: "Database Name"
      type: string
      required: true
    - name: time_window
      label: "Time Window"
      type: select
      options: ["15m", "1h", "6h", "24h"]
      default: "1h"

steps:
  - id: db_analysis
    agent: db_agent
    depends_on: []
    input:
      database_name: "{{ trigger.database_name }}"
      time_window: "{{ trigger.time_window }}"

  - id: query_analysis
    agent: code_navigator_agent
    depends_on: []
    input:
      database_name: "{{ trigger.database_name }}"

  - id: critic
    agent: critic_agent
    depends_on: [db_analysis, query_analysis]

  - id: fix
    agent: fix_generator
    depends_on: [critic]
    gate: human_approval
    gate_timeout: 30m
`;

export interface WorkflowTemplate {
  id: string;
  name: string;
  description: string;
  icon: string;
  yaml: string;
  stepCount: number;
}

export const WORKFLOW_TEMPLATES: WorkflowTemplate[] = [
  {
    id: 'app_diagnostics',
    name: 'App Diagnostics',
    description: 'Full application investigation: logs, metrics, K8s, critic, fix with human approval gate.',
    icon: 'bug_report',
    yaml: APP_DIAGNOSTICS_TEMPLATE,
    stepCount: 5,
  },
  {
    id: 'cluster_diagnostics',
    name: 'Cluster Diagnostics',
    description: 'Kubernetes cluster health: pod status, resource metrics, root cause, remediation.',
    icon: 'cloud',
    yaml: CLUSTER_DIAGNOSTICS_TEMPLATE,
    stepCount: 4,
  },
  {
    id: 'network_diagnostics',
    name: 'Network Diagnostics',
    description: 'Network path analysis: connectivity check, route tracing, and remediation proposal.',
    icon: 'hub',
    yaml: NETWORK_DIAGNOSTICS_TEMPLATE,
    stepCount: 4,
  },
  {
    id: 'db_diagnostics',
    name: 'Database Diagnostics',
    description: 'Database health analysis: query performance, slow queries, index recommendations.',
    icon: 'database',
    yaml: DB_DIAGNOSTICS_TEMPLATE,
    stepCount: 4,
  },
];
