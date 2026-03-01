import React from 'react';

interface ToolbeltPanelProps {
  tools: string[];
  toolHealthChecks: Record<string, string>;
  degradedTools: string[];
}

const ToolbeltPanel: React.FC<ToolbeltPanelProps> = ({ tools, toolHealthChecks, degradedTools }) => {
  const healthyCount = tools.length - degradedTools.length;

  if (tools.length === 0) {
    return (
      <div className="rounded-lg border p-4" style={{ backgroundColor: '#0a1214', borderColor: '#224349' }}>
        <h3 className="text-xs font-mono uppercase tracking-widest mb-3" style={{ color: '#64748b' }}>
          Toolbelt
        </h3>
        <div className="flex items-center gap-2 py-4 justify-center">
          <span
            className="material-symbols-outlined text-lg"
            style={{ fontFamily: 'Material Symbols Outlined', color: '#475569' }}
          >
            psychology
          </span>
          <span className="text-xs font-mono italic" style={{ color: '#475569' }}>
            LLM-only agent — no external tools
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border p-4" style={{ backgroundColor: '#0a1214', borderColor: '#224349' }}>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-mono uppercase tracking-widest" style={{ color: '#64748b' }}>
          Toolbelt
        </h3>
        <span className="text-[10px] font-mono" style={{ color: '#64748b' }}>
          <span style={{ color: '#07b6d5' }}>{healthyCount}</span>/{tools.length} online
        </span>
      </div>
      <div className="flex flex-col gap-1.5">
        {tools.map((tool) => {
          const isDegraded = degradedTools.includes(tool);
          // Check if tool has a health check entry
          const checks = toolHealthChecks || {};
          const hasHealthCheck = Object.values(checks).some(
            (v) => v.toLowerCase().includes(tool.toLowerCase())
          ) || Object.keys(checks).some(
            (k) => k.toLowerCase().includes(tool.replace(/_/g, '').toLowerCase())
          );

          return (
            <div
              key={tool}
              className="flex items-center gap-2 px-3 py-1.5 rounded"
              style={{ backgroundColor: '#162a2e' }}
            >
              <span
                className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                style={{
                  backgroundColor: isDegraded ? '#ef4444' : '#22c55e',
                }}
              />
              <span className="text-xs font-mono flex-1" style={{ color: isDegraded ? '#f87171' : '#e2e8f0' }}>
                {tool}
              </span>
              {hasHealthCheck && (
                <span
                  className="material-symbols-outlined text-xs"
                  style={{
                    fontFamily: 'Material Symbols Outlined',
                    color: isDegraded ? '#f59e0b' : '#475569',
                  }}
                >
                  monitor_heart
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default ToolbeltPanel;
