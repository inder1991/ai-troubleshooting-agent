import React, { DragEvent } from 'react';

type PaletteEnv = 'cloud' | 'on-prem' | 'hybrid';

interface PaletteItem {
  type: string;
  label: string;
  icon: string;
  env?: PaletteEnv;
}

interface PaletteCategory {
  label: string;
  items: PaletteItem[];
}

const envBadge: Record<PaletteEnv, { label: string; color: string; bg: string }> = {
  cloud:    { label: 'AWS', color: '#3b82f6', bg: 'rgba(59,130,246,0.15)' },
  'on-prem': { label: 'DC',  color: '#94a3b8', bg: 'rgba(148,163,184,0.15)' },
  hybrid:   { label: 'ANY', color: '#a855f7', bg: 'rgba(168,85,247,0.15)' },
};

const paletteCategories: PaletteCategory[] = [
  {
    label: 'Infrastructure',
    items: [
      { type: 'router', label: 'Router', icon: 'router', env: 'hybrid' },
      { type: 'switch', label: 'Switch', icon: 'swap_horiz', env: 'on-prem' },
      { type: 'firewall', label: 'Firewall', icon: 'local_fire_department', env: 'hybrid' },
      { type: 'workload', label: 'Workload', icon: 'memory', env: 'hybrid' },
    ],
  },
  {
    label: 'Cloud',
    items: [
      { type: 'vpc', label: 'VPC / VNet', icon: 'cloud_circle', env: 'cloud' },
      { type: 'transit_gateway', label: 'Transit Gateway', icon: 'hub', env: 'cloud' },
      { type: 'load_balancer', label: 'Load Balancer', icon: 'dns', env: 'hybrid' },
      { type: 'cloud_gateway', label: 'Cloud Gateway', icon: 'cloud', env: 'cloud' },
      { type: 'nat_gateway', label: 'NAT Gateway', icon: 'nat', env: 'cloud' },
      { type: 'internet_gateway', label: 'Internet Gateway', icon: 'language', env: 'cloud' },
      { type: 'lambda', label: 'Lambda', icon: 'functions', env: 'cloud' },
      { type: 'route_table', label: 'Route Table', icon: 'route', env: 'cloud' },
      { type: 'elastic_ip', label: 'Elastic IP', icon: 'pin_drop', env: 'cloud' },
      { type: 'availability_zone', label: 'Availability Zone', icon: 'dns', env: 'cloud' },
      { type: 'auto_scaling_group', label: 'Auto Scaling Group', icon: 'auto_awesome', env: 'cloud' },
    ],
  },
  {
    label: 'Connectivity',
    items: [
      { type: 'vpn_tunnel', label: 'VPN Tunnel', icon: 'vpn_lock', env: 'hybrid' },
      { type: 'direct_connect', label: 'Direct Connect', icon: 'cable', env: 'on-prem' },
      { type: 'mpls', label: 'MPLS Circuit', icon: 'conversion_path', env: 'on-prem' },
    ],
  },
  {
    label: 'Security',
    items: [
      { type: 'nacl', label: 'NACL', icon: 'checklist', env: 'cloud' },
      { type: 'zone', label: 'Zone', icon: 'shield', env: 'hybrid' },
      { type: 'subnet', label: 'Subnet', icon: 'lan', env: 'cloud' },
      { type: 'compliance_zone', label: 'Compliance Zone', icon: 'verified_user', env: 'hybrid' },
      { type: 'security_group', label: 'Security Group', icon: 'shield_lock', env: 'cloud' },
    ],
  },
  {
    label: 'Data Center',
    items: [
      { type: 'vlan', label: 'VLAN', icon: 'label', env: 'on-prem' },
      { type: 'ha_group', label: 'HA Group', icon: 'sync', env: 'hybrid' },
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
              <span className="text-xs font-mono flex-1">{item.label}</span>
              {item.env && (
                <span
                  className="text-[7px] font-mono font-bold px-1.5 py-0.5 rounded leading-none shrink-0"
                  style={{
                    backgroundColor: envBadge[item.env].bg,
                    color: envBadge[item.env].color,
                    border: `1px solid ${envBadge[item.env].color}40`,
                  }}
                >
                  {envBadge[item.env].label}
                </span>
              )}
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
