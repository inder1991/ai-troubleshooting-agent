import React from 'react';

export type NavView = 'home' | 'sessions' | 'integrations' | 'settings';

interface SidebarNavProps {
  activeView: NavView;
  onNavigate: (view: NavView) => void;
  onNewMission?: () => void;
}

const navItems: { id: NavView; label: string; icon: string }[] = [
  { id: 'home', label: 'Dashboard', icon: 'dashboard' },
  { id: 'sessions', label: 'Sessions', icon: 'history' },
  { id: 'integrations', label: 'Integrations', icon: 'hub' },
  { id: 'settings', label: 'Settings', icon: 'settings' },
];

const SidebarNav: React.FC<SidebarNavProps> = ({ activeView, onNavigate, onNewMission }) => {
  return (
    <aside className="w-64 flex-shrink-0 border-r border-[#224349] flex flex-col justify-between py-6" style={{ backgroundColor: '#0f2023' }}>
      <div className="flex flex-col gap-8">
        {/* Brand Logo */}
        <div className="px-6 flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg flex items-center justify-center border" style={{ backgroundColor: 'rgba(7,182,213,0.2)', borderColor: 'rgba(7,182,213,0.3)' }}>
            <span className="material-symbols-outlined text-2xl" style={{ fontFamily: 'Material Symbols Outlined', color: '#07b6d5' }}>pest_control</span>
          </div>
          <div className="flex flex-col">
            <h1 className="text-white text-lg font-bold leading-none tracking-tight">DebugDuck</h1>
            <p className="text-[10px] font-bold uppercase tracking-widest mt-1" style={{ color: '#07b6d5' }}>Command Center</p>
          </div>
        </div>

        {/* Navigation Links */}
        <nav className="flex flex-col gap-1 px-3">
          {navItems.map((item) => {
            const isActive = activeView === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onNavigate(item.id)}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors border ${
                  isActive
                    ? 'text-[#07b6d5]'
                    : 'text-slate-400 hover:text-white border-transparent'
                }`}
                style={isActive ? {
                  backgroundColor: 'rgba(7,182,213,0.1)',
                  borderColor: 'rgba(7,182,213,0.2)',
                } : {}}
              >
                <span className="material-symbols-outlined" style={{ fontFamily: 'Material Symbols Outlined' }}>{item.icon}</span>
                <span className={`text-sm ${isActive ? 'font-semibold tracking-wide' : 'font-medium'}`}>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </div>

      {/* Sidebar Bottom Action */}
      <div className="px-4">
        <button
          onClick={onNewMission}
          className="w-full flex items-center justify-center gap-2 font-bold py-2.5 rounded-lg transition-all group"
          style={{ backgroundColor: '#07b6d5', color: '#0f2023', boxShadow: '0 4px 14px rgba(7,182,213,0.1)' }}
        >
          <span className="material-symbols-outlined text-[20px] group-hover:rotate-180 transition-transform duration-500" style={{ fontFamily: 'Material Symbols Outlined' }}>add_circle</span>
          <span className="text-sm">New Mission</span>
        </button>
      </div>
    </aside>
  );
};

export default SidebarNav;
