import React, { useState, useRef, useCallback } from 'react';

interface HoldToConfirmProps {
  onConfirm: () => void;
  holdDuration?: number; // ms
  label: string;
  holdLabel?: string;
  icon?: string;
  className?: string;
  disabled?: boolean;
}

const HoldToConfirm: React.FC<HoldToConfirmProps> = ({
  onConfirm,
  holdDuration = 2000,
  label,
  holdLabel = 'Hold to confirm...',
  icon,
  className = '',
  disabled = false,
}) => {
  const [progress, setProgress] = useState(0);
  const [holding, setHolding] = useState(false);
  const startTimeRef = useRef<number>(0);
  const rafRef = useRef<number>(0);
  const confirmedRef = useRef(false);

  const animate = useCallback(() => {
    const elapsed = Date.now() - startTimeRef.current;
    const pct = Math.min(elapsed / holdDuration, 1);
    setProgress(pct);

    if (pct >= 1 && !confirmedRef.current) {
      confirmedRef.current = true;
      setHolding(false);
      setProgress(0);
      onConfirm();
      return;
    }

    if (pct < 1) {
      rafRef.current = requestAnimationFrame(animate);
    }
  }, [holdDuration, onConfirm]);

  const handleStart = useCallback(() => {
    if (disabled) return;
    confirmedRef.current = false;
    startTimeRef.current = Date.now();
    setHolding(true);
    rafRef.current = requestAnimationFrame(animate);
  }, [disabled, animate]);

  const handleEnd = useCallback(() => {
    cancelAnimationFrame(rafRef.current);
    setHolding(false);
    setProgress(0);
  }, []);

  return (
    <button
      onMouseDown={handleStart}
      onMouseUp={handleEnd}
      onMouseLeave={handleEnd}
      onTouchStart={handleStart}
      onTouchEnd={handleEnd}
      disabled={disabled}
      className={`relative overflow-hidden select-none ${className} ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
      aria-label={label}
    >
      {/* Progress fill */}
      {holding && (
        <div
          className="absolute inset-0 bg-green-500/20 transition-none"
          style={{ width: `${progress * 100}%` }}
        />
      )}
      <span className="relative z-10 flex items-center gap-1.5">
        {icon && (
          <span
            className="material-symbols-outlined text-xs"
            style={{ fontFamily: 'Material Symbols Outlined' }}
          >
            {icon}
          </span>
        )}
        {holding ? holdLabel : label}
      </span>
    </button>
  );
};

export default HoldToConfirm;
