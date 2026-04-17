import {
  createContext,
  useContext,
  useCallback,
  useState,
  useEffect,
  useRef,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';

/* ──────────────────────────────────────────────────────────── */
/*  Types                                                      */
/* ──────────────────────────────────────────────────────────── */

export interface Toast {
  id: string;
  type: 'success' | 'error' | 'info';
  message: string;
  action?: { label: string; onClick: () => void };
  duration?: number; // ms, default 4000
}

export type ShowToastInput = Omit<Toast, 'id'>;

interface ToastContextValue {
  showToast: (input: ShowToastInput) => void;
  dismissToast: (id: string) => void;
}

/* ──────────────────────────────────────────────────────────── */
/*  Context                                                    */
/* ──────────────────────────────────────────────────────────── */

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error('useToast must be used within a <ToastProvider>');
  }
  return ctx;
}

/* ──────────────────────────────────────────────────────────── */
/*  Helpers                                                    */
/* ──────────────────────────────────────────────────────────── */

let counter = 0;
function nextId(): string {
  return `toast-${++counter}-${Date.now()}`;
}

const DEFAULT_DURATION = 4000;

const typeConfig: Record<
  Toast['type'],
  { icon: string; borderColor: string; iconColor: string }
> = {
  success: {
    icon: 'check_circle',
    borderColor: 'border-l-emerald-500',
    iconColor: 'text-emerald-400',
  },
  error: {
    icon: 'error',
    borderColor: 'border-l-red-500',
    iconColor: 'text-red-400',
  },
  info: {
    icon: 'info',
    borderColor: 'border-l-wr-accent',
    iconColor: 'text-wr-accent',
  },
};

/* ──────────────────────────────────────────────────────────── */
/*  Single toast item                                          */
/* ──────────────────────────────────────────────────────────── */

function ToastItem({
  toast,
  onDismiss,
}: {
  toast: Toast;
  onDismiss: (id: string) => void;
}) {
  const [exiting, setExiting] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout>>();

  const dismiss = useCallback(() => {
    setExiting(true);
    setTimeout(() => onDismiss(toast.id), 200); // matches exit animation
  }, [onDismiss, toast.id]);

  useEffect(() => {
    const dur = toast.duration ?? DEFAULT_DURATION;
    if (dur > 0) {
      timerRef.current = setTimeout(dismiss, dur);
    }
    return () => clearTimeout(timerRef.current);
  }, [dismiss, toast.duration]);

  const cfg = typeConfig[toast.type];
  const role = toast.type === 'error' ? 'alert' : 'status';

  return (
    <div
      role={role}
      aria-live={toast.type === 'error' ? 'assertive' : 'polite'}
      data-testid="toast"
      className={[
        // layout
        'pointer-events-auto flex items-start gap-3 w-80 p-3 rounded-lg border-l-4',
        cfg.borderColor,
        // surface
        'bg-wr-elevated border border-wr-border shadow-lg',
        // animation
        exiting
          ? 'animate-[toast-exit_200ms_ease-in_forwards]'
          : 'animate-[toast-enter_250ms_ease-out_forwards]',
      ].join(' ')}
    >
      {/* Icon */}
      <span
        className={`material-symbols-outlined text-[20px] mt-0.5 shrink-0 ${cfg.iconColor}`}
        aria-hidden="true"
      >
        {cfg.icon}
      </span>

      {/* Body */}
      <div className="flex-1 min-w-0">
        <p className="text-body-sm text-wr-text leading-snug break-words">
          {toast.message}
        </p>

        {toast.action && (
          <button
            type="button"
            onClick={() => {
              toast.action!.onClick();
              dismiss();
            }}
            className="mt-1.5 text-body-xs font-semibold text-wr-accent hover:text-wr-accent/80 transition-colors"
          >
            {toast.action.label}
          </button>
        )}
      </div>

      {/* Close */}
      <button
        type="button"
        aria-label="Close"
        onClick={dismiss}
        className="shrink-0 text-wr-text-muted hover:text-wr-text transition-colors"
      >
        <span className="material-symbols-outlined text-[18px]">close</span>
      </button>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────── */
/*  Container (portal)                                         */
/* ──────────────────────────────────────────────────────────── */

function ToastContainer({
  toasts,
  onDismiss,
}: {
  toasts: Toast[];
  onDismiss: (id: string) => void;
}) {
  if (toasts.length === 0) return null;

  return createPortal(
    <div
      aria-label="Notifications"
      className="fixed top-4 right-4 z-50 flex flex-col gap-2 pointer-events-none"
    >
      {/* newest on top — reverse so latest renders first */}
      {[...toasts].reverse().map((t) => (
        <ToastItem key={t.id} toast={t} onDismiss={onDismiss} />
      ))}
    </div>,
    document.body,
  );
}

/* ──────────────────────────────────────────────────────────── */
/*  Provider                                                   */
/* ──────────────────────────────────────────────────────────── */

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const showToast = useCallback((input: ShowToastInput) => {
    const toast: Toast = { ...input, id: nextId() };
    setToasts((prev) => [...prev, toast]);
  }, []);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ showToast, dismissToast }}>
      {children}
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </ToastContext.Provider>
  );
}
