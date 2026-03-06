/**
 * Network validation utilities — shared across canvas, forms, and dialogs.
 * Backend is authoritative; these are for instant UX feedback.
 */

export interface ValidationError {
  field: string;
  message: string;
  severity: 'error' | 'warning' | 'suggestion';
  nodeId?: string;
}

/** Validate an IPv4 address. Returns error message or null. */
export function validateIPv4(ip: string): string | null {
  if (!ip) return null; // empty is allowed (optional field)
  const parts = ip.split('.');
  if (parts.length !== 4) return `'${ip}' is not a valid IPv4 address`;
  for (const part of parts) {
    const num = Number(part);
    if (!Number.isInteger(num) || num < 0 || num > 255 || part !== String(num)) {
      return `'${ip}' is not a valid IPv4 address`;
    }
  }
  return null;
}

/** Validate a CIDR block (e.g. 10.0.0.0/24). Returns error message or null. */
export function validateCIDR(cidr: string): string | null {
  if (!cidr) return null;
  const parts = cidr.split('/');
  if (parts.length !== 2) return `'${cidr}' is not valid CIDR notation`;
  const ipErr = validateIPv4(parts[0]);
  if (ipErr) return `'${cidr}' has invalid IP portion`;
  const prefix = Number(parts[1]);
  if (!Number.isInteger(prefix) || prefix < 0 || prefix > 32) {
    return `'${cidr}' has invalid prefix length (must be 0-32)`;
  }
  return null;
}

/** Validate a port number. Returns error message or null. */
export function validatePort(port: string | number): string | null {
  const num = typeof port === 'string' ? Number(port) : port;
  if (isNaN(num) || !Number.isInteger(num)) return 'Port must be a whole number';
  if (num < 0 || num > 65535) return 'Port must be 0–65535';
  return null;
}

/** Validate a VLAN ID. Returns error message or null. 0 means "unset". */
export function validateVLAN(vlan: string | number): string | null {
  const num = typeof vlan === 'string' ? Number(vlan) : vlan;
  if (isNaN(num) || !Number.isInteger(num)) return 'VLAN must be a whole number';
  if (num === 0) return null; // unset
  if (num < 1 || num > 4094) return 'VLAN must be 1–4094';
  return null;
}

/** Parse an IPv4 address to a 32-bit integer for comparison. */
function ipToInt(ip: string): number {
  return ip.split('.').reduce((acc, octet) => (acc << 8) + Number(octet), 0) >>> 0;
}

/** Parse CIDR to { network: number, mask: number }. */
function parseCIDR(cidr: string): { network: number; mask: number; prefix: number } | null {
  const parts = cidr.split('/');
  if (parts.length !== 2) return null;
  const prefix = Number(parts[1]);
  if (isNaN(prefix) || prefix < 0 || prefix > 32) return null;
  const mask = prefix === 0 ? 0 : (~0 << (32 - prefix)) >>> 0;
  const network = ipToInt(parts[0]) & mask;
  return { network, mask, prefix };
}

/** Check if an IP address falls within a CIDR block. */
export function isIPInCIDR(ip: string, cidr: string): boolean {
  const parsed = parseCIDR(cidr);
  if (!parsed) return false;
  const ipNum = ipToInt(ip);
  return (ipNum & parsed.mask) === parsed.network;
}

/** Check if child CIDR is a subset of parent CIDR. */
export function isCIDRSubsetOf(child: string, parent: string): boolean {
  const c = parseCIDR(child);
  const p = parseCIDR(parent);
  if (!c || !p) return false;
  // Child prefix must be >= parent prefix (smaller or equal network)
  if (c.prefix < p.prefix) return false;
  // Child network masked by parent mask must equal parent network
  return (c.network & p.mask) === p.network;
}

/**
 * Detect overlapping CIDRs in a list. Returns pairs of overlapping CIDRs.
 * Two CIDRs overlap if either is a subset of the other.
 */
export function detectOverlappingCIDRs(cidrs: string[]): Array<[string, string]> {
  const overlaps: Array<[string, string]> = [];
  for (let i = 0; i < cidrs.length; i++) {
    for (let j = i + 1; j < cidrs.length; j++) {
      if (isCIDRSubsetOf(cidrs[i], cidrs[j]) || isCIDRSubsetOf(cidrs[j], cidrs[i])) {
        overlaps.push([cidrs[i], cidrs[j]]);
      }
    }
  }
  return overlaps;
}

/** Check if two CIDRs overlap (either direction). */
export function doCIDRsOverlap(a: string, b: string): boolean {
  return isCIDRSubsetOf(a, b) || isCIDRSubsetOf(b, a);
}

export interface InterfaceData {
  id: string;
  name: string;
  ip: string;
  role: string;
  zone: string;
  subnetId?: string;
}

