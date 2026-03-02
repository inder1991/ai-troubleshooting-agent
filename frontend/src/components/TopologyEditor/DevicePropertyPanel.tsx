import React, { useState, useEffect } from 'react';
import type { Node } from 'reactflow';

interface DevicePropertyPanelProps {
  selectedNode: Node | null;
  onNodeUpdate: (nodeId: string, data: Record<string, unknown>) => void;
  onConfigureAdapter?: (nodeId: string) => void;
}

const DevicePropertyPanel: React.FC<DevicePropertyPanelProps> = ({
  selectedNode,
  onNodeUpdate,
  onConfigureAdapter,
}) => {
  const [name, setName] = useState('');
  const [ip, setIp] = useState('');
  const [vendor, setVendor] = useState('');
  const [deviceType, setDeviceType] = useState('');
  const [zone, setZone] = useState('');

  useEffect(() => {
    if (selectedNode) {
      const d = selectedNode.data as Record<string, string>;
      setName(d.label || '');
      setIp(d.ip || '');
      setVendor(d.vendor || '');
      setDeviceType(d.deviceType || '');
      setZone(d.zone || '');
    }
  }, [selectedNode]);

  if (!selectedNode) {
    return (
      <div
        className="w-72 flex-shrink-0 border-l flex items-center justify-center p-4"
        style={{ backgroundColor: '#0f2023', borderColor: '#224349' }}
      >
        <p className="text-xs font-mono text-center" style={{ color: '#64748b' }}>
          Select a device to edit properties
        </p>
      </div>
    );
  }

  const isFirewall = deviceType === 'firewall';

  const handleApply = () => {
    onNodeUpdate(selectedNode.id, {
      label: name,
      ip,
      vendor,
      deviceType,
      zone,
    });
  };

  const inputStyle: React.CSSProperties = {
    backgroundColor: '#0a0f13',
    borderColor: '#224349',
    color: '#e2e8f0',
  };

  return (
    <div
      className="w-72 flex-shrink-0 border-l flex flex-col p-4 overflow-y-auto"
      style={{ backgroundColor: '#0f2023', borderColor: '#224349' }}
    >
      <h3
        className="text-xs font-mono font-semibold uppercase tracking-widest mb-4"
        style={{ color: '#07b6d5' }}
      >
        Device Properties
      </h3>

      <div className="flex flex-col gap-3">
        {/* Name */}
        <div className="flex flex-col gap-1">
          <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>
            Name
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#07b6d5]"
            style={inputStyle}
          />
        </div>

        {/* IP */}
        <div className="flex flex-col gap-1">
          <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>
            IP Address
          </label>
          <input
            type="text"
            value={ip}
            onChange={(e) => setIp(e.target.value)}
            placeholder="192.168.1.1"
            className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#07b6d5]"
            style={inputStyle}
          />
        </div>

        {/* Vendor */}
        <div className="flex flex-col gap-1">
          <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>
            Vendor
          </label>
          <input
            type="text"
            value={vendor}
            onChange={(e) => setVendor(e.target.value)}
            placeholder="Cisco, Palo Alto, etc."
            className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#07b6d5]"
            style={inputStyle}
          />
        </div>

        {/* Type */}
        <div className="flex flex-col gap-1">
          <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>
            Type
          </label>
          <select
            value={deviceType}
            onChange={(e) => setDeviceType(e.target.value)}
            className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#07b6d5]"
            style={inputStyle}
          >
            <option value="router">Router</option>
            <option value="switch">Switch</option>
            <option value="firewall">Firewall</option>
            <option value="workload">Workload</option>
            <option value="cloud_gateway">Cloud Gateway</option>
            <option value="zone">Zone</option>
          </select>
        </div>

        {/* Zone */}
        <div className="flex flex-col gap-1">
          <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>
            Zone
          </label>
          <input
            type="text"
            value={zone}
            onChange={(e) => setZone(e.target.value)}
            placeholder="DMZ, Internal, etc."
            className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#07b6d5]"
            style={inputStyle}
          />
        </div>

        {/* Apply Button */}
        <button
          onClick={handleApply}
          className="mt-2 text-sm font-mono font-semibold px-4 py-2 rounded transition-colors"
          style={{ backgroundColor: '#07b6d5', color: '#0a0f13' }}
        >
          Apply Changes
        </button>

        {/* Firewall Adapter Config */}
        {isFirewall && onConfigureAdapter && (
          <button
            onClick={() => onConfigureAdapter(selectedNode.id)}
            className="text-sm font-mono px-4 py-2 rounded border transition-colors hover:border-[#f59e0b]"
            style={{
              backgroundColor: 'transparent',
              borderColor: '#224349',
              color: '#f59e0b',
            }}
          >
            <span className="flex items-center gap-2 justify-center">
              <span
                className="material-symbols-outlined text-base"
                style={{ fontFamily: 'Material Symbols Outlined' }}
              >
                settings
              </span>
              Configure Adapter
            </span>
          </button>
        )}
      </div>
    </div>
  );
};

export default DevicePropertyPanel;
