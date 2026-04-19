import React, { useCallback, useEffect, useRef, useState } from 'react';
import useEmblaCarousel, { type UseEmblaCarouselType } from 'embla-carousel-react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

/**
 * EditorialCarousel (PR 6 of the War Room grid-shell migration)
 *
 * Shared carousel primitive built on Embla. Replaces every
 * swipe-only carousel in the War Room (SymptomDeck today, future
 * ones via inheritance) with one that ships explicit chevron
 * controls + pagination dots so mouse-only inputs can reach every
 * item.
 *
 * Invariants:
 *   · Every item is reachable via click, keyboard (Left/Right Arrow),
 *     trackpad swipe, and touch.
 *   · Chevrons auto-disable at bar bounds via Embla's canScroll API.
 *   · Pagination dots track the active slide.
 *   · `prefers-reduced-motion: reduce` is honored via Embla's
 *     `duration: 0` when the media query matches.
 */

export interface EditorialCarouselProps<T> {
  items: T[];
  renderItem: (item: T, index: number) => React.ReactNode;
  getKey: (item: T, index: number) => string;
  /** Optional label announced to screen readers. */
  ariaLabel?: string;
  /** Optional className applied to the root. */
  className?: string;
  /** Optional slideClassName applied to each slide. */
  slideClassName?: string;
  /** Defaults to 1 (one slide visible); pass 2/3 etc. for multi-up. */
  slidesToShow?: number;
  /** Optional data-testid. */
  'data-testid'?: string;
}

function isReducedMotion(): boolean {
  if (typeof window === 'undefined') return false;
  if (typeof window.matchMedia !== 'function') return false;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

export function EditorialCarousel<T>({
  items,
  renderItem,
  getKey,
  ariaLabel = 'Carousel',
  className = '',
  slideClassName = '',
  slidesToShow = 1,
  ...rest
}: EditorialCarouselProps<T>) {
  const reduce = isReducedMotion();
  const [emblaRef, emblaApi]: UseEmblaCarouselType = useEmblaCarousel({
    loop: false,
    align: 'start',
    containScroll: 'trimSnaps',
    duration: reduce ? 0 : 25,
  });
  const [canScrollPrev, setCanScrollPrev] = useState(false);
  const [canScrollNext, setCanScrollNext] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [scrollSnaps, setScrollSnaps] = useState<number[]>([]);

  const onSelect = useCallback(() => {
    if (!emblaApi) return;
    setSelectedIndex(emblaApi.selectedScrollSnap());
    setCanScrollPrev(emblaApi.canScrollPrev());
    setCanScrollNext(emblaApi.canScrollNext());
  }, [emblaApi]);

  useEffect(() => {
    if (!emblaApi) return;
    onSelect();
    setScrollSnaps(emblaApi.scrollSnapList());
    emblaApi.on('select', onSelect);
    emblaApi.on('reInit', onSelect);
    return () => {
      emblaApi.off('select', onSelect);
      emblaApi.off('reInit', onSelect);
    };
  }, [emblaApi, onSelect, items.length]);

  const scrollPrev = useCallback(() => emblaApi?.scrollPrev(), [emblaApi]);
  const scrollNext = useCallback(() => emblaApi?.scrollNext(), [emblaApi]);
  const scrollTo = useCallback(
    (idx: number) => emblaApi?.scrollTo(idx),
    [emblaApi],
  );

  // Keyboard arrow support when the carousel root has focus.
  const rootRef = useRef<HTMLDivElement>(null);
  const onKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (e.key === 'ArrowLeft') {
        scrollPrev();
      } else if (e.key === 'ArrowRight') {
        scrollNext();
      }
    },
    [scrollPrev, scrollNext],
  );

  if (items.length === 0) return null;

  const slidePct = 100 / slidesToShow;

  return (
    <div
      ref={rootRef}
      className={`editorial-carousel relative ${className}`}
      role="region"
      aria-label={ariaLabel}
      tabIndex={0}
      onKeyDown={onKeyDown}
      data-testid={rest['data-testid']}
    >
      <div className="overflow-hidden" ref={emblaRef}>
        <div className="flex">
          {items.map((item, idx) => (
            <div
              key={getKey(item, idx)}
              className={`editorial-carousel__slide shrink-0 ${slideClassName}`}
              style={{ flex: `0 0 ${slidePct}%` }}
              data-testid={`editorial-slide-${idx}`}
            >
              {renderItem(item, idx)}
            </div>
          ))}
        </div>
      </div>

      {/* Chevrons */}
      <div className="flex items-center justify-between mt-2">
        <button
          type="button"
          onClick={scrollPrev}
          disabled={!canScrollPrev}
          aria-label="Previous slide"
          className="p-1 rounded text-wr-text-muted disabled:opacity-30 disabled:cursor-default hover:text-wr-paper transition-colors focus-visible:outline focus-visible:outline-1 focus-visible:outline-wr-text-muted"
          data-testid="editorial-carousel-prev"
        >
          <ChevronLeft className="w-4 h-4" aria-hidden />
        </button>

        {/* Pagination dots */}
        <div
          className="flex items-center gap-1"
          role="tablist"
          aria-label="Slide selection"
        >
          {scrollSnaps.map((_, idx) => (
            <button
              key={idx}
              type="button"
              role="tab"
              aria-selected={idx === selectedIndex}
              aria-label={`Go to slide ${idx + 1}`}
              onClick={() => scrollTo(idx)}
              className={
                idx === selectedIndex
                  ? 'w-1.5 h-1.5 rounded-full bg-wr-paper'
                  : 'w-1.5 h-1.5 rounded-full bg-wr-text-subtle hover:bg-wr-text-muted transition-colors'
              }
              data-testid={`editorial-carousel-dot-${idx}`}
            />
          ))}
        </div>

        <button
          type="button"
          onClick={scrollNext}
          disabled={!canScrollNext}
          aria-label="Next slide"
          className="p-1 rounded text-wr-text-muted disabled:opacity-30 disabled:cursor-default hover:text-wr-paper transition-colors focus-visible:outline focus-visible:outline-1 focus-visible:outline-wr-text-muted"
          data-testid="editorial-carousel-next"
        >
          <ChevronRight className="w-4 h-4" aria-hidden />
        </button>
      </div>
    </div>
  );
}

export default EditorialCarousel;
