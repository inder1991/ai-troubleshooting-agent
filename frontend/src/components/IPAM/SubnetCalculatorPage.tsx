import React, { useState, useMemo } from 'react';
import { parseCIDR, ipToInt, intToIp, validateCIDR } from '../../utils/networkValidation';

export default function SubnetCalculatorPage() {
  const [cidr, setCidr] = useState('192.168.1.0/24');
  const [splitPrefix, setSplitPrefix] = useState(25);

  const info = useMemo(() => {
    const err = validateCIDR(cidr);
    if (err) return null;
    const parsed = parseCIDR(cidr);
    if (!parsed) return null;

    const network = parsed.network >>> 0;
    const broadcast = (network | (~parsed.mask >>> 0)) >>> 0;
    const totalHosts = parsed.prefix === 32 ? 1 : parsed.prefix === 31 ? 2 : (broadcast - network - 1);
    const wildcard = (~parsed.mask) >>> 0;

    const toBinary = (n: number) =>
      [(n >>> 24) & 255, (n >>> 16) & 255, (n >>> 8) & 255, n & 255]
        .map(o => o.toString(2).padStart(8, '0'))
        .join('.');

    return {
      network: intToIp(network),
      broadcast: intToIp(broadcast),
      mask: intToIp(parsed.mask),
      wildcard: intToIp(wildcard),
      prefix: parsed.prefix,
      totalAddresses: broadcast - network + 1,
      usableHosts: Math.max(0, totalHosts),
      firstHost: parsed.prefix >= 31 ? intToIp(network) : intToIp(network + 1),
      lastHost: parsed.prefix >= 31 ? intToIp(broadcast) : intToIp(broadcast - 1),
      networkBinary: toBinary(network),
      maskBinary: toBinary(parsed.mask),
    };
  }, [cidr]);

  const splitResults = useMemo(() => {
    if (!info || splitPrefix <= info.prefix || splitPrefix > 32) return [];
    const count = Math.pow(2, splitPrefix - info.prefix);
    const subnetSize = Math.pow(2, 32 - splitPrefix);
    const results = [];
    let baseAddr = ipToInt(info.network);
    for (let i = 0; i < count && i < 64; i++) {
      const net = baseAddr >>> 0;
      const bcast = (net + subnetSize - 1) >>> 0;
      results.push({
        cidr: `${intToIp(net)}/${splitPrefix}`,
        network: intToIp(net),
        broadcast: intToIp(bcast),
        hosts: splitPrefix >= 31 ? (splitPrefix === 32 ? 1 : 2) : subnetSize - 2,
      });
      baseAddr += subnetSize;
    }
    return results;
  }, [info, splitPrefix]);

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <h2 className="text-2xl font-bold text-white">Subnet Calculator</h2>

      <div className="flex gap-4 items-end">
        <div className="flex-1">
          <label className="text-xs text-gray-400 block mb-1">CIDR Notation</label>
          <input
            type="text"
            value={cidr}
            onChange={e => setCidr(e.target.value)}
            placeholder="e.g., 192.168.1.0/24"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-lg text-white font-mono focus:outline-none focus:border-amber-500"
          />
        </div>
      </div>

      {info && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {[
              { label: 'Network', value: info.network },
              { label: 'Broadcast', value: info.broadcast },
              { label: 'Subnet Mask', value: info.mask },
              { label: 'Wildcard', value: info.wildcard },
              { label: 'First Host', value: info.firstHost },
              { label: 'Last Host', value: info.lastHost },
              { label: 'Total Addresses', value: info.totalAddresses.toLocaleString() },
              { label: 'Usable Hosts', value: info.usableHosts.toLocaleString() },
            ].map(({ label, value }) => (
              <div key={label} className="bg-gray-800/60 rounded-lg p-3 border border-gray-700">
                <div className="text-xs text-gray-500">{label}</div>
                <div className="text-white font-mono text-sm mt-1">{value}</div>
              </div>
            ))}
          </div>

          <div className="bg-gray-800/60 rounded-lg p-4 border border-gray-700">
            <div className="text-xs text-gray-500 mb-2">Binary Representation</div>
            <div className="space-y-1">
              <div className="flex gap-2 items-center">
                <span className="text-gray-400 text-xs w-16">Network:</span>
                <span className="text-amber-400 font-mono text-xs">{info.networkBinary}</span>
              </div>
              <div className="flex gap-2 items-center">
                <span className="text-gray-400 text-xs w-16">Mask:</span>
                <span className="text-emerald-400 font-mono text-xs">{info.maskBinary}</span>
              </div>
            </div>
          </div>

          {/* Subnet Splitter */}
          <div className="border-t border-gray-700 pt-4">
            <h3 className="text-lg font-semibold text-white mb-3">Subnet Splitter</h3>
            <div className="flex gap-4 items-end mb-4">
              <div>
                <label className="text-xs text-gray-400 block mb-1">Split into /{splitPrefix} subnets</label>
                <input
                  type="number"
                  min={info.prefix + 1}
                  max={32}
                  value={splitPrefix}
                  onChange={e => setSplitPrefix(Number(e.target.value))}
                  className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white w-24"
                />
              </div>
              <div className="text-sm text-gray-400">
                = {Math.pow(2, splitPrefix - info.prefix)} subnets of {Math.pow(2, 32 - splitPrefix)} addresses each
              </div>
            </div>
            {splitResults.length > 0 && (
              <div className="overflow-auto max-h-64 rounded-lg border border-gray-700">
                <table className="w-full text-sm">
                  <thead className="bg-gray-800 sticky top-0">
                    <tr>
                      <th className="px-3 py-2 text-left text-xs text-gray-400">#</th>
                      <th className="px-3 py-2 text-left text-xs text-gray-400">CIDR</th>
                      <th className="px-3 py-2 text-left text-xs text-gray-400">Network</th>
                      <th className="px-3 py-2 text-left text-xs text-gray-400">Broadcast</th>
                      <th className="px-3 py-2 text-left text-xs text-gray-400">Hosts</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800">
                    {splitResults.map((r, i) => (
                      <tr key={i} className="hover:bg-gray-800/50">
                        <td className="px-3 py-1.5 text-gray-500">{i + 1}</td>
                        <td className="px-3 py-1.5 text-amber-400 font-mono">{r.cidr}</td>
                        <td className="px-3 py-1.5 text-gray-300 font-mono">{r.network}</td>
                        <td className="px-3 py-1.5 text-gray-300 font-mono">{r.broadcast}</td>
                        <td className="px-3 py-1.5 text-gray-300">{r.hosts}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}

      {!info && cidr && <div className="text-red-400 text-sm">Invalid CIDR notation. Use format like 192.168.1.0/24</div>}
    </div>
  );
}
