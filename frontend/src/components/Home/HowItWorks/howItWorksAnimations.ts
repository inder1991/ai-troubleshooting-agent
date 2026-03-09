import type { Variants } from 'framer-motion';

export const sectionFadeUp: Variants = {
  hidden: { opacity: 0, y: 20 },
  visible: (i: number = 0) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.1, duration: 0.5, ease: 'easeOut' },
  }),
};

export const flowNodeVariants: Variants = {
  hidden: { opacity: 0, scale: 0.8, filter: 'blur(4px)' },
  visible: {
    opacity: 0.6,
    scale: 1,
    filter: 'blur(0px)',
    transition: { duration: 0.3, ease: 'easeOut' },
  },
  active: {
    opacity: 1,
    scale: 1.02,
    filter: 'blur(0px)',
    transition: { duration: 0.2, ease: 'easeOut' },
  },
  done: {
    opacity: 1,
    scale: 1,
    filter: 'blur(0px)',
    transition: { duration: 0.3, ease: 'easeOut' },
  },
};

export const tabContentVariants: Variants = {
  hidden: { opacity: 0, y: 10 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.3, ease: 'easeOut' } },
  exit: { opacity: 0, y: -10, transition: { duration: 0.2, ease: 'easeIn' } },
};
