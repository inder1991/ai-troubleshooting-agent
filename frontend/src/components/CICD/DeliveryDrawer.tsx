import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { DeliveryItem } from '../../types';
import { getCICDCommitDetail } from '../../services/api';

interface DeliveryDrawerProps {
  item: DeliveryItem | null;
  onClose: () => void;
}

type DrawerTab = 'commit' | 'diff' | 'related';

const FILE_STATUS_CLASSES: Record<string, string> = {
  added: 'bg-emerald-500/20 text-emerald-200 border-emerald-500/40',
  modified: 'bg-wr-severity-medium/20 text-amber-200 border-amber-500/40',
  removed: 'bg-wr-severity-high/20 text-red-200 border-red-500/40',
  renamed: 'bg-sky-500/20 text-sky-200 border-sky-500/40',
};

const parseOwnerRepo = (gitRepo: string | null | undefined): { owner: string; repo: string } => {
  if (!gitRepo) return { owner: '', repo: '' };
  const parts = gitRepo.split('/').filter(Boolean);
  if (parts.length < 2) return { owner: '', repo: '' };
  return { owner: parts[parts.length - 2], repo: parts[parts.length - 1] };
};

export function DeliveryDrawer({ item, onClose }: DeliveryDrawerProps) {
  const [activeTab, setActiveTab] = useState<DrawerTab>('commit');

  useEffect(() => {
    if (item == null) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [item, onClose]);

  const kind = item?.kind;
  const { owner, repo } = parseOwnerRepo(item?.git_repo);
  const sha = item?.git_sha ?? '';

  const diffEnabled =
    activeTab === 'diff' && !!item && kind === 'commit' && !!owner && !!repo && !!sha;

  const {
    data: commitDetail,
    isLoading: diffLoading,
    error: diffError,
  } = useQuery({
    queryKey: ['cicd-commit', owner, repo, sha],
    queryFn: () => getCICDCommitDetail(owner, repo, sha),
    enabled: diffEnabled,
    staleTime: 60000,
  });

  if (!item) return null;

  const tabs: { id: DrawerTab; label: string }[] = [
    { id: 'commit', label: 'Commit' },
    { id: 'diff', label: 'Diff' },
    { id: 'related', label: 'Related' },
  ];

  const shortSha = item.git_sha ? item.git_sha.slice(0, 8) : '—';
  const timestampLocal = (() => {
    try {
      return new Date(item.timestamp).toLocaleString();
    } catch {
      return item.timestamp;
    }
  })();

  return (
    <div className="fixed inset-y-0 right-0 w-[520px] max-w-[90vw] bg-zinc-950 border-l border-zinc-800 shadow-2xl z-50 flex flex-col">
      <div className="flex justify-between items-center px-4 py-3 border-b border-zinc-800">
        <h2 className="text-sm font-semibold text-zinc-100 truncate pr-3" title={item.title}>
          {item.title}
        </h2>
        <button
          type="button"
          onClick={onClose}
          className="text-zinc-400 hover:text-zinc-100 text-xl leading-none"
          aria-label="Close"
        >
          ×
        </button>
      </div>

      <div className="flex border-b border-zinc-800">
        {tabs.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 text-xs uppercase tracking-wider ${
                isActive
                  ? 'text-cyan-300 border-b-2 border-cyan-400'
                  : 'text-zinc-500 border-b-2 border-transparent'
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      <div className="flex-1 overflow-y-auto p-4 text-sm text-zinc-300">
        {activeTab === 'commit' && (
          <dl className="grid grid-cols-[120px_1fr] gap-y-1 gap-x-3">
            <dt className="text-zinc-500">Kind</dt>
            <dd>{item.kind}</dd>

            <dt className="text-zinc-500">Source</dt>
            <dd>{item.source}</dd>

            <dt className="text-zinc-500">Instance</dt>
            <dd>{item.source_instance}</dd>

            <dt className="text-zinc-500">Status</dt>
            <dd>{item.status}</dd>

            <dt className="text-zinc-500">Author</dt>
            <dd>{item.author ?? '—'}</dd>

            <dt className="text-zinc-500">Git SHA</dt>
            <dd className="font-mono text-xs">{shortSha}</dd>

            <dt className="text-zinc-500">Git Repo</dt>
            <dd>{item.git_repo ?? '—'}</dd>

            <dt className="text-zinc-500">Target</dt>
            <dd>{item.target ?? '—'}</dd>

            {item.duration_s != null && (
              <>
                <dt className="text-zinc-500">Duration</dt>
                <dd>{item.duration_s}s</dd>
              </>
            )}

            <dt className="text-zinc-500">Timestamp</dt>
            <dd>{timestampLocal}</dd>

            <dt className="text-zinc-500">Link</dt>
            <dd>
              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-cyan-300 underline"
              >
                Open
              </a>
            </dd>
          </dl>
        )}

        {activeTab === 'diff' && (
          <div>
            {item.kind !== 'commit' ? (
              <div className="text-zinc-500">Diff is only available for commits.</div>
            ) : !owner || !repo || !sha ? (
              <div className="text-zinc-500">Missing git repo or SHA.</div>
            ) : diffLoading ? (
              <div className="text-zinc-500">Loading diff…</div>
            ) : diffError ? (
              <div className="text-red-400">{(diffError as Error).message}</div>
            ) : commitDetail ? (
              <div className="space-y-4">
                <div>{commitDetail.message}</div>
                {commitDetail.files.map((file) => {
                  const chipClass =
                    FILE_STATUS_CLASSES[file.status] ??
                    'bg-zinc-500/20 text-zinc-200 border-zinc-500/40';
                  return (
                    <div key={file.filename} className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-zinc-400 font-mono">{file.filename}</span>
                        <span
                          className={`text-body-xs uppercase tracking-wider px-1.5 py-0.5 rounded border ${chipClass}`}
                        >
                          {file.status}
                        </span>
                        <span className="text-body-xs text-zinc-500">
                          +{file.additions}/-{file.deletions}
                        </span>
                      </div>
                      <pre className="text-body-xs text-zinc-400 whitespace-pre-wrap bg-zinc-900/50 p-2 rounded border border-zinc-800 overflow-x-auto">
                        {file.patch ?? '(no patch)'}
                      </pre>
                    </div>
                  );
                })}
              </div>
            ) : null}
          </div>
        )}

        {activeTab === 'related' && (
          <div className="text-zinc-500">Related events coming soon.</div>
        )}
      </div>
    </div>
  );
}

export default DeliveryDrawer;
