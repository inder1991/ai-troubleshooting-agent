import React from 'react';
import type { TimeSeriesDataPoint, Severity } from '../../../types';

interface AnomalySparklineProps {
  dataPoints: TimeSeriesDataPoint[];
  baselineValue: number;
  peakValue: number;
  spikeStart: string;
  spikeEnd: string;
  severity: Severity;
}

const WIDTH = 280;
const HEIGHT = 48;
const PAD_X = 2;
const PAD_Y = 4;

const AnomalySparkline: React.FC<AnomalySparklineProps> = ({
  dataPoints,
  baselineValue,
  peakValue,
  spikeStart,
  spikeEnd,
  severity,
}) => {
  // Fallback: synthetic trapezoid if no real data
  if (!dataPoints || dataPoints.length === 0) {
    return <SyntheticSparkline baselineValue={baselineValue} peakValue={peakValue} severity={severity} />;
  }

  const values = dataPoints.map((dp) => dp.value);
  const minVal = Math.min(...values, baselineValue) * 0.95;
  const maxVal = Math.max(...values, peakValue, baselineValue) * 1.05;
  const range = maxVal - minVal || 1;

  const scaleX = (i: number) => PAD_X + (i / Math.max(dataPoints.length - 1, 1)) * (WIDTH - 2 * PAD_X);
  const scaleY = (v: number) => PAD_Y + (1 - (v - minVal) / range) * (HEIGHT - 2 * PAD_Y);

  // Polyline points for metric line
  const linePoints = dataPoints.map((dp, i) => `${scaleX(i)},${scaleY(dp.value)}`).join(' ');

  // Baseline Y
  const baseY = scaleY(baselineValue);

  // Deviation fill path: area between metric line and baseline where metric > baseline
  const deviationPath = buildDeviationPath(dataPoints, baselineValue, scaleX, scaleY, baseY);

  // Spike window highlight
  const spikeStartTs = new Date(spikeStart).getTime();
  const spikeEndTs = new Date(spikeEnd).getTime();
  const spikeRect = buildSpikeRect(dataPoints, spikeStartTs, spikeEndTs, scaleX);

  const deviationColor = severity === 'critical' || severity === 'high' ? 'rgba(239,68,68,0.2)' : 'rgba(249,115,22,0.2)';

  return (
    <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full" style={{ height: '48px' }} preserveAspectRatio="none">
      {/* Spike window highlight */}
      {spikeRect && (
        <rect
          x={spikeRect.x}
          y={0}
          width={spikeRect.width}
          height={HEIGHT}
          fill="rgba(239,68,68,0.06)"
          rx="2"
        />
      )}

      {/* Deviation area */}
      {deviationPath && (
        <path d={deviationPath} fill={deviationColor} className="sparkline-deviation" />
      )}

      {/* Baseline dashed line */}
      <line
        x1={PAD_X}
        y1={baseY}
        x2={WIDTH - PAD_X}
        y2={baseY}
        stroke="#475569"
        strokeWidth="1"
        strokeDasharray="4 3"
      />

      {/* Metric polyline */}
      <polyline
        points={linePoints}
        fill="none"
        stroke="#07b6d5"
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
};

// Synthetic trapezoid fallback
const SyntheticSparkline: React.FC<{
  baselineValue: number;
  peakValue: number;
  severity: Severity;
}> = ({ baselineValue, peakValue, severity }) => {
  const minVal = baselineValue * 0.9;
  const maxVal = peakValue * 1.1;
  const range = maxVal - minVal || 1;
  const scaleY = (v: number) => PAD_Y + (1 - (v - minVal) / range) * (HEIGHT - 2 * PAD_Y);

  const bY = scaleY(baselineValue);
  const pY = scaleY(peakValue);
  const deviationColor = severity === 'critical' || severity === 'high' ? 'rgba(239,68,68,0.15)' : 'rgba(249,115,22,0.15)';

  // Trapezoid: flat baseline -> ramp up -> peak plateau -> ramp down -> baseline
  const points = [
    `${PAD_X},${bY}`,
    `${WIDTH * 0.25},${bY}`,
    `${WIDTH * 0.4},${pY}`,
    `${WIDTH * 0.6},${pY}`,
    `${WIDTH * 0.75},${bY}`,
    `${WIDTH - PAD_X},${bY}`,
  ].join(' ');

  const fillPath = `M ${PAD_X},${bY} L ${WIDTH * 0.25},${bY} L ${WIDTH * 0.4},${pY} L ${WIDTH * 0.6},${pY} L ${WIDTH * 0.75},${bY} L ${WIDTH - PAD_X},${bY} Z`;

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full opacity-60" style={{ height: '48px' }} preserveAspectRatio="none">
        <path d={fillPath} fill={deviationColor} />
        <line x1={PAD_X} y1={bY} x2={WIDTH - PAD_X} y2={bY} stroke="#475569" strokeWidth="1" strokeDasharray="4 3" />
        <polyline points={points} fill="none" stroke="#07b6d5" strokeWidth="1.5" strokeDasharray="6 3" strokeLinejoin="round" />
      </svg>
      <span className="absolute top-0 right-1 text-[8px] text-slate-600 italic">estimated</span>
    </div>
  );
};

