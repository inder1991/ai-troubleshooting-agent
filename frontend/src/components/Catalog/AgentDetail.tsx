import React, { useEffect, useState } from 'react';
import type { CatalogAgentDetail } from '../../types';
import { getAgent } from '../../services/catalog';
import JsonSchemaTree from './JsonSchemaTree';

const AgentDetail: React.FC<{ name: string }> = ({ name }) => {
  const [detail, setDetail] = useState<CatalogAgentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    setDetail(null);
    setError(null);
    getAgent(name, ctrl.signal)
      .then(setDetail)
      .catch((e) => {
        if (ctrl.signal.aborted) return;
        setError(String(e));
      });
    return () => ctrl.abort();
  }, [name]);

  if (error) return <div className="text-red-400">Error: {error}</div>;
  if (!detail) return <div className="text-wr-muted">Loading…</div>;

  return (
    <article className="max-w-3xl">
      <header className="mb-6">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold text-wr-text">{detail.name}</h2>
          <span className="px-2 py-0.5 rounded bg-wr-surface text-xs text-wr-muted">
            v{detail.version}
          </span>
          <span className="px-2 py-0.5 rounded bg-wr-surface text-xs text-wr-muted">
            {detail.category}
          </span>
        </div>
        <p className="mt-2 text-wr-text">{detail.description}</p>
        {detail.cost_hint && (
          <p className="mt-1 text-xs text-wr-muted">
            ~{detail.cost_hint.llm_calls} LLM calls · ~
            {detail.cost_hint.typical_duration_s}s typical
          </p>
        )}
      </header>

      <section className="mb-6">
        <h3 className="text-sm font-medium text-wr-text mb-2">Inputs</h3>
        <JsonSchemaTree schema={detail.input_schema} />
      </section>

      <section className="mb-6">
        <h3 className="text-sm font-medium text-wr-text mb-2">Outputs</h3>
        <JsonSchemaTree schema={detail.output_schema} />
      </section>

      <section className="mb-6">
        <h3 className="text-sm font-medium text-wr-text mb-2">Trigger examples</h3>
        <ul className="list-disc pl-5 text-sm text-wr-text">
          {detail.trigger_examples.map((t, i) => (
            <li key={i}>{t}</li>
          ))}
        </ul>
      </section>

      <section className="mb-6">
        <h3 className="text-sm font-medium text-wr-text mb-2">Runtime</h3>
        <dl className="text-sm grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
          <dt className="text-wr-muted">Timeout</dt>
          <dd>{detail.timeout_seconds}s</dd>
          <dt className="text-wr-muted">Retries on</dt>
          <dd>{detail.retry_on.length ? detail.retry_on.join(', ') : '—'}</dd>
        </dl>
      </section>

      <button
        disabled
        title="Workflow builder arrives in Phase 3"
        className="px-3 py-1.5 rounded bg-wr-surface text-wr-muted cursor-not-allowed text-sm"
      >
        Use in workflow
      </button>
    </article>
  );
};

export default AgentDetail;
