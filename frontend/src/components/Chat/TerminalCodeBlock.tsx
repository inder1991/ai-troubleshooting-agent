import React, { useState, useCallback } from 'react';

interface TerminalCodeBlockProps {
  children: string;
  className?: string;
  inline?: boolean;
}

const TerminalCodeBlock: React.FC<TerminalCodeBlockProps> = ({ children, className, inline }) => {
  const [copied, setCopied] = useState(false);

  // Extract language from className (e.g. "language-bash" → "bash")
  const language = className?.replace('language-', '') || '';

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(children);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for older browsers
      const textarea = document.createElement('textarea');
      textarea.value = children;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [children]);

  // Inline code — simple render
  if (inline) {
    return (
      <code className="text-cyan-300 bg-black/30 px-1 py-0.5 rounded text-[12px] font-mono">
        {children}
      </code>
    );
  }

  // Fenced code block
  return (
    <div className="my-2 rounded-lg border border-slate-700/50 overflow-hidden">
      {/* Header bar */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-slate-800/80 border-b border-slate-700/30">
        <span className="text-[10px] font-mono text-slate-500 uppercase tracking-wider">
          {language || 'code'}
        </span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 text-[10px] text-slate-500 hover:text-cyan-400 transition-colors"
          title="Copy to clipboard"
        >
          <span
            className="material-symbols-outlined text-sm"
            style={{ fontFamily: 'Material Symbols Outlined', fontSize: '14px' }}
          >
            {copied ? 'check' : 'content_copy'}
          </span>
          {copied && <span className="text-cyan-400">Copied</span>}
        </button>
      </div>
      {/* Code content */}
      <pre className="bg-black/40 p-3 overflow-x-auto">
        <code className={`font-mono text-[12px] leading-relaxed text-slate-200 ${className || ''}`}>
          {children}
        </code>
      </pre>
    </div>
  );
};

export default TerminalCodeBlock;
