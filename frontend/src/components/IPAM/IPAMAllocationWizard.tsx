import React, { useState, useEffect } from 'react';
import { fetchAvailableRanges, createSubnet } from '../../services/api';

interface AvailableRange {
  cidr: string;
  start_ip: string;
  end_ip: string;
  host_count: number;
}

interface Props {
  parentSubnetId: string;
  parentCidr: string;
  onClose: () => void;
  onCreated: () => void;
}

export default function IPAMAllocationWizard({ parentSubnetId, parentCidr, onClose, onCreated }: Props) {
  const [ranges, setRanges] = useState<AvailableRange[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedRange, setSelectedRange] = useState<string>('');
  const [_newPrefix, _setNewPrefix] = useState(24);
  const [description, setDescription] = useState('');
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    setLoading(true);
    fetchAvailableRanges(parentSubnetId)
      .then(data => setRanges(data.available_ranges || []))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [parentSubnetId]);

  const handleCreate = async () => {
    if (!selectedRange) return;
    setCreating(true);
    try {
      await createSubnet({
        cidr: selectedRange,
        parent_subnet_id: parentSubnetId,
        description,
      });
      onCreated();
    } catch (err) {
      console.error('Failed to create subnet:', err);
    } finally {
      setCreating(false);
    }
  };

  const totalSpace = ranges.reduce((sum, r) => sum + r.host_count, 0);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[#252118] border border-amber-900/50 rounded-xl p-6 w-[600px] max-h-[80vh] overflow-auto shadow-xl">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-semibold text-white">Subnet Allocation Wizard</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-white text-xl">&times;</button>
        </div>
        <p className="text-sm text-gray-400 mb-4">
          Parent: <span className="text-amber-400 font-mono">{parentCidr}</span>
          {' \u2022 '}{totalSpace.toLocaleString()} addresses available
        </p>

        {loading ? (
          <div className="text-gray-400 text-center py-8">Scanning available ranges...</div>
        ) : ranges.length === 0 ? (
          <div className="text-yellow-400 text-center py-8">No available space in this subnet</div>
        ) : (
          <>
            {/* Visual bar */}
            <div className="mb-4">
              <div className="text-xs text-gray-500 mb-1">Address Space</div>
              <div className="h-6 bg-gray-800 rounded-lg overflow-hidden flex">
                {ranges.map((r, i) => (
                  <div
                    key={i}
                    className={`h-full cursor-pointer transition-colors ${
                      selectedRange === r.cidr ? 'bg-amber-500' : 'bg-emerald-800 hover:bg-emerald-700'
                    }`}
                    style={{ width: `${Math.max((r.host_count / totalSpace) * 100, 2)}%` }}
                    onClick={() => setSelectedRange(r.cidr)}
                    title={`${r.cidr} (${r.host_count} addresses)`}
                  />
                ))}
              </div>
              <div className="flex justify-between text-body-xs text-gray-600 mt-1">
                <span>Available ranges (click to select)</span>
                <span>{ranges.length} range{ranges.length !== 1 ? 's' : ''}</span>
              </div>
            </div>

            {/* Range list */}
            <div className="space-y-1 mb-4 max-h-40 overflow-auto">
              {ranges.map((r, i) => (
                <div
                  key={i}
                  className={`flex items-center justify-between px-3 py-2 rounded-lg cursor-pointer transition-colors ${
                    selectedRange === r.cidr
                      ? 'bg-amber-900/40 border border-amber-500/50'
                      : 'bg-gray-800/50 hover:bg-gray-800 border border-transparent'
                  }`}
                  onClick={() => setSelectedRange(r.cidr)}
                >
                  <span className="font-mono text-sm text-gray-200">{r.cidr}</span>
                  <span className="text-xs text-gray-500">{r.host_count.toLocaleString()} hosts</span>
                </div>
              ))}
            </div>

            {selectedRange && (
              <div className="border-t border-gray-700 pt-4 space-y-3">
                <div>
                  <label className="text-xs text-gray-400 block mb-1">Selected CIDR</label>
                  <input
                    type="text"
                    value={selectedRange}
                    onChange={e => setSelectedRange(e.target.value)}
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white font-mono"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-400 block mb-1">Description</label>
                  <input
                    type="text"
                    value={description}
                    onChange={e => setDescription(e.target.value)}
                    placeholder="e.g., Production web servers"
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white"
                  />
                </div>
                <button
                  onClick={handleCreate}
                  disabled={creating}
                  className="w-full py-2 rounded-lg bg-amber-600 hover:bg-amber-500 text-white font-medium text-sm transition disabled:opacity-50"
                >
                  {creating ? 'Creating...' : 'Create Subnet'}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