interface CanvasNode {
  id: string;
  type?: string;
  position: { x: number; y: number };
  style?: { width?: number; height?: number };
  data: Record<string, unknown>;
}

/** Check if nodeA's position is inside containerB's bounds. */
function isNodeInsideContainer(nodeA: CanvasNode, containerB: CanvasNode): boolean {
  const cw = (containerB.style?.width as number) || 300;
  const ch = (containerB.style?.height as number) || 200;
  return (
    nodeA.position.x >= containerB.position.x &&
    nodeA.position.x <= containerB.position.x + cw &&
    nodeA.position.y >= containerB.position.y &&
    nodeA.position.y <= containerB.position.y + ch
  );
}

/** Validate all topology relationships before save/promote. */
export function validateTopology(nodes: CanvasNode[]): ValidationError[] {
  const errors: ValidationError[] = [];
  const containers = nodes.filter(
    (n) => n.type === 'vpc' || n.type === 'subnet' || n.type === 'compliance_zone'
      || n.type === 'availability_zone' || n.type === 'auto_scaling_group' || n.type === 'ha_group'
  );
  const devices = nodes.filter((n) => n.type === 'device');

  // Collect all device IPs for duplicate detection
  const ipToNodes: Map<string, string[]> = new Map();
  for (const dev of devices) {
    const ip = (dev.data.ip as string) || '';
    if (ip) {
      const existing = ipToNodes.get(ip) || [];
      existing.push(dev.id);
      ipToNodes.set(ip, existing);
    }
  }

  // Rule 10: Duplicate IPs
  for (const [ip, nodeIds] of ipToNodes) {
    if (nodeIds.length > 1) {
      const names = nodeIds.map((id) => {
        const n = nodes.find((nd) => nd.id === id);
        return (n?.data.label as string) || id;
      });
      for (const nodeId of nodeIds) {
        errors.push({
          field: 'ip',
          message: `Duplicate IP '${ip}' shared by: ${names.join(', ')}`,
          severity: 'error',
          nodeId,
        });
      }
    }
  }

  // Rule 6: Device IP must be within parent container CIDR
  for (const dev of devices) {
    const devIp = (dev.data.ip as string) || '';
    const parentId = (dev.data.parentContainerId as string) || '';
    if (!devIp || !parentId) continue;

    const parent = containers.find((c) => c.id === parentId);
    if (!parent) continue;

    const parentCidr = (parent.data.cidr as string) || '';
    if (!parentCidr) continue;

    if (validateIPv4(devIp) || validateCIDR(parentCidr)) continue; // skip if formats are bad

    if (!isIPInCIDR(devIp, parentCidr)) {
      errors.push({
        field: 'ip',
        message: `'${dev.data.label || dev.id}' IP ${devIp} is outside ${parent.data.label || parent.id} CIDR ${parentCidr}`,
        severity: 'error',
        nodeId: dev.id,
      });
    }
  }

  // Rule 9: Overlapping subnet CIDRs
  const subnetNodes = containers.filter((c) => c.type === 'subnet');
  const subnetCidrs = subnetNodes.map((s) => ({
    id: s.id,
    label: (s.data.label as string) || s.id,
    cidr: (s.data.cidr as string) || '',
  })).filter((s) => s.cidr && !validateCIDR(s.cidr));

  for (let i = 0; i < subnetCidrs.length; i++) {
    for (let j = i + 1; j < subnetCidrs.length; j++) {
      if (doCIDRsOverlap(subnetCidrs[i].cidr, subnetCidrs[j].cidr)) {
        errors.push({
          field: 'cidr',
          message: `Overlapping subnets: '${subnetCidrs[i].label}' (${subnetCidrs[i].cidr}) and '${subnetCidrs[j].label}' (${subnetCidrs[j].cidr})`,
          severity: 'warning',
          nodeId: subnetCidrs[i].id,
        });
      }
    }
  }

  // Rule 7: Subnet CIDR must be inside parent VPC CIDR
  for (const subnet of subnetNodes) {
    const subCidr = (subnet.data.cidr as string) || '';
    if (!subCidr || validateCIDR(subCidr)) continue;

    const parentVpc = containers.find(
      (c) => c.type === 'vpc' && isNodeInsideContainer(subnet, c)
    );
    if (!parentVpc) continue;

    const vpcCidr = (parentVpc.data.cidr as string) || '';
    if (!vpcCidr || validateCIDR(vpcCidr)) continue;

    if (!isCIDRSubsetOf(subCidr, vpcCidr)) {
      errors.push({
        field: 'cidr',
        message: `Subnet '${subnet.data.label || subnet.id}' CIDR ${subCidr} is not within VPC '${parentVpc.data.label || parentVpc.id}' CIDR ${vpcCidr}`,
        severity: 'error',
        nodeId: subnet.id,
      });
    }
  }

  // Rule 29: Interface IP must be within assigned subnet CIDR
  for (const dev of devices) {
    const ifaces = (dev.data.interfaces as InterfaceData[]) || [];
    for (const iface of ifaces) {
      if (!iface.ip || !iface.subnetId) continue;
      const ipErr = validateIPv4(iface.ip);
      if (ipErr) continue;
      const subnetNode = containers.find((c) => c.id === iface.subnetId);
      if (!subnetNode) continue;
      const subCidr = (subnetNode.data.cidr as string) || '';
      if (!subCidr || validateCIDR(subCidr)) continue;
      if (!isIPInCIDR(iface.ip, subCidr)) {
        errors.push({
          field: 'interface.ip',
          message: `Interface '${iface.name}' IP ${iface.ip} is outside subnet CIDR ${subCidr}`,
          severity: 'error',
          nodeId: dev.id,
        });
      }
    }
  }

  // Rule 30: No two non-sync interfaces on same device may share a zone
  for (const dev of devices) {
    const ifaces = (dev.data.interfaces as InterfaceData[]) || [];
    const zoneMap = new Map<string, string[]>();
    for (const iface of ifaces) {
      if (!iface.zone || iface.role === 'sync') continue;
      const existing = zoneMap.get(iface.zone) || [];
      existing.push(iface.name || iface.id);
      zoneMap.set(iface.zone, existing);
    }
    for (const [zone, names] of zoneMap) {
      if (names.length > 1) {
        errors.push({
          field: 'interface.zone',
          message: `Interfaces ${names.join(', ')} on '${dev.data.label || dev.id}' share zone '${zone}'`,
          severity: 'error',
          nodeId: dev.id,
        });
      }
    }
  }

  // Rule: AZ should be inside a VPC
  const azNodes = nodes.filter((n) => n.type === 'availability_zone');
  for (const az of azNodes) {
    const parentVpc = containers.find(
      (c) => c.type === 'vpc' && isNodeInsideContainer(az, c)
    );
    if (!parentVpc) {
      errors.push({
        field: 'placement',
        message: `Availability Zone '${az.data.label || az.id}' should be placed inside a VPC`,
        severity: 'warning',
        nodeId: az.id,
      });
    }
  }

  // Rule: ASG capacity: min <= desired <= max
  const asgNodes = nodes.filter((n) => n.type === 'auto_scaling_group');
  for (const asg of asgNodes) {
    const min = Number(asg.data.minCapacity) || 0;
    const desired = Number(asg.data.desiredCapacity) || 0;
    const max = Number(asg.data.maxCapacity) || 0;
    if (min > desired || desired > max) {
      errors.push({
        field: 'capacity',
        message: `ASG '${asg.data.label || asg.id}' capacity invalid: min(${min}) <= desired(${desired}) <= max(${max}) must hold`,
        severity: 'error',
        nodeId: asg.id,
      });
    }
  }

  // Rule 7 extended: Subnet CIDR must be inside parent VPC (allow AZ intermediary)
  for (const subnet of subnetNodes) {
    const subCidr = (subnet.data.cidr as string) || '';
    if (!subCidr || validateCIDR(subCidr)) continue;

    // Check if subnet is inside an AZ which is inside a VPC
    const parentAz = containers.find(
      (c) => c.type === 'availability_zone' && isNodeInsideContainer(subnet, c)
    );
    if (parentAz) {
      const grandparentVpc = containers.find(
        (c) => c.type === 'vpc' && isNodeInsideContainer(parentAz, c)
      );
      if (grandparentVpc) {
        const vpcCidr = (grandparentVpc.data.cidr as string) || '';
        if (vpcCidr && !validateCIDR(vpcCidr) && !isCIDRSubsetOf(subCidr, vpcCidr)) {
          errors.push({
            field: 'cidr',
            message: `Subnet '${subnet.data.label || subnet.id}' CIDR ${subCidr} is not within VPC '${grandparentVpc.data.label || grandparentVpc.id}' CIDR ${vpcCidr}`,
            severity: 'error',
            nodeId: subnet.id,
          });
        }
      }
    }
  }

  // Rule 31: Management interface should not be in data/dmz zone
  for (const dev of devices) {
    const ifaces = (dev.data.interfaces as InterfaceData[]) || [];
    for (const iface of ifaces) {
      if (iface.role !== 'management' || !iface.zone) continue;
      const zoneNode = nodes.find(
        (n) => (n.data.entityId === iface.zone || n.id === iface.zone)
              && (n.data.zoneType === 'data' || n.data.zoneType === 'dmz')
      );
      if (zoneNode) {
        errors.push({
          field: 'interface.role',
          message: `Management interface '${iface.name}' is in ${zoneNode.data.zoneType} zone '${zoneNode.data.label || iface.zone}'`,
          severity: 'warning',
          nodeId: dev.id,
        });
      }
    }
  }

  return errors;
}
