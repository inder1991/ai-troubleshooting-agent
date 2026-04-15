import { useEffect, useRef, useState } from 'react';

interface SplitFlapCellProps {
  value: string;
  status?: string;
  className?: string;
}

const STATUS_COLORS: Record<string, string> = {
  success: 'text-emerald-300',
  failed: 'text-red-400',
  in_progress: 'text-amber-300',
  aborted: 'text-zinc-400',
  healthy: 'text-emerald-300',
  degraded: 'text-amber-300',
  progressing: 'text-sky-300',
};

export function SplitFlapCell({ value, status, className = '' }: SplitFlapCellProps) {
  const prev = useRef(value);
  const [flipping, setFlipping] = useState(false);

  useEffect(() => {
    if (prev.current !== value) {
      setFlipping(true);
      const t = setTimeout(() => setFlipping(false), 400);
      prev.current = value;
      return () => clearTimeout(t);
    }
  }, [value]);

  const colorClass = (status && STATUS_COLORS[status]) ?? 'text-zinc-100';

  return (
    <span
      className={`inline-flex items-center justify-center px-2 py-1 font-mono text-xs rounded-sm border bg-zinc-900/70 border-zinc-700 ${colorClass} ${className}`}
    >
      <span className={flipping ? 'animate-flip' : ''}>{value}</span>
    </span>
  );
}

export default SplitFlapCell;
