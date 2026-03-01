import React, { useState, useEffect } from 'react';
import { useTelescopeContext } from '../../contexts/TelescopeContext';
import { useChatUI } from '../../contexts/ChatContext';
import { getResource } from '../../services/api';
import type { TelescopeResource } from '../../types';

const TelescopeDrawerV2: React.FC = () => {
  const { isOpen, target, defaultTab, breadcrumbs, closeTelescope, popBreadcrumb } = useTelescopeContext();
  const { sessionId } = useChatUI();
  const [activeTab, setActiveTab] = useState<'yaml' | 'logs' | 'events'>(defaultTab);
  const [data, setData] = useState<TelescopeResource | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => { setActiveTab(defaultTab); }, [defaultTab]);

  useEffect(() => {
    if (!isOpen || !target || !sessionId) return;
    setLoading(true);
    getResource(sessionId, target.namespace, target.kind, target.name)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [isOpen, target, sessionId]);

  return (
    <div
      className={`fixed right-0 top-0 bottom-0 w-[450px] z-[100] bg-[#0a1a1f] border-l border-slate-700/50 shadow-2xl flex flex-col transition-transform duration-300 ease-out ${isOpen && target ? 'translate-x-0' : 'translate-x-full'}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800/50">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" title="Viewing real-time cluster state" />
          <span className="text-[10px] font-bold text-slate-300 tracking-wider uppercase">TELESCOPE</span>
        </div>
        <button onClick={closeTelescope} className="p-1 rounded hover:bg-slate-800 transition-colors">
          <span className="material-symbols-outlined text-slate-400 text-[18px]">close</span>
        </button>
      </div>

      {/* Breadcrumbs */}
      {target && (
        <div className="flex items-center gap-1 px-4 py-2 text-[10px] text-slate-400 overflow-x-auto border-b border-slate-800/30">
          {breadcrumbs.length > 1 && (
            <button onClick={popBreadcrumb} className="mr-1 hover:text-cyan-400 transition-colors">
              <span className="material-symbols-outlined text-[14px]">arrow_back</span>
            </button>
          )}
          {breadcrumbs.map((bc, i) => (
            <React.Fragment key={i}>
              {i > 0 && <span className="text-slate-600">/</span>}
              <span className={i === breadcrumbs.length - 1 ? 'text-cyan-400 font-medium' : ''}>
                {bc.namespace}/{bc.kind}/{bc.name}
              </span>
            </React.Fragment>
          ))}
        </div>
      )}

      {/* Tab Switcher */}
      <div className="flex items-center gap-1 px-4 py-2 border-b border-slate-800/30">
        {(['yaml', 'logs', 'events'] as const).map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-3 py-1 rounded text-[10px] font-bold tracking-wider uppercase transition-colors
              ${activeTab === tab
                ? 'bg-cyan-950/40 text-cyan-400 border border-cyan-700/40'
                : 'text-slate-500 hover:text-slate-300 hover:bg-slate-800/40'}`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto">
        {loading ? (
          <div className="flex items-center justify-center h-32">
            <span className="text-[10px] text-slate-500 animate-pulse">Loading...</span>
          </div>
        ) : activeTab === 'yaml' ? (
          <YAMLTab yaml={data?.yaml || ''} />
        ) : activeTab === 'logs' ? (
          <div className="p-4 text-[10px] text-slate-500">Click LOGS tab to load</div>
        ) : (
          <EventsTab events={data?.events || []} />
        )}
      </div>
    </div>
  );
};

const YAMLTab: React.FC<{ yaml: string }> = ({ yaml }) => {
  if (!yaml) return <div className="p-4 text-[10px] text-slate-500">No YAML data</div>;
  return (
    <pre className="text-[10px] font-mono leading-5 p-4 text-slate-300 overflow-auto whitespace-pre-wrap">
      {yaml}
    </pre>
  );
};

const EventsTab: React.FC<{ events: Array<{ type: string; reason: string; message: string; count: number; last_timestamp: string }> }> = ({ events }) => {
  if (!events.length) return <div className="p-4 text-[10px] text-slate-500">No events</div>;
  return (
    <div className="divide-y divide-slate-800/30">
      {events.map((e, i) => (
        <div key={i} className={`px-4 py-2 ${e.type === 'Warning' ? 'border-l-2 border-amber-500/60' : 'border-l-2 border-slate-700/40'}`}>
          <div className="flex items-center gap-2">
            <span className={`text-[9px] font-bold ${e.type === 'Warning' ? 'text-amber-400' : 'text-slate-500'}`}>{e.reason}</span>
            {e.count > 1 && <span className="text-[9px] text-slate-600">x{e.count}</span>}
          </div>
          <div className="text-[10px] text-slate-400 mt-0.5">{e.message}</div>
        </div>
      ))}
    </div>
  );
};

export default TelescopeDrawerV2;
