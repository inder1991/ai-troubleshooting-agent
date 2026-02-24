import React, {useState} from 'react';
import { Mermaid } from './Mermaid';
import { 
  Fingerprint, AlertTriangle, ShieldCheck, GitPullRequest, 
  ExternalLink, Layers, Activity 
} from 'lucide-react';
import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import "highlight.js/styles/github-dark.css";

interface Agent2AnalysisData {
  root_cause_location: string;
  relevant_files: string[];
  diagnosticSummary: string;
  flowchart: string;
  impactAnalysis: string;
  recommendedFix: string;
  confidence?: number;
  call_chain?: any[];
  code_analysis?: boolean;
  // Summary is optional but good for metadata
  summary?: {
    mappingSuccessRate: string;
    functionsAnalyzed: number;
    callChainSteps: number;
    dependenciesFound: number;
  };
}

interface DiagnosticDashboardProps {
  data: Agent2AnalysisData;
  onStagePR: (fix: string) => void | Promise<void>;
}


const MarkdownRenderer = ({ content }: { content: string }) => {
  
  return (
    <ReactMarkdown
      rehypePlugins={[rehypeHighlight]}
      components={{
        code({ node, className, children, ...props }) {
          const isInline =
            node?.tagName === "code" &&
            !className;

          if (isInline) {
            return (
              <code className="bg-slate-800 text-emerald-400 px-1 py-0.5 rounded text-[10px]">
                {children}
              </code>
            );
          }

          return (
            <pre className="rounded-md bg-[#020617] border border-slate-800 p-4 overflow-x-auto text-[11px] leading-relaxed">
              <code className={className} {...props}>
                {children}
              </code>
            </pre>
          );
        }
      }}
    >
      {content}
    </ReactMarkdown>
  );
};


export const Agent2DiagnosticDashboard: React.FC<DiagnosticDashboardProps> = ({ 
  data, 
  onStagePR 
}) => {
  const [mermaidExpanded, setMermaidExpanded] = useState(false);
  
  if (!data) return null;
  return (
    <div className="space-y-6 mb-12 animate-in fade-in slide-in-from-bottom-4 duration-1000">
      
      {/* 1. CORRELATION HEADER */}
      <div className="p-4 bg-blue-500/10 border border-blue-500/30 rounded-lg">
        <div className="flex items-center gap-3 mb-2">
          <div className="p-2 bg-blue-500/20 rounded-full">
            <Fingerprint className="text-blue-400" size={20} />
          </div>
          <div>
            <h3 className="text-sm font-bold text-blue-400 uppercase tracking-tighter">Root Cause Correlated</h3>
            <p className="text-[10px] text-slate-500">Trace ID: {data.root_cause_location}</p>
          </div>
        </div>
        <div className="text-xs text-slate-200 leading-relaxed bg-slate-950/50 p-3 rounded border border-slate-800/50">
          <span className="text-red-400 font-bold mr-1">Race Condition Detected:</span>
          {data.diagnosticSummary}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* 2. LOGIC FLOW (MERMAID) */}
        <div className="bg-slate-900/40 border border-slate-800 rounded-lg p-4 flex flex-col">
          <div className="flex items-center gap-2 mb-4">
            <Activity size={14} className="text-slate-500" />
            <span className="text-[10px] font-bold text-slate-500 uppercase">Concurrency Logic Path</span>
          </div>
          <div className="flex-1 flex items-center justify-center bg-slate-950/40 rounded border border-slate-800/50 p-2">
            <Mermaid chart={data.flowchart} />
          </div>
          <div className="mt-3 text-[9px] text-slate-500 italic">
            Visualizing lost updates: concurrent threads reading shared state without locks.
          </div>
          <div className="p-3 border-b border-slate-800 flex items-center justify-between">
        <span className="text-xs font-bold text-slate-300">
            Concurrency Logic Path
        </span>

        <button
            onClick={() => setMermaidExpanded(true)}
            className="text-[9px] text-slate-400 hover:text-white transition"
        >
            ⛶ Expand
        </button>
        </div>
                {mermaidExpanded && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center">
            <div className="bg-[#020617] w-[90vw] h-[90vh] rounded-xl border border-slate-800 flex flex-col">
            
            <div className="p-3 border-b border-slate-800 flex justify-between items-center">
                <span className="text-xs font-bold text-slate-200">
                Concurrency Logic Path (Expanded)
                </span>

                <button
                onClick={() => setMermaidExpanded(false)}
                className="text-xs text-slate-400 hover:text-white"
                >
                ✕ Close
                </button>
            </div>

            <div className="flex-1 overflow-auto p-6">
                <Mermaid chart={data.flowchart} />
            </div>
            </div>
        </div>
        )}

        </div>

        {/* 3. PRODUCTION IMPACT */}
        <div className="bg-red-500/5 border border-red-500/20 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle size={14} className="text-red-400" />
            <span className="text-[10px] font-bold text-red-400 uppercase tracking-widest">Blast Radius Analysis</span>
          </div>
          <div className="prose-invert text-[11px] leading-relaxed text-slate-300 custom-markdown">
            <ReactMarkdown>{data.impactAnalysis}</ReactMarkdown>
          </div>
        </div>
      </div>

      {/* 4. RELEVANT FILES CLOUD */}
      <div className="flex flex-wrap gap-2">
        {data.relevant_files?.map((file, idx) => (
          <div key={idx} className="flex items-center gap-1.5 px-2 py-1 bg-slate-900 border border-slate-800 rounded text-[9px] text-slate-400 hover:text-blue-400 hover:border-blue-500/50 cursor-pointer transition-colors">
            <Layers size={10} />
            {file}
          </div>
        ))}
      </div>

      {/* 5. REMEDIATION PANEL */}
      <div className="border border-emerald-500/30 rounded-lg bg-slate-950 overflow-hidden shadow-2xl shadow-emerald-500/5">
        <div className="p-3 bg-emerald-500/5 border-b border-slate-900 flex justify-between items-center">
          <div className="flex items-center gap-2">
            <ShieldCheck size={16} className="text-emerald-500" />
            <div>
              <span className="text-[10px] font-bold text-emerald-400 uppercase block">Proposed Remediation</span>
              <span className="text-[8px] text-slate-500">Atomic Locking Fix (checkout_service.py)</span>
            </div>
          </div>
          <button 
            onClick={() => onStagePR(data.recommendedFix)}
            className="bg-emerald-600 hover:bg-emerald-500 text-white text-[10px] px-4 py-2 rounded-md font-bold transition-all flex items-center gap-2 shadow-lg shadow-emerald-900/20"
          >
            <GitPullRequest size={14} /> Stage Pull Request
          </button>
        </div>
        <div className="p-4 bg-slate-950 font-mono text-[10px] text-slate-300 overflow-x-auto custom-scrollbar border-t border-slate-900">
          <MarkdownRenderer content={data.recommendedFix} />
        </div>
      </div>
    </div>
  );
};