import { useEffect } from 'react';
import type { CapabilityType } from '../types';

interface KeyboardShortcutHandlers {
  onNewSession: () => void;
  onSelectCapability: (capability: CapabilityType) => void;
  onGoHome: () => void;
}

const capabilityKeys: Record<string, CapabilityType> = {
  '1': 'troubleshoot_app',
  '2': 'pr_review',
  '3': 'github_issue_fix',
  '4': 'cluster_diagnostics',
};

export const useKeyboardShortcuts = (handlers: KeyboardShortcutHandlers) => {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't intercept when typing in inputs
      const target = e.target as HTMLElement;
      if (
        target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.tagName === 'SELECT' ||
        target.isContentEditable
      ) {
        // Allow Escape even in inputs
        if (e.key === 'Escape') {
          (target as HTMLInputElement).blur();
          handlers.onGoHome();
          e.preventDefault();
          return;
        }
        return;
      }

      // Escape: Back to home
      if (e.key === 'Escape') {
        handlers.onGoHome();
        e.preventDefault();
        return;
      }

      // Ctrl/Cmd + N: New session
      if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
        handlers.onNewSession();
        e.preventDefault();
        return;
      }

      // Ctrl/Cmd + 1/2/3/4: Quick-pick capability
      if ((e.ctrlKey || e.metaKey) && capabilityKeys[e.key]) {
        handlers.onSelectCapability(capabilityKeys[e.key]);
        e.preventDefault();
        return;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handlers]);
};
