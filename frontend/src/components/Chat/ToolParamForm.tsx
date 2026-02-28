import React, { useState, useMemo } from 'react';
import type { ToolDefinition, ToolParam, RouterContext } from '../../types';
import { getContextValue } from '../../utils/contextHelpers';

interface ToolParamFormProps {
  tool: ToolDefinition;
  context: RouterContext;
  onExecute: (params: Record<string, unknown>) => void;
  onCancel: () => void;
}

export const ToolParamForm: React.FC<ToolParamFormProps> = ({ tool, context, onExecute, onCancel }) => {
  const initialParams = useMemo(() => {
    const params: Record<string, unknown> = {};
    for (const p of tool.params_schema) {
      if (p.default_from_context) {
        const ctxValue = getContextValue(context, p.default_from_context);
        if (ctxValue) params[p.name] = ctxValue;
      }
    }
    return params;
  }, [tool, context]);

  const [params, setParams] = useState<Record<string, unknown>>(initialParams);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onExecute(params);
  };

  const updateParam = (name: string, value: unknown) => {
    setParams((prev) => ({ ...prev, [name]: value }));
  };

  const canSubmit = tool.params_schema
    .filter((p) => p.required)
    .every((p) => params[p.name] !== undefined && params[p.name] !== '');

  return (
    <form onSubmit={handleSubmit} className="bg-slate-800/50 border border-slate-700 rounded-lg p-3 space-y-2">
      <div className="text-xs font-medium text-cyan-400 mb-2">{tool.label}</div>
      {tool.params_schema.map((p) => (
        <ParamField key={p.name} param={p} value={params[p.name]} onChange={(v) => updateParam(p.name, v)} />
      ))}
      <div className="flex justify-end gap-2 pt-1">
        <button type="button" onClick={onCancel}
          className="px-3 py-1 text-xs text-slate-400 hover:text-white transition-colors">
          Cancel
        </button>
        <button type="submit" disabled={!canSubmit}
          className="px-3 py-1 text-xs bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 text-white rounded transition-colors">
          Run
        </button>
      </div>
    </form>
  );
};

const ParamField: React.FC<{
  param: ToolParam;
  value: unknown;
  onChange: (v: unknown) => void;
}> = ({ param, value, onChange }) => {
  if (param.type === 'boolean') {
    return (
      <label className="flex items-center gap-2 text-xs text-slate-300">
        <input type="checkbox" checked={!!value} onChange={(e) => onChange(e.target.checked)}
          className="rounded border-slate-600 bg-slate-800" />
        {param.name}
      </label>
    );
  }
  if (param.type === 'select' && param.options?.length) {
    return (
      <label className="flex flex-col gap-1 text-xs text-slate-300">
        <span>{param.name}{param.required ? ' *' : ''}</span>
        <select value={String(value ?? '')} onChange={(e) => onChange(e.target.value)}
          className="bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs text-white">
          <option value="">Select...</option>
          {param.options.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      </label>
    );
  }
  return (
    <label className="flex flex-col gap-1 text-xs text-slate-300">
      <span>{param.name}{param.required ? ' *' : ''}</span>
      <input type={param.type === 'number' ? 'number' : 'text'}
        value={String(value ?? '')}
        placeholder={param.placeholder}
        onChange={(e) => onChange(param.type === 'number' ? Number(e.target.value) : e.target.value)}
        className="bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs text-white placeholder-slate-500" />
    </label>
  );
};
