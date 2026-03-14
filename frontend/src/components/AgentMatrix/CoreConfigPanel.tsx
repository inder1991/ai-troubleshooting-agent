import React from 'react';
import type { AgentLLMConfig } from '../../types';

interface CoreConfigPanelProps {
  llmConfig: AgentLLMConfig;
  timeoutS: number;
}

const CoreConfigPanel: React.FC<CoreConfigPanelProps> = ({ llmConfig, timeoutS }) => {
  const rows: { label: string; value: string; icon: string }[] = [
    { label: 'LLM Model', value: llmConfig.model, icon: 'psychology' },
    { label: 'Temperature', value: String(llmConfig.temperature), icon: 'thermostat' },
    { label: 'Context Window', value: `${(llmConfig.context_window / 1000).toFixed(0)}K tokens`, icon: 'token' },
    { label: 'Mode', value: llmConfig.mode.toUpperCase(), icon: 'tune' },
    { label: 'Timeout', value: `${timeoutS}s`, icon: 'timer' },
  ];

  return (
    <div className="rounded-lg border p-4" style={{ backgroundColor: '#0a1214', borderColor: '#3d3528' }}>
      <h3 className="text-xs font-mono uppercase tracking-widest mb-3" style={{ color: '#64748b' }}>
        Core Configuration
      </h3>
      <div className="flex flex-col gap-2">
        {rows.map((row) => (
          <div key={row.label} className="flex items-center justify-between py-1.5 border-b last:border-b-0" style={{ borderColor: '#1a2f33' }}>
            <div className="flex items-center gap-2">
              <span
                className="material-symbols-outlined text-sm"
                style={{ color: '#475569' }}
              >
                {row.icon}
              </span>
              <span className="text-xs" style={{ color: '#8a7e6b' }}>{row.label}</span>
            </div>
            <span className="text-xs font-mono font-medium text-white">{row.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default CoreConfigPanel;
