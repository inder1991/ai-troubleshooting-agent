import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import type { Node, Edge } from 'reactflow';
import { validateIPv4, validateCIDR, isIPInCIDR, isCIDRSubsetOf } from '../../utils/networkValidation';

interface DevicePropertyPanelProps {
  selectedNode: Node | null;
  selectedEdge?: Edge | null;
  allNodes?: Node[];
  onNodeUpdate: (nodeId: string, data: Record<string, unknown>) => void;
  onEdgeUpdate?: (edgeId: string, data: Record<string, unknown>) => void;
  onDeleteEdge?: (edgeId: string) => void;
  onConfigureAdapter?: (nodeId: string) => void;
  onAddInterface?: (parentNodeId: string) => void;
}

const CONTAINER_NODE_TYPES = new Set([
  'availability_zone', 'auto_scaling_group', 'vpc', 'subnet', 'compliance_zone', 'ha_group',
]);

const CIDR_CONTAINER_TYPES = new Set(['vpc', 'subnet', 'compliance_zone']);

const EDGE_TYPES = [
  'connected_to', 'routes_to', 'load_balances', 'tunnel_to',
  'nacl_guards', 'vpc_contains', 'attached_to',
];

const DevicePropertyPanel: React.FC<DevicePropertyPanelProps> = ({
  selectedNode,
  selectedEdge,
  onNodeUpdate,
  onEdgeUpdate,
  onDeleteEdge,
  allNodes,
  onConfigureAdapter,
  onAddInterface,
}) => {
  const [name, setName] = useState('');
  const [ip, setIp] = useState('');
  const [vendor, setVendor] = useState('');
  const [deviceType, setDeviceType] = useState('');
  const [zone, setZone] = useState('');
  const [cloudProvider, setCloudProvider] = useState('aws');
  const [region, setRegion] = useState('');
  const [cidr, setCidr] = useState('');
  const [tunnelType, setTunnelType] = useState('ipsec');
  const [encryption, setEncryption] = useState('');
  const [remoteGateway, setRemoteGateway] = useState('');
  const [lbType, setLbType] = useState('alb');
  const [lbScheme, setLbScheme] = useState('internal');
  const [interfaces, setInterfaces] = useState<Array<{
    id: string; name: string; ip: string; role: string; zone: string;
  }>>([]);
  const [zoneName, setZoneName] = useState('');
  const [minCapacity, setMinCapacity] = useState(0);
  const [maxCapacity, setMaxCapacity] = useState(0);
  const [desiredCapacity, setDesiredCapacity] = useState(0);
  const [launchTemplate, setLaunchTemplate] = useState('');
  const [elasticIp, setElasticIp] = useState('');
  const [subnetAssociation, setSubnetAssociation] = useState('');
  const [vpcAssociation, setVpcAssociation] = useState('');
  const [haMode, setHaMode] = useState('active_passive');
  const [virtualIps, setVirtualIps] = useState('');
  const [complianceFramework, setComplianceFramework] = useState('pci_dss');
  const [zoneType, setZoneType] = useState('');
  // Text annotation fields
  const [annotationText, setAnnotationText] = useState('');
  const [annotationFontSize, setAnnotationFontSize] = useState(12);
  const [annotationColor, setAnnotationColor] = useState('#e8e0d4');
  const [annotationBg, setAnnotationBg] = useState('transparent');
  const [annotationBorder, setAnnotationBorder] = useState('none');

  // Auto-save
  const [saved, setSaved] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isInitRef = useRef(false);

  useEffect(() => {
    if (selectedNode) {
      isInitRef.current = true;
      const d = selectedNode.data as Record<string, string>;
      setName(d.label || '');
      setIp(d.ip || '');
      setVendor(d.vendor || '');
      setDeviceType(d.deviceType || '');
      setZone(d.zone || '');
      setCloudProvider(d.cloudProvider || 'aws');
      setRegion(d.region || '');
      setCidr(d.cidr || '');
      setTunnelType(d.tunnelType || 'ipsec');
      setEncryption(d.encryption || '');
      setRemoteGateway(d.remoteGateway || '');
      setLbType(d.lbType || 'alb');
      setLbScheme(d.lbScheme || 'internal');
      const ifaces = (d.interfaces as unknown as typeof interfaces) || [];
      setInterfaces(ifaces);
      setZoneName(d.zoneName || '');
      setMinCapacity(Number(d.minCapacity) || 0);
      setMaxCapacity(Number(d.maxCapacity) || 0);
      setDesiredCapacity(Number(d.desiredCapacity) || 0);
      setLaunchTemplate(d.launchTemplate || '');
      setElasticIp(d.elasticIp || '');
      setSubnetAssociation(d.subnetAssociation || '');
      setVpcAssociation(d.vpcAssociation || '');
      setHaMode(d.haMode || 'active_passive');
      setVirtualIps(d.virtualIps || '');
      setComplianceFramework(d.complianceFramework || d.complianceStandard || 'pci_dss');
      setZoneType(d.zoneType || '');
      // Text annotation
      if (selectedNode.type === 'text_annotation') {
        setAnnotationText(d.text || '');
        setAnnotationFontSize(Number(d.fontSize) || 12);
        setAnnotationColor(d.color || '#e8e0d4');
        setAnnotationBg(d.backgroundColor || 'transparent');
        setAnnotationBorder(d.borderStyle || 'none');
      }
      // Reset init flag after a tick
      setTimeout(() => { isInitRef.current = false; }, 50);
    }
  }, [selectedNode]);

  // Find parent subnet CIDR for IP validation (both device and interface nodes)
  const parentSubnetCidr = useMemo(() => {
    if (!selectedNode || !allNodes) return null;
    const nodeData = selectedNode.data as Record<string, unknown>;

    if (selectedNode.type === 'interface') {
      // Check subnetId first, then look for parentContainerId on the parent device
      const subnetId = nodeData.subnetId as string;
      if (subnetId) {
        const subnet = allNodes.find((n) => n.id === subnetId);
        return (subnet?.data as Record<string, unknown>)?.cidr as string || null;
      }
      // Check the parent device's container
      const parentDeviceId = nodeData.parentDeviceId as string;
      if (parentDeviceId) {
        const parentDevice = allNodes.find((n) => n.id === parentDeviceId);
        const containerId = (parentDevice?.data as Record<string, unknown>)?.parentContainerId as string;
        if (containerId) {
          const container = allNodes.find((n) => n.id === containerId && n.type === 'subnet');
          return (container?.data as Record<string, unknown>)?.cidr as string || null;
        }
      }
    }

    // Device node: check parentContainerId for subnet CIDR
    if (selectedNode.type === 'device' || (!selectedNode.type && !CONTAINER_NODE_TYPES.has(selectedNode.type || ''))) {
      const containerId = nodeData.parentContainerId as string;
      if (containerId) {
        const container = allNodes.find((n) => n.id === containerId && n.type === 'subnet');
        if (container) {
          return (container.data as Record<string, unknown>).cidr as string || null;
        }
      }
    }

    return null;
  }, [selectedNode, allNodes]);

  // Find parent VPC CIDR for subnet containment validation
  const parentVpcCidr = useMemo(() => {
    if (!selectedNode || !allNodes || selectedNode.type !== 'subnet') return null;
    // Find VPC that contains this subnet spatially
    const vpcs = allNodes.filter((n) => n.type === 'vpc');
    for (const vpc of vpcs) {
      const cw = (vpc.style?.width as number) || 300;
      const ch = (vpc.style?.height as number) || 200;
      if (selectedNode.position.x >= vpc.position.x && selectedNode.position.x <= vpc.position.x + cw &&
          selectedNode.position.y >= vpc.position.y && selectedNode.position.y <= vpc.position.y + ch) {
        return (vpc.data as Record<string, unknown>).cidr as string || null;
      }
    }
    return null;
  }, [selectedNode, allNodes]);

  const errors = useMemo(() => {
    const ifaceErrors: Record<number, string | null> = {};
    interfaces.forEach((iface, idx) => {
      ifaceErrors[idx] = iface.ip ? validateIPv4(iface.ip) : null;
    });

    // IP-in-subnet validation for interface nodes
    let ipSubnetError: string | null = null;
    if (ip && !validateIPv4(ip) && parentSubnetCidr && !validateCIDR(parentSubnetCidr)) {
      if (!isIPInCIDR(ip, parentSubnetCidr)) {
        ipSubnetError = `IP not in subnet CIDR ${parentSubnetCidr}`;
      }
    }

    // CIDR containment validation for subnet nodes
    let cidrContainmentError: string | null = null;
    if (cidr && !validateCIDR(cidr) && parentVpcCidr && !validateCIDR(parentVpcCidr)) {
      if (!isCIDRSubsetOf(cidr, parentVpcCidr)) {
        cidrContainmentError = `Subnet CIDR not within VPC CIDR ${parentVpcCidr}`;
      }
    }

    return {
      ip: ip ? validateIPv4(ip) : null,
      ipSubnet: ipSubnetError,
      cidr: cidr ? validateCIDR(cidr) : null,
      cidrContainment: cidrContainmentError,
      remoteGateway: remoteGateway ? validateIPv4(remoteGateway) : null,
      interfaces: ifaceErrors,
    };
  }, [ip, cidr, remoteGateway, interfaces, parentSubnetCidr, parentVpcCidr]);

  const hasErrors = !!errors.ip || !!errors.cidr || !!errors.remoteGateway || !!errors.ipSubnet || !!errors.cidrContainment || Object.values(errors.interfaces).some(Boolean);

  // Debounced auto-save for node properties
  const doAutoSave = useCallback(() => {
    if (!selectedNode || isInitRef.current || hasErrors) return;

    const isContainer = CONTAINER_NODE_TYPES.has(selectedNode.type || '');
    const isInterface = selectedNode.type === 'interface';
    const isAnnotation = selectedNode.type === 'text_annotation';
    const nType = selectedNode.type || '';

    const base: Record<string, unknown> = { label: name };

    if (isAnnotation) {
      base.text = annotationText;
      base.fontSize = annotationFontSize;
      base.color = annotationColor;
      base.backgroundColor = annotationBg;
      base.borderStyle = annotationBorder;
      onNodeUpdate(selectedNode.id, base);
    } else if (isInterface) {
      base.name = name;
      base.ip = ip;
      base.role = zone;
      base.zone = zone;
      base.parentDeviceId = (selectedNode.data as Record<string, unknown>).parentDeviceId;
      base.parentDeviceName = (selectedNode.data as Record<string, unknown>).parentDeviceName;
      onNodeUpdate(selectedNode.id, base);
    } else if (isContainer) {
      if (CIDR_CONTAINER_TYPES.has(nType)) base.cidr = cidr;
      if (nType === 'vpc') { base.cloudProvider = cloudProvider; base.region = region; base.deviceType = deviceType; }
      if (nType === 'availability_zone') { base.zoneName = zoneName; base.cloudProvider = cloudProvider; base.region = region; base.deviceType = deviceType; }
      if (nType === 'auto_scaling_group') { base.minCapacity = minCapacity; base.maxCapacity = maxCapacity; base.desiredCapacity = desiredCapacity; base.launchTemplate = launchTemplate; base.deviceType = deviceType; }
      if (nType === 'ha_group') { base.haMode = haMode; base.virtualIps = virtualIps; base.deviceType = deviceType; }
      if (nType === 'compliance_zone') { base.complianceFramework = complianceFramework; base.complianceStandard = complianceFramework; base.zoneType = zoneType; base.deviceType = deviceType; }
      onNodeUpdate(selectedNode.id, base);
    } else {
      base.ip = ip; base.vendor = vendor; base.deviceType = deviceType; base.zone = zone;
      base.interfaces = interfaces; base.tunnelType = tunnelType; base.encryption = encryption;
      base.remoteGateway = remoteGateway; base.lbType = lbType; base.lbScheme = lbScheme;
      base.cloudProvider = cloudProvider; base.region = region; base.cidr = cidr;
      base.elasticIp = elasticIp; base.subnetAssociation = subnetAssociation; base.vpcAssociation = vpcAssociation;
      onNodeUpdate(selectedNode.id, base);
    }

    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  }, [selectedNode, name, ip, vendor, deviceType, zone, cloudProvider, region, cidr, tunnelType,
    encryption, remoteGateway, lbType, lbScheme, interfaces, zoneName, minCapacity, maxCapacity,
    desiredCapacity, launchTemplate, elasticIp, subnetAssociation, vpcAssociation, haMode,
    virtualIps, complianceFramework, zoneType, annotationText, annotationFontSize, annotationColor,
    annotationBg, annotationBorder, hasErrors, onNodeUpdate]);

  // Trigger debounced auto-save on any field change
  useEffect(() => {
    if (isInitRef.current || !selectedNode) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(doAutoSave, 300);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [name, ip, vendor, deviceType, zone, cloudProvider, region, cidr, tunnelType,
    encryption, remoteGateway, lbType, lbScheme, interfaces, zoneName, minCapacity,
    maxCapacity, desiredCapacity, launchTemplate, elasticIp, subnetAssociation,
    vpcAssociation, haMode, virtualIps, complianceFramework, zoneType,
    annotationText, annotationFontSize, annotationColor, annotationBg, annotationBorder,
    doAutoSave, selectedNode]);

  // === Edge Properties Panel ===
  if (selectedEdge && !selectedNode) {
    const edgeLabel = (selectedEdge.data?.label as string) || 'connected_to';
    return (
      <div className="w-72 flex-shrink-0 border-l flex flex-col p-4 overflow-y-auto"
        style={{ backgroundColor: '#1a1814', borderColor: '#3d3528' }}>
        <h3 className="text-xs font-mono font-semibold uppercase tracking-widest mb-4" style={{ color: '#e09f3e' }}>
          Edge Properties
        </h3>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Edge Type</label>
            <select
              value={edgeLabel}
              onChange={(e) => onEdgeUpdate?.(selectedEdge.id, { label: e.target.value })}
              className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e]"
              style={{ backgroundColor: '#0a0f13', borderColor: '#3d3528', color: '#e8e0d4' }}>
              {EDGE_TYPES.map((t) => (
                <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Source</label>
            <div className="text-xs font-mono px-3 py-2 rounded border" style={{ backgroundColor: '#0a0f13', borderColor: '#3d3528', color: '#8a7e6b' }}>
              {selectedEdge.source}
            </div>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Target</label>
            <div className="text-xs font-mono px-3 py-2 rounded border" style={{ backgroundColor: '#0a0f13', borderColor: '#3d3528', color: '#8a7e6b' }}>
              {selectedEdge.target}
            </div>
          </div>
          {onDeleteEdge && (
            <button
              onClick={() => onDeleteEdge(selectedEdge.id)}
              className="mt-2 text-sm font-mono font-semibold px-4 py-2 rounded transition-colors hover:bg-red-900/30"
              style={{ backgroundColor: 'transparent', color: '#ef4444', border: '1px solid #ef444440' }}>
              Delete Edge
            </button>
          )}
        </div>
      </div>
    );
  }

  if (!selectedNode) {
    return null;
  }

  const isFirewall = deviceType === 'firewall';
  const isContainer = CONTAINER_NODE_TYPES.has(selectedNode?.type || '');
  const isInterface = selectedNode?.type === 'interface';
  const isAnnotation = selectedNode?.type === 'text_annotation';
  const nodeType = selectedNode?.type || '';
  const isLiveNode = (selectedNode?.data as Record<string, unknown>)?._source === 'live';
  const isReadOnly = isLiveNode;

  const inputStyle: React.CSSProperties = {
    backgroundColor: '#0a0f13',
    borderColor: '#3d3528',
    color: isReadOnly ? '#64748b' : '#e8e0d4',
  };

  // === Text Annotation Properties ===
  if (isAnnotation) {
    return (
      <div className="w-72 flex-shrink-0 border-l flex flex-col p-4 overflow-y-auto"
        style={{ backgroundColor: '#1a1814', borderColor: '#3d3528' }}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xs font-mono font-semibold uppercase tracking-widest" style={{ color: '#e09f3e' }}>
            Annotation
          </h3>
          {saved && <span className="text-[10px] font-mono animate-pulse" style={{ color: '#22c55e' }}>Saved</span>}
        </div>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Label</label>
            <input type="text" value={name} onChange={(e) => setName(e.target.value)}
              className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e]" style={inputStyle} />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Text</label>
            <textarea value={annotationText} onChange={(e) => setAnnotationText(e.target.value)} rows={4}
              className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e] resize-none"
              style={inputStyle} placeholder="Enter annotation text..." />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Font Size</label>
            <select value={annotationFontSize} onChange={(e) => setAnnotationFontSize(Number(e.target.value))}
              className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e]" style={inputStyle}>
              <option value={10}>10px</option>
              <option value={12}>12px</option>
              <option value={14}>14px</option>
              <option value={18}>18px</option>
              <option value={24}>24px</option>
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Text Color</label>
            <div className="flex gap-1.5">
              {[
                { label: 'W', value: '#e8e0d4' },
                { label: 'C', value: '#e09f3e' },
                { label: 'A', value: '#f59e0b' },
                { label: 'R', value: '#ef4444' },
                { label: 'G', value: '#22c55e' },
                { label: 'Gr', value: '#64748b' },
              ].map((c) => (
                <button key={c.value} onClick={() => setAnnotationColor(c.value)}
                  className="w-7 h-7 rounded border text-[8px] font-mono font-bold flex items-center justify-center"
                  style={{
                    backgroundColor: c.value + '20', color: c.value,
                    borderColor: annotationColor === c.value ? c.value : '#3d3528',
                    borderWidth: annotationColor === c.value ? 2 : 1,
                  }}>
                  {c.label}
                </button>
              ))}
            </div>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Background</label>
            <select value={annotationBg} onChange={(e) => setAnnotationBg(e.target.value)}
              className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e]" style={inputStyle}>
              <option value="transparent">Transparent</option>
              <option value="rgba(15,32,35,0.8)">Dark</option>
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Border</label>
            <select value={annotationBorder} onChange={(e) => setAnnotationBorder(e.target.value)}
              className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e]" style={inputStyle}>
              <option value="none">None</option>
              <option value="dashed">Dashed</option>
              <option value="solid">Solid</option>
            </select>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className="w-72 flex-shrink-0 border-l flex flex-col p-4 overflow-y-auto"
      style={{ backgroundColor: '#1a1814', borderColor: '#3d3528' }}
    >
      <div className="flex items-center justify-between mb-4">
        <h3
          className="text-xs font-mono font-semibold uppercase tracking-widest"
          style={{ color: '#e09f3e' }}
        >
          {isInterface ? 'Interface Properties' : isContainer ? 'Container Properties' : 'Device Properties'}
        </h3>
        {saved && <span className="text-[10px] font-mono animate-pulse" style={{ color: '#22c55e' }}>Saved</span>}
      </div>

      {/* Live / Planned badge */}
      {isLiveNode && (
        <div className="mb-3 flex items-center gap-2 px-2 py-1.5 rounded text-[10px] font-semibold uppercase tracking-wider"
          style={{ background: 'rgba(34,197,94,0.08)', color: '#4ade80', border: '1px solid rgba(34,197,94,0.15)' }}>
          <span className="material-symbols-outlined" style={{ fontSize: 12 }}>lock</span>
          LIVE — Read Only
          {onConfigureAdapter && (
            <button
              onClick={() => onConfigureAdapter(selectedNode.id)}
              className="ml-auto text-[10px] underline"
              style={{ color: '#e09f3e' }}
            >
              Open Adapter Config
            </button>
          )}
        </div>
      )}

      <div className="flex flex-col gap-3">
        {/* Name — always shown */}
        <div className="flex flex-col gap-1">
          <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>
            Name
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={isReadOnly}
            className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e] disabled:opacity-50 disabled:cursor-not-allowed"
            style={inputStyle}
          />
        </div>

        {/* === INTERFACE-SPECIFIC FIELDS === */}
        {isInterface && (
          <>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>
                IP Address
              </label>
              <input
                type="text"
                value={ip}
                onChange={(e) => setIp(e.target.value)}
                placeholder="10.0.1.10"
                className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e]"
                style={{ ...inputStyle, borderColor: errors.ip ? '#ef4444' : '#3d3528' }}
              />
              {errors.ip && <p className="font-mono" style={{ color: '#ef4444', fontSize: '10px', marginTop: '2px' }}>{errors.ip}</p>}
              {!errors.ip && errors.ipSubnet && <p className="font-mono" style={{ color: '#f59e0b', fontSize: '10px', marginTop: '2px' }}>{errors.ipSubnet}</p>}
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>
                Role
              </label>
              <select
                value={zone}
                onChange={(e) => setZone(e.target.value)}
                className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e]"
                style={inputStyle}
              >
                <option value="">Select role...</option>
                <option value="management">Management</option>
                <option value="inside">Inside (Trust)</option>
                <option value="outside">Outside (Untrust)</option>
                <option value="dmz">DMZ</option>
                <option value="sync">Sync / HA</option>
                <option value="loopback">Loopback</option>
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>
                Parent Device
              </label>
              <div className="text-xs font-mono px-3 py-2 rounded border" style={{ ...inputStyle, color: '#8a7e6b' }}>
                {(selectedNode?.data as Record<string, unknown>)?.parentDeviceName as string || 'Unknown'}
              </div>
            </div>
          </>
        )}

        {/* === DEVICE-ONLY FIELDS === */}
        {!isContainer && !isInterface && (
          <>
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
                className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e]"
                style={{ ...inputStyle, borderColor: errors.ip ? '#ef4444' : errors.ipSubnet ? '#f59e0b' : '#3d3528' }}
              />
              {errors.ip && <p className="font-mono" style={{ color: '#ef4444', fontSize: '10px', marginTop: '2px' }}>{errors.ip}</p>}
              {!errors.ip && errors.ipSubnet && <p className="font-mono" style={{ color: '#f59e0b', fontSize: '10px', marginTop: '2px' }}>{errors.ipSubnet}</p>}
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
                className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e]"
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
                className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e]"
                style={inputStyle}
              >
                <option value="router">Router</option>
                <option value="switch">Switch</option>
                <option value="firewall">Firewall</option>
                <option value="workload">Workload</option>
                <option value="cloud_gateway">Cloud Gateway</option>
                <option value="zone">Zone</option>
                <option value="transit_gateway">Transit Gateway</option>
                <option value="load_balancer">Load Balancer</option>
                <option value="vpn_tunnel">VPN Tunnel</option>
                <option value="direct_connect">Direct Connect</option>
                <option value="nacl">NACL</option>
                <option value="vlan">VLAN</option>
                <option value="mpls">MPLS Circuit</option>
                <option value="nat_gateway">NAT Gateway</option>
                <option value="internet_gateway">Internet Gateway</option>
                <option value="lambda">Lambda</option>
                <option value="route_table">Route Table</option>
                <option value="security_group">Security Group</option>
                <option value="elastic_ip">Elastic IP</option>
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
                className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e]"
                style={inputStyle}
              />
            </div>
          </>
        )}

        {/* === CIDR — for VPC, Subnet, Compliance Zone === */}
        {isContainer && CIDR_CONTAINER_TYPES.has(nodeType) && (
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>CIDR</label>
            <input type="text" value={cidr} onChange={(e) => setCidr(e.target.value)}
                   placeholder={nodeType === 'vpc' ? '10.0.0.0/16' : '10.0.1.0/24'}
                   className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e]"
                   style={{ ...inputStyle, borderColor: errors.cidr ? '#ef4444' : '#3d3528' }} />
            {errors.cidr && <p className="font-mono" style={{ color: '#ef4444', fontSize: '10px', marginTop: '2px' }}>{errors.cidr}</p>}
            {!errors.cidr && errors.cidrContainment && <p className="font-mono" style={{ color: '#f59e0b', fontSize: '10px', marginTop: '2px' }}>{errors.cidrContainment}</p>}
          </div>
        )}

        {/* === VPC-specific fields === */}
        {(nodeType === 'vpc' || (deviceType === 'vpc' && !isContainer)) && (
          <>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Cloud Provider</label>
              <select value={cloudProvider} onChange={(e) => setCloudProvider(e.target.value)}
                      className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e]" style={inputStyle}>
                <option value="aws">AWS</option>
                <option value="azure">Azure</option>
                <option value="gcp">GCP</option>
                <option value="oci">Oracle Cloud</option>
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Region</label>
              <input type="text" value={region} onChange={(e) => setRegion(e.target.value)} placeholder="us-east-1"
                     className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e]" style={inputStyle} />
            </div>
          </>
        )}

        {/* === VPN-specific fields === */}
        {!isContainer && deviceType === 'vpn_tunnel' && (
          <>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Tunnel Type</label>
              <select value={tunnelType} onChange={(e) => setTunnelType(e.target.value)}
                      className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e]" style={inputStyle}>
                <option value="ipsec">IPSec</option>
                <option value="gre">GRE</option>
                <option value="ssl">SSL VPN</option>
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Encryption</label>
              <input type="text" value={encryption} onChange={(e) => setEncryption(e.target.value)} placeholder="AES-256-GCM"
                     className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e]" style={inputStyle} />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Remote Gateway</label>
              <input type="text" value={remoteGateway} onChange={(e) => setRemoteGateway(e.target.value)} placeholder="203.0.113.1"
                     className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e]"
                     style={{ ...inputStyle, borderColor: errors.remoteGateway ? '#ef4444' : '#3d3528' }} />
              {errors.remoteGateway && <p className="font-mono" style={{ color: '#ef4444', fontSize: '10px', marginTop: '2px' }}>{errors.remoteGateway}</p>}
            </div>
          </>
        )}

        {/* === Load Balancer fields === */}
        {!isContainer && deviceType === 'load_balancer' && (
          <>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>LB Type</label>
              <select value={lbType} onChange={(e) => setLbType(e.target.value)}
                      className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e]" style={inputStyle}>
                <option value="alb">Application LB (ALB)</option>
                <option value="nlb">Network LB (NLB)</option>
                <option value="azure_lb">Azure LB</option>
                <option value="haproxy">HAProxy</option>
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Scheme</label>
              <select value={lbScheme} onChange={(e) => setLbScheme(e.target.value)}
                      className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e]" style={inputStyle}>
                <option value="internal">Internal</option>
                <option value="internet_facing">Internet Facing</option>
              </select>
            </div>
          </>
        )}

        {/* === AZ-specific fields === */}
        {nodeType === 'availability_zone' && (
          <>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Zone Name</label>
              <input type="text" value={zoneName} onChange={(e) => setZoneName(e.target.value)} placeholder="us-east-1a"
                     className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e]" style={inputStyle} />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Cloud Provider</label>
              <select value={cloudProvider} onChange={(e) => setCloudProvider(e.target.value)}
                      className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e]" style={inputStyle}>
                <option value="aws">AWS</option>
                <option value="azure">Azure</option>
                <option value="gcp">GCP</option>
                <option value="oci">Oracle Cloud</option>
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Region</label>
              <input type="text" value={region} onChange={(e) => setRegion(e.target.value)} placeholder="us-east-1"
                     className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e]" style={inputStyle} />
            </div>
          </>
        )}

        {/* === ASG-specific fields === */}
        {nodeType === 'auto_scaling_group' && (
          <>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Min Capacity</label>
              <input type="number" value={minCapacity} onChange={(e) => setMinCapacity(Number(e.target.value))} min={0}
                     className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e]" style={inputStyle} />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Desired Capacity</label>
              <input type="number" value={desiredCapacity} onChange={(e) => setDesiredCapacity(Number(e.target.value))} min={0}
                     className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e]" style={inputStyle} />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Max Capacity</label>
              <input type="number" value={maxCapacity} onChange={(e) => setMaxCapacity(Number(e.target.value))} min={0}
                     className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e]" style={inputStyle} />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Launch Template</label>
              <input type="text" value={launchTemplate} onChange={(e) => setLaunchTemplate(e.target.value)} placeholder="lt-0123456789abcdef"
                     className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e]" style={inputStyle} />
            </div>
          </>
        )}

        {/* === HA Group fields === */}
        {nodeType === 'ha_group' && (
          <>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>HA Mode</label>
              <select value={haMode} onChange={(e) => setHaMode(e.target.value)}
                      className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e]" style={inputStyle}>
                <option value="active_passive">Active / Passive</option>
                <option value="active_active">Active / Active</option>
                <option value="vrrp">VRRP</option>
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Virtual IPs (VIPs)</label>
              <input type="text" value={virtualIps} onChange={(e) => setVirtualIps(e.target.value)} placeholder="10.0.1.100, 10.0.2.100"
                     className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e]" style={inputStyle} />
            </div>
          </>
        )}

        {/* === Compliance Zone fields === */}
        {nodeType === 'compliance_zone' && (
          <>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Compliance Framework</label>
              <select value={complianceFramework} onChange={(e) => setComplianceFramework(e.target.value)}
                      className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e]" style={inputStyle}>
                <option value="pci_dss">PCI-DSS</option>
                <option value="soc2">SOC2</option>
                <option value="hipaa">HIPAA</option>
                <option value="custom">Custom</option>
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Zone Type</label>
              <select value={zoneType} onChange={(e) => setZoneType(e.target.value)}
                      className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e]" style={inputStyle}>
                <option value="">Select...</option>
                <option value="data">Data</option>
                <option value="dmz">DMZ</option>
                <option value="management">Management</option>
              </select>
            </div>
          </>
        )}

        {/* === NAT Gateway fields === */}
        {!isContainer && deviceType === 'nat_gateway' && (
          <>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Elastic IP</label>
              <input type="text" value={elasticIp} onChange={(e) => setElasticIp(e.target.value)} placeholder="52.x.x.x"
                     className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e]"
                     style={{ ...inputStyle, borderColor: elasticIp && validateIPv4(elasticIp) ? '#ef4444' : '#3d3528' }} />
              {elasticIp && validateIPv4(elasticIp) && <p className="font-mono" style={{ color: '#ef4444', fontSize: '10px', marginTop: '2px' }}>{validateIPv4(elasticIp)}</p>}
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Subnet Association</label>
              <input type="text" value={subnetAssociation} onChange={(e) => setSubnetAssociation(e.target.value)} placeholder="subnet-xxx"
                     className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e]" style={inputStyle} />
            </div>
          </>
        )}

        {/* === Internet Gateway / Route Table fields === */}
        {!isContainer && (deviceType === 'internet_gateway' || deviceType === 'route_table') && (
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>VPC Association</label>
            <input type="text" value={vpcAssociation} onChange={(e) => setVpcAssociation(e.target.value)} placeholder="vpc-xxx"
                   className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#e09f3e]" style={inputStyle} />
          </div>
        )}

        {/* === Add Interface (device only — spawns separate InterfaceNode) === */}
        {!isContainer && !isInterface && ['firewall', 'router', 'switch', 'load_balancer'].includes(deviceType) && onAddInterface && (
          <div className="mt-2 pt-2 border-t" style={{ borderColor: '#3d3528' }}>
            <button
              onClick={() => onAddInterface(selectedNode.id)}
              className="w-full flex items-center justify-center gap-2 text-xs font-mono px-3 py-2 rounded border transition-colors hover:border-[#e09f3e]"
              style={{ borderColor: '#3d3528', color: '#e09f3e', backgroundColor: 'transparent' }}
            >
              <span
                className="material-symbols-outlined text-sm"
              >
                settings_ethernet
              </span>
              + Add Interface (ENI)
            </button>
            <p className="text-[9px] font-mono mt-1 text-center" style={{ color: '#475569' }}>
              Drag interface into a subnet to show placement
            </p>
          </div>
        )}

        {/* Firewall Adapter Config */}
        {isFirewall && onConfigureAdapter && (
          <button
            onClick={() => onConfigureAdapter(selectedNode.id)}
            className="text-sm font-mono px-4 py-2 rounded border transition-colors hover:border-[#f59e0b]"
            style={{
              backgroundColor: 'transparent',
              borderColor: '#3d3528',
              color: '#f59e0b',
            }}
          >
            <span className="flex items-center gap-2 justify-center">
              <span
                className="material-symbols-outlined text-base"
              >
                settings_input_component
              </span>
              Manage Adapters
            </span>
          </button>
        )}

        {/* Credentials for planned devices */}
        {!isReadOnly && !isContainer && !isInterface && !isAnnotation && vendor && (
          <details className="mt-2">
            <summary className="text-[10px] font-mono uppercase tracking-wider cursor-pointer select-none" style={{ color: '#64748b' }}>
              Credentials
            </summary>
            <div className="mt-2 flex flex-col gap-2 pl-1">
              {(vendor === 'palo_alto' || vendor === 'checkpoint' || vendor === 'cisco' || vendor === 'zscaler' || vendor === 'f5') && (
                <>
                  <div className="flex flex-col gap-1">
                    <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>API Endpoint</label>
                    <input type="text" placeholder="https://..." className="text-xs font-mono px-2 py-1.5 rounded border focus:outline-none focus:border-[#e09f3e]"
                      style={{ backgroundColor: '#0a0f13', borderColor: '#3d3528', color: '#e8e0d4' }}
                      onChange={(e) => onNodeUpdate(selectedNode!.id, { _cred_api_endpoint: e.target.value })}
                      defaultValue={(selectedNode?.data as any)?._cred_api_endpoint || ''} />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>API Key</label>
                    <input type="password" placeholder="API key or token" className="text-xs font-mono px-2 py-1.5 rounded border focus:outline-none focus:border-[#e09f3e]"
                      style={{ backgroundColor: '#0a0f13', borderColor: '#3d3528', color: '#e8e0d4' }}
                      onChange={(e) => onNodeUpdate(selectedNode!.id, { _cred_api_key: e.target.value })}
                      defaultValue={(selectedNode?.data as any)?._cred_api_key || ''} />
                  </div>
                </>
              )}
              {(vendor === 'cisco' || vendor === 'f5') && (
                <>
                  <div className="flex flex-col gap-1">
                    <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Username</label>
                    <input type="text" placeholder="admin" className="text-xs font-mono px-2 py-1.5 rounded border focus:outline-none focus:border-[#e09f3e]"
                      style={{ backgroundColor: '#0a0f13', borderColor: '#3d3528', color: '#e8e0d4' }}
                      onChange={(e) => onNodeUpdate(selectedNode!.id, { _cred_username: e.target.value })}
                      defaultValue={(selectedNode?.data as any)?._cred_username || ''} />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Password</label>
                    <input type="password" placeholder="password" className="text-xs font-mono px-2 py-1.5 rounded border focus:outline-none focus:border-[#e09f3e]"
                      style={{ backgroundColor: '#0a0f13', borderColor: '#3d3528', color: '#e8e0d4' }}
                      onChange={(e) => onNodeUpdate(selectedNode!.id, { _cred_password: e.target.value })}
                      defaultValue={(selectedNode?.data as any)?._cred_password || ''} />
                  </div>
                </>
              )}
              {vendor === 'snmp' && (
                <>
                  <div className="flex flex-col gap-1">
                    <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Community String</label>
                    <input type="password" placeholder="public" className="text-xs font-mono px-2 py-1.5 rounded border focus:outline-none focus:border-[#e09f3e]"
                      style={{ backgroundColor: '#0a0f13', borderColor: '#3d3528', color: '#e8e0d4' }}
                      onChange={(e) => onNodeUpdate(selectedNode!.id, { _cred_community: e.target.value })}
                      defaultValue={(selectedNode?.data as any)?._cred_community || ''} />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>SNMP Version</label>
                    <select className="text-xs font-mono px-2 py-1.5 rounded border focus:outline-none focus:border-[#e09f3e]"
                      style={{ backgroundColor: '#0a0f13', borderColor: '#3d3528', color: '#e8e0d4' }}
                      onChange={(e) => onNodeUpdate(selectedNode!.id, { _cred_snmp_version: e.target.value })}
                      defaultValue={(selectedNode?.data as any)?._cred_snmp_version || 'v2c'}>
                      <option value="v2c">v2c</option>
                      <option value="v3">v3</option>
                    </select>
                  </div>
                </>
              )}
              <button
                onClick={async () => {
                  if (!ip || !vendor) return;
                  try {
                    const resp = await fetch('http://localhost:8000/api/v4/network/adapters/test', {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({
                        vendor,
                        api_endpoint: (selectedNode?.data as any)?._cred_api_endpoint || '',
                        api_key: (selectedNode?.data as any)?._cred_api_key || '',
                      }),
                    });
                    if (resp.ok) {
                      alert('Connection successful!');
                    } else {
                      const err = await resp.json().catch(() => ({}));
                      alert(`Connection failed: ${err.detail || resp.statusText}`);
                    }
                  } catch (e: any) {
                    alert(`Connection failed: ${e.message}`);
                  }
                }}
                className="mt-1 text-xs font-mono font-semibold px-3 py-1.5 rounded transition-colors"
                style={{ backgroundColor: 'rgba(224,159,62,0.12)', color: '#e09f3e', border: '1px solid rgba(224,159,62,0.2)' }}
              >
                Test Connection
              </button>
            </div>
          </details>
        )}
      </div>
    </div>
  );
};

export default DevicePropertyPanel;
