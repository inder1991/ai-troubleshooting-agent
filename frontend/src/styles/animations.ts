import type { Variants } from 'framer-motion';

export const capsuleVariants: Variants = {
  hidden: { opacity: 0, x: -20, filter: 'blur(4px)' },
  visible: {
    opacity: 1,
    x: 0,
    filter: 'blur(0px)',
    transition: { type: 'spring', stiffness: 400, damping: 30 },
  },
  exit: { opacity: 0, x: -10, transition: { duration: 0.2 } },
};

export const findingVariants: Variants = {
  hidden: { opacity: 0, scale: 0.95, height: 0 },
  visible: {
    opacity: 1,
    scale: 1,
    height: 'auto',
    transition: { type: 'spring', stiffness: 400, damping: 30 },
  },
};

export const ribbonExpandVariants: Variants = {
  collapsed: { height: 24, overflow: 'hidden' as const },
  expanded: {
    height: 'auto',
    overflow: 'visible' as const,
    transition: { type: 'spring', stiffness: 400, damping: 30 },
  },
};
