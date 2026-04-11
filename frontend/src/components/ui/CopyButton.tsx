import React, { useState, useRef, useCallback } from 'react';

interface CopyButtonProps {
  text: string;
  className?: string;
  size?: number;
}

const CopyButton: React.FC<CopyButtonProps> = ({ text, className = '', size = 12 }) => {
  const [copied, setCopied] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(text).catch(() => {});
    setCopied(true);
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => setCopied(false), 2000);
  }, [text]);

  return (
    <button
      onClick={handleCopy}
      className={`p-1 rounded hover:bg-slate-700/50 transition-colors ${className}`}
      aria-label={copied ? 'Copied' : 'Copy to clipboard'}
      title={copied ? 'Copied!' : 'Copy'}
    >
      <span
        className={`material-symbols-outlined ${copied ? 'text-green-400' : 'text-slate-400'}`}
        style={{ fontFamily: 'Material Symbols Outlined', fontSize: `${size}px` }}
      >
        {copied ? 'check' : 'content_copy'}
      </span>
    </button>
  );
};

export default CopyButton;
