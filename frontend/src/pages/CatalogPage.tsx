import React, { useEffect, useState } from 'react';
import type { CatalogAgentSummary } from '../types';
import { listAgents, CatalogDisabledError } from '../services/catalog';
import AgentDetail from '../components/Catalog/AgentDetail';

const CatalogPage: React.FC = () => {
  const [agents, setAgents] = useState<CatalogAgentSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    listAgents(ctrl.signal)
      .then((a) => {
        setAgents(a);
        setSelected(a[0]?.name ?? null);
      })
      .catch((e) => {
        if (ctrl.signal.aborted) return;
        setError(e instanceof CatalogDisabledError ? 'disabled' : String(e));
      });
    return () => ctrl.abort();
  }, []);

  if (error === 'disabled') {
    return (
      <div className="p-8 text-wr-muted">
        The agent catalog is not enabled in this environment.
      </div>
    );
  }
  if (error) return <div className="p-8 text-red-400">Error: {error}</div>;
  if (!agents) return <div className="p-8 text-wr-muted">Loading agents…</div>;

  return (
    <div className="flex h-full">
      <aside
        className="w-80 border-r border-wr-border overflow-auto"
        aria-label="Agent list"
      >
        <header className="px-4 py-3 border-b border-wr-border">
          <h1 className="text-sm font-medium text-wr-text">Agent Catalog</h1>
          <p className="text-xs text-wr-muted">{agents.length} agents</p>
        </header>
        <ul>
          {agents.map((a) => (
            <li key={a.name}>
              <button
                className={`w-full text-left px-4 py-2 hover:bg-wr-surface-hover ${
                  selected === a.name ? 'bg-wr-surface-hover' : ''
                }`}
                onClick={() => setSelected(a.name)}
              >
                <div className="text-sm text-wr-text">{a.name}</div>
                <div className="text-xs text-wr-muted">
                  {a.category} · v{a.version}
                </div>
              </button>
            </li>
          ))}
        </ul>
      </aside>
      <main className="flex-1 overflow-auto p-6">
        {selected ? (
          <AgentDetail name={selected} />
        ) : (
          <div className="text-wr-muted">Select an agent.</div>
        )}
      </main>
    </div>
  );
};

export default CatalogPage;
