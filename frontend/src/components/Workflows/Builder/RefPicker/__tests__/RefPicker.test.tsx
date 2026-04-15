import { describe, expect, test, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RefPicker } from '../RefPicker';
import type { RefSource } from '../RefPicker';

const sources: RefSource[] = [
  {
    kind: 'input',
    label: 'Workflow Input',
    schema: {
      type: 'object',
      properties: {
        ticket_id: { type: 'string' },
        user: {
          type: 'object',
          properties: { name: { type: 'string' } },
        },
      },
    },
  },
  {
    kind: 'node',
    nodeId: 'step-1',
    label: 'step-1 (agent-a)',
    schema: {
      type: 'object',
      properties: {
        summary: { type: 'string' },
        score: { type: 'number' },
      },
    },
  },
  {
    kind: 'env',
    label: 'Environment',
    schema: { type: 'object', properties: { region: { type: 'string' } } },
  },
];

describe('RefPicker', () => {
  test('step 1 renders source radio list', () => {
    render(
      <RefPicker sources={sources} onChange={vi.fn()} onClose={vi.fn()} />,
    );
    expect(screen.getByRole('radio', { name: /Workflow Input/i })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /step-1/i })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /Environment/i })).toBeInTheDocument();
  });

  test('emits input RefExpr with structured ref', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <RefPicker sources={sources} onChange={onChange} onClose={vi.fn()} />,
    );
    await user.click(screen.getByRole('radio', { name: /Workflow Input/i }));
    await user.click(screen.getByRole('button', { name: /next/i }));
    const input = screen.getByRole('combobox', { name: /path/i });
    await user.type(input, 'ticket_id');
    await user.click(screen.getByRole('button', { name: /select|use|confirm/i }));
    expect(onChange).toHaveBeenCalledWith({
      ref: { from: 'input', path: 'ticket_id' },
    });
  });

  test('emits node RefExpr with output.-prefixed path', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <RefPicker sources={sources} onChange={onChange} onClose={vi.fn()} />,
    );
    await user.click(screen.getByRole('radio', { name: /step-1/i }));
    await user.click(screen.getByRole('button', { name: /next/i }));
    const input = screen.getByRole('combobox', { name: /path/i });
    await user.type(input, 'summary');
    await user.click(screen.getByRole('button', { name: /select|use|confirm/i }));
    expect(onChange).toHaveBeenCalledWith({
      ref: { from: 'node', node_id: 'step-1', path: 'output.summary' },
    });
  });

  test('emits env RefExpr', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <RefPicker sources={sources} onChange={onChange} onClose={vi.fn()} />,
    );
    await user.click(screen.getByRole('radio', { name: /Environment/i }));
    await user.click(screen.getByRole('button', { name: /next/i }));
    const input = screen.getByRole('combobox', { name: /path/i });
    await user.type(input, 'region');
    await user.click(screen.getByRole('button', { name: /select|use|confirm/i }));
    expect(onChange).toHaveBeenCalledWith({
      ref: { from: 'env', path: 'region' },
    });
  });

  test('path autocomplete filters suggestions by substring', async () => {
    const user = userEvent.setup();
    render(
      <RefPicker sources={sources} onChange={vi.fn()} onClose={vi.fn()} />,
    );
    await user.click(screen.getByRole('radio', { name: /Workflow Input/i }));
    await user.click(screen.getByRole('button', { name: /next/i }));
    const input = screen.getByRole('combobox', { name: /path/i });
    await user.type(input, 'user');
    expect(screen.getByRole('option', { name: /user\.name/ })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /ticket_id/ })).not.toBeInTheDocument();
  });

  test('keyboard arrow+enter selects suggestion', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <RefPicker sources={sources} onChange={onChange} onClose={vi.fn()} />,
    );
    await user.click(screen.getByRole('radio', { name: /Workflow Input/i }));
    await user.click(screen.getByRole('button', { name: /next/i }));
    const input = screen.getByRole('combobox', { name: /path/i });
    await user.click(input);
    await user.keyboard('{ArrowDown}{Enter}');
    // Something should be filled in
    expect((input as HTMLInputElement).value.length).toBeGreaterThan(0);
    await user.click(screen.getByRole('button', { name: /select|use|confirm/i }));
    expect(onChange).toHaveBeenCalled();
  });

  test('escape closes the picker', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(
      <RefPicker sources={sources} onChange={vi.fn()} onClose={onClose} />,
    );
    await user.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalled();
  });

  test('back button returns from path step to source step', async () => {
    const user = userEvent.setup();
    render(
      <RefPicker sources={sources} onChange={vi.fn()} onClose={vi.fn()} />,
    );
    await user.click(screen.getByRole('radio', { name: /Workflow Input/i }));
    await user.click(screen.getByRole('button', { name: /next/i }));
    expect(screen.getByRole('combobox', { name: /path/i })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /back/i }));
    expect(screen.getByRole('radio', { name: /Workflow Input/i })).toBeInTheDocument();
  });
});
