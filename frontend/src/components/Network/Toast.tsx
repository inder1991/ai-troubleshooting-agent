import React, { useState, useCallback, useEffect, useRef } from 'react';

export type ToastType = 'success' | 'error' | 'info' | 'warning';

interface ToastItem {
  id: number;
  message: string;
  type: ToastType;
}

const TYPE_STYLES: Record<ToastType, { bg: string; border: string; icon: string; color: string }> = {
  success: { bg: 'rgba(34,197,94,0.12)', border: 'rgba(34,197,94,0.3)', icon: 'check_circle', color: '#22c55e' },
  error:   { bg: 'rgba(239,68,68,0.12)', border: 'rgba(239,68,68,0.3)', icon: 'error', color: '#ef4444' },
  warning: { bg: 'rgba(245,158,11,0.12)', border: 'rgba(245,158,11,0.3)', icon: 'warning', color: '#f59e0b' },
  info:    { bg: 'rgba(7,182,213,0.12)', border: 'rgba(7,182,213,0.3)', icon: 'info', color: '#07b6d5' },
};

let globalAddToast: ((message: string, type?: ToastType) => void) | null = null;

export function showToast(message: string, type: ToastType = 'info') {
  if (globalAddToast) globalAddToast(message, type);
}

export const ToastContainer: React.FC = () => {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(0);

  const addToast = useCallback((message: string, type: ToastType = 'info') => {
    const id = nextId.current++;
    setToasts(prev => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 4000);
  }, []);

  useEffect(() => {
    globalAddToast = addToast;
    return () => { globalAddToast = null; };
  }, [addToast]);

  if (toasts.length === 0) return null;

  return (
    <div style={{
      position: 'fixed', bottom: 20, right: 20, zIndex: 9999,
      display: 'flex', flexDirection: 'column', gap: 8, maxWidth: 380,
    }}>
      {toasts.map(toast => {
        const style = TYPE_STYLES[toast.type];
        return (
          <div key={toast.id} style={{
            padding: '10px 16px', borderRadius: 8,
            background: style.bg, border: `1px solid ${style.border}`,
            display: 'flex', alignItems: 'flex-start', gap: 8,
            animation: 'toast-slide-in 0.2s ease-out',
            boxShadow: '0 4px 16px rgba(0,0,0,0.3)',
          }}>
            <span className="material-symbols-outlined" style={{ fontSize: 18, color: style.color, flexShrink: 0, marginTop: 1 }}>
              {style.icon}
            </span>
            <span style={{ fontSize: 13, color: '#e2e8f0', lineHeight: 1.4, whiteSpace: 'pre-line' }}>
              {toast.message}
            </span>
            <button
              onClick={() => setToasts(prev => prev.filter(t => t.id !== toast.id))}
              style={{
                marginLeft: 'auto', background: 'transparent', border: 'none',
                color: '#64748b', cursor: 'pointer', padding: 0, flexShrink: 0,
              }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>close</span>
            </button>
          </div>
        );
      })}
      <style>{`
        @keyframes toast-slide-in {
          from { transform: translateX(100%); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
      `}</style>
    </div>
  );
};
