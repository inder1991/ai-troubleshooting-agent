import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useCampaignContext } from '../../contexts/CampaignContext';
import CausalRoleBadge from './cards/CausalRoleBadge';
import VSCodeLink from './VSCodeLink';
import { telescopeVariants } from '../../styles/campaign-animations';

const causalRoleToBadge: Record<string, 'root_cause' | 'cascading_failure' | 'correlated_anomaly'> = {
  root_cause: 'root_cause',
  cascading: 'cascading_failure',
  correlated: 'correlated_anomaly',
};

const SurgicalTelescope: React.FC = () => {
  const {
    telescopeRepo, telescopeData, closeTelescope, campaign,
    approveRepo, rejectRepo,
  } = useCampaignContext();

  const [activeFileIdx, setActiveFileIdx] = useState(0);

  if (!telescopeRepo || !telescopeData) return null;

  const repoFix = campaign?.repos.find(r => r.repo_url === telescopeRepo);
  const causalRole = repoFix?.causal_role || 'correlated';
  const badgeRole = causalRoleToBadge[causalRole] || 'correlated_anomaly';
  const serviceName = telescopeData.service_name;
  const files = telescopeData.files;
  const activeFile = files[activeFileIdx];

  return (
    <AnimatePresence>
      <motion.div
        key="telescope-overlay"
        className="fixed inset-0 z-[80] flex items-start justify-center"
        initial="hidden"
        animate="visible"
        exit="exit"
      >
        {/* Backdrop */}
        <motion.div
          className="absolute inset-0 bg-black/85 backdrop-blur-sm"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={closeTelescope}
        />

        {/* Content panel */}
        <motion.div
          variants={telescopeVariants}
          className="relative mt-12 mx-4 w-full max-w-[95vw] max-h-[calc(100vh-6rem)] flex flex-col bg-[#0a1a1f] border border-slate-700/50 rounded-xl shadow-2xl overflow-hidden"
        >
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-3 border-b border-slate-800/50 bg-slate-900/50">
            <div className="flex items-center gap-3">
              <span className="material-symbols-outlined text-cyan-400 text-[20px]">biotech</span>
              <span className="text-[12px] font-black text-slate-200 tracking-[0.1em] uppercase">
                Surgical Telescope
              </span>
              <span className="text-[11px] text-slate-400 font-mono">
                {serviceName}
              </span>
              <CausalRoleBadge role={badgeRole} />
            </div>
            <button
              onClick={closeTelescope}
              className="p-1 rounded hover:bg-slate-800 transition-colors"
            >
              <span className="material-symbols-outlined text-slate-400 text-[20px]">close</span>
            </button>
          </div>

          {/* File tabs */}
          {files.length > 1 && (
            <div className="flex items-center gap-1 px-5 py-2 border-b border-slate-800/30 overflow-x-auto">
              {files.map((f, i) => (
                <button
                  key={f.file_path}
                  onClick={() => setActiveFileIdx(i)}
                  className={`px-3 py-1 rounded text-[10px] font-mono whitespace-nowrap transition-colors
                    ${i === activeFileIdx
                      ? 'bg-cyan-950/40 text-cyan-400 border border-cyan-700/40'
                      : 'text-slate-500 hover:text-slate-300 hover:bg-slate-800/40'}
                  `}
                >
                  {f.file_path.split('/').pop()}
                </button>
              ))}
            </div>
          )}

          {/* Diff viewer */}
          <div className="flex-1 overflow-auto">
            {activeFile && (
              <DiffSplitView
                originalCode={activeFile.original_code}
                fixedCode={activeFile.fixed_code}
                diff={activeFile.diff}
              />
            )}
          </div>

          {/* Footer actions */}
          <div className="flex items-center justify-between px-5 py-3 border-t border-slate-800/50 bg-slate-900/30">
            <div className="flex items-center gap-2">
              {files.map((f) => (
                <VSCodeLink key={f.file_path} filePath={f.file_path} repoName={serviceName} />
              ))}
            </div>
            {repoFix?.status === 'awaiting_review' && (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => { approveRepo(telescopeRepo); closeTelescope(); }}
                  className="px-4 py-1.5 rounded bg-emerald-950/40 border border-emerald-700/50 hover:bg-emerald-900/40 text-[10px] text-emerald-400 font-bold tracking-wider transition-colors"
                >
                  APPROVE
                </button>
                <button
                  onClick={() => { rejectRepo(telescopeRepo); closeTelescope(); }}
                  className="px-4 py-1.5 rounded bg-red-950/30 border border-red-700/40 hover:bg-red-900/30 text-[10px] text-red-400 font-bold tracking-wider transition-colors"
                >
                  REJECT
                </button>
              </div>
            )}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
};

