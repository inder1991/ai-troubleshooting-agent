import { describe, expect, test, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { VersionSwitcher } from '../VersionSwitcher';
import type { VersionSummary } from '../../../../types';

const mkV = (version: number): VersionSummary => ({
  version_id: `vid-${version}`,
  workflow_id: 'wf-1',
  version,
  created_at: '2026-04-10T12:00:00Z',
});

describe('VersionSwitcher', () => {
  test('renders empty state when versions is empty', () => {
    render(
      <VersionSwitcher
        versions={[]}
        onSelect={vi.fn()}
        onFork={vi.fn()}
      />,
    );
    expect(screen.getByText(/no versions yet/i)).toBeInTheDocument();
  });

  test('dropdown lists all versions in desc order with Active badge on active version', () => {
    render(
      <VersionSwitcher
        versions={[mkV(1), mkV(3), mkV(2)]}
        activeVersion={3}
        selectedVersion={3}
        onSelect={vi.fn()}
        onFork={vi.fn()}
      />,
    );
    const select = screen.getByRole('combobox') as HTMLSelectElement;
    const opts = Array.from(select.options).map((o) => o.textContent ?? '');
    expect(opts[0]).toMatch(/v3/);
    expect(opts[1]).toMatch(/v2/);
    expect(opts[2]).toMatch(/v1/);
    // v3 row should include "Active"
    expect(opts[0]).toMatch(/active/i);
    expect(opts[1]).not.toMatch(/active/i);
  });

  test('selecting a dropdown option calls onSelect with that version', () => {
    const onSelect = vi.fn();
    render(
      <VersionSwitcher
        versions={[mkV(1), mkV(2)]}
        activeVersion={2}
        selectedVersion={2}
        onSelect={onSelect}
        onFork={vi.fn()}
      />,
    );
    const select = screen.getByRole('combobox');
    fireEvent.change(select, { target: { value: '1' } });
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith(1);
  });

  test('Edit button calls onFork(selectedVersion)', () => {
    const onFork = vi.fn();
    render(
      <VersionSwitcher
        versions={[mkV(1), mkV(2)]}
        activeVersion={2}
        selectedVersion={2}
        onSelect={vi.fn()}
        onFork={onFork}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /edit/i }));
    expect(onFork).toHaveBeenCalledTimes(1);
    expect(onFork).toHaveBeenCalledWith(2);
  });

  test('View button calls onSelect(selectedVersion)', () => {
    const onSelect = vi.fn();
    render(
      <VersionSwitcher
        versions={[mkV(1), mkV(2)]}
        activeVersion={2}
        selectedVersion={1}
        onSelect={onSelect}
        onFork={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /^view$/i }));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith(1);
  });

  test('baseVersion subhead only appears when defined', () => {
    const { rerender } = render(
      <VersionSwitcher
        versions={[mkV(1), mkV(2)]}
        activeVersion={2}
        selectedVersion={2}
        onSelect={vi.fn()}
        onFork={vi.fn()}
      />,
    );
    expect(screen.queryByText(/editing new version/i)).not.toBeInTheDocument();
    rerender(
      <VersionSwitcher
        versions={[mkV(1), mkV(2)]}
        activeVersion={2}
        selectedVersion={2}
        baseVersion={1}
        onSelect={vi.fn()}
        onFork={vi.fn()}
      />,
    );
    expect(screen.getByText(/editing new version \(based on v1\)/i)).toBeInTheDocument();
  });

  test('disabled prop disables View and Edit buttons', () => {
    render(
      <VersionSwitcher
        versions={[mkV(1)]}
        activeVersion={1}
        selectedVersion={1}
        onSelect={vi.fn()}
        onFork={vi.fn()}
        disabled
      />,
    );
    expect(screen.getByRole('button', { name: /^view$/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /edit/i })).toBeDisabled();
  });
});
