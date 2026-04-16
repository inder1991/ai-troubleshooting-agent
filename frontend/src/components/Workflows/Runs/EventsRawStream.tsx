import { useRef, useEffect } from 'react';
import type { LiveEvent } from './StepStatusPanel';

interface EventsRawStreamProps {
  events: LiveEvent[];
}

export function EventsRawStream({ events }: EventsRawStreamProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ behavior: 'smooth' });
  }, [events.length]);

  return (
    <div
      data-testid="events-raw-stream"
      className="max-h-64 overflow-auto rounded bg-wr-bg border border-wr-border p-2"
    >
      <pre className="text-xs font-mono text-wr-text-secondary whitespace-pre-wrap">
        {events.length === 0 && (
          <span className="text-wr-text-tertiary italic">No events yet</span>
        )}
        {events.map((evt, i) => (
          <div key={evt.id ?? i}>{JSON.stringify(evt)}</div>
        ))}
      </pre>
      <div ref={bottomRef} />
    </div>
  );
}
