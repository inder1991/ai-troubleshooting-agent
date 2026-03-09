import React, { useState, useMemo, useRef, useCallback } from 'react';
import type { MonitoredDevice } from '../../types';

interface NDMTopologyTabProps {
  devices: MonitoredDevice[];
  onSelectDevice: (id: string) => void;
}

const DEVICE_TYPE_ICONS: Record<string, string> = {
  router: 'router',
  switch: 'switch',
  firewall: 'security',
  wireless: 'wifi',
  server: 'dns',
  storage: 'storage',
  load_balancer: 'balance',
  default: 'devices_other',
};

const STATUS_COLORS: Record<string, string> = {
  up: '#22c55e',
  down: '#ef4444',
  unreachable: '#f59e0b',
  new: '#64748b',
};

const STATUS_LABELS: Record<string, string> = {
  up: 'Up',
  down: 'Down',
  unreachable: 'Unreachable',
  new: 'New',
};

type GroupByOption = 'none' | 'vendor' | 'device_type' | 'tags';

const SVG_WIDTH = 900;
const SVG_HEIGHT = 600;

function inferDeviceType(device: MonitoredDevice): string {
  const profile = (device.matched_profile || '').toLowerCase();
  const vendor = (device.vendor || '').toLowerCase();
  const hostname = (device.hostname || '').toLowerCase();

  if (profile.includes('router') || hostname.includes('rtr') || hostname.includes('router')) return 'router';
  if (profile.includes('switch') || hostname.includes('sw') || hostname.includes('switch')) return 'switch';
  if (profile.includes('firewall') || hostname.includes('fw') || vendor.includes('palo') || vendor.includes('fortinet')) return 'firewall';
  if (profile.includes('wireless') || profile.includes('ap') || hostname.includes('ap-')) return 'wireless';
  if (profile.includes('server') || hostname.includes('srv') || hostname.includes('server')) return 'server';
  if (profile.includes('storage') || hostname.includes('nas') || hostname.includes('san')) return 'storage';
  if (profile.includes('load_balancer') || profile.includes('lb') || hostname.includes('lb')) return 'load_balancer';
  return 'default';
}

function getDeviceIcon(device: MonitoredDevice): string {
  const type = inferDeviceType(device);
  return DEVICE_TYPE_ICONS[type] || DEVICE_TYPE_ICONS.default;
}

function truncate(str: string, max: number): string {
  if (!str) return '';
  return str.length > max ? str.slice(0, max) + '...' : str;
}

interface LayoutNode {
  device: MonitoredDevice;
  x: number;
  y: number;
}

interface Link {
  from: number;
  to: number;
}

