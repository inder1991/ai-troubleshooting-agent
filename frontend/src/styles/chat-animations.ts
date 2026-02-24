import type { Variants } from 'framer-motion';

export const drawerVariants: Variants = {
  hidden: { x: '100%' },
  visible: {
    x: 0,
    transition: { type: 'spring', stiffness: 280, damping: 32, mass: 1.2 },
  },
  exit: {
    x: '100%',
    transition: { type: 'spring', stiffness: 280, damping: 32, mass: 1.2 },
  },
};

export const backdropVariants: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { duration: 0.2 } },
  exit: { opacity: 0, transition: { duration: 0.2 } },
};

export const triggerTabVariants: Variants = {
  hidden: { x: 60 },
  visible: { x: 0, transition: { type: 'spring', stiffness: 280, damping: 32, mass: 1.2 } },
  exit: { x: 60, transition: { duration: 0.15 } },
};

export const messageVariants: Variants = {
  hidden: { opacity: 0, y: 10 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { type: 'spring', stiffness: 400, damping: 30 },
  },
};
