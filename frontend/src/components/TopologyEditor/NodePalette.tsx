import React, { DragEvent } from 'react';

interface PaletteItem {
  type: string;
  label: string;
  icon: string;
}

interface PaletteCategory {
  label: string;
  items: PaletteItem[];
}

const paletteCategories: PaletteCategory[] = [
  {
    label: 'Infrastructure',
    items: [
      { type: 'router', label: 'Router', icon: 'router' },
      { type: 'switch', label: 'Switch', icon: 'swap_horiz' },
      { type: 'firewall', label: 'Firewall', icon: 'local_fire_department' },
      { type: 'workload', label: 'Workload', icon: 'memory' },
    ],
  },
  {
    label: 'Cloud',
    items: [
      { type: 'vpc', label: 'VPC / VNet', icon: 'cloud_circle' },
      { type: 'transit_gateway', label: 'Transit Gateway', icon: 'hub' },
      { type: 'load_balancer', label: 'Load Balancer', icon: 'dns' },
      { type: 'cloud_gateway', label: 'Cloud Gateway', icon: 'cloud' },
      { type: 'nat_gateway', label: 'NAT Gateway', icon: 'nat' },
      { type: 'internet_gateway', label: 'Internet Gateway', icon: 'language' },
      { type: 'lambda', label: 'Lambda', icon: 'functions' },
      { type: 'route_table', label: 'Route Table', icon: 'route' },
      { type: 'elastic_ip', label: 'Elastic IP', icon: 'pin_drop' },
      { type: 'availability_zone', label: 'Availability Zone', icon: 'dns' },
      { type: 'auto_scaling_group', label: 'Auto Scaling Group', icon: 'auto_awesome' },
    ],
  },
  {
    label: 'Connectivity',
    items: [
      { type: 'vpn_tunnel', label: 'VPN Tunnel', icon: 'vpn_lock' },
      { type: 'direct_connect', label: 'Direct Connect', icon: 'cable' },
      { type: 'mpls', label: 'MPLS Circuit', icon: 'conversion_path' },
    ],
  },
  {
    label: 'Security',
    items: [
      { type: 'nacl', label: 'NACL', icon: 'checklist' },
      { type: 'zone', label: 'Zone', icon: 'shield' },
      { type: 'subnet', label: 'Subnet', icon: 'lan' },
      { type: 'compliance_zone', label: 'Compliance Zone', icon: 'verified_user' },
      { type: 'security_group', label: 'Security Group', icon: 'shield_lock' },
    ],
  },
  {
    label: 'Data Center',
    items: [
      { type: 'vlan', label: 'VLAN', icon: 'label' },
      { type: 'ha_group', label: 'HA Group', icon: 'sync' },
    ],
  },
  {
    label: 'Annotations',
    items: [
      { type: 'text_annotation', label: 'Text Note', icon: 'sticky_note_2' },
    ],
  },
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

      {paletteCategories.map((cat) => (
        <div key={cat.label}>
          <div
            className="text-[9px] font-mono uppercase tracking-widest px-2 pt-3 pb-1"
            style={{ color: '#64748b' }}
          >
            {cat.label}
          </div>
          {cat.items.map((item) => (
            <div
              key={item.type}
              draggable
              onDragStart={(e) => onDragStart(e, item.type)}
              className="flex items-center gap-3 px-3 py-2 rounded-lg cursor-grab active:cursor-grabbing border transition-colors hover:border-[#07b6d5]/30"
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
              <span className="text-xs font-mono">{item.label}</span>
            </div>
          ))}
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
