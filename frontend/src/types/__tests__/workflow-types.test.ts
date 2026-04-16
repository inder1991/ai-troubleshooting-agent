import { describe, expect, test } from 'vitest';
import type {
  WorkflowSummary,
  WorkflowDetail,
  VersionSummary,
  WorkflowVersionDetail,
  WorkflowDag,
  StepSpec,
  RefExpr,
  LiteralExpr,
  TransformExpr,
  PredicateExpr,
  MappingExpr,
  RunDetail,
  StepRunDetail,
  RunStatus,
  StepRunStatus,
} from '../index';

describe('workflow types', () => {
  test('WorkflowSummary and RunStatus compile', () => {
    const s: WorkflowSummary = {
      id: 'w1',
      name: 'n',
      description: 'd',
      created_at: '2026-04-15T00:00:00Z',
    };
    const r: RunStatus = 'succeeded';
    expect(s.id).toBe('w1');
    expect(r).toBe('succeeded');
  });

  test('VersionSummary compiles', () => {
    const v: VersionSummary = {
      version_id: 'v1',
      workflow_id: 'w1',
      version: 1,
      created_at: '2026-04-15T00:00:00Z',
    };
    expect(v.version).toBe(1);
  });

  test('WorkflowDetail extends WorkflowSummary', () => {
    const d: WorkflowDetail = {
      id: 'w1',
      name: 'n',
      description: 'd',
      created_at: '2026-04-15T00:00:00Z',
      latest_version: { version: 2, created_at: '2026-04-15T00:00:00Z' },
    };
    expect(d.latest_version?.version).toBe(2);
  });

  test('RefExpr, LiteralExpr, TransformExpr, MappingExpr', () => {
    const input_ref: RefExpr = { ref: { from: 'input', path: 'a.b' } };
    const env_ref: RefExpr = { ref: { from: 'env', path: 'FOO' } };
    const node_ref: RefExpr = { ref: { from: 'node', node_id: 's1', path: 'out' } };
    const lit: LiteralExpr = { literal: 42 };
    const tr: TransformExpr = { op: 'coalesce', args: [lit, input_ref] };
    const m: MappingExpr = tr;
    expect((input_ref as any).ref.from).toBe('input');
    expect((env_ref as any).ref.from).toBe('env');
    expect((node_ref as any).ref.node_id).toBe('s1');
    expect(m).toBeDefined();
  });

  test('PredicateExpr shapes', () => {
    const eq: PredicateExpr = {
      op: 'eq',
      left: { ref: { from: 'input', path: 'x' } },
      right: { literal: 1 },
    };
    const andP: PredicateExpr = { op: 'and', args: [eq, { op: 'not', arg: eq }] };
    expect(andP.op).toBe('and');
  });

  test('StepSpec and WorkflowDag', () => {
    const step: StepSpec = {
      id: 's1',
      agent: 'log_agent',
      agent_version: 'latest',
      inputs: { service_name: { ref: { from: 'input', path: 'service_name' } } },
    };
    const dag: WorkflowDag = { inputs_schema: {}, steps: [step] };
    expect(dag.steps[0].id).toBe('s1');
  });

  test('WorkflowVersionDetail compiles', () => {
    const wvd: WorkflowVersionDetail = {
      workflow_id: 'w1',
      version: 1,
      created_at: '2026-04-15T00:00:00Z',
      dag: { inputs_schema: {}, steps: [] },
      compiled: {},
    };
    expect(wvd.version).toBe(1);
  });

  test('RunDetail + StepRunDetail + StepRunStatus', () => {
    const srs: StepRunStatus = 'success';
    const sr: StepRunDetail = {
      id: 'sr1',
      step_id: 's1',
      status: srs,
      attempt: 1,
    };
    const run: RunDetail = {
      id: 'r1',
      workflow_version_id: 'v1',
      status: 'running',
      inputs: {},
      step_runs: [sr],
    };
    expect(run.step_runs[0].status).toBe('success');
  });
});
