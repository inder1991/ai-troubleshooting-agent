import React, { useState } from 'react';
import { addDiscoveryConfig } from '../../services/api';

interface DiscoveryConfigFormProps {
  onSuccess: () => void;
  onCancel: () => void;
}

const DiscoveryConfigForm: React.FC<DiscoveryConfigFormProps> = ({ onSuccess, onCancel }) => {
  const [cidr, setCidr] = useState('');
  const [snmpVersion, setSnmpVersion] = useState<'2c' | '3'>('2c');
  const [community, setCommunity] = useState('public');
  const [port, setPort] = useState(161);
  const [interval, setInterval] = useState(300);
  const [excludedIps, setExcludedIps] = useState('');
  const [tags, setTags] = useState('');
  const [v3User, setV3User] = useState('');
  const [v3AuthProto, setV3AuthProto] = useState('SHA');
  const [v3AuthKey, setV3AuthKey] = useState('');
  const [v3PrivProto, setV3PrivProto] = useState('AES');
  const [v3PrivKey, setV3PrivKey] = useState('');
  const [pingEnabled, setPingEnabled] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!cidr.trim()) { setError('CIDR is required'); return; }
    setSubmitting(true);
    setError('');
    try {
      await addDiscoveryConfig({
        cidr: cidr.trim(),
        snmp_version: snmpVersion,
        community: snmpVersion === '2c' ? community : undefined,
        port,
        interval_seconds: interval,
        excluded_ips: excludedIps.split(',').map(s => s.trim()).filter(Boolean),
        tags: tags.split(',').map(t => t.trim()).filter(Boolean),
        v3_user: snmpVersion === '3' ? v3User : undefined,
        v3_auth_protocol: snmpVersion === '3' ? v3AuthProto : undefined,
        v3_auth_key: snmpVersion === '3' ? v3AuthKey : undefined,
        v3_priv_protocol: snmpVersion === '3' ? v3PrivProto : undefined,
        v3_priv_key: snmpVersion === '3' ? v3PrivKey : undefined,
        ping: { enabled: pingEnabled },
      });
      onSuccess();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to add discovery config');
    } finally {
      setSubmitting(false);
    }
  };

  const inputStyle: React.CSSProperties = {
    width: '100%', padding: '8px 12px', background: 'rgba(224,159,62,0.06)',
    border: '1px solid rgba(224,159,62,0.2)', borderRadius: 6, color: '#e8e0d4',
    fontSize: 13, outline: 'none',
  };
  const labelStyle: React.CSSProperties = {
    display: 'block', fontSize: 12, color: '#8a7e6b', marginBottom: 4, fontWeight: 500,
  };

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
        <div>
          <label style={labelStyle}>CIDR Range *</label>
          <input style={inputStyle} value={cidr} onChange={e => setCidr(e.target.value)} placeholder="10.0.0.0/24" />
        </div>
        <div>
          <label style={labelStyle}>SNMP Version</label>
          <select style={{ ...inputStyle, cursor: 'pointer' }} value={snmpVersion} onChange={e => setSnmpVersion(e.target.value as '2c' | '3')}>
            <option value="2c">v2c</option>
            <option value="3">v3</option>
          </select>
        </div>
        <div>
          <label style={labelStyle}>Scan Interval (seconds)</label>
          <input style={inputStyle} type="number" value={interval} onChange={e => setInterval(Number(e.target.value))} min={60} />
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        {snmpVersion === '2c' && (
          <div>
            <label style={labelStyle}>Community String</label>
            <input style={inputStyle} value={community} onChange={e => setCommunity(e.target.value)} />
          </div>
        )}
        <div>
          <label style={labelStyle}>Port</label>
          <input style={inputStyle} type="number" value={port} onChange={e => setPort(Number(e.target.value))} />
        </div>
      </div>

      {snmpVersion === '3' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div>
            <label style={labelStyle}>v3 Username</label>
            <input style={inputStyle} value={v3User} onChange={e => setV3User(e.target.value)} />
          </div>
          <div>
            <label style={labelStyle}>Auth Protocol</label>
            <select style={{ ...inputStyle, cursor: 'pointer' }} value={v3AuthProto} onChange={e => setV3AuthProto(e.target.value)}>
              <option value="SHA">SHA</option>
              <option value="MD5">MD5</option>
            </select>
          </div>
          <div>
            <label style={labelStyle}>Auth Key</label>
            <input style={inputStyle} type="password" value={v3AuthKey} onChange={e => setV3AuthKey(e.target.value)} />
          </div>
          <div>
            <label style={labelStyle}>Privacy Protocol</label>
            <select style={{ ...inputStyle, cursor: 'pointer' }} value={v3PrivProto} onChange={e => setV3PrivProto(e.target.value)}>
              <option value="AES">AES</option>
              <option value="DES">DES</option>
            </select>
          </div>
          <div>
            <label style={labelStyle}>Privacy Key</label>
            <input style={inputStyle} type="password" value={v3PrivKey} onChange={e => setV3PrivKey(e.target.value)} />
          </div>
        </div>
      )}

      <div>
        <label style={labelStyle}>Excluded IPs (comma-separated)</label>
        <input style={inputStyle} value={excludedIps} onChange={e => setExcludedIps(e.target.value)} placeholder="10.0.0.1, 10.0.0.254" />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 12, alignItems: 'end' }}>
        <div>
          <label style={labelStyle}>Tags (comma-separated)</label>
          <input style={inputStyle} value={tags} onChange={e => setTags(e.target.value)} placeholder="site:dc1, env:prod" />
        </div>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#8a7e6b', cursor: 'pointer', paddingBottom: 8 }}>
          <input type="checkbox" checked={pingEnabled} onChange={e => setPingEnabled(e.target.checked)} />
          Ping enabled
        </label>
      </div>

      {error && <div style={{ color: '#ef4444', fontSize: 13 }}>{error}</div>}

      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button type="button" onClick={onCancel} style={{
          padding: '8px 16px', background: 'transparent', border: '1px solid rgba(148,163,184,0.3)',
          borderRadius: 6, color: '#8a7e6b', cursor: 'pointer', fontSize: 13,
        }}>Cancel</button>
        <button type="submit" disabled={submitting} style={{
          padding: '8px 16px', background: '#e09f3e', border: 'none',
          borderRadius: 6, color: '#1a1814', cursor: 'pointer', fontSize: 13, fontWeight: 600,
          opacity: submitting ? 0.6 : 1,
        }}>{submitting ? 'Adding...' : 'Add Network'}</button>
      </div>
    </form>
  );
};

export default DiscoveryConfigForm;
