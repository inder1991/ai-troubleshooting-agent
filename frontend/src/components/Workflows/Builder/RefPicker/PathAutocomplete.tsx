import { useMemo, useState, useRef, useEffect } from 'react';

interface Props {
  value: string;
  onChange: (v: string) => void;
  suggestions: string[];
  /** Prefix displayed (non-editable) before the input, e.g. 'output.' */
  displayPrefix?: string;
  placeholder?: string;
  onEscape?: () => void;
  id?: string;
}

export function PathAutocomplete({
  value,
  onChange,
  suggestions,
  displayPrefix,
  placeholder,
  onEscape,
  id,
}: Props) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);

  const filtered = useMemo(() => {
    const needle = value.trim().toLowerCase();
    if (!needle) return suggestions.slice(0, 50);
    return suggestions
      .filter((s) => s.toLowerCase().includes(needle))
      .slice(0, 50);
  }, [value, suggestions]);

  useEffect(() => {
    setActive(0);
  }, [value]);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Escape') {
      e.preventDefault();
      if (open) setOpen(false);
      else onEscape?.();
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setOpen(true);
      setActive((a) => Math.min(a + 1, Math.max(0, filtered.length - 1)));
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      setOpen(true);
      setActive((a) => Math.max(0, a - 1));
      return;
    }
    if (e.key === 'Enter') {
      if (open && filtered[active]) {
        e.preventDefault();
        onChange(filtered[active]);
        setOpen(false);
      }
    }
  }

  return (
    <div ref={rootRef} className="relative">
      <div className="flex items-stretch rounded-md border border-wr-border bg-wr-surface focus-within:border-wr-accent">
        {displayPrefix && (
          <span
            aria-hidden="true"
            className="flex items-center border-r border-wr-border bg-wr-elevated px-2 font-mono text-xs text-wr-text-muted"
          >
            {displayPrefix}
          </span>
        )}
        <input
          id={id}
          role="combobox"
          aria-label="Path"
          aria-autocomplete="list"
          aria-expanded={open}
          aria-controls={id ? `${id}-listbox` : undefined}
          className="flex-1 bg-transparent px-2 py-1.5 font-mono text-sm text-wr-text outline-none placeholder:text-wr-text-muted"
          placeholder={placeholder}
          value={value}
          onFocus={() => setOpen(true)}
          onChange={(e) => {
            onChange(e.target.value);
            setOpen(true);
          }}
          onKeyDown={onKeyDown}
        />
      </div>
      {open && filtered.length > 0 && (
        <ul
          id={id ? `${id}-listbox` : undefined}
          role="listbox"
          className="absolute left-0 right-0 z-10 mt-1 max-h-56 overflow-y-auto rounded-md border border-wr-border bg-wr-surface shadow-lg"
        >
          {filtered.map((s, i) => (
            <li
              key={s}
              role="option"
              aria-label={s}
              aria-selected={i === active}
              onMouseDown={(e) => {
                e.preventDefault();
                onChange(s);
                setOpen(false);
              }}
              onMouseEnter={() => setActive(i)}
              className={`cursor-pointer px-2 py-1 font-mono text-xs ${
                i === active
                  ? 'bg-wr-elevated text-wr-text'
                  : 'text-wr-text-muted hover:bg-wr-elevated'
              }`}
            >
              {s}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default PathAutocomplete;
