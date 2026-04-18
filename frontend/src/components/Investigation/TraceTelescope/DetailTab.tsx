import React, { useState } from 'react';
import type { SpanInfo } from '../../../types';

interface DetailTabProps {
  span: SpanInfo | null;
  traceId: string;
  backendUrl?: string;
}

/**
 * Single-span detail panel. Shows tags, process_tags, events, error info,
 * and redaction provenance. The raw-JSON toggle is collapsed by default so
 * the panel reads scannable even for heavy spans.
 */
export default function DetailTab({ span, traceId, backendUrl }: DetailTabProps) {
  const [showRaw, setShowRaw] = useState(false);

  if (!span) {
    return (
      <div className="flex items-center justify-center h-full text-wr-text-muted">
        <p>Select a span from the Flow or Waterfall tab to see its details.</p>
      </div>
    );
  }

  const service = span.service_name || span.service;
  const op = span.operation_name || span.operation;
  const tagCount = Object.keys(span.tags || {}).length;
  const processTagCount = Object.keys(span.process_tags || {}).length;
  const stripped = span.stripped_tag_keys || [];
  const redactions = span.value_redactions || 0;

  return (
    <div className="h-full overflow-y-auto custom-scrollbar p-4 space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 pb-3 border-b border-wr-border">
        <div>
          <p className="text-body-xs text-wr-text-muted font-mono">{span.span_id}</p>
          <h3 className="text-sm font-semibold text-wr-text mt-1">
            <span className="text-wr-accent">{service}</span>
            <span className="text-wr-text-muted"> / {op}</span>
          </h3>
          <div className="flex items-center gap-3 mt-2 text-body-xs">
            <span className={
              span.status === 'error' ? 'text-red-400 font-bold' :
              span.status === 'timeout' ? 'text-orange-400 font-bold' : 'text-wr-text-muted'
            }>
              {span.status}
            </span>
            <span className="text-wr-text-muted">·</span>
            <span className="text-wr-text-muted">{Math.round(span.duration_ms)}ms</span>
            {span.kind && (
              <>
                <span className="text-wr-text-muted">·</span>
                <span className="text-wr-text-muted">kind: {span.kind}</span>
              </>
            )}
          </div>
        </div>
        {backendUrl && (
          <a
            href={`${backendUrl.replace(/\/$/, '')}/trace/${traceId}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-body-xs text-wr-accent hover:underline px-2 py-1 border border-wr-border rounded"
            data-testid="open-in-backend"
          >
            Open in backend
          </a>
        )}
      </div>

      {/* Error message */}
      {span.error_message && (
        <div className="bg-red-950/30 border border-red-900/50 rounded p-3">
          <p className="text-body-xs uppercase tracking-wider text-red-400 font-semibold mb-1">Error</p>
          <p className="text-body-sm text-red-200 font-mono break-all">{span.error_message}</p>
        </div>
      )}

      {/* Redaction provenance */}
      {(stripped.length > 0 || redactions > 0) && (
        <div className="bg-wr-bg/60 border border-wr-border rounded p-3 text-body-xs text-wr-text-muted">
          <span className="font-semibold text-wr-text">Redaction policy applied:</span>
          {' '}
          {stripped.length > 0 && (
            <span>{stripped.length} tag{stripped.length === 1 ? '' : 's'} stripped ({stripped.join(', ')})</span>
          )}
          {stripped.length > 0 && redactions > 0 && <span>, </span>}
          {redactions > 0 && (
            <span>{redactions} value{redactions === 1 ? '' : 's'} scrubbed for PII</span>
          )}
        </div>
      )}

      {/* Span tags */}
      {tagCount > 0 && (
        <section>
          <p className="text-body-xs uppercase tracking-wider text-wr-text-muted mb-2">
            Span tags ({tagCount})
          </p>
          <dl className="grid grid-cols-1 gap-1 text-body-xs font-mono">
            {Object.entries(span.tags || {}).map(([k, v]) => (
              <div key={k} className="flex gap-2 py-1 border-b border-wr-border/30">
                <dt className="text-wr-text-muted w-56 shrink-0 truncate" title={k}>{k}</dt>
                <dd className="text-wr-text break-all">{v}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      {/* Process tags (host / pod / service version) */}
      {processTagCount > 0 && (
        <section>
          <p className="text-body-xs uppercase tracking-wider text-wr-text-muted mb-2">
            Process tags
          </p>
          <dl className="grid grid-cols-1 gap-1 text-body-xs font-mono">
            {Object.entries(span.process_tags || {}).map(([k, v]) => (
              <div key={k} className="flex gap-2 py-1 border-b border-wr-border/30">
                <dt className="text-wr-text-muted w-56 shrink-0 truncate">{k}</dt>
                <dd className="text-wr-text break-all">{v}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      {/* Events (span-scoped logs) */}
      {span.events && span.events.length > 0 && (
        <section>
          <p className="text-body-xs uppercase tracking-wider text-wr-text-muted mb-2">
            Events ({span.events.length})
          </p>
          <div className="space-y-1 text-body-xs font-mono">
            {span.events.map((e, i) => (
              <div key={i} className="bg-wr-bg/50 rounded px-2 py-1">
                <pre className="whitespace-pre-wrap break-all">{JSON.stringify(e, null, 2)}</pre>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Raw JSON toggle */}
      <section>
        <button
          type="button"
          className="text-body-xs text-wr-accent hover:underline"
          onClick={() => setShowRaw(!showRaw)}
        >
          {showRaw ? 'Hide' : 'Show'} raw JSON
        </button>
        {showRaw && (
          <pre className="mt-2 bg-wr-bg/60 border border-wr-border rounded p-3 text-body-xs font-mono overflow-x-auto">
            {JSON.stringify(span, null, 2)}
          </pre>
        )}
      </section>
    </div>
  );
}
