import type { Variants } from 'framer-motion';

export const nodeEnterVariants: Variants = {
  hidden: { scale: 0, opacity: 0 },
  visible: {
    scale: 1,
    opacity: 1,
    transition: { type: 'spring', stiffness: 400, damping: 30 },
  },
  exit: { scale: 0, opacity: 0, transition: { duration: 0.2 } },
};

export const edgeEnterVariants: Variants = {
  hidden: { pathLength: 0, opacity: 0 },
  visible: {
    pathLength: 1,
    opacity: 1,
    transition: { ease: 'easeOut', duration: 0.6 },
  },
};

export const filterBannerVariants: Variants = {
  hidden: { height: 0, opacity: 0, overflow: 'hidden' as const },
  visible: {
    height: 'auto',
    opacity: 1,
    overflow: 'visible' as const,
    transition: { type: 'spring', stiffness: 400, damping: 30 },
  },
  exit: {
    height: 0,
    opacity: 0,
    overflow: 'hidden' as const,
    transition: { duration: 0.2 },
  },
};
