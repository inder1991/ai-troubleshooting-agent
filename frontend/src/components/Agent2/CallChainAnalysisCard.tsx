import React from 'react';
import { ArrowRight, AlertTriangle, Activity } from 'lucide-react'; // Added Activity
import { Mermaid } from './mermaid'; // Import the new component

interface CallStep {
  function: string;
  file: string;
  line: number;
  codePreview: string;
  mapped: boolean;
}

interface FailureAnalysis {
  location: string;
  function: string;
  reason: string;
  variable?: string;
  missingCleanup?: string;
}
interface CallChainAnalysisProps {
  data: {
    callChain: string[];
    callChainDetailed: CallStep[];
    flowchart?: string; // ADD THIS: New Mermaid field
    dataFlow: {
      entryPoint: string;
      failurePoint: string;
      transformations: number;
    };
    failureAnalysis: FailureAnalysis;
  };
}

export const CallChainAnalysisCard: React.FC<CallChainAnalysisProps> = ({ data }) => {
  if (!data) return null;
  
  return (
    <div className="transition-all duration-700">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">
          3️⃣ Execution Logic Flow
        </span>
      </div>
      
      <div className="min-h-[100px] border border-dashed border-slate-800 rounded bg-slate-950/40 p-3">
        <div className="space-y-4"> {/* Increased spacing */}
          
          {/* NEW: Mermaid Logic Diagram */}
          {data.flowchart && (
            <div className="mb-4">
              <div className="flex items-center gap-1 mb-2">
                <Activity size={10} className="text-blue-400" />
                <span className="text-[8px] text-slate-500 uppercase font-bold">Logic Diagram</span>
              </div>
              <Mermaid chart={data.flowchart} />
            </div>
          )}

          {/* Simple Call Chain - existing list view below the diagram */}
          {data.callChain && data.callChain.length > 0 && (
            <div>
               <div className="text-[8px] text-slate-600 uppercase mb-2">Sequence Trace</div>
               <div className="flex items-center gap-1 flex-wrap">
                {data.callChain.map((step, idx) => (
                  <React.Fragment key={idx}>
                    <code className="text-[9px] text-blue-400">{step}</code>
                    {idx < data.callChain.length - 1 && (
                      <ArrowRight size={8} className="text-slate-700" />
                    )}
                  </React.Fragment>
                ))}
              </div>
            </div>
          )}

         {/* Failure Analysis */}
          {data.failureAnalysis && data.failureAnalysis.location !== 'Unknown' && (
            <div className="border border-red-800/50 rounded p-2 bg-red-950/20 mt-2">
              <div className="flex items-center gap-1 mb-1">
                <AlertTriangle size={10} className="text-red-500" />
                <span className="text-[9px] text-red-400 font-bold">Failure Point</span>
              </div>
              
              <div className="text-[8px] text-slate-400 mb-1">
                📍 <code>{data.failureAnalysis.location}</code>
              </div>
              
              <div className="text-[8px] text-slate-500">
                {data.failureAnalysis.reason}
              </div>
              
              {data.failureAnalysis.variable && (
                <div className="text-[8px] text-yellow-400 mt-1">
                  Variable: <code>{data.failureAnalysis.variable}</code>
                </div>
              )}
              
              {data.failureAnalysis.missingCleanup && (
                <div className="text-[8px] text-yellow-400 mt-1 flex items-start gap-1">
                  <span>⚠️</span>
                  <span>{data.failureAnalysis.missingCleanup}</span>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};