import React, { createContext, useContext, useState, useCallback, useRef } from 'react';

type ToastType = 'success' | 'error' | 'info' | 'warning';

interface Toast {
  id: string;
  type: ToastType;
  message: string;
  duration: number;
}

interface ToastContextType {
  addToast: (type: ToastType, message: string, duration?: number) => void;
}

const ToastContext = createContext<ToastContextType | null>(null);

export const useToast = (): ToastContextType => {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within ToastProvider');
  return ctx;
};

const typeStyles: Record<ToastType, { bg: string; border: string; text: string; icon: string }> = {
  success: { bg: 'bg-green-900/90', border: 'border-green-500', text: 'text-green-100', icon: 'check_circle' },
  error: { bg: 'bg-red-900/90', border: 'border-red-500', text: 'text-red-100', icon: 'error' },
  info: { bg: 'bg-[#0a2a3d]/90', border: 'border-[#07b6d5]', text: 'text-[#07b6d5]', icon: 'info' },
  warning: { bg: 'bg-amber-900/90', border: 'border-amber-500', text: 'text-amber-100', icon: 'warning' },
};

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const counterRef = useRef(0);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = useCallback((type: ToastType, message: string, duration = 4000) => {
    const id = `toast-${++counterRef.current}`;
    setToasts((prev) => [...prev, { id, type, message, duration }]);
    setTimeout(() => removeToast(id), duration);
  }, [removeToast]);

  return (
    <ToastContext.Provider value={{ addToast }}>
      {children}
      <div className="fixed top-4 right-4 z-50 flex flex-col gap-2 pointer-events-none">
        {toasts.map((toast) => {
          const style = typeStyles[toast.type];
          return (
            <div
              key={toast.id}
              className={`pointer-events-auto ${style.bg} border ${style.border} ${style.text} px-4 py-3 rounded-lg shadow-lg max-w-md animate-[slideIn_0.2s_ease-out] flex items-start gap-2`}
            >
              <span
                className="material-symbols-outlined text-base mt-0.5 shrink-0"
                style={{ fontFamily: 'Material Symbols Outlined' }}
              >
                {style.icon}
              </span>
              <p className="text-sm flex-1">{toast.message}</p>
              <button
                onClick={() => removeToast(toast.id)}
                className="text-current opacity-60 hover:opacity-100 shrink-0 ml-2"
              >
                &times;
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
};
