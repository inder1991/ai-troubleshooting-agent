import React, { useState } from 'react';
import { Code, FileText } from 'lucide-react';

interface FunctionDefinition {
  name: string;
  signature: string;
  startLine: number;
  endLine: number;
  docstring: string;
}

interface CodeSnippet {
  location: string;
  code: string;
  preview: string;
}

interface ContextRetrievalProps {
  data: {
    codeSnippetsCount: number;
    functionDefinitionsCount: number;
    codeSnippets: CodeSnippet[];
    functionDefinitions: FunctionDefinition[];
  };
}

export const ContextRetrievalCard: React.FC<ContextRetrievalProps> = ({ data }) => {
  const [activeTab, setActiveTab] = useState<'functions' | 'snippets'>('functions');
  const [selectedSnippet, setSelectedSnippet] = useState(0);
  
  if (!data) return null;
  
  return (
    <div className="transition-all duration-700">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-body-xs font-bold text-slate-400 uppercase tracking-widest">
          2️⃣ Context Retrieval
        </span>
      </div>
      
      <div className="min-h-[100px] border border-dashed border-wr-border rounded bg-slate-950/40 p-3">
        {/* Tab Toggle */}
        <div className="flex gap-1 mb-3 bg-wr-bg p-0.5 rounded">
          <button
            onClick={() => setActiveTab('functions')}
            className={`flex-1 text-chrome font-bold py-1 rounded transition-colors ${
              activeTab === 'functions'
                ? 'bg-blue-600 text-white'
                : 'text-slate-400 hover:text-slate-400'
            }`}
          >
            <Code size={10} className="inline mr-1" />
            FUNCTIONS ({data.functionDefinitionsCount})
          </button>
          <button
            onClick={() => setActiveTab('snippets')}
            className={`flex-1 text-chrome font-bold py-1 rounded transition-colors ${
              activeTab === 'snippets'
                ? 'bg-blue-600 text-white'
                : 'text-slate-400 hover:text-slate-400'
            }`}
          >
            <FileText size={10} className="inline mr-1" />
            SNIPPETS ({data.codeSnippetsCount})
          </button>
        </div>
        
        {/* Functions Tab */}
        {activeTab === 'functions' && (
          <div className="space-y-2">
            {data.functionDefinitions && data.functionDefinitions.length > 0 ? (
              data.functionDefinitions.map((func, idx) => (
                <div key={idx} className="border border-wr-border rounded p-2 bg-wr-bg/40">
                  <code className="text-body-xs text-blue-400 block mb-1">
                    {func.signature}
                  </code>
                  <div className="text-chrome text-slate-500">
                    Lines {func.startLine}-{func.endLine}
                  </div>
                  {func.docstring && (
                    <div className="text-chrome text-slate-400 mt-1 italic">
                      {func.docstring}
                    </div>
                  )}
                </div>
              ))
            ) : (
              <div className="text-body-xs text-slate-700 text-center py-4">
                No functions extracted
              </div>
            )}
          </div>
        )}
        
        {/* Snippets Tab */}
        {activeTab === 'snippets' && (
          <div className="space-y-2">
            {data.codeSnippets && data.codeSnippets.length > 0 ? (
              <>
                <div className="space-y-1">
                  {data.codeSnippets.map((snippet, idx) => (
                    <button
                      key={idx}
                      onClick={() => setSelectedSnippet(idx)}
                      className={`w-full text-left p-2 rounded text-body-xs font-mono transition-colors ${
                        selectedSnippet === idx
                          ? 'bg-blue-900/30 border border-blue-800'
                          : 'bg-wr-bg/40 border border-wr-border hover:border-wr-border-strong'
                      }`}
                    >
                      {snippet.location}
                    </button>
                  ))}
                </div>
                
                {data.codeSnippets[selectedSnippet] && (
                  <pre className="bg-slate-950 border border-wr-border rounded p-2 overflow-x-auto text-chrome text-slate-400">
                    <code>{data.codeSnippets[selectedSnippet].preview}</code>
                  </pre>
                )}
              </>
            ) : (
              <div className="text-body-xs text-slate-700 text-center py-4">
                No code snippets available
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};