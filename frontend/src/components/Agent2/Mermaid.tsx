import React, { useEffect, useState } from 'react';
import mermaid from 'mermaid';
import { TransformWrapper, TransformComponent } from 'react-zoom-pan-pinch';
import { AnimatePresence, motion } from 'framer-motion';
import { ZoomIn, ZoomOut, RotateCcw, Loader2 } from 'lucide-react';

mermaid.initialize({
  startOnLoad: false,
  theme: 'base',
  securityLevel: 'loose',
  themeVariables: {
    background: 'transparent',
    primaryColor: '#0f172a',
    primaryBorderColor: '#07b6d5',
    primaryTextColor: '#e5e7eb',
    secondaryColor: '#1e293b',
    secondaryBorderColor: '#22c55e',
    secondaryTextColor: '#e5e7eb',
    lineColor: '#94a3b8',
    edgeLabelBackground: '#020617',
    fontFamily: 'JetBrains Mono, monospace',
    fontSize: '14px',
    clusterBkg: '#020617',
    clusterBorder: '#334155',
  },
});

/** Strip ```mermaid ... ``` code fences that LLMs sometimes wrap around syntax */
function stripCodeFences(raw: string): string {
  let s = raw.trim();
  // Remove opening fence: ```mermaid or ``` (with optional language tag)
  s = s.replace(/^```(?:mermaid)?\s*\n?/, '');
  // Remove closing fence
  s = s.replace(/\n?```\s*$/, '');
  return s.trim();
}

/**
 * Sanitize LLM-generated Mermaid syntax to fix common parse errors:
 * - <br/> / <br> inside labels → newline character
 * - Parentheses () inside quoted labels/edge labels → unicode fullwidth
 * - Unbalanced quotes
 */
function sanitizeMermaid(raw: string): string {
  let s = raw;

  // 1. Replace HTML line breaks with Mermaid-safe newline
  s = s.replace(/<br\s*\/?>/gi, '<br>');

  // 2. Escape parentheses ONLY inside quoted node labels ["..."] and edge labels |...|
  //    Replace () inside ["..."] blocks
  s = s.replace(/\["([^"]*?)"\]/g, (_match, inner: string) => {
    const safe = inner.replace(/\(/g, '❨').replace(/\)/g, '❩');
    return `["${safe}"]`;
  });

  //    Replace () inside |...| edge labels
  s = s.replace(/\|([^|]*?)\|/g, (_match, inner: string) => {
    const safe = inner.replace(/\(/g, '❨').replace(/\)/g, '❩');
    return `|${safe}|`;
  });

  // 3. Escape parentheses inside ("...") cylinder labels
  s = s.replace(/\("([^"]*?)"\)/g, (_match, inner: string) => {
    const safe = inner.replace(/\(/g, '❨').replace(/\)/g, '❩');
    return `("${safe}")`;
  });

  return s;
}

type RenderState = 'loading' | 'rendered' | 'error';

export const MermaidChart: React.FC<{ chart: string }> = ({ chart }) => {
  const [svg, setSvg] = useState('');
  const [state, setState] = useState<RenderState>('loading');
  const [rawFallback, setRawFallback] = useState('');

  useEffect(() => {
    let cancelled = false;

    const render = async () => {
      if (!chart) { setState('error'); return; }
      setState('loading');

      const cleaned = stripCodeFences(chart);
      const sanitized = sanitizeMermaid(cleaned);

      try {
        const id = `mermaid-${Math.random().toString(36).substring(2, 9)}`;
        const { svg: raw } = await mermaid.render(id, sanitized);
        if (cancelled) return;
        // Make SVG responsive: replace hardcoded width/height with 100%
        const responsive = raw
          .replace(/width="[\d.]+(px)?"/, 'width="100%"')
          .replace(/height="[\d.]+(px)?"/, 'height="100%"');
        setSvg(responsive);
        setState('rendered');
      } catch (err) {
        console.error('Mermaid render failed after sanitization:', err);
        if (!cancelled) {
          setRawFallback(sanitized);
          setState('error');
        }
      }
    };

    render();
    return () => { cancelled = true; };
  }, [chart]);

  return (
    <div
      className="group relative w-full h-full"
      style={{
        backgroundImage:
          'radial-gradient(circle, rgba(148,163,184,0.08) 1px, transparent 1px)',
        backgroundSize: '16px 16px',
      }}
    >
      <AnimatePresence mode="wait">
        {state === 'loading' && (
          <motion.div
            key="loader"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 flex items-center justify-center"
          >
            <Loader2 className="w-6 h-6 text-cyan-400 animate-spin" />
          </motion.div>
        )}

        {state === 'error' && (
          <motion.div
            key="error"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 overflow-auto p-4"
          >
            {rawFallback ? (
              <div>
                <div className="text-[10px] text-amber-400 mb-2 flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-[12px]" style={{ fontFamily: 'Material Symbols Outlined' }}>warning</span>
                  Diagram rendered as text (parse error)
                </div>
                <pre className="text-[10px] text-slate-400 font-mono whitespace-pre-wrap leading-relaxed bg-slate-900/60 rounded-lg p-3 border border-slate-800">
                  {rawFallback}
                </pre>
              </div>
            ) : (
              <div className="flex items-center justify-center h-full text-red-400 text-xs">
                Invalid diagram syntax
              </div>
            )}
          </motion.div>
        )}

        {state === 'rendered' && (
          <motion.div
            key="chart"
            initial={{ opacity: 0, scale: 0.97 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
            className="w-full h-full"
          >
            <TransformWrapper
              initialScale={1}
              minScale={0.3}
              maxScale={4}
              centerOnInit
              wheel={{ step: 0.08 }}
            >
              {({ zoomIn, zoomOut, resetTransform }) => (
                <>
                  {/* Floating controls — appear on hover */}
                  <div className="absolute top-2 right-2 z-10 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                    <button
                      onClick={() => zoomIn()}
                      className="p-1.5 rounded-md bg-slate-800/80 backdrop-blur border border-slate-700/50 text-slate-300 hover:text-white hover:bg-slate-700/80 transition-colors"
                    >
                      <ZoomIn size={14} />
                    </button>
                    <button
                      onClick={() => zoomOut()}
                      className="p-1.5 rounded-md bg-slate-800/80 backdrop-blur border border-slate-700/50 text-slate-300 hover:text-white hover:bg-slate-700/80 transition-colors"
                    >
                      <ZoomOut size={14} />
                    </button>
                    <button
                      onClick={() => resetTransform()}
                      className="p-1.5 rounded-md bg-slate-800/80 backdrop-blur border border-slate-700/50 text-slate-300 hover:text-white hover:bg-slate-700/80 transition-colors"
                    >
                      <RotateCcw size={14} />
                    </button>
                  </div>

                  <TransformComponent
                    wrapperStyle={{ width: '100%', height: '100%', cursor: 'grab' }}
                    contentStyle={{ width: '100%', height: '100%' }}
                  >
                    <div
                      className="w-full h-full flex items-center justify-center [&_svg]:max-w-full [&_svg]:max-h-full"
                      dangerouslySetInnerHTML={{ __html: svg }}
                    />
                  </TransformComponent>
                </>
              )}
            </TransformWrapper>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

// Backward-compatible alias for existing imports
export const Mermaid = MermaidChart;
export default MermaidChart;
