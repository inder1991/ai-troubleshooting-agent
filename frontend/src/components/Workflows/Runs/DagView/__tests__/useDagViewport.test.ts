import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useDagViewport } from '../useDagViewport';

describe('useDagViewport', () => {
  it('returns initial viewport x=0, y=0, zoom=1', () => {
    const { result } = renderHook(() => useDagViewport());
    expect(result.current.viewport).toEqual({ x: 0, y: 0, zoom: 1 });
  });

  it('fitToView sets centered viewport with appropriate zoom', () => {
    const { result } = renderHook(() => useDagViewport());

    // Graph 800x600, container 400x300 → need to scale down
    // Available space: 400-80=320 wide, 300-80=220 tall (40px padding each side)
    // scaleX = 320/800 = 0.4, scaleY = 220/600 = 0.3667 → zoom = min = 0.3667
    // Clamped to MIN_ZOOM (0.25) at minimum
    // Center: x = (400 - 800*zoom)/2, y = (300 - 600*zoom)/2
    act(() => {
      result.current.fitToView(400, 300, 800, 600);
    });

    const { x, y, zoom } = result.current.viewport;
    // zoom should be ~0.3667
    expect(zoom).toBeCloseTo(220 / 600, 2);
    // centered: x = (400 - 800 * zoom) / 2
    expect(x).toBeCloseTo((400 - 800 * zoom) / 2, 2);
    expect(y).toBeCloseTo((300 - 600 * zoom) / 2, 2);
  });

  it('zoomTo clamps between MIN_ZOOM and MAX_ZOOM', () => {
    const { result } = renderHook(() => useDagViewport());

    // Zoom way up past MAX (3)
    act(() => {
      result.current.zoomTo(100);
    });
    expect(result.current.viewport.zoom).toBe(3);

    // Zoom way down past MIN (0.25)
    act(() => {
      result.current.zoomTo(-100);
    });
    expect(result.current.viewport.zoom).toBe(0.25);
  });

  it('focusNode centers viewport on given node coordinates', () => {
    const { result } = renderHook(() => useDagViewport());

    const containerW = 800;
    const containerH = 600;
    const nodeX = 300;
    const nodeY = 200;
    const nodeW = 200;
    const nodeH = 80;

    act(() => {
      result.current.focusNode(nodeX, nodeY, nodeW, nodeH, containerW, containerH);
    });

    const { x, y, zoom } = result.current.viewport;
    // Should center the node: viewport x = containerW/2 - (nodeX + nodeW/2) * zoom
    const nodeCenterX = nodeX + nodeW / 2;
    const nodeCenterY = nodeY + nodeH / 2;
    expect(x).toBeCloseTo(containerW / 2 - nodeCenterX * zoom, 2);
    expect(y).toBeCloseTo(containerH / 2 - nodeCenterY * zoom, 2);
  });

  it('wheel handler adjusts zoom by ZOOM_STEP', () => {
    const { result } = renderHook(() => useDagViewport());

    const initialZoom = result.current.viewport.zoom; // 1

    // Simulate wheel scroll down (zoom out)
    act(() => {
      result.current.handlers.onWheel({
        preventDefault: () => {},
        deltaY: 100,
      } as unknown as React.WheelEvent);
    });

    expect(result.current.viewport.zoom).toBeCloseTo(initialZoom - 0.1, 5);

    // Simulate wheel scroll up (zoom in)
    act(() => {
      result.current.handlers.onWheel({
        preventDefault: () => {},
        deltaY: -100,
      } as unknown as React.WheelEvent);
    });

    // Back to initial
    expect(result.current.viewport.zoom).toBeCloseTo(initialZoom, 5);
  });
});
