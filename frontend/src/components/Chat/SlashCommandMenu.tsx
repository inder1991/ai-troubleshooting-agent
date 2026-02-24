import React, { useEffect, useRef } from 'react';

export interface SlashCommand {
  cmd: string;
  label: string;
  icon: string;
}

export const SLASH_COMMANDS: SlashCommand[] = [
  { cmd: '/logs', label: 'Search logs', icon: 'terminal' },
  { cmd: '/k8s', label: 'Check K8s health', icon: 'deployed_code' },
  { cmd: '/trace', label: 'Trace request', icon: 'route' },
  { cmd: '/fix', label: 'Generate fix', icon: 'build' },
  { cmd: '/rollback', label: 'Rollback changes', icon: 'undo' },
  { cmd: '/status', label: 'Investigation status', icon: 'monitoring' },
];

interface SlashCommandMenuProps {
  filter: string;
  selectedIndex: number;
  onSelect: (cmd: string) => void;
  onClose: () => void;
}

const SlashCommandMenu: React.FC<SlashCommandMenuProps> = ({
  filter,
  selectedIndex,
  onSelect,
  onClose,
}) => {
  const menuRef = useRef<HTMLDivElement>(null);

  const filtered = SLASH_COMMANDS.filter(
    c => c.cmd.toLowerCase().includes(filter.toLowerCase()) ||
         c.label.toLowerCase().includes(filter.toLowerCase())
  );

  // Close on click outside
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [onClose]);

  if (filtered.length === 0) return null;

  return (
    <div
      ref={menuRef}
      className="absolute bottom-full left-0 right-0 z-[70] mb-1 max-h-[200px] overflow-y-auto rounded-lg border border-slate-700/50 bg-slate-900/95 backdrop-blur-lg shadow-xl"
    >
      {filtered.map((cmd, i) => (
        <button
          key={cmd.cmd}
          className={`flex items-center gap-3 w-full px-3 py-2 text-left text-sm transition-colors ${
            i === selectedIndex
              ? 'bg-cyan-500/15 text-cyan-300'
              : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
          }`}
          onClick={() => onSelect(cmd.cmd)}
          onMouseDown={(e) => e.preventDefault()}
        >
          <span
            className="material-symbols-outlined text-sm"
            style={{ fontFamily: 'Material Symbols Outlined', fontSize: '16px' }}
          >
            {cmd.icon}
          </span>
          <span className="font-mono text-[12px]">{cmd.cmd}</span>
          <span className="text-[11px] text-slate-500 ml-auto">{cmd.label}</span>
        </button>
      ))}
    </div>
  );
};

export default SlashCommandMenu;
