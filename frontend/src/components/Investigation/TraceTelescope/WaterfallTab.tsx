import React, { useMemo, useRef, useEffect, useState } from 'react';
import type { SpanInfo } from '../../../types';

interface WaterfallTabProps {
  spans: SpanInfo[];
  serviceFilter: string | null;
  selectedSpanId: string | null;
  onSelectSpan: (id: string | null) => void;
}

/**
 * Concurrency-honest waterfall. Uses `start_time_us` for positioning (vs
 * TA-PR1's TraceWaterfall which used duration_ms and showed concurrent
 * spans as stacked serial bars — a real bug on fan-out patterns).
 *
 * Virtual-scroll strategy: fixed-height rows (28px) + windowed render of
 * ~80 rows around the viewport. Handles 2000-span traces without
 * sluggishness; gracefully degrades if fewer spans are present.
 */
const ROW_HEIGHT = 28;
const VISIBLE_BUFFER = 20;

export default function WaterfallTab(props: WaterfallTabProps) {
  const { spans, serviceFilter, selectedSpanId, onSelectSpan } = props;

  const filtered = useMemo(
    () => (serviceFilter ? spans.filter((s) => (s.service_name || s.service) === serviceFilter) : spans),
    [spans, serviceFilter],
  );

  const { sortedSpans, globalStart, totalDurationUs } = useMemo(() => {
    const withStart = filtered.filter((s): s is SpanInfo & { start_time_us: number } =>
      typeof s.start_time_us === 'number' && s.start_time_us > 0,
    );
    if (withStart.length === 0) {
      return { sortedSpans: filtered, globalStart: 0, totalDurationUs: 0 };
    }
    const starts = withStart.map((s) => s.start_time_us);
    const ends = withStart.map((s) => s.start_time_us + s.duration_ms * 1000);
    const gs = Math.min(...starts);
    const ge = Math.max(...ends);
    const sorted = [...withStart].sort((a, b) => a.start_time_us - b.start_time_us);
    return {
      sortedSpans: sorted,
      globalStart: gs,
      totalDurationUs: Math.max(ge - gs, 1),
    };
  }, [filtered]);

  const scrollRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => setScrollTop(el.scrollTop);
    el.addEventListener('scroll', onScroll);
    return () => el.removeEventListener('scroll', onScroll);
  }, []);

  const totalHeight = sortedSpans.length * ROW_HEIGHT;
  const startIdx = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - VISIBLE_BUFFER);
  const endIdx = Math.min(
    sortedSpans.length,
    Math.ceil((scrollTop + 600) / ROW_HEIGHT) + VISIBLE_BUFFER,
  );
  const visible = sortedSpans.slice(startIdx, endIdx);

  if (sortedSpans.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-wr-text-muted">
        <p>No spans match the current filter.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-2 border-b border-wr-border flex items-center gap-3 text-body-xs text-wr-text-muted">
        <span>{sortedSpans.length} spans</span>
        {totalDurationUs > 0 && <span>· {(totalDurationUs / 1000).toFixed(0)}ms total</span>}
        {serviceFilter && (
          <span className="text-wr-accent">filtered to {serviceFilter}</span>
        )}
      </div>
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto overflow-x-hidden custom-scrollbar"
        data-testid="waterfall-scroll"
      >
        <div style={{ height: totalHeight, position: 'relative' }}>
          {visible.map((span, i) => {
            const idx = startIdx + i;
            const top = idx * ROW_HEIGHT;
            const isSelected = span.span_id === selectedSpanId;
            return (
              <WaterfallRow
                key={span.span_id}
                span={span}
                top={top}
                globalStart={globalStart}
                totalDurationUs={totalDurationUs}
                isSelected={isSelected}
                onClick={() => onSelectSpan(span.span_id)}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── Row ─────────────────────────────────────────────────────────────────

interface RowProps {
  span: SpanInfo;
  top: number;
  globalStart: number;
  totalDurationUs: number;
  isSelected: boolean;
  onClick: () => void;
}

function WaterfallRow({ span, top, globalStart, totalDurationUs, isSelected, onClick }: RowProps) {
  const startTime = span.start_time_us ?? globalStart;
  const leftPct = totalDurationUs > 0 ? ((startTime - globalStart) / totalDurationUs) * 100 : 0;
  const widthPct = totalDurationUs > 0
    ? Math.max((span.duration_ms * 1000 / totalDurationUs) * 100, 0.5)
    : 0.5;
  const service = span.service_name || span.service;
  const op = span.operation_name || span.operation;

  const barColor =
    span.status === 'error'
      ? 'bg-red-500/70'
      : span.status === 'timeout'
      ? 'bg-orange-500/70'
      : span.critical_path
      ? 'bg-wr-accent/70'
      : 'bg-emerald-500/60';

  return (
    <div
      data-testid={`waterfall-row-${span.span_id}`}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter') onClick(); }}
      style={{ position: 'absolute', top, left: 0, right: 0, height: ROW_HEIGHT }}
      className={`flex items-center gap-2 px-4 cursor-pointer border-b border-wr-border/30 ${
        isSelected ? 'bg-wr-accent/10' : 'hover:bg-wr-surface/40'
      }`}
    >
      <div className="w-40 truncate text-body-xs text-wr-text shrink-0">
        <span className="font-mono text-wr-accent">{service}</span>
        <span className="text-wr-text-muted"> / {op}</span>
      </div>
      <div className="flex-1 relative h-5">
        <div
          className={`absolute top-0 ${barColor} rounded`}
          style={{ left: `${leftPct}%`, width: `${widthPct}%`, height: '100%' }}
        />
      </div>
      <div className="w-20 text-right text-body-xs font-mono text-wr-text-muted shrink-0">
        {span.duration_ms < 1 ? '<1ms' : `${Math.round(span.duration_ms)}ms`}
      </div>
    </div>
  );
}
