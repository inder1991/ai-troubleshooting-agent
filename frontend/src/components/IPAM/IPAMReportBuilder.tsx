import React, { useState } from 'react';
import { fetchIPAMReport } from '../../services/api';

const REPORT_TYPES = [
  { id: 'subnet_inventory', name: 'Subnet Inventory', description: 'All subnets with utilization metrics' },
  { id: 'ip_allocation', name: 'IP Allocation', description: 'IP addresses by device, status, and subnet' },
  { id: 'conflict_report', name: 'Conflict Report', description: 'Duplicate IPs and DNS mismatches' },
  { id: 'capacity_forecast', name: 'Capacity Forecast', description: 'Subnet utilization trends and risk levels' },
];

export default function IPAMReportBuilder() {
  const [selectedType, setSelectedType] = useState('subnet_inventory');
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const handleGenerate = async () => {
    setLoading(true);
    try {
      const result = await fetchIPAMReport(selectedType);
      setData(result);
    } catch (err) {
      console.error('Report generation failed:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleExportCSV = async () => {
    try {
      const csvText = await fetchIPAMReport(selectedType, 'csv');
      const blob = new Blob([csvText as string], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `ipam_${selectedType}_${new Date().toISOString().split('T')[0]}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('CSV export failed:', err);
    }
  };

  const reportData = data?.data || [];
  const columns = reportData.length > 0 ? Object.keys(reportData[0]) : [];

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-semibold text-white">Report Builder</h3>
        <div className="flex gap-2">
          {data && (
            <button onClick={handleExportCSV}
              className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm transition">
              Export CSV
            </button>
          )}
        </div>
      </div>

      {/* Report type selector */}
      <div className="grid grid-cols-2 gap-2">
        {REPORT_TYPES.map(rt => (
          <div
            key={rt.id}
            className={`p-3 rounded-lg cursor-pointer transition border ${
              selectedType === rt.id
                ? 'bg-amber-900/30 border-amber-500/50'
                : 'bg-gray-800/50 border-gray-700 hover:bg-gray-800'
            }`}
            onClick={() => { setSelectedType(rt.id); setData(null); }}
          >
            <div className="text-sm font-medium text-white">{rt.name}</div>
            <div className="text-xs text-gray-400">{rt.description}</div>
          </div>
        ))}
      </div>

      <button
        onClick={handleGenerate}
        disabled={loading}
        className="px-4 py-2 rounded-lg bg-amber-600 hover:bg-amber-500 text-white text-sm transition disabled:opacity-50"
      >
        {loading ? 'Generating...' : 'Generate Report'}
      </button>

      {/* Results table */}
      {data && reportData.length > 0 && (
        <div className="overflow-auto max-h-[400px] rounded-lg border border-gray-700">
          <table className="w-full text-sm">
            <thead className="bg-gray-800 sticky top-0">
              <tr>
                {columns.map(col => (
                  <th key={col} className="px-3 py-2 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">{col}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {reportData.slice(0, 100).map((row: Record<string, unknown>, i: number) => (
                <tr key={i} className="hover:bg-gray-800/50">
                  {columns.map(col => (
                    <td key={col} className="px-3 py-2 text-gray-300 whitespace-nowrap">{String(row[col] ?? '')}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {reportData.length > 100 && (
            <div className="text-center text-xs text-gray-500 py-2">Showing 100 of {reportData.length} rows. Export CSV for full data.</div>
          )}
        </div>
      )}

      {data && reportData.length === 0 && (
        <div className="text-gray-500 text-center py-8">No data for this report</div>
      )}
    </div>
  );
}
