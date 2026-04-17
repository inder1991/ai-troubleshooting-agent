import { Outlet, useLocation } from 'react-router-dom';
import { useState, useEffect } from 'react';
import SidebarNav from '../components/Layout/SidebarNav';
import { NavigationProvider, useNavigation, pathToNavView } from '../contexts/NavigationContext';

function shouldHideSidebar(pathname: string): boolean {
  // Live topology is the only fullscreen-only view.
  if (pathname === '/network/live-topology') return true;
  return false;
}

function shouldForceCollapse(pathname: string): boolean {
  // Investigation routes keep a 48px rail (no labels) so users don't lose
  // orientation; full-width sidebar would steal real estate from the War Room.
  if (pathname.startsWith('/investigations/') && pathname !== '/investigations/') return true;
  return false;
}

export default function AppLayout() {
  const location = useLocation();
  const showSidebar = !shouldHideSidebar(location.pathname);
  const forceCollapsed = shouldForceCollapse(location.pathname);

  const [isSidebarPinned, setIsSidebarPinned] = useState(() => {
    try { return localStorage.getItem('sidebar-pinned') === 'true'; } catch { return false; }
  });

  useEffect(() => {
    const handlePinChange = () => {
      try { setIsSidebarPinned(localStorage.getItem('sidebar-pinned') === 'true'); } catch { /* noop */ }
    };
    window.addEventListener('sidebar-pin-change', handlePinChange);
    return () => window.removeEventListener('sidebar-pin-change', handlePinChange);
  }, []);

  return (
    <NavigationProvider>
      <AppLayoutInner
        showSidebar={showSidebar}
        isSidebarPinned={isSidebarPinned}
        forceCollapsed={forceCollapsed}
      />
    </NavigationProvider>
  );
}

function AppLayoutInner({
  showSidebar,
  isSidebarPinned,
  forceCollapsed,
}: {
  showSidebar: boolean;
  isSidebarPinned: boolean;
  forceCollapsed: boolean;
}) {
  const { navigateByView } = useNavigation();
  const location = useLocation();
  const activeView = pathToNavView(location.pathname);

  // Forced-collapsed routes ignore the pinned pref (rail mode is 48px, not 215px).
  const effectivePinned = isSidebarPinned && !forceCollapsed;

  return (
    <div className="flex h-screen w-full overflow-hidden text-slate-100 antialiased command-center-bg">
      {showSidebar && (
        <SidebarNav
          activeView={activeView}
          onNavigate={navigateByView}
          onNewMission={() => navigateByView('home')}
          forceCollapsed={forceCollapsed}
        />
      )}
      <div
        className="flex-1 flex flex-col min-w-0 overflow-hidden transition-all duration-300 ease-out"
        style={{ paddingLeft: showSidebar && effectivePinned ? 215 : 0 }}
      >
        <Outlet />
      </div>
    </div>
  );
}
