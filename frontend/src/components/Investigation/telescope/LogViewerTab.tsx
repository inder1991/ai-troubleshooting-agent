import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { getResourceLogs } from '../../../services/api';

interface LogViewerTabProps {
  namespace: string;
  kind: string;
  name: string;
  sessionId: string;
}

type Severity = 'error' | 'warn' | 'info' | 'debug';

interface ParsedLine {
  raw: string;
  severity: Severity;
  isJson: boolean;
  jsonParsed?: string;
}

const SEVERITY_REGEX = {
  error: /\b(ERROR|FATAL|PANIC|CRIT)\b/i,
  warn: /\b(WARN|WARNING)\b/i,
  debug: /\b(DEBUG|TRACE)\b/i,
};

const parseSeverity = (line: string): Severity => {
  if (SEVERITY_REGEX.error.test(line)) return 'error';
  if (SEVERITY_REGEX.warn.test(line)) return 'warn';
  if (SEVERITY_REGEX.debug.test(line)) return 'debug';
  return 'info';
};

const SEVERITY_STYLES: Record<Severity, string> = {
  error: 'bg-red-950/30 border-l-2 border-red-500 text-red-300',
  warn: 'text-amber-300 border-l-2 border-amber-500/40',
  info: 'text-slate-400 border-l-2 border-transparent',
  debug: 'text-slate-600 border-l-2 border-transparent',
};

const parseLine = (raw: string): ParsedLine => {
  const severity = parseSeverity(raw);
  const trimmed = raw.trim();
  let isJson = false;
  let jsonParsed: string | undefined;

  if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
    try {
      jsonParsed = JSON.stringify(JSON.parse(trimmed), null, 2);
      isJson = true;
    } catch { /* not valid JSON */ }
  }

  return { raw, severity, isJson, jsonParsed };
};

const LogLine: React.FC<{ line: ParsedLine; lineNumber: number }> = ({ line, lineNumber }) => {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className={`px-3 py-0.5 font-mono text-[10px] leading-5 ${SEVERITY_STYLES[line.severity]}`}>
      <div className="flex items-start gap-2">
        <span className="text-slate-600 select-none w-8 text-right shrink-0">{lineNumber}</span>
        {line.isJson && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-cyan-500 hover:text-cyan-400 shrink-0"
          >
            [{expanded ? '-' : '+'}]
          </button>
        )}
        <span className="break-all whitespace-pre-wrap">{line.raw}</span>
      </div>
      {expanded && line.jsonParsed && (
        <pre className="ml-10 mt-1 text-[9px] text-slate-500 bg-slate-950/40 rounded p-2 overflow-x-auto">
          {line.jsonParsed}
        </pre>
      )}
    </div>
  );
};

const LogViewerTab: React.FC<LogViewerTabProps> = ({ namespace, kind, name, sessionId }) => {
  const [rawLogs, setRawLogs] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterText, setFilterText] = useState('');
  const [severityFilter, setSeverityFilter] = useState<Set<Severity>>(new Set(['error', 'warn', 'info', 'debug']));
  const [autoScroll, setAutoScroll] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);
  const userScrolledRef = useRef(false);

  // Fetch logs on mount
  useEffect(() => {
    setLoading(true);
    setError(null);
    getResourceLogs(sessionId, namespace, kind, name, 500)
      .then(result => {
        setRawLogs(result.logs || '');
        if (result.error) setError(result.error);
      })
      .catch(() => setError('Failed to fetch logs'))
      .finally(() => setLoading(false));
  }, [sessionId, namespace, kind, name]);

  // Parse and filter lines
  const parsedLines = useMemo(() => {
    if (!rawLogs) return [];
    return rawLogs.split('\n').filter(Boolean).map(parseLine);
  }, [rawLogs]);

  const filteredLines = useMemo(() => {
    return parsedLines.filter(line => {
      if (!severityFilter.has(line.severity)) return false;
      if (filterText) {
        try {
          const regex = new RegExp(filterText, 'i');
          return regex.test(line.raw);
        } catch {
          return line.raw.toLowerCase().includes(filterText.toLowerCase());
        }
      }
      return true;
    });
  }, [parsedLines, severityFilter, filterText]);

  // Auto-scroll
  useEffect(() => {
    if (autoScroll && !userScrolledRef.current && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [filteredLines, autoScroll]);

  // Human Override - disengage auto-scroll on manual scroll
  const handleWheel = useCallback(() => {
    userScrolledRef.current = true;
    setAutoScroll(false);
  }, []);

  const toggleSeverity = useCallback((sev: Severity) => {
    setSeverityFilter(prev => {
      const next = new Set(prev);
      if (next.has(sev)) next.delete(sev);
      else next.add(sev);
      return next;
    });
  }, []);

  const reEnableAutoScroll = useCallback(() => {
    userScrolledRef.current = false;
    setAutoScroll(true);
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-32">
        <span className="text-[10px] text-slate-500 animate-pulse">Loading logs...</span>
      </div>
    );
  }

  if (error && !rawLogs) {
    return (
      <div className="p-4 text-[10px] text-red-400">{error}</div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Sticky filter bar */}
      <div className="sticky top-0 z-10 flex items-center gap-2 px-3 py-2 bg-[#0a1a1f] border-b border-slate-800/30">
        <input
          type="text"
          value={filterText}
          onChange={e => setFilterText(e.target.value)}
          placeholder="Filter (regex)..."
          className="flex-1 text-[10px] bg-slate-950/60 border border-slate-800/50 rounded px-2 py-1 text-slate-300 placeholder-slate-600 focus:outline-none focus:border-cyan-700/40"
        />
        {(['error', 'warn', 'info', 'debug'] as Severity[]).map(sev => (
          <button
            key={sev}
            onClick={() => toggleSeverity(sev)}
            className={`text-[8px] font-bold px-1.5 py-0.5 rounded uppercase ${
              severityFilter.has(sev)
                ? sev === 'error' ? 'bg-red-950/40 text-red-400'
                : sev === 'warn' ? 'bg-amber-950/40 text-amber-400'
                : sev === 'debug' ? 'bg-slate-800/40 text-slate-500'
                : 'bg-cyan-950/40 text-cyan-400'
                : 'text-slate-700'
            }`}
          >
            {sev}
          </button>
        ))}
        <button
          onClick={reEnableAutoScroll}
          className={`text-[10px] ${autoScroll ? 'text-cyan-400' : 'text-slate-600'}`}
          title={autoScroll ? 'Auto-scroll ON' : 'Auto-scroll OFF (scroll detected)'}
        >
          <span className="material-symbols-outlined text-[14px]">vertical_align_bottom</span>
        </button>
      </div>

      {/* Log content */}
      <div
        ref={containerRef}
        className="flex-1 overflow-auto"
        onWheel={handleWheel}
      >
        {filteredLines.length === 0 ? (
          <div className="p-4 text-[10px] text-slate-500">No log lines match filters</div>
        ) : (
          filteredLines.map((line, i) => (
            <LogLine key={i} line={line} lineNumber={i + 1} />
          ))
        )}
      </div>

      {/* Status bar */}
      <div className="flex items-center justify-between px-3 py-1 border-t border-slate-800/30 text-[9px] text-slate-600">
        <span>{filteredLines.length} / {parsedLines.length} lines</span>
        {!autoScroll && <span className="text-amber-500">Manual scroll -- click arrow to re-enable</span>}
      </div>
    </div>
  );
};

export default LogViewerTab;
