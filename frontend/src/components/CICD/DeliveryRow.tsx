import type { KeyboardEvent, MouseEvent } from 'react';
import type { DeliveryItem } from '../../types';
import { SplitFlapCell } from './SplitFlapCell';

interface DeliveryRowProps {
  item: DeliveryItem;
  onSelect?: (item: DeliveryItem) => void;
  onInvestigate?: (item: DeliveryItem) => void;
}

const KIND_PILL_CLASSES: Record<string, string> = {
  commit: 'bg-violet-500/20 text-violet-200 border-violet-500/40',
  build: 'bg-amber-500/20 text-amber-200 border-amber-500/40',
  sync: 'bg-sky-500/20 text-sky-200 border-sky-500/40',
};

export function DeliveryRow({ item, onSelect, onInvestigate }: DeliveryRowProps) {
  const handleSelect = () => {
    onSelect?.(item);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handleSelect();
    }
  };

  const handleInvestigate = (e: MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    onInvestigate?.(item);
  };

  const pillClass =
    KIND_PILL_CLASSES[item.kind] ?? 'bg-zinc-500/20 text-zinc-200 border-zinc-500/40';

  const timeLabel = (() => {
    try {
      return new Date(item.timestamp).toLocaleTimeString();
    } catch {
      return item.timestamp;
    }
  })();

  const showInvestigate =
    (item.kind === 'build' || item.kind === 'sync') && Boolean(onInvestigate);

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={handleSelect}
      onKeyDown={handleKeyDown}
      className="flex items-center gap-3 px-3 py-2 border-b border-zinc-800 hover:bg-zinc-900/40 cursor-pointer transition-colors"
    >
      <span
        className={`rounded-full px-2 py-0.5 text-body-xs uppercase border ${pillClass}`}
      >
        {item.kind}
      </span>

      <span className="text-xs">
        <span className="text-zinc-300">{item.source.toUpperCase()}</span>{' '}
        <span className="text-zinc-500">{item.source_instance}</span>
      </span>

      <span className="flex-1 truncate text-sm text-zinc-100">{item.title}</span>

      <span className="w-28 truncate text-xs text-zinc-400">{item.author ?? '—'}</span>

      <span className="w-24 truncate text-xs text-zinc-400">{item.target ?? '—'}</span>

      <span className="w-12 text-xs text-zinc-400">
        {item.duration_s != null ? `${item.duration_s}s` : ''}
      </span>

      <SplitFlapCell value={item.status} status={item.status} />

      <span className="w-20 text-xs text-zinc-500">{timeLabel}</span>

      {showInvestigate && (
        <button
          type="button"
          onClick={handleInvestigate}
          className="text-cyan-300 hover:text-cyan-200 text-xs"
        >
          Investigate
        </button>
      )}
    </div>
  );
}

export default DeliveryRow;
