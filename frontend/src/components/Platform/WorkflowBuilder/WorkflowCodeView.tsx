import React, { useRef, useState, useCallback, useEffect } from 'react';
import type { ParsedWorkflow } from './workflowParser';
import { stateToYaml } from './workflowSerializer';
import { t } from '../../../styles/tokens';

interface Props {
  yaml: string;
  parsed: ParsedWorkflow;
  dirty: boolean;
  onChange: (newYaml: string) => void;
}

const WorkflowCodeView: React.FC<Props> = ({ yaml, parsed, dirty, onChange }) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const lineNumbersRef = useRef<HTMLDivElement>(null);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [focused, setFocused] = useState(false);
  const [copied, setCopied] = useState(false);

  // Fix 4: clean up copy timer on unmount
  useEffect(() => {
    return () => {
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
    };
  }, []);

  const lineCount = yaml.split('\n').length;
  const lineNumbers = Array.from({ length: lineCount }, (_, i) => i + 1);

  // Sync line numbers scroll with textarea scroll
  const handleScroll = useCallback(() => {
    if (textareaRef.current && lineNumbersRef.current) {
      lineNumbersRef.current.scrollTop = textareaRef.current.scrollTop;
    }
  }, []);

  const handleCopy = useCallback(() => {
    // Fix 3: guard against environments where clipboard API is unavailable
    if (!navigator.clipboard) return;
    navigator.clipboard.writeText(yaml).then(() => {
      setCopied(true);
      // Fix 4: cancel any in-flight timer before starting a new one
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
      copyTimerRef.current = setTimeout(() => setCopied(false), 1500);
    }).catch(() => {});
  }, [yaml]);

  const handleFormat = useCallback(() => {
    const formatted = stateToYaml(parsed);
    onChange(formatted);
  }, [parsed, onChange]);

  // Determine status state
  // Fix 5: optional chaining guards against parsed.errors being null/undefined
  const hasErrors = (parsed.errors?.length ?? 0) > 0;
  const statusLabel = hasErrors
    ? `⚠ ${parsed.errors?.length ?? 0} error${(parsed.errors?.length ?? 0) !== 1 ? 's' : ''}`
    : dirty
    ? '◌ Unsaved changes'
    : '● Synced';

  const statusColor = hasErrors ? t.red : dirty ? t.amber : t.green;
  const statusBg = hasErrors ? t.redBg : dirty ? t.amberBg : t.greenBg;
  const statusBorder = hasErrors ? t.redBorder : dirty ? t.amberBorder : t.greenBorder;

  return (
    <div
      className="flex flex-col"
      style={{ width: '100%', height: '100%' }}
    >
      {/* Editor area — flex-1 */}
      <div
        className="flex flex-1 overflow-hidden relative"
        style={{
          borderRadius: 4,
          border: `1px solid ${focused ? t.cyanBorder : t.borderDefault}`,
          boxShadow: focused ? `0 0 0 1px ${t.cyanBorder} inset` : 'none',
          background: t.bgDeep,
          transition: 'border-color 0.15s, box-shadow 0.15s',
          minHeight: 0,
        }}
      >
        {/* Line numbers column */}
        <div
          ref={lineNumbersRef}
          aria-hidden="true"
          style={{
            width: 40,
            flexShrink: 0,
            overflowY: 'hidden',
            paddingTop: 16,
            paddingBottom: 16,
            background: t.bgDeep,
            borderRight: `1px solid ${t.borderFaint}`,
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
            fontSize: 11,
            lineHeight: 1.6,
            color: t.textFaint,
            textAlign: 'right',
            userSelect: 'none',
            pointerEvents: 'none',
          }}
        >
          {lineNumbers.map(n => (
            <div
              key={n}
              style={{
                paddingRight: 8,
                height: `${1.6}em`,
              }}
            >
              {n}
            </div>
          ))}
        </div>

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          value={yaml}
          onChange={e => onChange(e.target.value)}
          onScroll={handleScroll}
          onFocus={e => {
            setFocused(true);
            // Fix 1: the focusable element itself also signals focus via an inset shadow,
            // complementing the parent wrapper's border/shadow change.
            e.currentTarget.style.boxShadow = 'inset 0 0 0 1px rgba(7,182,213,0.4)';
          }}
          onBlur={e => {
            setFocused(false);
            e.currentTarget.style.boxShadow = 'none';
          }}
          spellCheck={false}
          aria-label="Workflow YAML editor"
          style={{
            flex: 1,
            resize: 'none',
            background: t.bgDeep,
            color: t.textPrimary,
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
            fontSize: 11,
            lineHeight: 1.6,
            padding: '16px 16px 16px 8px',
            outline: 'none',
            border: 'none',
            overflowY: 'auto',
            overflowX: 'auto',
            whiteSpace: 'pre',
            tabSize: 2,
          }}
        />
      </div>

      {/* Status bar — always shown, flex-shrink-0 */}
      <div
        className="flex items-center justify-between flex-shrink-0"
        style={{
          marginTop: 6,
          padding: '5px 10px',
          borderRadius: 4,
          background: statusBg,
          border: `1px solid ${statusBorder}`,
        }}
      >
        {/* Status indicator */}
        <span
          className="text-body-xs font-sans font-medium"
          style={{ color: statusColor, letterSpacing: '0.01em' }}
        >
          {statusLabel}
        </span>

        {/* Action buttons */}
        <div className="flex items-center gap-2">
          <ActionButton
            onClick={handleCopy}
            label={copied ? 'Copied!' : 'Copy'}
            icon={copied ? 'check' : 'content_copy'}
            active={copied}
          />
          <ActionButton
            onClick={handleFormat}
            label="Format"
            icon="format_align_left"
          />
        </div>
      </div>

      {/* Error panel — only shown when there are errors */}
      {hasErrors && (
        <div
          className="flex-shrink-0"
          style={{
            marginTop: 4,
            maxHeight: 120,
            overflowY: 'auto',
            background: t.bgBase,
            border: `1px solid ${t.redBorder}`,
            borderRadius: 4,
          }}
        >
          {/* Fix 5: (parsed.errors ?? []) guards against null; Fix 2: composite key instead of bare index */}
          {(parsed.errors ?? []).map((err, i) => (
            <ErrorRow key={`${i}-${err.slice(0, 20)}`} message={err} />
          ))}
        </div>
      )}
    </div>
  );
};