interface GroupRect {
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

function layoutDevices(devices: MonitoredDevice[]): LayoutNode[] {
  const nodes: LayoutNode[] = [];
  if (devices.length === 0) return nodes;

  if (devices.length === 1) {
    nodes.push({ device: devices[0], x: SVG_WIDTH / 2, y: SVG_HEIGHT / 2 });
    return nodes;
  }

  const cols = Math.ceil(Math.sqrt(devices.length));
  const rows = Math.ceil(devices.length / cols);

  devices.forEach((d, i) => {
    const row = Math.floor(i / cols);
    const col = i % cols;
    const xSpacing = cols > 1 ? (SVG_WIDTH - 160) / (cols - 1) : 0;
    const ySpacing = rows > 1 ? (SVG_HEIGHT - 160) / (rows - 1) : 0;
    const x = 80 + col * xSpacing;
    const y = 80 + row * ySpacing;
    nodes.push({
      device: d,
      x: isNaN(x) ? SVG_WIDTH / 2 : x,
      y: isNaN(y) ? SVG_HEIGHT / 2 : y,
    });
  });

  return nodes;
}

function layoutDevicesGrouped(
  devices: MonitoredDevice[],
  groupBy: GroupByOption
): { nodes: LayoutNode[]; groups: GroupRect[] } {
  if (groupBy === 'none' || devices.length === 0) {
    return { nodes: layoutDevices(devices), groups: [] };
  }

  const groupMap = new Map<string, MonitoredDevice[]>();

  devices.forEach((d) => {
    let keys: string[] = [];
    if (groupBy === 'vendor') {
      keys = [d.vendor || 'Unknown'];
    } else if (groupBy === 'device_type') {
      keys = [inferDeviceType(d)];
    } else if (groupBy === 'tags') {
      keys = d.tags.length > 0 ? [d.tags[0]] : ['Untagged'];
    }
    keys.forEach((key) => {
      if (!groupMap.has(key)) groupMap.set(key, []);
      groupMap.get(key)!.push(d);
    });
  });

  const groupEntries = Array.from(groupMap.entries());
  const groupCount = groupEntries.length;
  const groupCols = Math.ceil(Math.sqrt(groupCount));
  const groupRows = Math.ceil(groupCount / groupCols);

  const groupPadding = 20;
  const groupWidth = (SVG_WIDTH - groupPadding * (groupCols + 1)) / groupCols;
  const groupHeight = (SVG_HEIGHT - groupPadding * (groupRows + 1) - 20) / groupRows;

  const nodes: LayoutNode[] = [];
  const groups: GroupRect[] = [];

  groupEntries.forEach(([label, groupDevices], gi) => {
    const gRow = Math.floor(gi / groupCols);
    const gCol = gi % groupCols;
    const gx = groupPadding + gCol * (groupWidth + groupPadding);
    const gy = groupPadding + gRow * (groupHeight + groupPadding) + 20;

    groups.push({ label, x: gx, y: gy, width: groupWidth, height: groupHeight });

    const innerPadX = 40;
    const innerPadY = 50;
    const innerW = groupWidth - innerPadX * 2;
    const innerH = groupHeight - innerPadY - 30;

    if (groupDevices.length === 1) {
      nodes.push({
        device: groupDevices[0],
        x: gx + groupWidth / 2,
        y: gy + groupHeight / 2 + 10,
      });
      return;
    }

    const cols = Math.ceil(Math.sqrt(groupDevices.length));
    const rows = Math.ceil(groupDevices.length / cols);

    groupDevices.forEach((d, i) => {
      const row = Math.floor(i / cols);
      const col = i % cols;
      const xSpacing = cols > 1 ? innerW / (cols - 1) : 0;
      const ySpacing = rows > 1 ? innerH / (rows - 1) : 0;
      const x = gx + innerPadX + col * xSpacing;
      const y = gy + innerPadY + row * ySpacing;
      nodes.push({
        device: d,
        x: isNaN(x) ? gx + groupWidth / 2 : x,
        y: isNaN(y) ? gy + groupHeight / 2 : y,
      });
    });
  });

  return { nodes, groups };
}

function generateLinks(nodes: LayoutNode[]): Link[] {
  const links: Link[] = [];
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const tagsA = nodes[i].device.tags;
      const tagsB = nodes[j].device.tags;
      const sharedTags = tagsA.filter((t) => tagsB.includes(t));
      if (sharedTags.length > 0) {
        links.push({ from: i, to: j });
      }
    }
  }
  return links;
}

function getLinkColor(statusA: string, statusB: string): string {
  if (statusA === 'down' && statusB === 'down') return '#ef4444';
  if (statusA === 'down' || statusB === 'down') return '#f59e0b';
  if (statusA === 'unreachable' || statusB === 'unreachable') return '#f59e0b';
  return '#22c55e';
}

const MIN_ZOOM = 0.25;
const MAX_ZOOM = 4;
const ZOOM_STEP = 0.15;

