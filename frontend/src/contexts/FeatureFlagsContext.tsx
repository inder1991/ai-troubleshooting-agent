import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from 'react';
import type { ReactNode } from 'react';
import { API_BASE_URL } from '../services/api';

interface FeatureFlags {
  workflows: boolean;
  loading: boolean;
}

interface FeatureFlagsContextValue extends FeatureFlags {
  retry: () => Promise<void>;
}

const FeatureFlagsContext = createContext<FeatureFlagsContextValue | null>(null);

export function FeatureFlagsProvider({ children }: { children: ReactNode }) {
  const [flags, setFlags] = useState<FeatureFlags>({
    workflows: false,
    loading: true,
  });

  const probe = useCallback(async () => {
    setFlags((f) => ({ ...f, loading: true }));
    try {
      const resp = await fetch(`${API_BASE_URL}/api/v4/workflows`);
      setFlags({ workflows: resp.status !== 404, loading: false });
    } catch {
      // Network error => treat as disabled; UI can call retry().
      setFlags({ workflows: false, loading: false });
    }
  }, []);

  useEffect(() => {
    void probe();
  }, [probe]);

  return (
    <FeatureFlagsContext.Provider value={{ ...flags, retry: probe }}>
      {children}
    </FeatureFlagsContext.Provider>
  );
}

export function useFeatureFlags(): FeatureFlagsContextValue {
  const ctx = useContext(FeatureFlagsContext);
  if (ctx === null) {
    throw new Error('useFeatureFlags must be used within FeatureFlagsProvider');
  }
  return ctx;
}
