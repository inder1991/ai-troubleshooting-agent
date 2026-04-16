import { useState, useRef, useCallback } from 'react';

export interface ViewportState {
  x: number;
  y: number;
  zoom: number;
}

export const MIN_ZOOM = 0.25;
export const MAX_ZOOM = 3;
export const ZOOM_STEP = 0.1;
const FIT_PADDING = 40;

function clampZoom(z: number): number {
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z));
}

export function useDagViewport() {
  const [viewport, setViewport] = useState<ViewportState>({ x: 0, y: 0, zoom: 1 });
  const isPanning = useRef(false);
  const lastPointer = useRef({ x: 0, y: 0 });

  const fitToView = useCallback(
    (containerWidth: number, containerHeight: number, graphWidth: number, graphHeight: number) => {
      if (graphWidth <= 0 || graphHeight <= 0) return;

      const availW = containerWidth - FIT_PADDING * 2;
      const availH = containerHeight - FIT_PADDING * 2;
      const zoom = clampZoom(Math.min(availW / graphWidth, availH / graphHeight));
      const x = (containerWidth - graphWidth * zoom) / 2;
      const y = (containerHeight - graphHeight * zoom) / 2;
      setViewport({ x, y, zoom });
    },
    [],
  );

  const zoomTo = useCallback((delta: number) => {
    setViewport((prev) => ({ ...prev, zoom: clampZoom(prev.zoom + delta) }));
  }, []);

  const focusNode = useCallback(
    (
      nodeX: number,
      nodeY: number,
      nodeWidth: number,
      nodeHeight: number,
      containerWidth: number,
      containerHeight: number,
    ) => {
      setViewport((prev) => {
        const nodeCenterX = nodeX + nodeWidth / 2;
        const nodeCenterY = nodeY + nodeHeight / 2;
        return {
          ...prev,
          x: containerWidth / 2 - nodeCenterX * prev.zoom,
          y: containerHeight / 2 - nodeCenterY * prev.zoom,
        };
      });
    },
    [],
  );

  /* ── Pointer event handlers ─────────────────────────────────── */

  const onWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -ZOOM_STEP : ZOOM_STEP;
    setViewport((prev) => ({ ...prev, zoom: clampZoom(prev.zoom + delta) }));
  }, []);

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    isPanning.current = true;
    lastPointer.current = { x: e.clientX, y: e.clientY };
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
  }, []);

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (!isPanning.current) return;
    const dx = e.clientX - lastPointer.current.x;
    const dy = e.clientY - lastPointer.current.y;
    lastPointer.current = { x: e.clientX, y: e.clientY };
    setViewport((prev) => ({ ...prev, x: prev.x + dx, y: prev.y + dy }));
  }, []);

  const onPointerUp = useCallback((e: React.PointerEvent) => {
    isPanning.current = false;
    (e.currentTarget as Element).releasePointerCapture(e.pointerId);
  }, []);

  return {
    viewport,
    fitToView,
    zoomTo,
    focusNode,
    handlers: { onWheel, onPointerDown, onPointerMove, onPointerUp },
  };
}