function buildDeviationPath(
  dataPoints: TimeSeriesDataPoint[],
  baseline: number,
  scaleX: (i: number) => number,
  scaleY: (v: number) => number,
  baseY: number
): string | null {
  // Build path segments where value > baseline
  const segments: string[] = [];
  let inDeviation = false;
  let pathStart = '';

  for (let i = 0; i < dataPoints.length; i++) {
    const v = dataPoints[i].value;
    const x = scaleX(i);
    const y = scaleY(v);

    if (v > baseline) {
      if (!inDeviation) {
        pathStart = `M ${x},${baseY} L ${x},${y}`;
        inDeviation = true;
      } else {
        pathStart += ` L ${x},${y}`;
      }
    } else if (inDeviation) {
      pathStart += ` L ${x},${baseY} Z`;
      segments.push(pathStart);
      inDeviation = false;
    }
  }

  if (inDeviation) {
    pathStart += ` L ${scaleX(dataPoints.length - 1)},${baseY} Z`;
    segments.push(pathStart);
  }

  return segments.length > 0 ? segments.join(' ') : null;
}

function buildSpikeRect(
  dataPoints: TimeSeriesDataPoint[],
  startTs: number,
  endTs: number,
  scaleX: (i: number) => number
): { x: number; width: number } | null {
  if (isNaN(startTs) || isNaN(endTs)) return null;

  let startX: number | null = null;
  let endX: number | null = null;

  for (let i = 0; i < dataPoints.length; i++) {
    const ts = new Date(dataPoints[i].timestamp).getTime();
    if (startX === null && ts >= startTs) startX = scaleX(i);
    if (ts <= endTs) endX = scaleX(i);
  }

  if (startX === null || endX === null || endX <= startX) return null;
  return { x: startX, width: endX - startX };
}

/** Fuzzy key matcher: finds the best time_series_data key matching an anomaly metric_name */
export function findMatchingTimeSeries(
  tsData: Record<string, TimeSeriesDataPoint[]>,
  metricName: string
): TimeSeriesDataPoint[] | null {
  if (!tsData || !metricName) return null;

  const keys = Object.keys(tsData);
  if (keys.length === 0) return null;

  const nameLower = metricName.toLowerCase();

  // Exact match
  if (tsData[metricName]) return tsData[metricName];

  // Substring match: key contains metric name or vice versa
  for (const key of keys) {
    const keyLower = key.toLowerCase();
    if (keyLower.includes(nameLower) || nameLower.includes(keyLower)) {
      return tsData[key];
    }
  }

  // Shared word match: split on non-alphanumeric, find key with most shared words
  const nameWords = new Set(nameLower.split(/[^a-z0-9]+/).filter(Boolean));
  let bestKey: string | null = null;
  let bestScore = 0;

  for (const key of keys) {
    const keyWords = key.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
    const shared = keyWords.filter((w) => nameWords.has(w)).length;
    if (shared > bestScore) {
      bestScore = shared;
      bestKey = key;
    }
  }

  if (bestKey && bestScore >= 2) return tsData[bestKey];
  return null;
}

export default AnomalySparkline;
