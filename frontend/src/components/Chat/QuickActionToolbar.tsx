import React, { useState, useCallback } from 'react';
import { ToolParamForm } from './ToolParamForm';
import type { ToolDefinition, RouterContext, QuickActionPayload } from '../../types';
import { getContextValue } from '../../utils/contextHelpers';

interface QuickActionToolbarProps {
  tools: ToolDefinition[];
  context: RouterContext;
  onExecute: (payload: QuickActionPayload) => void;
  loading: boolean;
  error?: string | null;
  onRetry?: () => void;
}

export const QuickActionToolbar: React.FC<QuickActionToolbarProps> = ({
  tools, context, onExecute, loading, error, onRetry,
}) => {
  const [activeTool, setActiveTool] = useState<ToolDefinition | null>(null);
  const [collapsed, setCollapsed] = useState(false);

  const handleClick = useCallback((tool: ToolDefinition) => {
    const needsInput = tool.params_schema.some(
      (p) => p.required && !p.default_from_context
    );
    if (!needsInput) {
      const params: Record<string, unknown> = {};
      for (const p of tool.params_schema) {
        if (p.default_from_context) {
          const v = getContextValue(context, p.default_from_context);
          if (v) params[p.name] = v;
        }
      }
      onExecute({ intent: tool.intent, params });
    } else {
      setActiveTool(tool);
    }
  }, [context, onExecute]);

  const handleFormExecute = useCallback((params: Record<string, unknown>) => {
    if (!activeTool) return;
    onExecute({ intent: activeTool.intent, params });
    setActiveTool(null);
  }, [activeTool, onExecute]);

  const isDisabled = useCallback((tool: ToolDefinition) => {
    return tool.requires_context.some((req) => {
      const val = getContextValue(context, `active_${req}`);
      return !val;
    });
  }, [context]);

  if (collapsed) {
    return (
      <button onClick={() => setCollapsed(false)}
        className="w-full py-1 text-xs text-slate-400 hover:text-amber-400 transition-colors">
        Show Quick Actions
      </button>
    );
  }

  return (
    <div role="toolbar" aria-label="Investigation quick actions" className="border-b border-wr-border p-2 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-body-xs font-medium text-slate-400 uppercase tracking-wider">Quick Actions</span>
        <button onClick={() => setCollapsed(true)} className="text-slate-500 hover:text-slate-400">
          <span className="material-symbols-outlined text-sm">expand_less</span>
        </button>
      </div>

      {/* F5: Error state */}
      {error ? (
        <div className="flex items-center gap-2 px-2 py-1.5 rounded bg-wr-severity-high/10 border border-red-500/20">
          <span className="material-symbols-outlined text-sm text-red-400">error</span>
          <span className="text-xs text-red-400 flex-1">{error}</span>
          {onRetry && (
            <button
              onClick={onRetry}
              className="text-xs text-red-300 hover:text-red-200 underline transition-colors"
            >
              Retry
            </button>
          )}
        </div>
      ) : tools.length === 0 ? (
        /* F5: Empty state */
        <div className="flex items-center gap-2 px-2 py-1.5">
          <span className="text-xs text-slate-500">No tools available</span>
        </div>
      ) : (
        /* Normal tools list */
        <div className="flex flex-wrap gap-1.5">
          {tools.map((tool) => (
            <button key={tool.intent} onClick={() => handleClick(tool)}
              disabled={loading || isDisabled(tool)}
              title={isDisabled(tool) ? `Requires: ${tool.requires_context.join(', ')}` : tool.description}
              className={`flex items-center gap-1 px-2 py-1 text-xs rounded border transition-colors
                ${isDisabled(tool)
                  ? 'border-wr-border-strong text-slate-500 cursor-not-allowed opacity-40'
                  : 'border-wr-border-strong text-slate-300 hover:border-amber-600 hover:text-amber-400'
                }`}>
              <span className="material-symbols-outlined text-sm">{tool.icon}</span>
              {tool.label}
            </button>
          ))}
        </div>
      )}

      {activeTool && (
        <ToolParamForm
          tool={activeTool}
          context={context}
          onExecute={handleFormExecute}
          onCancel={() => setActiveTool(null)}
        />
      )}
    </div>
  );
};
