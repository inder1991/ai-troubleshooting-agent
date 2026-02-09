import React from 'react';
import { CheckCircle, ExternalLink, GitPullRequest, Copy, Check } from 'lucide-react';

interface PRSuccessProps {
  data: {
    pr_url: string;
    pr_number: number;
    branch_name?: string;
  };
}

export const PRSuccessScreen: React.FC<PRSuccessProps> = ({ data }) => {
  const [copied, setCopied] = React.useState(false);

  const handleCopyURL = () => {
    navigator.clipboard.writeText(data.pr_url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleOpenPR = () => {
    window.open(data.pr_url, '_blank', 'noopener,noreferrer');
  };

  return (
    <div className="border border-emerald-500/30 rounded bg-gradient-to-br from-emerald-950/20 to-slate-950/40 p-6 space-y-4">
      {/* Success Icon & Header */}
      <div className="flex flex-col items-center gap-3 text-center">
        <div className="relative">
          <div className="absolute inset-0 bg-emerald-500/20 blur-xl rounded-full" />
          <div className="relative bg-emerald-500/10 border border-emerald-500/30 rounded-full p-4">
            <CheckCircle size={32} className="text-emerald-400" />
          </div>
        </div>
        
        <div>
          <h3 className="text-[14px] font-bold text-emerald-400 uppercase tracking-widest mb-1">
            Pull Request Created
          </h3>
          <p className="text-[10px] text-slate-500">
            Your fix has been successfully submitted for review
          </p>
        </div>
      </div>

      {/* PR Details */}
      <div className="border border-slate-800 rounded bg-slate-950/40 p-4 space-y-3">
        <div className="flex items-center gap-2 mb-2">
          <GitPullRequest size={12} className="text-slate-500" />
          <span className="text-[9px] text-slate-500 uppercase font-bold">PR Details</span>
        </div>

        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <span className="text-[9px] text-slate-600">PR Number:</span>
            <span className="text-[10px] font-mono text-emerald-400">#{data.pr_number}</span>
          </div>

          {data.branch_name && (
            <div className="flex justify-between items-center">
              <span className="text-[9px] text-slate-600">Branch:</span>
              <span className="text-[10px] font-mono text-blue-400">{data.branch_name}</span>
            </div>
          )}

          <div className="pt-2 border-t border-slate-800">
            <div className="text-[9px] text-slate-600 mb-2">PR URL:</div>
            <div className="flex items-center gap-2 bg-slate-950 border border-slate-900 rounded p-2">
              <span className="text-[8px] font-mono text-slate-400 flex-1 truncate">
                {data.pr_url}
              </span>
              <button
                onClick={handleCopyURL}
                className="text-slate-500 hover:text-blue-400 transition-colors flex-shrink-0"
                title="Copy URL"
              >
                {copied ? (
                  <Check size={12} className="text-emerald-400" />
                ) : (
                  <Copy size={12} />
                )}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex gap-3">
        <button
          onClick={handleOpenPR}
          className="flex-1 bg-emerald-600 hover:bg-emerald-700 py-3 rounded text-[10px] font-bold uppercase tracking-widest text-white transition-all shadow-lg hover:shadow-emerald-500/50 flex items-center justify-center gap-2"
        >
          <ExternalLink size={14} />
          View Pull Request
        </button>
      </div>

      {/* Next Steps */}
      <div className="border border-slate-800 rounded bg-slate-950/40 p-3 space-y-2">
        <div className="text-[9px] font-bold text-slate-500 uppercase">Next Steps:</div>
        <ul className="space-y-1.5 text-[8px] text-slate-600">
          <li className="flex items-start gap-2">
            <span className="text-emerald-500">1.</span>
            <span>Review the changes in GitHub</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-emerald-500">2.</span>
            <span>Request reviews from team members</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-emerald-500">3.</span>
            <span>Wait for CI/CD checks to pass</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-emerald-500">4.</span>
            <span>Merge when approved</span>
          </li>
        </ul>
      </div>
    </div>
  );
};