// ── Inline Diff Split View ──────────────────────────────────────────

interface DiffSplitViewProps {
  originalCode: string;
  fixedCode: string;
  diff: string;
}

const DiffSplitView: React.FC<DiffSplitViewProps> = ({ originalCode, fixedCode, diff }) => {
  // Parse diff to find changed line numbers
  const changedOriginal = new Set<number>();
  const changedFixed = new Set<number>();

  if (diff) {
    let origLine = 0;
    let fixLine = 0;
    for (const line of diff.split('\n')) {
      if (line.startsWith('@@')) {
        const match = line.match(/@@ -(\d+)/);
        if (match) {
          origLine = parseInt(match[1], 10) - 1;
          const fixMatch = line.match(/\+(\d+)/);
          fixLine = fixMatch ? parseInt(fixMatch[1], 10) - 1 : origLine;
        }
      } else if (line.startsWith('-') && !line.startsWith('---')) {
        origLine++;
        changedOriginal.add(origLine);
      } else if (line.startsWith('+') && !line.startsWith('+++')) {
        fixLine++;
        changedFixed.add(fixLine);
      } else {
        origLine++;
        fixLine++;
      }
    }
  }

  const origLines = originalCode.split('\n');
  const fixLines = fixedCode.split('\n');

  return (
    <div className="flex min-h-0">
      {/* Original */}
      <div className="flex-1 border-r border-slate-800/50 overflow-auto">
        <div className="sticky top-0 z-10 px-3 py-1.5 bg-red-950/20 border-b border-slate-800/30">
          <span className="text-[9px] font-bold text-red-400 tracking-wider uppercase">Original</span>
        </div>
        <pre className="text-[10px] font-mono leading-5">
          {origLines.map((line, i) => (
            <div
              key={i}
              className={`flex px-2 ${changedOriginal.has(i + 1) ? 'bg-red-950/30' : ''}`}
            >
              <span className="w-10 text-right pr-3 text-slate-600 select-none shrink-0">{i + 1}</span>
              <span className={`${changedOriginal.has(i + 1) ? 'text-red-300' : 'text-slate-400'}`}>
                {line || ' '}
              </span>
            </div>
          ))}
        </pre>
      </div>

      {/* Fixed */}
      <div className="flex-1 overflow-auto">
        <div className="sticky top-0 z-10 px-3 py-1.5 bg-emerald-950/20 border-b border-slate-800/30">
          <span className="text-[9px] font-bold text-emerald-400 tracking-wider uppercase">Fixed</span>
        </div>
        <pre className="text-[10px] font-mono leading-5">
          {fixLines.map((line, i) => (
            <div
              key={i}
              className={`flex px-2 ${changedFixed.has(i + 1) ? 'bg-emerald-950/30' : ''}`}
            >
              <span className="w-10 text-right pr-3 text-slate-600 select-none shrink-0">{i + 1}</span>
              <span className={`${changedFixed.has(i + 1) ? 'text-emerald-300' : 'text-slate-400'}`}>
                {line || ' '}
              </span>
            </div>
          ))}
        </pre>
      </div>
    </div>
  );
};

export default SurgicalTelescope;
