import { useState, useEffect, useRef } from 'react';

export function usePhaseTracker(scrollRef: React.RefObject<HTMLDivElement | null>): string | null {
  const [activePhaseId, setActivePhaseId] = useState<string | null>(null);
  const observerRef = useRef<IntersectionObserver | null>(null);

  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;

    observerRef.current = new IntersectionObserver(
      (entries) => {
        // Find the most visible phase element near the top
        let topMostVisible: { id: string; top: number } | null = null;

        for (const entry of entries) {
          if (entry.isIntersecting) {
            const top = entry.boundingClientRect.top;
            if (!topMostVisible || top < topMostVisible.top) {
              topMostVisible = { id: entry.target.id, top };
            }
          }
        }

        if (topMostVisible) {
          setActivePhaseId(topMostVisible.id);
        }
      },
      {
        root: container,
        rootMargin: '-32px 0px -80% 0px',
        threshold: 0,
      },
    );

    // Observe all phase elements
    const phaseElements = container.querySelectorAll('[id^="phase-"]');
    phaseElements.forEach((el) => observerRef.current!.observe(el));

    return () => {
      observerRef.current?.disconnect();
    };
  }, [scrollRef]);

  // Re-observe when new phases appear
  useEffect(() => {
    const container = scrollRef.current;
    if (!container || !observerRef.current) return;

    const mutationObserver = new MutationObserver(() => {
      const observer = observerRef.current;
      if (!observer) return;
      observer.disconnect();
      const phaseElements = container.querySelectorAll('[id^="phase-"]');
      phaseElements.forEach((el) => observer.observe(el));
    });

    mutationObserver.observe(container, { childList: true, subtree: true });
    return () => mutationObserver.disconnect();
  }, [scrollRef]);

  return activePhaseId;
}
