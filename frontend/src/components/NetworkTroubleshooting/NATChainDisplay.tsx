import React from 'react';

interface IdentityStage {
  stage: string;
  ip: string;
  port: number;
  device_id?: string;
}

interface NATChainDisplayProps {
  chain: IdentityStage[];
}

const STAGE_LABELS: Record<string, string> = {
  original: 'Original',
  post_snat: 'Post-SNAT',
  post_dnat: 'Post-DNAT',
  final: 'Final',
};

const NATChainDisplay: React.FC<NATChainDisplayProps> = ({ chain }) => {
  if (!chain || chain.length === 0) {
    return null;
  }

  return (
    <div>
      <div className="text-xs font-mono mb-2 uppercase tracking-wider" style={{ color: '#64748b' }}>
        NAT Identity Chain
      </div>
      <div className="flex items-center gap-1 overflow-x-auto pb-1">
        {chain.map((stage, idx) => (
          <React.Fragment key={stage.stage}>
            {/* Stage card */}
            <div
              className="flex-shrink-0 rounded px-2.5 py-1.5 font-mono text-xs"
              style={{ backgroundColor: '#0a0f13', border: '1px solid #224349' }}
            >
              <div
                className="text-[10px] uppercase tracking-wider mb-0.5"
                style={{ color: '#f59e0b' }}
              >
                {STAGE_LABELS[stage.stage] || stage.stage}
              </div>
              <div style={{ color: '#e2e8f0' }}>
                {stage.ip}:{stage.port}
              </div>
              {stage.device_id && (
                <div className="text-[10px] mt-0.5" style={{ color: '#64748b' }}>
                  {stage.device_id}
                </div>
              )}
            </div>

            {/* Arrow connector */}
            {idx < chain.length - 1 && (
              <span
                className="material-symbols-outlined text-sm flex-shrink-0"
                style={{ color: '#f59e0b' }}
              >
                arrow_forward
              </span>
            )}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
};

export default NATChainDisplay;
