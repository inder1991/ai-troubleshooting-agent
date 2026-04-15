import { useState, useRef, useEffect } from 'react';

type ExportFormat = 'png' | 'svg' | 'pdf' | 'json';

interface ExportMenuProps {
  onExport: (format: ExportFormat) => void;
}

const OPTIONS: { format: ExportFormat; label: string; icon: string }[] = [
  { format: 'png', label: 'PNG Image', icon: 'image' },
  { format: 'svg', label: 'SVG Vector', icon: 'draw' },
  { format: 'pdf', label: 'PDF Document', icon: 'picture_as_pdf' },
  { format: 'json', label: 'JSON Data', icon: 'data_object' },
];

export default function ExportMenu({ onExport }: ExportMenuProps) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [open]);

  return (
    <div ref={menuRef} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-body-xs font-mono font-medium border transition-colors hover:border-[#e09f3e]/40"
        style={{ backgroundColor: '#1e1b15', borderColor: '#3d3528', color: '#e8e0d4' }}
      >
        <span className="material-symbols-outlined" style={{ fontSize: 15, color: '#e09f3e' }}>
          download
        </span>
        Export
        <span className="material-symbols-outlined" style={{ fontSize: 11, color: '#64748b' }}>
          {open ? 'expand_less' : 'expand_more'}
        </span>
      </button>

      {open && (
        <div
          className="absolute top-full left-0 mt-1 z-50 rounded-md border shadow-xl overflow-hidden"
          style={{ background: '#0b1a1f', borderColor: 'rgba(224,159,62,0.2)', minWidth: 170 }}
        >
          {OPTIONS.map((opt) => (
            <button
              key={opt.format}
              onClick={() => { onExport(opt.format); setOpen(false); }}
              className="w-full flex items-center gap-2 px-3 py-2 text-body-xs font-mono text-left transition-colors hover:bg-[#1e1b15]"
              style={{ color: '#e8e0d4' }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 15, color: '#e09f3e' }}>
                {opt.icon}
              </span>
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