// ── Sub-components ──────────────────────────────────────────────────────────

interface ActionButtonProps {
  onClick: () => void;
  label: string;
  icon: string;
  active?: boolean;
}

const ActionButton: React.FC<ActionButtonProps> = ({ onClick, label, icon, active }) => {
  const [hovered, setHovered] = useState(false);

  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className="flex items-center gap-1"
      style={{
        padding: '2px 8px',
        borderRadius: 3,
        fontSize: 11,
        fontFamily: 'sans-serif',
        background: hovered ? t.cyanBg : 'transparent',
        border: `1px solid ${hovered ? t.cyanBorder : t.borderDefault}`,
        color: active ? t.green : hovered ? t.cyan : t.textSecondary,
        cursor: 'pointer',
        transition: 'background 0.1s, border-color 0.1s, color 0.1s',
      }}
    >
      <span className="material-symbols-outlined" style={{ fontSize: 12 }}>{icon}</span>
      {label}
    </button>
  );
};

interface ErrorRowProps {
  message: string;
}

const ErrorRow: React.FC<ErrorRowProps> = ({ message }) => {
  const [hovered, setHovered] = useState(false);

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className="flex items-start gap-1.5"
      style={{
        padding: '5px 10px',
        background: hovered ? t.redBg : 'transparent',
        cursor: 'default',
        transition: 'background 0.1s',
      }}
    >
      <span
        className="material-symbols-outlined flex-shrink-0"
        style={{ fontSize: 13, color: t.red, marginTop: 1 }}
      >
        error
      </span>
      <span
        className="text-body-xs font-sans"
        style={{ color: t.red, lineHeight: 1.5 }}
      >
        {message}
      </span>
    </div>
  );
};

export default WorkflowCodeView;
