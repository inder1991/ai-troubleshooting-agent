import React, { useRef } from 'react';
import { motion } from 'framer-motion';
import { useInView } from 'react-intersection-observer';

interface GhostPhaseWrapperProps {
  isComplete: boolean;
  phaseId: string;
  children: React.ReactNode;
}

export const GhostPhaseWrapper: React.FC<GhostPhaseWrapperProps> = ({
  isComplete,
  phaseId,
  children,
}) => {
  const { ref, inView, entry } = useInView({ threshold: 0 });
  const hasBeenSeen = useRef(false);
  if (inView) hasBeenSeen.current = true;

  const isOffScreenTop = entry ? entry.boundingClientRect.top < 0 : false;
  const shouldGhost = isComplete && !inView && isOffScreenTop && hasBeenSeen.current;

  return (
    <motion.div
      ref={ref}
      data-phase={phaseId}
      animate={{
        opacity: shouldGhost ? 0.3 : 1,
        filter: shouldGhost ? 'grayscale(1)' : 'grayscale(0)',
      }}
      transition={{ duration: 0.6, ease: 'easeInOut' }}
      className={shouldGhost ? 'ghost-phase' : undefined}
      style={shouldGhost ? { contentVisibility: 'auto', containIntrinsicSize: 'auto 500px' } : undefined}
    >
      {children}
    </motion.div>
  );
};
