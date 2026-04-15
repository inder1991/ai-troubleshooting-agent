import { describe, expect, test, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { InputMappingField } from '../InputMappingField';
import type { RefSource } from '../../RefPicker/RefPicker';
import type { MappingExpr } from '../../../../../types';

const refSources: RefSource[] = [
  {
    kind: 'input',
    label: 'Input',
    schema: { type: 'object', properties: { ticket: { type: 'string' } } },
  },
  {
    kind: 'node',
    nodeId: 'step-1',
    label: 'step-1',
    schema: { type: 'object', properties: { result: { type: 'string' } } },
  },
  {
    kind: 'env',
    label: 'Env',
    schema: { type: 'object', properties: { region: { type: 'string' } } },
  },
];

describe('InputMappingField', () => {
  test('renders mode toggle with 4 visible modes (Transform under Advanced)', () => {
    render(
      <InputMappingField
        fieldName="foo"
        fieldSchema={{ type: 'string' }}
        onChange={vi.fn()}
        refSources={refSources}
      />,
    );
    expect(screen.getByRole('button', { name: /^literal$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^input$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^node$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^env$/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^transform$/i })).not.toBeInTheDocument();
  });

  test('literal string mode emits {literal: value}', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <InputMappingField
        fieldName="foo"
        fieldSchema={{ type: 'string' }}
        onChange={onChange}
        refSources={refSources}
      />,
    );
    const input = screen.getByRole('textbox', { name: /foo/i });
    await user.type(input, 'hi');
    const last = onChange.mock.calls.at(-1)?.[0] as MappingExpr;
    expect(last).toEqual({ literal: 'hi' });
  });

  test('literal boolean mode emits {literal: true|false}', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <InputMappingField
        fieldName="flag"
        fieldSchema={{ type: 'boolean' }}
        onChange={onChange}
        refSources={refSources}
      />,
    );
    await user.click(screen.getByRole('checkbox', { name: /flag/i }));
    expect(onChange).toHaveBeenLastCalledWith({ literal: true });
  });

  test('literal integer mode emits numeric literal', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <InputMappingField
        fieldName="n"
        fieldSchema={{ type: 'integer' }}
        onChange={onChange}
        refSources={refSources}
      />,
    );
    const spin = screen.getByRole('spinbutton', { name: /n/i });
    await user.type(spin, '42');
    expect(onChange).toHaveBeenLastCalledWith({ literal: 42 });
  });

  test('literal enum mode uses select', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <InputMappingField
        fieldName="color"
        fieldSchema={{ type: 'string', enum: ['red', 'green'] }}
        onChange={onChange}
        refSources={refSources}
      />,
    );
    await user.selectOptions(
      screen.getByRole('combobox', { name: /color/i }),
      'green',
    );
    expect(onChange).toHaveBeenLastCalledWith({ literal: 'green' });
  });

  test('Input mode opens RefPicker restricted to input and emits ref', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <InputMappingField
        fieldName="foo"
        fieldSchema={{ type: 'string' }}
        onChange={onChange}
        refSources={refSources}
      />,
    );
    await user.click(screen.getByRole('button', { name: /^input$/i }));
    // Only one source (input) so we skip to path
    const pathInput = screen.getByRole('combobox', { name: /path/i });
    await user.type(pathInput, 'ticket');
    await user.click(screen.getByRole('button', { name: /select/i }));
    expect(onChange).toHaveBeenLastCalledWith({
      ref: { from: 'input', path: 'ticket' },
    });
  });

  test('Node mode opens RefPicker restricted to node kind', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <InputMappingField
        fieldName="foo"
        fieldSchema={{ type: 'string' }}
        onChange={onChange}
        refSources={refSources}
      />,
    );
    await user.click(screen.getByRole('button', { name: /^node$/i }));
    const pathInput = screen.getByRole('combobox', { name: /path/i });
    await user.type(pathInput, 'result');
    await user.click(screen.getByRole('button', { name: /select/i }));
    expect(onChange).toHaveBeenLastCalledWith({
      ref: { from: 'node', node_id: 'step-1', path: 'output.result' },
    });
  });

  test('Advanced disclosure reveals Transform mode', async () => {
    const user = userEvent.setup();
    render(
      <InputMappingField
        fieldName="foo"
        fieldSchema={{ type: 'string' }}
        onChange={vi.fn()}
        refSources={refSources}
      />,
    );
    await user.click(screen.getByRole('button', { name: /advanced/i }));
    expect(screen.getByRole('button', { name: /^transform$/i })).toBeInTheDocument();
  });

  test('Transform mode emits coalesce AST', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <InputMappingField
        fieldName="foo"
        fieldSchema={{ type: 'string' }}
        onChange={onChange}
        refSources={refSources}
      />,
    );
    await user.click(screen.getByRole('button', { name: /advanced/i }));
    await user.click(screen.getByRole('button', { name: /^transform$/i }));
    // op select defaults to coalesce; set explicitly
    await user.selectOptions(
      screen.getByRole('combobox', { name: /transform op/i }),
      'coalesce',
    );
    // add first arg as literal "x"
    await user.click(screen.getByRole('button', { name: /add arg/i }));
    const argInputs = screen.getAllByRole('textbox', { name: /arg 0/i });
    await user.type(argInputs[0], 'x');
    const last = onChange.mock.calls.at(-1)?.[0] as MappingExpr;
    expect(last).toEqual({ op: 'coalesce', args: [{ literal: 'x' }] });
  });

  test('Transform op select only offers coalesce and concat', async () => {
    const user = userEvent.setup();
    render(
      <InputMappingField
        fieldName="foo"
        fieldSchema={{ type: 'string' }}
        onChange={vi.fn()}
        refSources={refSources}
      />,
    );
    await user.click(screen.getByRole('button', { name: /advanced/i }));
    await user.click(screen.getByRole('button', { name: /^transform$/i }));
    const sel = screen.getByRole('combobox', { name: /transform op/i }) as HTMLSelectElement;
    const opts = Array.from(sel.options).map((o) => o.value).sort();
    expect(opts).toEqual(['coalesce', 'concat']);
  });
});
