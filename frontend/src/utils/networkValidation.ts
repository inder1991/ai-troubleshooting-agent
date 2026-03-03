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
