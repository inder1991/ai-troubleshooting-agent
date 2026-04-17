import { describe, expect, test, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MappingModeToggle } from '../MappingModeToggle';
import type { MappingMode } from '../MappingModeToggle';

describe('MappingModeToggle', () => {
  test('renders buttons for the four default modes', () => {
    render(<MappingModeToggle mode="literal" onChange={vi.fn()} />);

    expect(screen.getByRole('button', { name: 'Literal' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Input' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Node' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Env' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Transform' })).not.toBeInTheDocument();
  });

  test('renders Transform button when showTransform is true', () => {
    render(<MappingModeToggle mode="literal" onChange={vi.fn()} showTransform />);

    expect(screen.getByRole('button', { name: 'Transform' })).toBeInTheDocument();
  });

  test('marks the active mode button with aria-pressed="true"', () => {
    render(<MappingModeToggle mode="node" onChange={vi.fn()} />);

    expect(screen.getByRole('button', { name: 'Node' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Literal' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: 'Input' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: 'Env' })).toHaveAttribute('aria-pressed', 'false');
  });

  test('clicking a mode button calls onChange with that mode', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();

    render(<MappingModeToggle mode="literal" onChange={onChange} />);

    await user.click(screen.getByRole('button', { name: 'Env' }));
    expect(onChange).toHaveBeenCalledWith('env');

    await user.click(screen.getByRole('button', { name: 'Node' }));
    expect(onChange).toHaveBeenCalledWith('node');
  });

  test('displays correct label text for each mode', () => {
    const modes: MappingMode[] = ['literal', 'input', 'node', 'env', 'transform'];
    const expectedLabels = ['Literal', 'Input', 'Node', 'Env', 'Transform'];

    render(<MappingModeToggle mode="literal" onChange={vi.fn()} showTransform />);

    const buttons = screen.getAllByRole('button');
    expect(buttons).toHaveLength(modes.length);
    buttons.forEach((btn, i) => {
      expect(btn).toHaveTextContent(expectedLabels[i]);
    });
  });

  test('has accessible group role with aria-label', () => {
    render(<MappingModeToggle mode="literal" onChange={vi.fn()} />);
    expect(screen.getByRole('group', { name: 'Mapping mode' })).toBeInTheDocument();
  });
});
