import { describe, expect, test, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SimplePredicate } from '../SimplePredicate';
import type { RefSource } from '../../RefPicker/RefPicker';
import { FROZEN_OPS } from '../predicateTypes';

const refSources: RefSource[] = [
  {
    kind: 'input',
    label: 'Input',
    schema: {
      type: 'object',
      properties: {
        name: { type: 'string' },
        active: { type: 'boolean' },
        count: { type: 'integer' },
      },
    },
  },
];

async function pickInputField(user: ReturnType<typeof userEvent.setup>, path: string) {
  await user.click(screen.getByRole('button', { name: /pick field/i }));
  // RefPicker single-source auto-skips to path step
  const pathInput = screen.getByRole('combobox', { name: /path/i });
  await user.type(pathInput, path);
  await user.click(screen.getByRole('button', { name: /select/i }));
}

describe('FROZEN_OPS', () => {
  test('does NOT include gt/gte/lt/lte', () => {
    expect(FROZEN_OPS).not.toContain('gt');
    expect(FROZEN_OPS).not.toContain('gte');
    expect(FROZEN_OPS).not.toContain('lt');
    expect(FROZEN_OPS).not.toContain('lte');
  });
  test('includes exactly the allowed ops', () => {
    expect(FROZEN_OPS.sort()).toEqual(
      ['contains', 'eq', 'exists', 'neq', 'not_contains', 'not_exists'].sort(),
    );
  });
});

describe('SimplePredicate', () => {
  test('submission disabled until field + op + value are filled (non-exists)', async () => {
    const user = userEvent.setup();
    render(
      <SimplePredicate onChange={vi.fn()} refSources={refSources} />,
    );
    const apply = screen.getByRole('button', { name: /apply/i });
    expect(apply).toBeDisabled();
    await pickInputField(user, 'name');
    expect(apply).toBeDisabled();
    await user.selectOptions(
      screen.getByRole('combobox', { name: /operator/i }),
      'eq',
    );
    expect(apply).toBeDisabled();
    await user.type(screen.getByRole('textbox', { name: /value/i }), 'x');
    expect(apply).not.toBeDisabled();
  });

  test('string field offers eq/neq/contains/not_contains/exists/not_exists', async () => {
    const user = userEvent.setup();
    render(<SimplePredicate onChange={vi.fn()} refSources={refSources} />);
    await pickInputField(user, 'name');
    const sel = screen.getByRole('combobox', { name: /operator/i }) as HTMLSelectElement;
    const opts = Array.from(sel.options).map((o) => o.value).filter(Boolean).sort();
    expect(opts).toEqual(
      ['contains', 'eq', 'exists', 'neq', 'not_contains', 'not_exists'].sort(),
    );
  });

  test('boolean field restricts operators to eq/neq and exists/not_exists', async () => {
    const user = userEvent.setup();
    render(<SimplePredicate onChange={vi.fn()} refSources={refSources} />);
    await pickInputField(user, 'active');
    const sel = screen.getByRole('combobox', { name: /operator/i }) as HTMLSelectElement;
    const opts = Array.from(sel.options).map((o) => o.value).filter(Boolean).sort();
    expect(opts).toEqual(['eq', 'exists', 'neq', 'not_exists'].sort());
  });

  test('eq emits {op:eq, args:[ref, {literal:value}]}', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<SimplePredicate onChange={onChange} refSources={refSources} />);
    await pickInputField(user, 'name');
    await user.selectOptions(
      screen.getByRole('combobox', { name: /operator/i }),
      'eq',
    );
    await user.type(screen.getByRole('textbox', { name: /value/i }), 'alice');
    await user.click(screen.getByRole('button', { name: /apply/i }));
    expect(onChange).toHaveBeenCalledWith({
      op: 'eq',
      args: [
        { ref: { from: 'input', path: 'name' } },
        { literal: 'alice' },
      ],
    });
  });

  test('neq wraps eq in not', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<SimplePredicate onChange={onChange} refSources={refSources} />);
    await pickInputField(user, 'name');
    await user.selectOptions(
      screen.getByRole('combobox', { name: /operator/i }),
      'neq',
    );
    await user.type(screen.getByRole('textbox', { name: /value/i }), 'bob');
    await user.click(screen.getByRole('button', { name: /apply/i }));
    expect(onChange).toHaveBeenCalledWith({
      op: 'not',
      args: [
        {
          op: 'eq',
          args: [
            { ref: { from: 'input', path: 'name' } },
            { literal: 'bob' },
          ],
        },
      ],
    });
  });

  test('contains emits in with literal first, ref second', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<SimplePredicate onChange={onChange} refSources={refSources} />);
    await pickInputField(user, 'name');
    await user.selectOptions(
      screen.getByRole('combobox', { name: /operator/i }),
      'contains',
    );
    await user.type(screen.getByRole('textbox', { name: /value/i }), 'al');
    await user.click(screen.getByRole('button', { name: /apply/i }));
    expect(onChange).toHaveBeenCalledWith({
      op: 'in',
      args: [
        { literal: 'al' },
        { ref: { from: 'input', path: 'name' } },
      ],
    });
  });

  test('not_contains wraps in with not', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<SimplePredicate onChange={onChange} refSources={refSources} />);
    await pickInputField(user, 'name');
    await user.selectOptions(
      screen.getByRole('combobox', { name: /operator/i }),
      'not_contains',
    );
    await user.type(screen.getByRole('textbox', { name: /value/i }), 'x');
    await user.click(screen.getByRole('button', { name: /apply/i }));
    expect(onChange).toHaveBeenCalledWith({
      op: 'not',
      args: [
        {
          op: 'in',
          args: [
            { literal: 'x' },
            { ref: { from: 'input', path: 'name' } },
          ],
        },
      ],
    });
  });

  test('exists omits value input and emits exists AST', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<SimplePredicate onChange={onChange} refSources={refSources} />);
    await pickInputField(user, 'name');
    await user.selectOptions(
      screen.getByRole('combobox', { name: /operator/i }),
      'exists',
    );
    expect(screen.queryByRole('textbox', { name: /value/i })).not.toBeInTheDocument();
    const apply = screen.getByRole('button', { name: /apply/i });
    expect(apply).not.toBeDisabled();
    await user.click(apply);
    expect(onChange).toHaveBeenCalledWith({
      op: 'exists',
      args: [{ ref: { from: 'input', path: 'name' } }],
    });
  });

  test('not_exists wraps exists in not', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<SimplePredicate onChange={onChange} refSources={refSources} />);
    await pickInputField(user, 'name');
    await user.selectOptions(
      screen.getByRole('combobox', { name: /operator/i }),
      'not_exists',
    );
    await user.click(screen.getByRole('button', { name: /apply/i }));
    expect(onChange).toHaveBeenCalledWith({
      op: 'not',
      args: [
        {
          op: 'exists',
          args: [{ ref: { from: 'input', path: 'name' } }],
        },
      ],
    });
  });
});
