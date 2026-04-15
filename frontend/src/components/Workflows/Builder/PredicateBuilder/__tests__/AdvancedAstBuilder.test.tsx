import { describe, expect, test, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AdvancedAstBuilder } from '../AdvancedAstBuilder';
import type { RefSource } from '../../RefPicker/RefPicker';
import type { PredicateExpr } from '../../../../../types';

const refSources: RefSource[] = [
  {
    kind: 'input',
    label: 'Input',
    schema: {
      type: 'object',
      properties: {
        name: { type: 'string' },
        active: { type: 'boolean' },
      },
    },
  },
];

const schemaByRef = () => undefined;

function makeEq(name: string, value: string): PredicateExpr {
  return {
    op: 'eq',
    args: [
      { ref: { from: 'input', path: name } },
      { literal: value },
    ],
  } as unknown as PredicateExpr;
}

describe('AdvancedAstBuilder', () => {
  test('renders a leaf clause when value is a simple eq', () => {
    render(
      <AdvancedAstBuilder
        value={makeEq('name', 'alice')}
        onChange={vi.fn()}
        refSources={refSources}
        schemaByRef={schemaByRef}
      />,
    );
    // The leaf clause should surface operator select from SimplePredicate
    expect(screen.getByRole('combobox', { name: /operator/i })).toBeInTheDocument();
  });

  test('and node renders child predicates and an "Add clause" button', () => {
    const ast: PredicateExpr = {
      op: 'and',
      args: [makeEq('name', 'a'), makeEq('name', 'b')],
    };
    render(
      <AdvancedAstBuilder
        value={ast}
        onChange={vi.fn()}
        refSources={refSources}
        schemaByRef={schemaByRef}
      />,
    );
    expect(screen.getByRole('button', { name: /add clause/i })).toBeInTheDocument();
    // Two child rows → two operator selects
    const ops = screen.getAllByRole('combobox', { name: /operator/i });
    expect(ops.length).toBe(2);
  });

  test('toggle AND to OR changes root op', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const ast: PredicateExpr = {
      op: 'and',
      args: [makeEq('name', 'a')],
    };
    render(
      <AdvancedAstBuilder
        value={ast}
        onChange={onChange}
        refSources={refSources}
        schemaByRef={schemaByRef}
      />,
    );
    await user.click(screen.getByRole('button', { name: /change to or/i }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ op: 'or' }),
    );
  });

  test('add clause appends an empty clause slot', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const ast: PredicateExpr = {
      op: 'and',
      args: [makeEq('name', 'a')],
    };
    render(
      <AdvancedAstBuilder
        value={ast}
        onChange={onChange}
        refSources={refSources}
        schemaByRef={schemaByRef}
      />,
    );
    await user.click(screen.getByRole('button', { name: /add clause/i }));
    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0][0] as { op: string; args: unknown[] };
    expect(next.op).toBe('and');
    expect(next.args.length).toBe(2);
  });

  test('not node renders its inner child and an unwrap button', () => {
    const ast: PredicateExpr = {
      op: 'not',
      args: [makeEq('name', 'a')],
    } as unknown as PredicateExpr;
    render(
      <AdvancedAstBuilder
        value={ast}
        onChange={vi.fn()}
        refSources={refSources}
        schemaByRef={schemaByRef}
      />,
    );
    expect(screen.getByRole('button', { name: /unwrap not/i })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: /operator/i })).toBeInTheDocument();
  });

  test('unwrap NOT emits the inner predicate', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const inner = makeEq('name', 'a');
    const ast: PredicateExpr = { op: 'not', args: [inner] } as unknown as PredicateExpr;
    render(
      <AdvancedAstBuilder
        value={ast}
        onChange={onChange}
        refSources={refSources}
        schemaByRef={schemaByRef}
      />,
    );
    await user.click(screen.getByRole('button', { name: /unwrap not/i }));
    expect(onChange).toHaveBeenCalledWith(inner);
  });

  test('child row exposes "Wrap in NOT" and wraps the child', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const ast: PredicateExpr = {
      op: 'and',
      args: [makeEq('name', 'a'), makeEq('name', 'b')],
    };
    render(
      <AdvancedAstBuilder
        value={ast}
        onChange={onChange}
        refSources={refSources}
        schemaByRef={schemaByRef}
      />,
    );
    const wraps = screen.getAllByRole('button', { name: /wrap in not/i });
    await user.click(wraps[0]);
    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0][0] as { op: string; args: { op: string }[] };
    expect(next.op).toBe('and');
    expect((next.args[0] as { op: string }).op).toBe('not');
  });

  test('child row delete removes that child', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const ast: PredicateExpr = {
      op: 'and',
      args: [makeEq('name', 'a'), makeEq('name', 'b')],
    };
    render(
      <AdvancedAstBuilder
        value={ast}
        onChange={onChange}
        refSources={refSources}
        schemaByRef={schemaByRef}
      />,
    );
    const deletes = screen.getAllByRole('button', { name: /^delete clause$/i });
    await user.click(deletes[0]);
    const next = onChange.mock.calls[0][0] as { args: unknown[] };
    expect(next.args.length).toBe(1);
  });

  test('root AND has no delete button', () => {
    const ast: PredicateExpr = {
      op: 'and',
      args: [makeEq('name', 'a')],
    };
    render(
      <AdvancedAstBuilder
        value={ast}
        onChange={vi.fn()}
        refSources={refSources}
        schemaByRef={schemaByRef}
      />,
    );
    // Only per-child deletes, not a root delete
    const deletes = screen.queryAllByRole('button', { name: /delete group/i });
    expect(deletes.length).toBe(0);
  });

  test('wrap child in AND nests it into a group', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const ast: PredicateExpr = {
      op: 'or',
      args: [makeEq('name', 'a'), makeEq('name', 'b')],
    };
    render(
      <AdvancedAstBuilder
        value={ast}
        onChange={onChange}
        refSources={refSources}
        schemaByRef={schemaByRef}
      />,
    );
    const wraps = screen.getAllByRole('button', { name: /wrap in and/i });
    await user.click(wraps[0]);
    const next = onChange.mock.calls[0][0] as { args: { op: string; args: unknown[] }[] };
    expect(next.args[0].op).toBe('and');
    expect(next.args[0].args.length).toBe(1);
  });
});

// Silence unused
void within;
