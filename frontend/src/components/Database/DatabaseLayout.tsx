/**
 * DatabaseLayout — Main wrapper with capability-first sidebar.
 * Internal sub-views: overview, connections, diagnostics, monitoring, schema.
 */
import React, { useState } from 'react';
import DBOverview from './DBOverview';
import DBConnections from './DBConnections';
import DBDiagnostics from './DBDiagnostics';
import DBMonitoring from './DBMonitoring';
import DBSchema from './DBSchema';
import DBOperations from './DBOperations';

type DBView = 'overview' | 'connections' | 'diagnostics' | 'monitoring' | 'schema' | 'operations';

const sidebarItems: { id: DBView; label: string; icon: string }[] = [
  { id: 'overview', label: 'Overview', icon: 'dashboard' },
  { id: 'connections', label: 'Connections', icon: 'cable' },
  { id: 'diagnostics', label: 'Diagnostics', icon: 'troubleshoot' },
  { id: 'monitoring', label: 'Monitoring', icon: 'monitoring' },
  { id: 'schema', label: 'Schema', icon: 'account_tree' },
  { id: 'operations', label: 'Operations', icon: 'build' },
];

const DatabaseLayout: React.FC = () => {
  const [activeView, setActiveView] = useState<DBView>('overview');

  return (
    <div className="flex h-full overflow-hidden">
      {/* Internal sidebar */}
      <nav className="w-48 flex-shrink-0 border-r border-slate-700/50 bg-[#0a1a1d] flex flex-col py-3">
        <div className="px-4 mb-4">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-cyan-400 text-xl">storage</span>
            <span className="text-sm font-semibold text-slate-200 tracking-wide">Databases</span>
          </div>
        </div>
        {sidebarItems.map((item) => (
          <button
            key={item.id}
            onClick={() => setActiveView(item.id)}
            className={`
              flex items-center gap-2.5 px-4 py-2 text-left text-sm transition-colors
              ${activeView === item.id
                ? 'bg-cyan-500/10 text-cyan-400 border-r-2 border-cyan-400'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/40'}
            `}
          >
            <span className="material-symbols-outlined text-[18px]">{item.icon}</span>
            {item.label}
          </button>
        ))}
      </nav>

      {/* Content area */}
      <div className="flex-1 overflow-auto">
        {activeView === 'overview' && <DBOverview />}
        {activeView === 'connections' && <DBConnections />}
        {activeView === 'diagnostics' && <DBDiagnostics />}
        {activeView === 'monitoring' && <DBMonitoring />}
        {activeView === 'schema' && <DBSchema />}
        {activeView === 'operations' && <DBOperations />}
      </div>
    </div>
  );
};

export default DatabaseLayout;
