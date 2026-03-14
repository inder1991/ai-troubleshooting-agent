import React, { useMemo } from 'react';
import { NetworkTroubleshootingForm } from '../../../types';
import { validateIPv4, validatePort } from '../../../utils/networkValidation';

interface NetworkTroubleshootingFieldsProps {
  data: NetworkTroubleshootingForm;
  onChange: (data: NetworkTroubleshootingForm) => void;
}

const NetworkTroubleshootingFields: React.FC<NetworkTroubleshootingFieldsProps> = ({ data, onChange }) => {
  const update = (field: Partial<NetworkTroubleshootingForm>) => {
    onChange({ ...data, ...field });
  };

  const errors = useMemo(() => ({
    src_ip: data.src_ip ? validateIPv4(data.src_ip) : null,
    dst_ip: data.dst_ip ? validateIPv4(data.dst_ip) : null,
    port: data.port ? validatePort(data.port) : null,
  }), [data.src_ip, data.dst_ip, data.port]);

  const inputClasses = "w-full rounded-lg border px-3 py-2 text-sm font-mono focus:outline-none focus:ring-1";
  const inputStyle = (hasError: boolean) => ({
    backgroundColor: '#1a1814',
    borderColor: hasError ? '#ef4444' : '#3d3528',
    color: '#e8e0d4',
  });
  const labelClasses = "text-xs font-mono uppercase tracking-widest mb-1.5 block";
  const labelStyle = { color: '#64748b' };
  const errorStyle = { color: '#ef4444', fontSize: '10px', marginTop: '4px' };

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
          style={inputStyle(!!errors.src_ip)}
        />
        {errors.src_ip && <p className="font-mono" style={errorStyle}>{errors.src_ip}</p>}
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
          style={inputStyle(!!errors.dst_ip)}
        />
        {errors.dst_ip && <p className="font-mono" style={errorStyle}>{errors.dst_ip}</p>}
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
          style={inputStyle(!!errors.port)}
        />
        {errors.port && <p className="font-mono" style={errorStyle}>{errors.port}</p>}
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
                backgroundColor: data.protocol === proto ? '#e09f3e' : '#1a1814',
                color: data.protocol === proto ? '#1a1814' : '#64748b',
                borderWidth: 1,
                borderColor: data.protocol === proto ? '#e09f3e' : '#3d3528',
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
