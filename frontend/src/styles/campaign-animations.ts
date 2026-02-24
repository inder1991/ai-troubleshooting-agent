// Framer Motion variants for campaign UI components

export const telescopeVariants = {
  hidden: { opacity: 0, scale: 0.92, y: 20 },
  visible: { opacity: 1, scale: 1, y: 0, transition: { type: 'spring', stiffness: 300, damping: 28 } },
  exit: { opacity: 0, scale: 0.95, transition: { duration: 0.2 } },
};

export const repoNodeVariants = {
  hidden: { opacity: 0, x: -20 },
  visible: (i: number) => ({
    opacity: 1, x: 0,
    transition: { delay: i * 0.1, type: 'spring', stiffness: 400, damping: 30 },
  }),
};

export const packetCardVariants = {
  hidden: { opacity: 0, scale: 0.95, y: 8 },
  visible: { opacity: 1, scale: 1, y: 0, transition: { type: 'spring', stiffness: 400, damping: 30 } },
};

export const approvalTransition = {
  approved: { borderColor: '#10b981', backgroundColor: 'rgba(16, 185, 129, 0.05)' },
  rejected: { borderColor: '#ef4444', backgroundColor: 'rgba(239, 68, 68, 0.05)' },
  revoked: { borderColor: '#f59e0b', backgroundColor: 'rgba(245, 158, 11, 0.05)' },
};

export const masterGateVariants = {
  hidden: { y: 10, opacity: 0 },
  visible: { y: 0, opacity: 1, transition: { type: 'spring', stiffness: 300, damping: 25 } },
};
