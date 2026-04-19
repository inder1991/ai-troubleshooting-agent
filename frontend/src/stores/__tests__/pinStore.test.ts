import { describe, it, expect, beforeEach } from 'vitest';
import { usePinStore } from '../pinStore';

const item = (id: string, label = 'Root Cause', code = 'L') => ({
  id,
  label,
  agentCode: code,
});

describe('pinStore', () => {
  beforeEach(() => {
    usePinStore.getState().clear();
  });

  it('starts empty', () => {
    const s = usePinStore.getState();
    expect(s.count()).toBe(0);
    expect(s.items()).toEqual([]);
  });

  it('pin adds an item', () => {
    usePinStore.getState().pin(item('root-cause'));
    expect(usePinStore.getState().count()).toBe(1);
    expect(usePinStore.getState().isPinned('root-cause')).toBe(true);
  });

  it('pin is idempotent', () => {
    usePinStore.getState().pin(item('root-cause'));
    usePinStore.getState().pin(item('root-cause'));
    expect(usePinStore.getState().count()).toBe(1);
  });

  it('unpin removes an item', () => {
    usePinStore.getState().pin(item('root-cause'));
    usePinStore.getState().unpin('root-cause');
    expect(usePinStore.getState().isPinned('root-cause')).toBe(false);
    expect(usePinStore.getState().count()).toBe(0);
  });

  it('toggle adds then removes', () => {
    const s = usePinStore.getState();
    s.toggle(item('metrics'));
    expect(s.isPinned('metrics')).toBe(true);
    // toggle again
    usePinStore.getState().toggle(item('metrics'));
    expect(usePinStore.getState().isPinned('metrics')).toBe(false);
  });

  it('preserves metadata on items()', () => {
    usePinStore.getState().pin(item('rc', 'NullPointer', 'L'));
    const items = usePinStore.getState().items();
    expect(items[0]).toEqual({ id: 'rc', label: 'NullPointer', agentCode: 'L' });
  });

  it('clear removes everything', () => {
    usePinStore.getState().pin(item('a'));
    usePinStore.getState().pin(item('b'));
    usePinStore.getState().clear();
    expect(usePinStore.getState().count()).toBe(0);
  });

  it('multiple sequential pins keep insertion order', () => {
    usePinStore.getState().pin(item('a'));
    usePinStore.getState().pin(item('b'));
    usePinStore.getState().pin(item('c'));
    expect(usePinStore.getState().items().map((p) => p.id)).toEqual(['a', 'b', 'c']);
  });
});
