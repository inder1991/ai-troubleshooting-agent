import { useState, useCallback, useMemo } from 'react';
import type { SpanInfo } from '../../../types';

/**
 * Single source of selection state shared across Flow / Waterfall / Detail tabs.
 *
 * The user picks a span in any tab; the other tabs react. Keeps the three
 * tabs from fighting each other for selection authority.
 */
export interface TraceSelectionState {
  selectedSpanId: string | null;
  selectedServiceFilter: string | null;
  selectSpan: (id: string | null) => void;
  selectService: (service: string | null) => void;
  clear: () => void;
  selectedSpan: SpanInfo | null;
}

export function useTraceSelection(spans: SpanInfo[]): TraceSelectionState {
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);
  const [selectedServiceFilter, setSelectedServiceFilter] = useState<string | null>(null);

  const selectedSpan = useMemo(
    () => (selectedSpanId ? spans.find((s) => s.span_id === selectedSpanId) ?? null : null),
    [selectedSpanId, spans],
  );

  const selectSpan = useCallback((id: string | null) => {
    setSelectedSpanId(id);
  }, []);

  const selectService = useCallback((svc: string | null) => {
    setSelectedServiceFilter(svc);
  }, []);

  const clear = useCallback(() => {
    setSelectedSpanId(null);
    setSelectedServiceFilter(null);
  }, []);

  return {
    selectedSpanId,
    selectedServiceFilter,
    selectSpan,
    selectService,
    clear,
    selectedSpan,
  };
}
