import React, { useState, useEffect } from 'react';
import type { ClusterDiagnosticsForm } from '../../../types';
import type { ClusterProfile } from '../../../types/profiles';
import { listProfiles } from '../../../services/profileApi';
import { ClusterProfileSelector } from './ClusterProfileSelector';
import { t } from '../../../styles/tokens';

interface ClusterDiagnosticsFieldsProps {
  data: ClusterDiagnosticsForm;
  onChange: (data: ClusterDiagnosticsForm) => void;
}

const namespaces = ['default', 'kube-system', 'monitoring', 'production', 'staging'];
const resourceTypes = ['All Resources', 'Pods', 'Deployments', 'Services', 'StatefulSets', 'DaemonSets', 'Nodes'];

// Shared input style (inline, uses t. tokens)
const inputStyle: React.CSSProperties = {
  background: t.bgDeep,
  border: `1px solid ${t.borderDefault}`,
  borderRadius: 6,
  color: t.textPrimary,
  padding: '8px 10px',
  fontSize: 13,
  width: '100%',
  boxSizing: 'border-box',
};

const labelStyle: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  color: t.textSecondary,
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
};

const fieldStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 6,
};

const ClusterDiagnosticsFields: React.FC<ClusterDiagnosticsFieldsProps> = ({ data: formData, onChange }) => {
  const [profiles, setProfiles] = useState<ClusterProfile[]>([]);

  // selectedId: real profile id OR null (= temp cluster)
  // Start with the current profile_id from formData, or null if use_temp_cluster is set
  const [selectedId, setSelectedId] = useState<string | null>(
    formData.use_temp_cluster ? null : (formData.profile_id ?? (profiles.length > 0 ? profiles[0].id : null))
  );

  const [tempCluster, setTempCluster] = useState({
    cluster_url: '',
    auth_method: 'token' as 'token' | 'kubeconfig' | 'service_account',
    credential: '',
    role: '',
  });
  const [testResult, setTestResult] = useState<{ status: string; platform: string; version: string } | null>(null);
  const [testing, setTesting] = useState(false);
  const [elkIndex, setElkIndex] = useState(formData.elk_index ?? '');

  useEffect(() => {
    listProfiles()
      .then(loaded => {
        setProfiles(loaded);
        // If no profile_id set yet and not using temp cluster, auto-select first
        if (!formData.profile_id && !formData.use_temp_cluster && loaded.length > 0) {
          setSelectedId(loaded[0].id);
        }
      })
      .catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const update = (field: Partial<ClusterDiagnosticsForm>) => {
    onChange({ ...formData, ...field });
  };

  const handleProfileSelect = (profileId: string | null) => {
    setSelectedId(profileId);
    setTestResult(null);

    if (profileId !== null) {
      // Selected a real profile
      const profile = profiles.find(p => p.id === profileId);
      onChange({
        ...formData,
        profile_id: profileId,
        cluster_url: profile?.cluster_url ?? formData.cluster_url,
        auth_method: 'token',
        auth_token: undefined,
        use_temp_cluster: undefined,
        kubeconfig_content: undefined,
        role: undefined,
      });
    } else {
      // Selected "Use a different cluster"
      onChange({
        ...formData,
        profile_id: undefined,
        use_temp_cluster: true,
        auth_token: undefined,
        kubeconfig_content: undefined,
      });
    }
  };

  const handleTestConnection = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const resp = await fetch('/api/v5/profiles/test-connection', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cluster_url: tempCluster.cluster_url,
          auth_method: tempCluster.auth_method,
          credential: tempCluster.credential,
          verify_ssl: false,
        }),
      });
      const data = await resp.json();
      setTestResult(data);
      if (data.status === 'connected') {
        const updatedData: ClusterDiagnosticsForm = {
          ...formData,
          cluster_url: tempCluster.cluster_url,
          auth_method: tempCluster.auth_method,
          auth_token: tempCluster.auth_method === 'token' ? tempCluster.credential : undefined,
          kubeconfig_content: tempCluster.auth_method === 'kubeconfig' ? tempCluster.credential : undefined,
          role: tempCluster.role,
          use_temp_cluster: true,
          profile_id: undefined,
        };
        onChange(updatedData);
      }
    } catch {
      setTestResult({ status: 'unreachable', platform: '', version: '' });
    } finally {
      setTesting(false);
    }
  };

  const showTempPanel = formData.use_temp_cluster === true || selectedId === null;

  return (
    <div className="space-y-4">

      {/* Cluster Profile Selector */}
      <ClusterProfileSelector
        profiles={profiles}
        selectedId={selectedId}
        onSelect={handleProfileSelect}
        loading={false}
      />

      {/* Temporary cluster inline panel */}
      {showTempPanel && (
        <div style={{
          border: `1px solid ${t.borderDefault}`,
          borderRadius: 8,
          padding: 14,
          background: t.bgSurface,
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
        }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: t.textSecondary, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            One-time cluster credentials (not saved)
          </span>

          {/* Cluster API URL */}
          <div style={fieldStyle}>
            <label style={labelStyle}>
              Cluster API URL <span style={{ color: t.red }}>*</span>
            </label>
            <input
              type="text"
              value={tempCluster.cluster_url}
              onChange={e => setTempCluster(prev => ({ ...prev, cluster_url: e.target.value }))}
              placeholder="https://api.cluster.example.com:6443"
              style={inputStyle}
            />
          </div>

          {/* Auth Method */}
          <div style={fieldStyle}>
            <label style={labelStyle}>Auth Method</label>
            <div style={{ display: 'flex', gap: 6 }}>
              {(['token', 'kubeconfig', 'service_account'] as const).map(method => {
                const active = tempCluster.auth_method === method;
                return (
                  <button
                    key={method}
                    type="button"
                    onClick={() => setTempCluster(prev => ({ ...prev, auth_method: method, credential: '' }))}
                    style={{
                      flex: 1,
                      padding: '6px 8px',
                      borderRadius: 6,
                      border: `1px solid ${active ? t.cyanBorder : t.borderDefault}`,
                      background: active ? t.cyanBg : t.bgDeep,
                      color: active ? t.cyan : t.textSecondary,
                      fontSize: 11,
                      fontWeight: 600,
                      cursor: 'pointer',
                      transition: 'all 0.15s',
                    }}
                  >
                    {method === 'token' ? 'Token' : method === 'kubeconfig' ? 'Kubeconfig' : 'Service Acct'}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Credentials */}
          <div style={fieldStyle}>
            <label style={labelStyle}>
              {tempCluster.auth_method === 'token'
                ? 'Bearer Token'
                : tempCluster.auth_method === 'kubeconfig'
                ? 'Kubeconfig YAML'
                : 'Service Account Token'}
            </label>
            <textarea
              value={tempCluster.credential}
              onChange={e => setTempCluster(prev => ({ ...prev, credential: e.target.value }))}
              rows={3}
              placeholder={
                tempCluster.auth_method === 'token'
                  ? 'eyJhbGciOi...'
                  : tempCluster.auth_method === 'kubeconfig'
                  ? 'Paste kubeconfig YAML...'
                  : 'Paste service account token...'
              }
              style={{ ...inputStyle, fontFamily: 'monospace', resize: 'none' }}
            />
          </div>

          {/* Role */}
          <div style={fieldStyle}>
            <label style={labelStyle}>
              Role <span style={{ color: t.textMuted, fontWeight: 400 }}>(optional)</span>
            </label>
            <input
              type="text"
              value={tempCluster.role}
              onChange={e => setTempCluster(prev => ({ ...prev, role: e.target.value }))}
              placeholder="e.g. cluster-admin, view, edit"
              style={inputStyle}
            />
          </div>

          {/* Test Connection button */}
          <button
            type="button"
            onClick={handleTestConnection}
            disabled={testing || !tempCluster.cluster_url || !tempCluster.credential}
            style={{
              padding: '8px 14px',
              borderRadius: 6,
              border: `1px solid ${t.cyanBorder}`,
              background: t.cyanBg,
              color: t.cyan,
              fontSize: 12,
              fontWeight: 600,
              cursor: testing || !tempCluster.cluster_url || !tempCluster.credential ? 'not-allowed' : 'pointer',
              opacity: testing || !tempCluster.cluster_url || !tempCluster.credential ? 0.5 : 1,
              transition: 'all 0.15s',
              alignSelf: 'flex-start',
            }}
          >
            {testing ? 'Testing…' : 'Test Connection'}
          </button>

          {/* Test result status */}
          {testResult && (
            <div style={{
              fontSize: 12,
              fontWeight: 500,
              color: testResult.status === 'connected' ? t.green : t.red,
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}>
              {testResult.status === 'connected'
                ? `✓ Connected${testResult.platform ? ` to ${testResult.platform}` : ''}${testResult.version ? ` ${testResult.version}` : ''}`
                : `✗ ${testResult.status === 'unreachable' ? 'Unreachable — check URL and credentials' : testResult.status}`}
            </div>
          )}
        </div>
      )}

      {/* Target Namespace */}
      <div style={fieldStyle}>
        <label style={labelStyle}>Target Namespace</label>
        <select
          value={formData.namespace || ''}
          onChange={e => update({ namespace: e.target.value || undefined })}
          style={inputStyle}
        >
          <option value="">All Namespaces</option>
          {namespaces.map(ns => (
            <option key={ns} value={ns}>{ns}</option>
          ))}
        </select>
      </div>

      {/* ELK Log Index (optional) */}
      <div style={fieldStyle}>
        <label style={labelStyle}>
          ELK Log Index <span style={{ color: t.textMuted, fontWeight: 400 }}>(optional)</span>
        </label>
        <input
          type="text"
          value={elkIndex}
          onChange={e => {
            setElkIndex(e.target.value);
            onChange({ ...formData, elk_index: e.target.value || undefined });
          }}
          placeholder="e.g. cluster-logs-* or leave blank to skip log analysis"
          style={inputStyle}
        />
      </div>

      {/* Resource Type */}
      <div style={fieldStyle}>
        <label style={labelStyle}>Resource Type</label>
        <select
          value={formData.resource_type || ''}
          onChange={e => update({ resource_type: e.target.value || undefined, workload: undefined })}
          style={inputStyle}
        >
          <option value="">All Resources</option>
          {resourceTypes.filter(r => r !== 'All Resources').map(rt => (
            <option key={rt} value={rt.toLowerCase()}>{rt}</option>
          ))}
        </select>
      </div>

      {/* Workload Name — visible when a specific resource type is selected */}
      {formData.resource_type && (
        <div style={fieldStyle}>
          <label style={labelStyle}>Workload Name</label>
          <input
            type="text"
            value={formData.workload || ''}
            onChange={e => update({ workload: e.target.value || undefined })}
            placeholder={`e.g. my-${formData.resource_type === 'pods' ? 'pod' : 'app'}-name`}
            style={inputStyle}
          />
        </div>
      )}

      {/* Include Control Plane */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <input
          type="checkbox"
          id="include_control_plane"
          checked={formData.include_control_plane ?? true}
          onChange={e => update({ include_control_plane: e.target.checked })}
          style={{ width: 14, height: 14, accentColor: t.cyan, cursor: 'pointer' }}
        />
        <label htmlFor="include_control_plane" style={{ fontSize: 12, color: t.textSecondary, cursor: 'pointer' }}>
          Include control plane diagnostics
        </label>
      </div>

      {/* Symptoms */}
      <div style={fieldStyle}>
        <label style={labelStyle}>Symptoms Description</label>
        <textarea
          value={formData.symptoms || ''}
          onChange={e => update({ symptoms: e.target.value || undefined })}
          rows={2}
          placeholder="Describe the observed symptoms..."
          style={{ ...inputStyle, resize: 'none' }}
        />
      </div>

      {/* Validation warning: temp cluster not tested */}
      {formData.use_temp_cluster && testResult?.status !== 'connected' && (
        <div style={{
          fontSize: 11,
          color: t.amber,
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '6px 10px',
          borderRadius: 6,
          border: `1px solid ${t.amberBorder}`,
          background: t.amberBg,
        }}>
          ⚠ Test the connection before starting diagnostics
        </div>
      )}
    </div>
  );
};

export default ClusterDiagnosticsFields;
