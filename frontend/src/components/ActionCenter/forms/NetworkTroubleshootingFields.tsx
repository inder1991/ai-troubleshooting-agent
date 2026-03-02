import React from 'react';
import { NetworkTroubleshootingForm } from '../../../types';

interface NetworkTroubleshootingFieldsProps {
  data: NetworkTroubleshootingForm;
  onChange: (data: NetworkTroubleshootingForm) => void;
}

const NetworkTroubleshootingFields: React.FC<NetworkTroubleshootingFieldsProps> = ({ data, onChange }) => {
  const update = (field: Partial<NetworkTroubleshootingForm>) => {
    onChange({ ...data, ...field });
  };

  // Shared input styling (match existing forms)
  const inputClasses = "w-full rounded-lg border px-3 py-2 text-sm font-mono focus:outline-none focus:ring-1";
  const inputStyle = {
    backgroundColor: '#0f2023',
    borderColor: '#224349',
    color: '#e2e8f0',
  };
  const labelClasses = "text-xs font-mono uppercase tracking-widest mb-1.5 block";
  const labelStyle = { color: '#64748b' };

  return (
    <div className="space-y-4">
      {/* Source IP */}
      <div>
        <label className={labelClasses} style={labelStyle}>Source IP</label>
        <input
          type="text"
          placeholder="e.g. 10.0.1.50"
          value={data.src_ip}
          onChange={(e) => update({ src_ip: e.target.value })}
          className={inputClasses}
          style={inputStyle}
        />
      </div>

      {/* Destination IP */}
      <div>
        <label className={labelClasses} style={labelStyle}>Destination IP</label>
        <input
          type="text"
          placeholder="e.g. 10.2.0.100"
          value={data.dst_ip}
          onChange={(e) => update({ dst_ip: e.target.value })}
          className={inputClasses}
          style={inputStyle}
        />
      </div>

      {/* Port */}
      <div>
        <label className={labelClasses} style={labelStyle}>Port</label>
        <input
          type="text"
          placeholder="e.g. 443"
          value={data.port}
          onChange={(e) => update({ port: e.target.value })}
          className={inputClasses}
          style={inputStyle}
        />
      </div>

      {/* Protocol Toggle */}
      <div>
        <label className={labelClasses} style={labelStyle}>Protocol</label>
        <div className="flex gap-2">
          {(['tcp', 'udp'] as const).map((proto) => (
            <button
              key={proto}
              type="button"
              onClick={() => update({ protocol: proto })}
              className="px-4 py-2 rounded-lg text-xs font-mono uppercase tracking-wider transition-colors"
              style={{
                backgroundColor: data.protocol === proto ? '#07b6d5' : '#0f2023',
                color: data.protocol === proto ? '#0f2023' : '#64748b',
                borderWidth: 1,
                borderColor: data.protocol === proto ? '#07b6d5' : '#224349',
              }}
            >
              {proto}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};

export default NetworkTroubleshootingFields;
