import { Outlet, useLocation } from 'react-router-dom';
import { useState, useEffect } from 'react';
import SidebarNav from '../components/Layout/SidebarNav';
import { NavigationProvider, useNavigation, pathToNavView } from '../contexts/NavigationContext';

function shouldHideSidebar(pathname: string): boolean {
  if (pathname === '/network/live-topology') return true;
  if (pathname.startsWith('/investigations/') && pathname !== '/investigations/') return true;
  return false;
}

export default function AppLayout() {
  const location = useLocation();
  const showSidebar = !shouldHideSidebar(location.pathname);

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
      <AppLayoutInner showSidebar={showSidebar} isSidebarPinned={isSidebarPinned} />
    </NavigationProvider>
  );
}

function AppLayoutInner({ showSidebar, isSidebarPinned }: { showSidebar: boolean; isSidebarPinned: boolean }) {
  const { navigateByView } = useNavigation();
  const location = useLocation();
  const activeView = pathToNavView(location.pathname);

  return (
    <div className="flex h-screen w-full overflow-hidden text-slate-100 antialiased command-center-bg">
      {showSidebar && (
        <SidebarNav
          activeView={activeView}
          onNavigate={navigateByView}
          onNewMission={() => navigateByView('home')}
        />
      )}
      <div
        className="flex-1 flex flex-col min-w-0 overflow-hidden transition-all duration-300 ease-out"
        style={{ paddingLeft: showSidebar && isSidebarPinned ? 215 : 0 }}
      >
        <Outlet />
      </div>
    </div>
  );
}
