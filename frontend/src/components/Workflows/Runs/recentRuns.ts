import type { RunStatus } from '../../../types';

const STORAGE_KEY = 'wf-recent-runs';
const MAX_ENTRIES = 50;

export interface RecentRunEntry {
  runId: string;
  workflowId: string;
  workflowName?: string;
  status: RunStatus;
  startedAt: string;
}

function readStore(): RecentRunEntry[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    return JSON.parse(raw) as RecentRunEntry[];
  } catch {
    return [];
  }
}

function writeStore(entries: RecentRunEntry[]): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
  } catch {
    // ignore
  }
}

export function addRecentRun(entry: RecentRunEntry): void {
  const list = readStore().filter((e) => e.runId !== entry.runId);
  list.unshift(entry);
  writeStore(list.slice(0, MAX_ENTRIES));
}

export function getRecentRuns(): RecentRunEntry[] {
  return readStore();
}

export function updateRunStatus(runId: string, status: RunStatus): void {
  const list = readStore();
  const idx = list.findIndex((e) => e.runId === runId);
  if (idx >= 0) {
    list[idx] = { ...list[idx], status };
    writeStore(list);
  }
}
