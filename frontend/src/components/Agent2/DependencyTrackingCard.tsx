import React, { useState } from 'react';
import { Package, AlertCircle } from 'lucide-react';

interface DependencyConflict {
  package: string;
  versions: string[];
  severity: string;
}

interface DependencyTrackingProps {
  data: {
    externalDependencies: string[];
    internalDependencies: string[];
    totalExternal: number;
    totalInternal: number;
    conflicts: DependencyConflict[];
    hasConflicts: boolean;
  };
}

export const DependencyTrackingCard: React.FC<DependencyTrackingProps> = ({ data }) => {
  const [activeTab, setActiveTab] = useState<'external' | 'internal' | 'conflicts'>('external');
  
  if (!data) return null;
  
  return (
    <div className="transition-all duration-700">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">
          4️⃣ Dependency Tracking
        </span>
        {data.hasConflicts && (
          <span className="text-[8px] px-1.5 py-0.5 rounded bg-red-900/30 text-red-400 border border-red-800">
            {data.conflicts.length} CONFLICTS
          </span>
        )}
      </div>
      
      <div className="min-h-[100px] border border-dashed border-slate-800 rounded bg-slate-950/40 p-3">
        {/* Tab Toggle */}
        <div className="flex gap-1 mb-3 bg-slate-900 p-0.5 rounded">
          <button
            onClick={() => setActiveTab('external')}
            className={`flex-1 text-[8px] font-bold py-1 rounded transition-colors ${
              activeTab === 'external'
                ? 'bg-blue-600 text-white'
                : 'text-slate-500 hover:text-slate-400'
            }`}
          >
            EXTERNAL ({data.totalExternal})
          </button>
          <button
            onClick={() => setActiveTab('internal')}
            className={`flex-1 text-[8px] font-bold py-1 rounded transition-colors ${
              activeTab === 'internal'
                ? 'bg-blue-600 text-white'
                : 'text-slate-500 hover:text-slate-400'
            }`}
          >
            INTERNAL ({data.totalInternal})
          </button>
          {data.hasConflicts && (
            <button
              onClick={() => setActiveTab('conflicts')}
              className={`flex-1 text-[8px] font-bold py-1 rounded transition-colors ${
                activeTab === 'conflicts'
                  ? 'bg-red-600 text-white'
                  : 'text-red-400 hover:text-red-300'
              }`}
            >
              ⚠️ ({data.conflicts.length})
            </button>
          )}
        </div>
        
        {/* External Dependencies Tab */}
        {activeTab === 'external' && (
          <div className="space-y-1">
            {data.externalDependencies && data.externalDependencies.length > 0 ? (
              <div className="flex flex-wrap gap-1">
                {data.externalDependencies.slice(0, 20).map((dep, idx) => (
                  <span
                    key={idx}
                    className="text-[8px] bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded font-mono"
                  >
                    {dep}
                  </span>
                ))}
                {data.externalDependencies.length > 20 && (
                  <span className="text-[8px] text-slate-600">
                    +{data.externalDependencies.length - 20} more
                  </span>
                )}
              </div>
            ) : (
              <div className="text-[9px] text-slate-700 text-center py-4">
                No external dependencies found
              </div>
            )}
          </div>
        )}
        
        {/* Internal Dependencies Tab */}
        {activeTab === 'internal' && (
          <div className="space-y-1">
            {data.internalDependencies && data.internalDependencies.length > 0 ? (
              data.internalDependencies.map((dep, idx) => (
                <div
                  key={idx}
                  className="flex items-center gap-2 p-1.5 bg-slate-900/40 border border-slate-800 rounded"
                >
                  <Package size={10} className="text-blue-500" />
                  <span className="text-[9px] text-slate-400 font-mono">{dep}</span>
                </div>
              ))
            ) : (
              <div className="text-[9px] text-slate-700 text-center py-4">
                No internal dependencies found
              </div>
            )}
          </div>
        )}
        
        {/* Conflicts Tab */}
        {activeTab === 'conflicts' && (
          <div className="space-y-2">
            {data.conflicts && data.conflicts.length > 0 ? (
              data.conflicts.map((conflict, idx) => (
                <div
                  key={idx}
                  className="border border-red-800/50 rounded p-2 bg-red-950/20"
                >
                  <div className="flex items-center gap-1 mb-1">
                    <AlertCircle size={10} className="text-red-500" />
                    <code className="text-[9px] text-red-400 font-bold">
                      {conflict.package}
                    </code>
                  </div>
                  <div className="text-[8px] text-slate-500 ml-4">
                    Versions: {conflict.versions.join(', ')}
                  </div>
                  <div className="text-[7px] text-yellow-400 ml-4 mt-0.5 uppercase">
                    Severity: {conflict.severity}
                  </div>
                </div>
              ))
            ) : (
              <div className="text-[9px] text-green-400 text-center py-4">
                ✅ No conflicts found
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};