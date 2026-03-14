import React, { useRef, useEffect, useState, useCallback } from 'react';
import type { IPAddress } from '../../types';

interface Props {
  subnetId: string;
  subnetCidr: string;
  ips: IPAddress[];
}

const STATUS_COLORS: Record<string, string> = {
  available: '#10b981',
  assigned: '#d4922e',
  reserved: '#3b82f6',
  deprecated: '#64748b',
  gateway: '#f59e0b',
};

function cidrHostCount(cidr: string): number {
  const parts = cidr.split('/');
  const prefix = parseInt(parts[1] || '32', 10);
  if (prefix >= 31) return 2;
  return Math.pow(2, 32 - prefix) - 2; // exclude network & broadcast
}

function ipToNumber(ip: string): number {
  return ip.split('.').reduce((acc, oct) => (acc << 8) + parseInt(oct, 10), 0) >>> 0;
}

function networkAddress(cidr: string): number {
  const [ip, prefix] = cidr.split('/');
  const mask = (0xffffffff << (32 - parseInt(prefix, 10))) >>> 0;
  return (ipToNumber(ip) & mask) >>> 0;
}

export default function IPAMSubnetHeatmap({ subnetCidr, ips }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [tooltip, setTooltip] = useState<{ x: number; y: number; text: string } | null>(null);
  const hostCount = cidrHostCount(subnetCidr);
  const prefix = parseInt(subnetCidr.split('/')[1] || '32', 10);

  // Build IP status map
  const ipStatusMap = useCallback(() => {
    const map = new Map<number, IPAddress>();
    const netAddr = networkAddress(subnetCidr);
    for (const ip of ips) {
      const offset = (ipToNumber(ip.address) - netAddr - 1) >>> 0; // -1 for network addr
      map.set(offset, ip);
    }
    return map;
  }, [ips, subnetCidr]);

  // Determine rendering mode
  const isPerIP = prefix >= 20; // /20 to /32: per-IP cells
  const cellCount = isPerIP ? Math.min(hostCount, 4094) : Math.min(Math.ceil(hostCount / 256), 256);
  const cols = Math.ceil(Math.sqrt(cellCount));
  const rows = Math.ceil(cellCount / cols);
  const cellSize = isPerIP ? Math.max(4, Math.min(16, Math.floor(400 / cols))) : Math.max(8, Math.min(24, Math.floor(400 / cols)));
  const canvasWidth = cols * cellSize;
  const canvasHeight = rows * cellSize;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    canvas.width = canvasWidth;
    canvas.height = canvasHeight;

    const statusMap = ipStatusMap();

    if (isPerIP) {
      // Per-IP rendering
      for (let i = 0; i < cellCount; i++) {
        const col = i % cols;
        const row = Math.floor(i / cols);
        const ip = statusMap.get(i);
        let color = STATUS_COLORS.available;
        if (ip) {
          if (ip.ip_type === 'gateway') color = STATUS_COLORS.gateway;
          else color = STATUS_COLORS[ip.status] || STATUS_COLORS.available;
        }
        ctx.fillStyle = color;
        ctx.fillRect(col * cellSize, row * cellSize, cellSize - 1, cellSize - 1);
      }
    } else {
      // Aggregated /24-block rendering for larger subnets
      const blockSize = 256;
      for (let blockIdx = 0; blockIdx < cellCount; blockIdx++) {
        const col = blockIdx % cols;
        const row = Math.floor(blockIdx / cols);
        const startOffset = blockIdx * blockSize;
        let assignedInBlock = 0;
        let totalInBlock = Math.min(blockSize, hostCount - startOffset);
        for (let j = 0; j < totalInBlock; j++) {
          if (statusMap.has(startOffset + j)) assignedInBlock++;
        }
        const utilPct = totalInBlock > 0 ? assignedInBlock / totalInBlock : 0;
        // Gradient from emerald (0%) to amber (50%) to red (100%)
        const r = utilPct < 0.5 ? Math.round(16 + utilPct * 2 * (245 - 16)) : Math.round(245 - (utilPct - 0.5) * 2 * (245 - 239));
        const g = utilPct < 0.5 ? Math.round(185 - utilPct * 2 * (185 - 158)) : Math.round(158 - (utilPct - 0.5) * 2 * (158 - 68));
        const b = utilPct < 0.5 ? Math.round(129 - utilPct * 2 * (129 - 11)) : Math.round(11 + (utilPct - 0.5) * 2 * (68 - 11));
        ctx.fillStyle = `rgb(${r},${g},${b})`;
        ctx.fillRect(col * cellSize, row * cellSize, cellSize - 1, cellSize - 1);
      }
    }
  }, [cellCount, cellSize, cols, canvasWidth, canvasHeight, ipStatusMap, isPerIP, hostCount]);

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const col = Math.floor(x / cellSize);
    const row = Math.floor(y / cellSize);
    const idx = row * cols + col;

    if (idx < 0 || idx >= cellCount) {
      setTooltip(null);
      return;
    }

    const statusMap = ipStatusMap();

    if (isPerIP) {
      const ip = statusMap.get(idx);
      const netAddr = networkAddress(subnetCidr);
      const hostNum = netAddr + idx + 1;
      const ipStr = `${(hostNum >>> 24) & 0xff}.${(hostNum >>> 16) & 0xff}.${(hostNum >>> 8) & 0xff}.${hostNum & 0xff}`;
      const text = ip
        ? `${ipStr} (${ip.status})${ip.hostname ? ' - ' + ip.hostname : ''}${ip.mac_address ? ' [' + ip.mac_address + ']' : ''}`
        : `${ipStr} (available)`;
      setTooltip({ x: e.clientX, y: e.clientY, text });
    } else {
      const startOffset = idx * 256;
      let assigned = 0;
      const total = Math.min(256, hostCount - startOffset);
      for (let j = 0; j < total; j++) {
        if (statusMap.has(startOffset + j)) assigned++;
      }
      const pct = total > 0 ? Math.round((assigned / total) * 100) : 0;
      setTooltip({ x: e.clientX, y: e.clientY, text: `Block ${idx}: ${assigned}/${total} used (${pct}%)` });
    }
  }, [cellCount, cellSize, cols, ipStatusMap, isPerIP, subnetCidr, hostCount]);

  if (prefix < 16) {
    return (
      <div className="text-center text-slate-500 py-8 text-sm">
        Heatmap not available for subnets larger than /16.
      </div>
    );
  }

  return (
    <div className="py-4">
      <div className="flex items-center gap-4 mb-3">
        <span className="text-xs text-slate-400">
          {isPerIP ? `${hostCount} hosts — 1 cell per IP` : `${cellCount} blocks of /24 — color = utilization`}
        </span>
        <div className="flex items-center gap-3 ml-auto">
          {Object.entries(STATUS_COLORS).map(([status, color]) => (
            <div key={status} className="flex items-center gap-1 text-xs text-slate-400">
              <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: color }} />
              {status}
            </div>
          ))}
        </div>
      </div>
      <div className="relative inline-block">
        <canvas
          ref={canvasRef}
          onMouseMove={handleMouseMove}
          onMouseLeave={() => setTooltip(null)}
          className="rounded border border-[#1e3a40] cursor-crosshair"
          style={{ width: canvasWidth, height: canvasHeight }}
        />
        {tooltip && (
          <div
            className="fixed z-50 px-2 py-1 bg-[#132a2f] border border-[#1e3a40] rounded text-xs text-slate-200 shadow-lg pointer-events-none whitespace-nowrap"
            style={{ left: tooltip.x + 12, top: tooltip.y - 8 }}
          >
            {tooltip.text}
          </div>
        )}
      </div>
    </div>
  );
}
