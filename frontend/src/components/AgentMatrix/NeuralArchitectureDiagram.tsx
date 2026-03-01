import React from 'react';

interface NeuralArchitectureDiagramProps {
  stages: string[];
}

const NeuralArchitectureDiagram: React.FC<NeuralArchitectureDiagramProps> = ({ stages }) => {
  if (stages.length === 0) {
    return (
      <div className="rounded-lg border p-4" style={{ backgroundColor: '#0a1214', borderColor: '#224349' }}>
        <h3 className="text-xs font-mono uppercase tracking-widest mb-3" style={{ color: '#64748b' }}>
          Architecture Pipeline
        </h3>
        <p className="text-xs font-mono italic" style={{ color: '#475569' }}>No architecture stages defined</p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border p-4" style={{ backgroundColor: '#0a1214', borderColor: '#224349' }}>
      <h3 className="text-xs font-mono uppercase tracking-widest mb-4" style={{ color: '#64748b' }}>
        Architecture Pipeline
      </h3>
      <div className="flex flex-col items-center gap-0">
        {stages.map((stage, i) => (
          <React.Fragment key={i}>
            {/* Stage box */}
            <div
              className="w-full rounded-lg border px-4 py-2.5 text-center transition-all"
              style={{
                backgroundColor: '#162a2e',
                borderColor: 'rgba(7,182,213,0.25)',
              }}
            >
              <span className="text-xs font-mono font-medium text-white">{stage}</span>
            </div>
            {/* Arrow connector (except after last) */}
            {i < stages.length - 1 && (
              <div className="flex flex-col items-center py-0.5">
                <div className="w-px h-3" style={{ backgroundColor: 'rgba(7,182,213,0.4)' }} />
                <span
                  className="material-symbols-outlined text-sm"
                  style={{ fontFamily: 'Material Symbols Outlined', color: '#07b6d5', marginTop: '-2px', marginBottom: '-2px' }}
                >
                  arrow_downward
                </span>
                <div className="w-px h-3" style={{ backgroundColor: 'rgba(7,182,213,0.4)' }} />
              </div>
            )}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
};

export default NeuralArchitectureDiagram;
