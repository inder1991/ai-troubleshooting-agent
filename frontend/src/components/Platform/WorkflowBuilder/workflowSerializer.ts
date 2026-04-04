import type { ParsedWorkflow, WorkflowStep } from './workflowParser';

function indent(n: number): string { return '  '.repeat(n); }

function stepToYaml(step: WorkflowStep): string {
  const lines: string[] = [];
  lines.push(`${indent(1)}- id: ${step.id}`);
  if (step.label) lines.push(`${indent(2)}label: "${step.label}"`);
  lines.push(`${indent(2)}agent: ${step.agent}`);

  if (step.depends_on.length === 0) {
    lines.push(`${indent(2)}depends_on: []`);
  } else {
    lines.push(`${indent(2)}depends_on: [${step.depends_on.join(', ')}]`);
  }

  if (step.timeout !== undefined) lines.push(`${indent(2)}timeout: ${step.timeout}`);
  if (step.retries !== undefined) lines.push(`${indent(2)}retries: ${step.retries}`);
  if (step.retry_delay !== undefined) lines.push(`${indent(2)}retry_delay: ${step.retry_delay}`);
  if (step.human_gate) {
    lines.push(`${indent(2)}gate: human_approval`);
    lines.push(`${indent(2)}gate_timeout: 30m`);
  }
  if (step.condition) lines.push(`${indent(2)}condition: "${step.condition}"`);
  if (step.skip_if) lines.push(`${indent(2)}skip_if: "${step.skip_if}"`);
  if (step.parameters && Object.keys(step.parameters).length > 0) {
    lines.push(`${indent(2)}parameters:`);
    Object.entries(step.parameters).forEach(([k, v]) => {
      lines.push(`${indent(3)}${k}: "${v}"`);
    });
  }
  return lines.join('\n');
}

export function stateToYaml(workflow: ParsedWorkflow): string {
  const lines: string[] = [];
  if (workflow.id) lines.push(`id: ${workflow.id}`);
  if (workflow.name) lines.push(`name: ${workflow.name}`);
  if (workflow.version) lines.push(`version: "${workflow.version}"`);
  if (workflow.triggers && workflow.triggers.length > 0) {
    lines.push(`trigger: [${workflow.triggers.join(', ')}]`);
  }
  lines.push('');
  lines.push('steps:');
  workflow.steps.forEach(step => {
    lines.push(stepToYaml(step));
  });
  return lines.join('\n') + '\n';
}
