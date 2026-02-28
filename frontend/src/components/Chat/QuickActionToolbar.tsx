import React, { useState, useCallback } from 'react';
import { ToolParamForm } from './ToolParamForm';
import type { ToolDefinition, RouterContext, QuickActionPayload } from '../../types';

interface QuickActionToolbarProps {
  tools: ToolDefinition[];
  context: RouterContext;
  onExecute: (payload: QuickActionPayload) => void;
  loading: boolean;
}

export const QuickActionToolbar: React.FC<QuickActionToolbarProps> = ({
  tools, context, onExecute, loading,
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
          const v = (context as unknown as Record<string, unknown>)[p.default_from_context];
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
      const val = (context as unknown as Record<string, unknown>)[`active_${req}`];
      return !val;
    });
  }, [context]);

  if (collapsed) {
    return (
      <button onClick={() => setCollapsed(false)}
        className="w-full py-1 text-xs text-slate-500 hover:text-cyan-400 transition-colors">
        Show Quick Actions
      </button>
    );
  }

  return (
    <div className="border-b border-slate-800 p-2 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-medium text-slate-500 uppercase tracking-wider">Quick Actions</span>
        <button onClick={() => setCollapsed(true)} className="text-slate-600 hover:text-slate-400">
          <span className="material-symbols-outlined text-sm">expand_less</span>
        </button>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {tools.map((tool) => (
          <button key={tool.intent} onClick={() => handleClick(tool)}
            disabled={loading || isDisabled(tool)}
            title={isDisabled(tool) ? `Requires: ${tool.requires_context.join(', ')}` : tool.description}
            className={`flex items-center gap-1 px-2 py-1 text-xs rounded border transition-colors
              ${isDisabled(tool)
                ? 'border-slate-700 text-slate-600 cursor-not-allowed opacity-40'
                : 'border-slate-700 text-slate-300 hover:border-cyan-600 hover:text-cyan-400'
              }`}>
            <span className="material-symbols-outlined text-sm">{tool.icon}</span>
            {tool.label}
          </button>
        ))}
      </div>
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
