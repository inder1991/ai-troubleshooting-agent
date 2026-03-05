import { useState, useEffect, useCallback, useRef } from 'react';
import { fetchMonitorSnapshot } from '../../../services/api';

export interface DeviceStatus {
  device_id: string;
  status: 'up' | 'down' | 'degraded';
  latency_ms: number;
  packet_loss: number;
  last_seen: string;
  last_status_change: string;
  probe_method: string;
}

export interface LinkMetric {
  src_device_id: string;
  dst_device_id: string;
  latency_ms: number;
  bandwidth_bps: number;
  error_rate: number;
  utilization: number;
}

export interface DriftEvent {
  id: string;
  entity_type: string;
  entity_id: string;
  drift_type: 'missing' | 'added' | 'changed';
  field: string;
  expected: string;
  actual: string;
  severity: 'info' | 'warning' | 'critical';
  detected_at: string;
}

export interface DiscoveryCandidate {
  ip: string;
  mac: string;
  hostname: string;
  discovered_via: string;
  source_device_id: string;
  first_seen: string;
  last_seen: string;
}

export interface AlertEvent {
  key: string;
  rule_id: string;
  rule_name: string;
  entity_id: string;
  severity: 'critical' | 'warning' | 'info';
  metric: string;
  value: number;
  threshold: number;
  condition: string;
  fired_at: number;
  acknowledged: boolean;
  message: string;
}

export interface AlertRule {
  id: string;
  name: string;
  severity: string;
  entity_type: string;
  entity_filter: string;
  metric: string;
  condition: string;
  threshold: number;
  duration_seconds: number;
  cooldown_seconds: number;
  enabled: boolean;
}

export interface MetricDataPoint {
  time: string;
  value: number;
}

export interface TopTalker {
  src_ip: string;
  dst_ip: string;
  protocol: string;
  bytes: number;
}

export interface TrafficMatrixEntry {
  src: string;
  dst: string;
  bytes: number;
}

export interface ProtocolBreakdown {
  protocol: string;
  bytes: number;
}

export interface MonitorSnapshot {
  devices: DeviceStatus[];
  links: LinkMetric[];
  drifts: DriftEvent[];
  candidates: DiscoveryCandidate[];
  alerts: AlertEvent[];
}

export function useMonitorSnapshot(intervalMs: number = 30_000) {
  const [snapshot, setSnapshot] = useState<MonitorSnapshot>({
    devices: [], links: [], drifts: [], candidates: [], alerts: [],
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await fetchMonitorSnapshot();
      setSnapshot(data);
      setLastUpdated(new Date());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch snapshot');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    timerRef.current = setInterval(refresh, intervalMs);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [refresh, intervalMs]);

  return { snapshot, loading, error, lastUpdated, refresh };
}
