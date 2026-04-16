import { describe, expect, test } from 'vitest';
import { humanTriggerSummary } from '../humanTriggerSummary';
import type { PredicateExpr } from '../../../../types';

const inputRef = { ref: { from: 'input', path: 'color' } };
const envRef = { ref: { from: 'env', path: 'TENANT' } };
const nodeRef = { ref: { from: 'node', node_id: 'step1', path: 'output.result' } };

describe('humanTriggerSummary', () => {
  test('undefined → empty string', () => {
    expect(humanTriggerSummary(undefined)).toBe('');
  });

  test('eq input literal', () => {
    const expr = {
      op: 'eq',
      args: [inputRef, { literal: 'red' }],
    } as unknown as PredicateExpr;
    expect(humanTriggerSummary(expr)).toBe('if input.color == "red"');
  });

  test('eq node ref strips leading output. from path', () => {
    const expr = {
      op: 'eq',
      args: [nodeRef, { literal: 42 }],
    } as unknown as PredicateExpr;
    expect(humanTriggerSummary(expr)).toBe('if step1.result == 42');
  });

  test('eq env ref', () => {
    const expr = {
      op: 'eq',
      args: [envRef, { literal: 'prod' }],
    } as unknown as PredicateExpr;
    expect(humanTriggerSummary(expr)).toBe('if env.TENANT == "prod"');
  });

  test('in (contains) phrasing', () => {
    const expr = {
      op: 'in',
      args: [{ literal: 'x' }, inputRef],
    } as unknown as PredicateExpr;
    expect(humanTriggerSummary(expr)).toBe('if input.color contains "x"');
  });

  test('exists phrasing', () => {
    const expr = {
      op: 'exists',
      args: [inputRef],
    } as unknown as PredicateExpr;
    expect(humanTriggerSummary(expr)).toBe('if input.color exists');
  });

  test('not wraps inner with "not (...)"', () => {
    const expr = {
      op: 'not',
      args: [
        {
          op: 'eq',
          args: [inputRef, { literal: 'red' }],
        },
      ],
    } as unknown as PredicateExpr;
    expect(humanTriggerSummary(expr)).toBe('not (if input.color == "red")');
  });

  test('and joins with AND and wraps in parens', () => {
    const expr = {
      op: 'and',
      args: [
        {
          op: 'eq',
          args: [inputRef, { literal: 'red' }],
        },
        {
          op: 'exists',
          args: [envRef],
        },
      ],
    } as unknown as PredicateExpr;
    expect(humanTriggerSummary(expr)).toBe(
      '(if input.color == "red" AND if env.TENANT exists)',
    );
  });

  test('or joins with OR', () => {
    const expr = {
      op: 'or',
      args: [
        { op: 'exists', args: [inputRef] },
        { op: 'exists', args: [envRef] },
      ],
    } as unknown as PredicateExpr;
    expect(humanTriggerSummary(expr)).toBe(
      '(if input.color exists OR if env.TENANT exists)',
    );
  });

  test('truncates to 80 chars with ellipsis', () => {
    const longLiteral = 'x'.repeat(200);
    const expr = {
      op: 'eq',
      args: [inputRef, { literal: longLiteral }],
    } as unknown as PredicateExpr;
    const out = humanTriggerSummary(expr);
    expect(out.length).toBeLessThanOrEqual(80);
    expect(out.endsWith('…')).toBe(true);
  });

  test('unknown op → empty string', () => {
    const expr = { op: 'bogus', args: [] } as unknown as PredicateExpr;
    expect(humanTriggerSummary(expr)).toBe('');
  });
});
