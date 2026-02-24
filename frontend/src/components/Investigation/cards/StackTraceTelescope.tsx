import React, { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

interface StackTraceTelescopeProps {
  traces: string[];
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

const StackTraceTelescope: React.FC<StackTraceTelescopeProps> = ({ traces }) => {
  const [showFramework, setShowFramework] = useState(false);
  const [showTrace, setShowTrace] = useState(false);

  const { app, framework } = useMemo(() => splitFrames(traces[0] || ''), [traces]);

  if (traces.length === 0) return null;

  return (
    <div>
      <button
        onClick={() => setShowTrace(!showTrace)}
        className="text-[10px] text-purple-400 hover:underline"
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
              <pre className="p-2 bg-black/30 rounded text-[10px] font-mono text-slate-300 overflow-x-auto max-h-48 custom-scrollbar whitespace-pre-wrap">
                {app.join('\n')}
              </pre>
              <AnimatePresence initial={false}>
                {framework.length > 0 && (
                  <>
                    <button
                      onClick={() => setShowFramework(!showFramework)}
                      className="text-[9px] text-slate-500 hover:text-slate-400"
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
                        <pre className="p-2 bg-black/20 rounded text-[10px] font-mono text-slate-500 overflow-x-auto max-h-32 custom-scrollbar whitespace-pre-wrap">
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
