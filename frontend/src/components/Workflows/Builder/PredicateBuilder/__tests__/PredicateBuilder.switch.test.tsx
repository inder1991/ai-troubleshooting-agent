import { describe, expect, test, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PredicateBuilder } from '../index';
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
      },
    },
  },
];

const schemaByRef = () => undefined;

function simpleEq(v: string): PredicateExpr {
  return {
    op: 'eq',
    args: [{ ref: { from: 'input', path: 'name' } }, { literal: v }],
  } as unknown as PredicateExpr;
}

describe('PredicateBuilder mode switch', () => {
  test('defaults to Simple when no value is provided', () => {
    render(
      <PredicateBuilder
        onChange={vi.fn()}
        refSources={refSources}
        schemaByRef={schemaByRef}
      />,
    );
    const simpleBtn = screen.getByRole('button', { name: /^simple$/i });
    expect(simpleBtn).toHaveAttribute('aria-pressed', 'true');
  });

  test('defaults to Simple when value is a single eq clause', () => {
    render(
      <PredicateBuilder
        value={simpleEq('a')}
        onChange={vi.fn()}
        refSources={refSources}
        schemaByRef={schemaByRef}
      />,
    );
    const simpleBtn = screen.getByRole('button', { name: /^simple$/i });
    expect(simpleBtn).toHaveAttribute('aria-pressed', 'true');
  });

  test('defaults to Advanced when value is compound (and)', () => {
    const ast: PredicateExpr = { op: 'and', args: [simpleEq('a'), simpleEq('b')] };
    render(
      <PredicateBuilder
        value={ast}
        onChange={vi.fn()}
        refSources={refSources}
        schemaByRef={schemaByRef}
      />,
    );
    const advBtn = screen.getByRole('button', { name: /^advanced$/i });
    expect(advBtn).toHaveAttribute('aria-pressed', 'true');
  });

  test('Simple → Advanced wraps single clause in AND group', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <PredicateBuilder
        value={simpleEq('a')}
        onChange={onChange}
        refSources={refSources}
        schemaByRef={schemaByRef}
      />,
    );
    await user.click(screen.getByRole('button', { name: /^advanced$/i }));
    // Wrapped into and with one arg
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ op: 'and' }),
    );
    const next = onChange.mock.calls[0][0] as { args: unknown[] };
    expect(next.args.length).toBe(1);
  });

  test('Advanced → Simple allowed when AST reduces to a single leaf', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const ast: PredicateExpr = { op: 'and', args: [simpleEq('a')] };
    render(
      <PredicateBuilder
        value={ast}
        onChange={onChange}
        refSources={refSources}
        schemaByRef={schemaByRef}
      />,
    );
    // starts in Advanced
    await user.click(screen.getByRole('button', { name: /^simple$/i }));
    expect(onChange).toHaveBeenCalledWith(simpleEq('a'));
  });

  test('Advanced → Simple shows banner when AST is compound', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const ast: PredicateExpr = { op: 'and', args: [simpleEq('a'), simpleEq('b')] };
    render(
      <PredicateBuilder
        value={ast}
        onChange={onChange}
        refSources={refSources}
        schemaByRef={schemaByRef}
      />,
    );
    await user.click(screen.getByRole('button', { name: /^simple$/i }));
    // Stays in advanced; shows inline banner
    expect(
      screen.getByText(/cannot be represented as a simple predicate/i),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /stay in advanced/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /reset to simple/i })).toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });

  test('Reset to simple clears AST', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const ast: PredicateExpr = { op: 'and', args: [simpleEq('a'), simpleEq('b')] };
    render(
      <PredicateBuilder
        value={ast}
        onChange={onChange}
        refSources={refSources}
        schemaByRef={schemaByRef}
      />,
    );
    await user.click(screen.getByRole('button', { name: /^simple$/i }));
    await user.click(screen.getByRole('button', { name: /reset to simple/i }));
    expect(onChange).toHaveBeenCalledWith(undefined);
  });

  test('Stay in advanced dismisses the banner', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const ast: PredicateExpr = { op: 'and', args: [simpleEq('a'), simpleEq('b')] };
    render(
      <PredicateBuilder
        value={ast}
        onChange={onChange}
        refSources={refSources}
        schemaByRef={schemaByRef}
      />,
    );
    await user.click(screen.getByRole('button', { name: /^simple$/i }));
    await user.click(screen.getByRole('button', { name: /stay in advanced/i }));
    expect(
      screen.queryByText(/cannot be represented as a simple predicate/i),
    ).not.toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });
});
