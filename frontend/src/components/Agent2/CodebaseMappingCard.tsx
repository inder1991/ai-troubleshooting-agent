import React from 'react';
import { CheckCircle, XCircle } from 'lucide-react';

interface MappedLocation {
  original: string;
  normalized: string;
  repoFile: string;
  line: number;
  function: string;
  confidence: 'high' | 'medium' | 'low';
  mapped: boolean;
}

interface CodebaseMappingProps {
  data: {
    successRate: string;
    totalLocations: number;
    mappedLocations: MappedLocation[];
  };
}

export const CodebaseMappingCard: React.FC<CodebaseMappingProps> = ({ data }) => {
  if (!data) return null;
  
  const getConfidenceBadge = (confidence: string) => {
    const colors = {
      high: 'bg-green-900/30 text-green-400 border-green-800',
      medium: 'bg-yellow-900/30 text-yellow-400 border-yellow-800',
      low: 'bg-red-900/30 text-red-400 border-red-800'
    };
    
    return (
      <span className={`text-chrome px-1.5 py-0.5 rounded border ${colors[confidence as keyof typeof colors]}`}>
        {confidence.toUpperCase()}
      </span>
    );
  };
  
  return (
    <div className="transition-all duration-700">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-body-xs font-bold text-slate-400 uppercase tracking-widest">
          1️⃣ Codebase Mapping ({data.successRate})
        </span>
      </div>
      
      <div className="min-h-[100px] border border-dashed border-wr-border rounded bg-slate-950/40 p-3">
        <div className="space-y-2">
          {data.mappedLocations && data.mappedLocations.length > 0 ? (
            data.mappedLocations.map((loc, idx) => (
              <div key={idx} className="border border-wr-border rounded p-2 bg-wr-bg/40">
                <div className="flex items-start justify-between mb-1">
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    {loc.mapped ? (
                      <CheckCircle size={10} className="text-green-500 flex-shrink-0" />
                    ) : (
                      <XCircle size={10} className="text-red-500 flex-shrink-0" />
                    )}
                    <code className="text-body-xs text-blue-400 truncate">{loc.original}</code>
                  </div>
                  {getConfidenceBadge(loc.confidence)}
                </div>
                {loc.mapped && (
                  <div className="ml-4 text-body-xs text-slate-400 mt-1">
                    → <code className="text-emerald-400">{loc.repoFile}:{loc.line}</code>
                  </div>
                )}
                <div className="ml-4 text-chrome text-slate-500 mt-0.5">
                  in <code>{loc.function}()</code>
                </div>
              </div>
            ))
          ) : (
            <div className="text-body-xs font-mono text-slate-700 text-center py-4">
              No mapped locations
            </div>
          )}
        </div>
      </div>
    </div>
  );
};