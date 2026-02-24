import React, { useState } from 'react';
import { motion } from 'framer-motion';

interface ActionChipProps {
  label: string;
  icon?: React.ComponentType<{ size: number | string }>;
  variant: 'primary' | 'warning' | 'danger';
  onClick: () => void;
  disabled?: boolean;
}

const variantStyles: Record<ActionChipProps['variant'], { bg: string; border: string; text: string; hoverBg: string }> = {
  primary: {
    bg: 'bg-cyan-500/15',
    border: 'border-cyan-500/30',
    text: 'text-cyan-400',
    hoverBg: 'hover:bg-cyan-500/25',
  },
  warning: {
    bg: 'bg-amber-500/15',
    border: 'border-amber-500/30',
    text: 'text-amber-400',
    hoverBg: 'hover:bg-amber-500/25',
  },
  danger: {
    bg: 'bg-red-500/15',
    border: 'border-red-500/30',
    text: 'text-red-400',
    hoverBg: 'hover:bg-red-500/25',
  },
};

const ActionChip: React.FC<ActionChipProps> = ({ label, icon: Icon, variant, onClick, disabled = false }) => {
  const [isClicked, setIsClicked] = useState(false);
  const styles = variantStyles[variant];

  const handleClick = () => {
    if (isClicked || disabled) return;
    setIsClicked(true);
    setTimeout(() => onClick(), 400);
  };

  return (
    <motion.button
      type="button"
      whileHover={!isClicked && !disabled ? { y: -2, scale: 1.02 } : undefined}
      whileTap={!isClicked && !disabled ? { scale: 0.98 } : undefined}
      onClick={handleClick}
      disabled={disabled || isClicked}
      className={`
        inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-[10px] font-bold uppercase tracking-wider
        transition-colors cursor-pointer
        disabled:opacity-40 disabled:cursor-not-allowed
        ${isClicked ? 'animate-chip-success' : `${styles.bg} ${styles.border} ${styles.text} ${styles.hoverBg}`}
      `}
    >
      {Icon && <Icon size={12} />}
      {label}
    </motion.button>
  );
};

export default ActionChip;
