export interface WorkflowStep {
  id: string;
  agent: string;
  depends_on: string[];
  condition?: string;
  gate?: string;
}

export interface ParsedWorkflow {
  id?: string;
  name?: string;
  steps: WorkflowStep[];
  errors: string[];
}

export function parseWorkflowYaml(yaml: string): ParsedWorkflow {
  const errors: string[] = [];
  const steps: WorkflowStep[] = [];

  const idMatch = yaml.match(/^id:\s*(.+)$/m);
  const nameMatch = yaml.match(/^name:\s*(.+)$/m);

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
    const gateM = block.match(/gate:\s*(\S+)/);

    steps.push({
      id: stepId,
      agent,
      depends_on,
      condition: conditionM?.[1],
      gate: gateM?.[1],
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

  return { id: idMatch?.[1]?.trim(), name: nameMatch?.[1]?.trim(), steps, errors };
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
