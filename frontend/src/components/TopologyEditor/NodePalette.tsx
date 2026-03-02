import React, { DragEvent } from 'react';

interface PaletteItem {
  type: string;
  label: string;
  icon: string;
}

const paletteItems: PaletteItem[] = [
  { type: 'router', label: 'Router', icon: 'router' },
  { type: 'switch', label: 'Switch', icon: 'swap_horiz' },
  { type: 'firewall', label: 'Firewall', icon: 'local_fire_department' },
  { type: 'subnet', label: 'Subnet', icon: 'lan' },
  { type: 'zone', label: 'Zone', icon: 'shield' },
  { type: 'workload', label: 'Workload', icon: 'memory' },
  { type: 'cloud_gateway', label: 'Cloud Gateway', icon: 'cloud' },
];

const NodePalette: React.FC = () => {
  const onDragStart = (event: DragEvent<HTMLDivElement>, nodeType: string) => {
    event.dataTransfer.setData('application/reactflow', nodeType);
    event.dataTransfer.effectAllowed = 'move';
  };

  return (
    <div
      className="w-56 flex-shrink-0 border-r flex flex-col gap-1 p-3 overflow-y-auto"
      style={{ backgroundColor: '#0f2023', borderColor: '#224349' }}
    >
      <h3
        className="text-xs font-mono font-semibold uppercase tracking-widest px-2 py-2 mb-1"
        style={{ color: '#07b6d5' }}
      >
        Device Palette
      </h3>

      {paletteItems.map((item) => (
        <div
          key={item.type}
          draggable
          onDragStart={(e) => onDragStart(e, item.type)}
          className="flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-grab active:cursor-grabbing border transition-colors hover:border-[#07b6d5]/30"
          style={{
            backgroundColor: '#162a2e',
            borderColor: '#224349',
            color: '#e2e8f0',
          }}
        >
          <span
            className="material-symbols-outlined text-lg"
            style={{ fontFamily: 'Material Symbols Outlined', color: '#f59e0b' }}
          >
            {item.icon}
          </span>
          <span className="text-sm font-mono">{item.label}</span>
        </div>
      ))}

      <div className="mt-4 px-2">
        <p className="text-[10px] font-mono" style={{ color: '#64748b' }}>
          Drag a device onto the canvas to add it to the topology.
        </p>
      </div>
    </div>
  );
};

export default NodePalette;