const NDMTopologyTab: React.FC<NDMTopologyTabProps> = ({ devices, onSelectDevice }) => {
  const [groupBy, setGroupBy] = useState<GroupByOption>('none');
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const svgRef = useRef<SVGSVGElement>(null);

  // Zoom & pan state
  const [scale, setScale] = useState(1);
  const [translate, setTranslate] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const panStart = useRef({ x: 0, y: 0, tx: 0, ty: 0 });

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -ZOOM_STEP : ZOOM_STEP;
    setScale(s => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, s + delta)));
  }, []);

  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    if (e.button !== 0) return;
    // Only pan if clicking on background (not a node)
    const target = e.target as SVGElement;
    if (target.tagName === 'circle' || target.tagName === 'text' || target.closest('g[style]')) return;
    setIsPanning(true);
    panStart.current = { x: e.clientX, y: e.clientY, tx: translate.x, ty: translate.y };
    (e.target as Element).setPointerCapture?.(e.pointerId);
  }, [translate]);

  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    if (!isPanning) return;
    const dx = e.clientX - panStart.current.x;
    const dy = e.clientY - panStart.current.y;
    setTranslate({ x: panStart.current.tx + dx, y: panStart.current.ty + dy });
  }, [isPanning]);

  const handlePointerUp = useCallback(() => {
    setIsPanning(false);
  }, []);

  const handleFit = useCallback(() => {
    setScale(1);
    setTranslate({ x: 0, y: 0 });
  }, []);

  const { nodes, groups } = useMemo(
    () => layoutDevicesGrouped(devices, groupBy),
    [devices, groupBy]
  );

  const links = useMemo(() => generateLinks(nodes), [nodes]);

  const hoveredDevice = useMemo(() => {
    if (!hoveredNode) return null;
    return devices.find((d) => d.device_id === hoveredNode) || null;
  }, [hoveredNode, devices]);

  const handleMouseEnter = useCallback(
    (deviceId: string, event: React.MouseEvent) => {
      setHoveredNode(deviceId);
      const svgEl = svgRef.current;
      if (svgEl) {
        const rect = svgEl.getBoundingClientRect();
        setTooltipPos({
          x: event.clientX - rect.left,
          y: event.clientY - rect.top,
        });
      }
    },
    []
  );

  const handleMouseLeave = useCallback(() => {
    setHoveredNode(null);
  }, []);

  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = { up: 0, down: 0, unreachable: 0, new: 0 };
    devices.forEach((d) => {
      counts[d.status] = (counts[d.status] || 0) + 1;
    });
    return counts;
  }, [devices]);

  if (devices.length === 0) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          height: 400,
          color: '#64748b',
          gap: 12,
        }}
      >
        <span className="material-symbols-outlined" style={{ fontSize: 48, color: '#334155' }}>
          hub
        </span>
        <p style={{ fontSize: 14 }}>No devices to display. Add devices in the Devices tab.</p>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <style>{`
        @keyframes ndm-pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
      `}</style>

      {/* Controls Bar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '8px 12px',
          background: '#0a1a1f',
          borderRadius: 8,
          border: '1px solid #1e3a4a',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {/* Group By Dropdown */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 12, color: '#64748b', fontWeight: 500 }}>Group By</span>
            <select
              value={groupBy}
              onChange={(e) => setGroupBy(e.target.value as GroupByOption)}
              style={{
                background: '#0f2023',
                color: '#e2e8f0',
                border: '1px solid #1e3a4a',
                borderRadius: 4,
                padding: '4px 8px',
                fontSize: 12,
                outline: 'none',
                cursor: 'pointer',
              }}
            >
              <option value="none">None</option>
              <option value="vendor">Vendor</option>
              <option value="device_type">Device Type</option>
              <option value="tags">Tags</option>
            </select>
          </div>

          {/* Device Count Badge */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              background: 'rgba(7, 182, 213, 0.1)',
              border: '1px solid rgba(7, 182, 213, 0.3)',
              borderRadius: 12,
              padding: '2px 10px',
              fontSize: 12,
              color: '#07b6d5',
              fontWeight: 600,
            }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
              devices
            </span>
            {devices.length} device{devices.length !== 1 ? 's' : ''}
          </div>
        </div>

        {/* Legend */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          {Object.entries(STATUS_LABELS).map(([status, label]) => (
            <div key={status} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <div
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  background: STATUS_COLORS[status],
                }}
              />
              <span style={{ fontSize: 11, color: '#94a3b8' }}>
                {label}
                {statusCounts[status] > 0 && (
                  <span style={{ color: '#64748b', marginLeft: 3 }}>({statusCounts[status]})</span>
                )}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* SVG Topology Map */}
      <div
        style={{
          position: 'relative',
          background: '#0a1a1f',
          borderRadius: 8,
          border: '1px solid #1e3a4a',
          overflow: 'hidden',
        }}
      >
        {/* Zoom Controls */}
        <div style={{
          position: 'absolute', top: 10, right: 10, zIndex: 20,
          display: 'flex', flexDirection: 'column', gap: 4,
          background: 'rgba(15,32,35,0.9)', borderRadius: 6,
          border: '1px solid #1e3a4a', padding: 4,
        }}>
          {[
            { icon: 'add', action: () => setScale(s => Math.min(MAX_ZOOM, s + ZOOM_STEP)), label: 'Zoom in' },
            { icon: 'remove', action: () => setScale(s => Math.max(MIN_ZOOM, s - ZOOM_STEP)), label: 'Zoom out' },
            { icon: 'fit_screen', action: handleFit, label: 'Fit to view' },
          ].map(btn => (
            <button
              key={btn.icon}
              onClick={btn.action}
              title={btn.label}
              aria-label={btn.label}
              style={{
                width: 28, height: 28, border: 'none', borderRadius: 4,
                background: 'transparent', color: '#94a3b8', cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 18,
              }}
              onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = 'rgba(7,182,213,0.15)'; }}
              onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = 'transparent'; }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 18 }}>{btn.icon}</span>
            </button>
          ))}
          <div style={{ fontSize: 9, color: '#64748b', textAlign: 'center', padding: '2px 0' }}>
            {Math.round(scale * 100)}%
          </div>
        </div>

        <svg
          ref={svgRef}
          viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`}
          style={{ width: '100%', height: 'auto', display: 'block', cursor: isPanning ? 'grabbing' : 'grab' }}
          onWheel={handleWheel}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
        >
          {/* Background */}
          <rect x={0} y={0} width={SVG_WIDTH} height={SVG_HEIGHT} fill="#0a1a1f" />

          {/* Grid pattern for visual depth */}
          <defs>
            <pattern id="ndm-grid" width={40} height={40} patternUnits="userSpaceOnUse">
              <path
                d="M 40 0 L 0 0 0 40"
                fill="none"
                stroke="#0f2a30"
                strokeWidth={0.5}
              />
            </pattern>
          </defs>
          <rect x={0} y={0} width={SVG_WIDTH} height={SVG_HEIGHT} fill="url(#ndm-grid)" />

          {/* Zoom/Pan Transform */}
          <g transform={`translate(${translate.x}, ${translate.y}) scale(${scale})`}>

          {/* Group Rectangles */}
          {groups.map((group, gi) => (
            <g key={`group-${gi}`}>
              <rect
                x={group.x}
                y={group.y}
                width={group.width}
                height={group.height}
                rx={8}
                fill="rgba(7, 182, 213, 0.03)"
                stroke="rgba(7, 182, 213, 0.15)"
                strokeWidth={1}
                strokeDasharray="4 2"
              />
              <text
                x={group.x + 10}
                y={group.y + 18}
                fill="#07b6d5"
                fontSize={11}
                fontWeight={600}
                fontFamily="Inter, system-ui, sans-serif"
              >
                {truncate(group.label, 20)}
              </text>
            </g>
          ))}

          {/* Links */}
          {links.map((link, li) => {
            const fromNode = nodes[link.from];
            const toNode = nodes[link.to];
            const color = getLinkColor(fromNode.device.status, toNode.device.status);
            return (
              <line
                key={`link-${li}`}
                x1={fromNode.x}
                y1={fromNode.y}
                x2={toNode.x}
                y2={toNode.y}
                stroke={color}
                strokeWidth={1.5}
                opacity={0.4}
              />
            );
          })}

          {/* Nodes */}
          {nodes.map((node, ni) => {
            const isHovered = hoveredNode === node.device.device_id;
            const isDown = node.device.status === 'down';
            const statusColor = STATUS_COLORS[node.device.status] || STATUS_COLORS.new;
            const icon = getDeviceIcon(node.device);

            return (
              <g
                key={node.device.device_id}
                style={{ cursor: 'pointer' }}
                onClick={() => onSelectDevice(node.device.device_id)}
                onMouseEnter={(e) => handleMouseEnter(node.device.device_id, e)}
                onMouseLeave={handleMouseLeave}
              >
                {/* Outer glow for hovered or down */}
                {(isHovered || isDown) && (
                  <circle
                    cx={node.x}
                    cy={node.y}
                    r={34}
                    fill="none"
                    stroke={statusColor}
                    strokeWidth={2}
                    opacity={isHovered ? 0.6 : 0.3}
                    style={
                      isDown
                        ? { animation: 'ndm-pulse 2s ease-in-out infinite' }
                        : undefined
                    }
                  />
                )}

                {/* Node circle */}
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={28}
                  fill="#0f2023"
                  stroke={statusColor}
                  strokeWidth={isHovered ? 2.5 : 2}
                />

                {/* Device type icon */}
                <text
                  x={node.x}
                  y={node.y + 1}
                  textAnchor="middle"
                  dominantBaseline="central"
                  fill={isHovered ? '#e2e8f0' : '#94a3b8'}
                  fontSize={22}
                  fontFamily="Material Symbols Outlined"
                  style={{ pointerEvents: 'none' }}
                >
                  {icon}
                </text>

                {/* Hostname label */}
                <text
                  x={node.x}
                  y={node.y + 44}
                  textAnchor="middle"
                  fill={isHovered ? '#e2e8f0' : '#64748b'}
                  fontSize={10}
                  fontFamily="Inter, system-ui, sans-serif"
                  fontWeight={isHovered ? 600 : 400}
                  style={{ pointerEvents: 'none' }}
                >
                  {truncate(node.device.hostname, 12)}
                </text>
              </g>
            );
          })}
          </g>{/* End zoom/pan transform */}
        </svg>

        {/* Tooltip */}
        {hoveredDevice && (
          <div
            style={{
              position: 'absolute',
              left: tooltipPos.x + 16,
              top: tooltipPos.y - 10,
              background: '#0f2023',
              border: '1px solid #1e3a4a',
              borderRadius: 8,
              padding: '10px 14px',
              zIndex: 50,
              pointerEvents: 'none',
              minWidth: 180,
              boxShadow: '0 4px 20px rgba(0, 0, 0, 0.5)',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                marginBottom: 6,
              }}
            >
              <span
                className="material-symbols-outlined"
                style={{
                  fontSize: 16,
                  color: STATUS_COLORS[hoveredDevice.status],
                }}
              >
                {getDeviceIcon(hoveredDevice)}
              </span>
              <span
                style={{
                  fontSize: 13,
                  fontWeight: 600,
                  color: '#e2e8f0',
                }}
              >
                {hoveredDevice.hostname}
              </span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16 }}>
                <span style={{ fontSize: 11, color: '#64748b' }}>IP</span>
                <span style={{ fontSize: 11, color: '#94a3b8', fontFamily: 'monospace' }}>
                  {hoveredDevice.management_ip}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16 }}>
                <span style={{ fontSize: 11, color: '#64748b' }}>Status</span>
                <span
                  style={{
                    fontSize: 11,
                    color: STATUS_COLORS[hoveredDevice.status],
                    fontWeight: 600,
                  }}
                >
                  {STATUS_LABELS[hoveredDevice.status]}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16 }}>
                <span style={{ fontSize: 11, color: '#64748b' }}>Vendor</span>
                <span style={{ fontSize: 11, color: '#94a3b8' }}>
                  {hoveredDevice.vendor || 'Unknown'}
                </span>
              </div>
              {hoveredDevice.model && (
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16 }}>
                  <span style={{ fontSize: 11, color: '#64748b' }}>Model</span>
                  <span style={{ fontSize: 11, color: '#94a3b8' }}>{hoveredDevice.model}</span>
                </div>
              )}
              {hoveredDevice.tags.length > 0 && (
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16 }}>
                  <span style={{ fontSize: 11, color: '#64748b' }}>Tags</span>
                  <span style={{ fontSize: 11, color: '#07b6d5' }}>
                    {hoveredDevice.tags.slice(0, 3).join(', ')}
                    {hoveredDevice.tags.length > 3 ? ` +${hoveredDevice.tags.length - 3}` : ''}
                  </span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default NDMTopologyTab;
