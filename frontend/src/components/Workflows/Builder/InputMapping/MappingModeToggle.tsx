export type MappingMode = 'literal' | 'input' | 'node' | 'env' | 'transform';

interface Props {
  mode: MappingMode;
  onChange: (m: MappingMode) => void;
  /** When false, hides the Transform button (gated behind Advanced disclosure) */
  showTransform?: boolean;
}

const LABELS: Record<MappingMode, string> = {
  literal: 'Literal',
  input: 'Input',
  node: 'Node',
  env: 'Env',
  transform: 'Transform',
};

export function MappingModeToggle({ mode, onChange, showTransform }: Props) {
  const modes: MappingMode[] = showTransform
    ? ['literal', 'input', 'node', 'env', 'transform']
    : ['literal', 'input', 'node', 'env'];

  return (
    <div
      role="group"
      aria-label="Mapping mode"
      className="inline-flex overflow-hidden rounded-md border border-wr-border"
    >
      {modes.map((m) => {
        const active = m === mode;
        return (
          <button
            key={m}
            type="button"
            onClick={() => onChange(m)}
            aria-pressed={active}
            className={`px-3 py-1.5 text-xs font-medium ${
              active
                ? 'bg-wr-accent text-wr-on-accent'
                : 'bg-wr-surface text-wr-text-muted hover:bg-wr-elevated'
            }`}
          >
            {LABELS[m]}
          </button>
        );
      })}
    </div>
  );
}

export default MappingModeToggle;
