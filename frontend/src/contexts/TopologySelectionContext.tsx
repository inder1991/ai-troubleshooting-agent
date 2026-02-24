import React, { createContext, useContext, useState, useCallback, useMemo } from 'react';

interface TopologySelectionValue {
  selectedService: string | null;
  selectService: (id: string | null) => void;
  clearSelection: () => void;
}

const TopologySelectionContext = createContext<TopologySelectionValue | null>(null);

export function useTopologySelection(): TopologySelectionValue {
  const ctx = useContext(TopologySelectionContext);
  if (!ctx) throw new Error('useTopologySelection must be used within TopologySelectionProvider');
  return ctx;
}

export const TopologySelectionProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [selectedService, setSelectedService] = useState<string | null>(null);

  const selectService = useCallback((id: string | null) => {
    setSelectedService((prev) => (prev === id ? null : id));
  }, []);

  const clearSelection = useCallback(() => {
    setSelectedService(null);
  }, []);

  const value = useMemo<TopologySelectionValue>(
    () => ({ selectedService, selectService, clearSelection }),
    [selectedService, selectService, clearSelection],
  );

  return (
    <TopologySelectionContext.Provider value={value}>
      {children}
    </TopologySelectionContext.Provider>
  );
};
