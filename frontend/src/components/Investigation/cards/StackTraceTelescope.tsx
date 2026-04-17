import React, { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

export interface StackFrameValidation {
  file: string;
  line: number;
  is_stale: boolean;
  reason?: string;
}

interface StackTraceTelescopeProps {
  traces: string[];
  /** Phase 4, Task 4.20 — pre-validated frames from the stack-trace line
   * validator (Task 3.13). When any frame is stale at the deployed SHA,
   * we surface an amber warning so users don't chase a line that no
   * longer exists. Passing this prop doesn't alter the raw trace view. */
  frames?: StackFrameValidation[];
  deployedSha?: string;
}

const FRAMEWORK_PATTERNS = [
  /^\s+at\s+(java\.|javax\.|sun\.|com\.sun\.|org\.springframework\.|org\.apache\.|io\.netty\.|reactor\.|rx\.)/,
  /^\s+at\s+(jdk\.|kotlin\.coroutines|kotlinx\.coroutines)/,
  /^\s+File\s+".*\/(site-packages|dist-packages|lib\/python)\//,
  /^\s+at\s+node:internal\//,
  /^\s+at\s+(Module\.|require\s)/,
];

function isFrameworkLine(line: string): boolean {
  return FRAMEWORK_PATTERNS.some((p) => p.test(line));
}

function splitFrames(trace: string): { app: string[]; framework: string[] } {
  const lines = trace.split('\n');
  const app: string[] = [];
  const framework: string[] = [];

  for (const line of lines) {
    if (isFrameworkLine(line)) {
      framework.push(line);
    } else {
      app.push(line);
    }
  }
  return { app, framework };
}

const StackTraceTelescope: React.FC<StackTraceTelescopeProps> = ({
  traces,
  frames,
  deployedSha,
}) => {
  const [showFramework, setShowFramework] = useState(false);
  const [showTrace, setShowTrace] = useState(false);

  const { app, framework } = useMemo(() => splitFrames(traces[0] || ''), [traces]);

  const staleFrames = (frames || []).filter((f) => f.is_stale);

  if (traces.length === 0) return null;

  return (
    <div>
      {staleFrames.length > 0 && (
        <div
          data-testid="stale-line-warning"
          className="mb-2 border border-wr-amber/40 bg-wr-amber/10 text-wr-amber rounded px-2 py-1.5 text-body-xs flex items-start gap-2"
          role="alert"
        >
          <span
            className="material-symbols-outlined text-[14px]"
            aria-hidden
          >
            warning
          </span>
          <div className="flex-1">
            <div className="font-medium">
              Line numbers may be stale for deployed sha
              {deployedSha ? ` ${deployedSha.slice(0, 8)}` : ''}
            </div>
            <ul className="mt-1 space-y-0.5 font-mono text-[10px]">
              {staleFrames.map((f, i) => (
                <li key={i} className="truncate" title={f.reason}>
                  {f.file}:{f.line}
                  {f.reason ? ` — ${f.reason}` : ''}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
      <button
        onClick={() => setShowTrace(!showTrace)}
        className="text-body-xs text-purple-400 hover:underline"
      >
        {showTrace ? 'Hide' : 'Show'} stack trace ({traces.length})
      </button>
      <AnimatePresence initial={false}>
        {showTrace && (
          <motion.div
            key="trace-content"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 300, damping: 30 }}
            className="overflow-hidden"
          >
            <div className="mt-1 space-y-1">
              <pre className="p-2 bg-black/30 rounded text-body-xs font-mono text-slate-300 overflow-x-auto max-h-48 custom-scrollbar whitespace-pre-wrap">
                {app.join('\n')}
              </pre>
              <AnimatePresence initial={false}>
                {framework.length > 0 && (
                  <>
                    <button
                      onClick={() => setShowFramework(!showFramework)}
                      className="text-body-xs text-slate-400 hover:text-slate-400"
                    >
                      {showFramework ? 'Hide' : `${framework.length} framework frames hidden`}
                    </button>
                    {showFramework && (
                      <motion.div
                        key="framework-frames"
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ type: 'spring', stiffness: 300, damping: 30 }}
                        className="overflow-hidden"
                      >
                        <pre className="p-2 bg-black/20 rounded text-body-xs font-mono text-slate-400 overflow-x-auto max-h-32 custom-scrollbar whitespace-pre-wrap">
                          {framework.join('\n')}
                        </pre>
                      </motion.div>
                    )}
                  </>
                )}
              </AnimatePresence>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default StackTraceTelescope;
