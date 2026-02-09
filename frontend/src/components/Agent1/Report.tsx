import React, { useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import { Terminal, AlertCircle, FileCode, Cpu, Layers, ShieldCheck, Zap, Fingerprint, Download } from 'lucide-react';
import html2canvas from 'html2canvas';
import jsPDF from 'jspdf';



export const Agent1Report = ({ content, data }: any) => {
  const reportRef = useRef<HTMLDivElement>(null);
  const downloadPDF = async () => {
    if (!reportRef.current) return;
    const patterns = data?.errorPatterns || [];
    if (patterns.length === 0) {
      alert('No error patterns to export');
      return;
    }
    const canvas = await html2canvas(reportRef.current, {
      backgroundColor: '#020617', // Match your slate-950 theme
      scale: 2, // Higher quality
      height: reportRef.current.scrollHeight,      // ✅ ADD THIS
      windowHeight: reportRef.current.scrollHeight
    });
    const imgData = canvas.toDataURL('image/png');
    const hiddenDiv = reportRef.current.parentElement;
    if (hiddenDiv) {
      hiddenDiv.style.opacity = '1';
      hiddenDiv.style.position = 'absolute';
      hiddenDiv.style.left = '-9999px'; // Rendered but off-screen
      hiddenDiv.style.top = '0';
      hiddenDiv.style.zIndex = '9999';
    }
    await new Promise(resolve => setTimeout(resolve, 500));
    const pdf = new jsPDF('p', 'mm', 'a4');
    const imgProps = pdf.getImageProperties(imgData);
    const pdfWidth = pdf.internal.pageSize.getWidth();
    const pdfHeight = pdf.internal.pageSize.getHeight();
    
    const patternCards = reportRef.current.querySelectorAll('[data-pattern-card]');
    
    if (patternCards.length === 0) {
      // Fallback: Capture entire container
      console.log('⚠️ No pattern cards found, capturing entire report');
      
      const canvas = await html2canvas(reportRef.current, {
        backgroundColor: '#020617',
        scale: 2,
        logging: false,
        useCORS: true,
        height: reportRef.current.scrollHeight,
        windowHeight: reportRef.current.scrollHeight
      });
      
      const imgData = canvas.toDataURL('image/png');
      const imgProps = pdf.getImageProperties(imgData);
      const imgHeight = (imgProps.height * pdfWidth) / imgProps.width;
      
      let heightLeft = imgHeight;
      let position = 0;
      
      pdf.addImage(imgData, 'PNG', 0, position, pdfWidth, imgHeight);
      heightLeft -= pdfHeight;
      
      while (heightLeft > 0) {
        position = heightLeft - imgHeight;
        pdf.addPage();
        pdf.addImage(imgData, 'PNG', 0, position, pdfWidth, imgHeight);
        heightLeft -= pdfHeight;
      }
      
    } else {
      // Capture each pattern card separately
      console.log(`📄 Capturing ${patternCards.length} pattern cards...`);
      
      for (let i = 0; i < patternCards.length; i++) {
        console.log(`  Pattern ${i + 1}/${patternCards.length}`);
        
        const card = patternCards[i] as HTMLElement;
        
        const canvas = await html2canvas(card, {
          backgroundColor: '#020617',
          scale: 2,
          logging: false,
          useCORS: true,
          allowTaint: true,
          height: card.scrollHeight,
          windowHeight: card.scrollHeight
        });
        
        const imgData = canvas.toDataURL('image/png');
        const imgProps = pdf.getImageProperties(imgData);
        const imgHeight = (imgProps.height * pdfWidth) / imgProps.width;
        
        // Add new page for each pattern (except first)
        if (i > 0) {
          pdf.addPage();
        }
        
        // If pattern fits on one page, center it vertically
        const yPosition = imgHeight < pdfHeight ? (pdfHeight - imgHeight) / 2 : 0;
        
        // Add to PDF
        pdf.addImage(imgData, 'PNG', 0, yPosition, pdfWidth, Math.min(imgHeight, pdfHeight));
        
        // If pattern is taller than one page, add continuation pages
        if (imgHeight > pdfHeight) {
          let heightLeft = imgHeight - pdfHeight;
          let position = -pdfHeight;
          
          while (heightLeft > 0) {
            pdf.addPage();
            position -= pdfHeight;
            pdf.addImage(imgData, 'PNG', 0, position, pdfWidth, imgHeight);
            heightLeft -= pdfHeight;
          }
        }
      }
    }
    const filename = `Agent1_Analysis_${patterns.length}patterns_${Date.now()}.pdf`;
    pdf.save(filename);
    
    console.log(`✅ PDF saved: ${filename}`);
    if (hiddenDiv) {
      hiddenDiv.style.opacity = '0';
      hiddenDiv.style.position = 'fixed';
      hiddenDiv.style.left = '0';
      hiddenDiv.style.zIndex = '-1';
    }
  };
  // Calculate confidence percentage (e.g., 0.85 -> 85%)
  const confidenceScore = Math.round((data?.confidence || 0) * 100);

  const getSeverityStyle = (severity: string) => {
    switch (severity?.toUpperCase()) {
      case 'CRITICAL': return 'bg-red-500/10 text-red-400 border-red-500/20';
      case 'HIGH': return 'bg-orange-500/10 text-orange-400 border-orange-500/20';
      default: return 'bg-blue-500/10 text-blue-400 border-blue-500/20';
    }
  };
  const formatKey = (key: string) => key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
  return (
    <div className="space-y-4 min-w-0 w-full overflow-hidden">
      <div ref={reportRef} className="p-5 rounded-2xl bg-slate-950 border border-slate-800 space-y-6">
        
        {/* 1. Header: Severity & Confidence Meter */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-4">
          <div className="flex items-center gap-3">
            <div className={`px-2.5 py-1 rounded-full border text-[10px] font-black uppercase tracking-widest ${getSeverityStyle(data?.severity)}`}>
              {data?.severity || 'MEDIUM'}
            </div>
            <div className="h-4 w-[1px] bg-slate-800" />
            <div className="flex items-center gap-2">
              <ShieldCheck size={14} className={confidenceScore > 70 ? "text-emerald-400" : "text-yellow-400"} />
              <span className="text-[10px] font-bold text-slate-500 uppercase tracking-tighter">Confidence:</span>
              <div className="w-16 h-1.5 bg-slate-900 rounded-full overflow-hidden border border-slate-800">
                <div 
                  className={`h-full transition-all duration-1000 ${confidenceScore > 70 ? "bg-emerald-500" : "bg-yellow-500"}`}
                  style={{ width: `${confidenceScore}%` }}
                />
              </div>
              <span className="text-[10px] font-mono font-bold text-slate-300">{confidenceScore}%</span>
            </div>
          </div>
          <span className="text-[10px] font-bold text-slate-600 uppercase tracking-widest font-mono">
            Analysis Node v1
          </span>
        </div>

       {/* 2. Diagnostic Summary - High Impact Header */}
        <div className="space-y-1 py-2">
        <div className="flex items-center gap-2 group">
            <div className="p-1.5 bg-blue-500/10 rounded-lg border border-blue-500/20 shadow-[0_0_15px_rgba(59,130,246,0.1)]">
            <Zap size={16} className="text-blue-400 fill-blue-400/20 animate-pulse" />
            </div>
            <h2 className="text-lg font-bold tracking-tight bg-gradient-to-r from-slate-100 to-slate-400 bg-clip-text text-transparent">
            {data?.diagnosticSummary || "Diagnostic Insight"}
            </h2>
        </div>
        </div>

        {/* 3. Narrative Body - Structured Console Look */}
        <div className="relative group">
        {/* Subtle side accent line */}
        <div className="absolute left-[-1.25rem] top-0 bottom-0 w-[2px] bg-gradient-to-b from-blue-500/50 via-slate-800 to-transparent rounded-full opacity-50" />
        
        <div className="prose prose-invert prose-xs max-w-none 
            !text-[13px] leading-[1.6] font-mono tracking-tight text-slate-300
            prose-strong:text-blue-400 prose-strong:font-bold prose-strong:drop-shadow-[0_0_8px_rgba(96,165,250,0.3)]
            prose-headings:text-slate-100 prose-headings:tracking-tighter
            prose-code:text-blue-300 prose-code:bg-blue-500/10 prose-code:px-1 prose-code:rounded prose-code:before:content-none prose-code:after:content-none
            prose-li:marker:text-blue-500/50">
            
            <ReactMarkdown>
            {/* Moved the cleaning logic here for better performance and readability */}
            {String(data?.preliminary_rca || "")
                .split('\n')
                .map(line => line.trim())
                .join('\n')
                .replace(/\\?Enough thinking\.?/gi, '')} 
            </ReactMarkdown>
        </div>
        </div>

        {/* 4. Technical Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="bg-slate-900/40 border border-slate-800/50 p-3 rounded-xl flex items-center gap-3">
            <AlertCircle size={16} className="text-red-400" />
            <div className="overflow-hidden">
              <p className="text-[9px] text-slate-500 uppercase font-bold">Exception</p>
              <p className="text-xs font-mono text-slate-300 truncate">{data?.exception_type}</p>
            </div>
          </div>
          <div className="bg-slate-900/40 border border-slate-800/50 p-3 rounded-xl flex items-center gap-3">
            <FileCode size={16} className="text-blue-400" />
            <div className="overflow-hidden">
              <p className="text-[9px] text-slate-500 uppercase font-bold">Impact Source</p>
              <p className="text-xs font-mono text-slate-300 truncate">{data?.functionName || 'Unknown'}</p>
            </div>
          </div>
        </div>
        {/* 3. NEW: Sample Trace IDs Block */}
        {/* We assume data.correlationIds is an array of strings from the backend */}
        {data?.traceIDs && data.traceIDs.length > 0 && (
          <div className="rounded-xl border border-slate-800 bg-black/40 overflow-hidden w-full">
            <div className="flex items-center gap-2 px-3 py-2 bg-slate-900/50 border-b border-slate-800">
              <Fingerprint size={14} className="text-emerald-500/70" />
              <span className="text-[10px] font-bold text-slate-500 uppercase font-mono tracking-widest">
                Sample Trace IDs (Correlation)
              </span>
            </div>
            <div className="p-3 max-h-24 overflow-x-auto overflow-y-auto custom-scrollbar min-w-0">
              <div className="flex flex-wrap gap-2">
                {data.traceIDs.map((id: string, idx: number) => (
                  <code key={idx} className="text-[10px] font-mono text-emerald-400/80 bg-emerald-500/5 px-2 py-0.5 rounded border border-emerald-500/10 whitespace-nowrap">
                    {id}
                  </code>
                ))}
              </div>
            </div>
          </div>
        )}
        {data?.stacktrace && (
        <div className="rounded-xl border border-slate-800 bg-black/60 w-full overflow-hidden">
            <div className="flex items-center px-3 py-2 bg-slate-900/80 border-b border-slate-800">
            <Terminal size={14} className="text-slate-500" />
            <span className="text-[10px] font-bold text-slate-500 uppercase font-mono tracking-widest leading-none">
             Stack Trace Evidence
            </span>
            </div>
            <pre 
            className="p-4 m-0 bg-slate-950 text-slate-300 font-mono text-[11px] leading-relaxed whitespace-pre-wrap tracking-widest"
            style={{ maxHeight: '160px', overflow: 'auto' }}
            >
            {data.stacktrace.replace(/\\?Enough thinking\.?/gi, '').replace(/\\n/g, '\n').trim()}
            </pre>
        </div>
        )}
        {/* 6. Simplified Handoff Footer */}
        <div className="pt-2 border-t border-slate-900">
          <div className="flex items-center gap-3 text-blue-400/80 group">
            <div className="p-1.5 bg-blue-500/10 rounded-lg group-hover:bg-blue-500/20 transition-colors">
              <Cpu size={16} className="animate-pulse" />
            </div>
            <span className="text-[11px] font-medium italic tracking-wide">
              Handing over to Agent 2 for codebase mapping... Enough thinking.
            </span>
          </div>
          <button 
          onClick={downloadPDF}
          className="flex items-center gap-2 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-[11px] font-bold transition-all border border-slate-700"
        >
          <Download size={12} />
          Export Report
        </button>
        </div>
      </div>

      {/* --- EXPORT TEMPLATE (Hidden) --- */}
      <div className="fixed top-0 left-0 opacity-0 pointer-events-none z-[-1]"
        style={{ width: '800px' }}>
        <div ref={reportRef} className="w-[800px] p-16 bg-slate-950 text-white space-y-10 font-mono">
          <h1 className="text-3xl font-bold border-b border-slate-800 pb-4 text-blue-400">DYNAMIC PATTERN ANALYSIS</h1>

          {Array.isArray(data?.errorPatterns) && data.errorPatterns.map((pattern: any, idx: number) => (
            <div key={idx} data-pattern-card={idx} className="p-8 bg-slate-900/40 border border-slate-800 rounded-3xl space-y-6">
              <h2 className="text-xl font-black text-slate-100 uppercase tracking-tighter border-l-4 border-blue-500 pl-4">
                Pattern Cluster #{idx + 1}
              </h2>

              {/* DYNAMIC LOOP STARTS HERE */}
              <div className="grid grid-cols-2 gap-y-4 gap-x-8">
                {Object.entries(pattern).map(([key, value]) => {
                  // Skip keys that are too long for a small grid (like stack traces)
                  if (key === 'stack_trace_sample' || key === 'stack_frames') return null;

                  return (
                    <div key={key} className="border-b border-slate-800/50 pb-2">
                      <p className="text-[10px] text-slate-500 font-bold uppercase tracking-widest">{formatKey(key)}</p>
                      <p className="text-xs text-slate-200 mt-1 break-all">
                        {Array.isArray(value) ? value.join(', ') : String(value)}
                      </p>
                    </div>
                  );
                })}
              </div>

              {/* SPECIAL HANDLING FOR LONG FIELDS (Stack Trace) */}
              {pattern.stack_trace_sample && (
                <div className="mt-6 space-y-2">
                  <p className="text-[10px] text-slate-500 font-bold uppercase tracking-widest">Representative Trace</p>
                  <pre className="p-4 bg-black rounded-xl text-[10px] text-slate-400 border border-slate-800 overflow-hidden whitespace-pre-wrap leading-relaxed">
                    {pattern.stack_trace_sample}
                  </pre>
                </div>
              )}
            </div>
          ))}
          <div className="pt-10 border-t border-slate-900">
            <p className="text-2xl italic font-serif text-slate-500">"Enough thinking."</p>
          </div>
        </div>
      </div>
    </div>
  );
};