import React, { createContext, useContext, useState, useCallback } from 'react';

export interface TelescopeTarget {
  kind: string;
  name: string;
  namespace: string;
}

interface TelescopeContextValue {
  isOpen: boolean;
  target: TelescopeTarget | null;
  defaultTab: 'yaml' | 'logs' | 'events';
  breadcrumbs: TelescopeTarget[];
  openTelescope: (target: TelescopeTarget, defaultTab?: 'yaml' | 'logs' | 'events') => void;
  closeTelescope: () => void;
  pushBreadcrumb: (target: TelescopeTarget) => void;
  popBreadcrumb: () => void;
}

const TelescopeCtx = createContext<TelescopeContextValue | null>(null);

export const useTelescopeContext = () => {
  const ctx = useContext(TelescopeCtx);
  if (!ctx) throw new Error('useTelescopeContext must be used within TelescopeProvider');
  return ctx;
};

export const TelescopeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [target, setTarget] = useState<TelescopeTarget | null>(null);
  const [defaultTab, setDefaultTab] = useState<'yaml' | 'logs' | 'events'>('yaml');
  const [breadcrumbs, setBreadcrumbs] = useState<TelescopeTarget[]>([]);

  const openTelescope = useCallback((t: TelescopeTarget, tab: 'yaml' | 'logs' | 'events' = 'yaml') => {
    setTarget(t);
    setDefaultTab(tab);
    setBreadcrumbs([t]);
    setIsOpen(true);
  }, []);

  const closeTelescope = useCallback(() => {
    setIsOpen(false);
    setTarget(null);
    setBreadcrumbs([]);
  }, []);

  const pushBreadcrumb = useCallback((t: TelescopeTarget) => {
    setTarget(t);
    setBreadcrumbs(prev => [...prev, t]);
  }, []);

  const popBreadcrumb = useCallback(() => {
    setBreadcrumbs(prev => {
      if (prev.length <= 1) return prev;
      const next = prev.slice(0, -1);
      setTarget(next[next.length - 1]);
      return next;
    });
  }, []);

  return (
    <TelescopeCtx.Provider value={{ isOpen, target, defaultTab, breadcrumbs, openTelescope, closeTelescope, pushBreadcrumb, popBreadcrumb }}>
      {children}
    </TelescopeCtx.Provider>
  );
};
