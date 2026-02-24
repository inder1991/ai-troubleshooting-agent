import React from 'react';

interface VSCodeLinkProps {
  filePath: string;
  repoName: string;
  line?: number;
}

const VSCodeLink: React.FC<VSCodeLinkProps> = ({ filePath, repoName, line }) => {
  const localWorkspace = '~/Projects';

  // Extract relative path after repo name
  const pathParts = filePath.split(repoName);
  const relativePath = pathParts.length > 1 ? pathParts[1] : filePath;

  const localTarget = `${localWorkspace}/${repoName}${relativePath}`;
  const href = `vscode://file/${localTarget}${line ? `:${line}` : ''}`;

  return (
    <a
      href={href}
      className="inline-flex items-center gap-1.5 px-2 py-1 rounded bg-slate-800/60 border border-slate-700 hover:bg-slate-700 transition-colors text-[10px] text-cyan-400 font-mono"
    >
      <span className="material-symbols-outlined text-[12px]">code</span>
      LAUNCH IDE
    </a>
  );
};

export default VSCodeLink;
