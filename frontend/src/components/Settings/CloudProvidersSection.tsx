import React, { useState, useCallback } from 'react';
import type { GlobalIntegration } from '../../types/profiles';

// ── Provider definitions ──

const CLOUD_PROVIDERS = ['aws', 'azure', 'gcp', 'oracle'] as const;
type CloudProvider = (typeof CLOUD_PROVIDERS)[number];

interface ProviderMeta {
  displayName: string;
  accent: string;
  accentBg: string;
  authMethod: string;
  icon: string;
}

const PROVIDER_META: Record<CloudProvider, ProviderMeta> = {
  aws: {
    displayName: 'Amazon Web Services',
    accent: '#ff9900',
    accentBg: 'bg-[#ff9900]/10',
    authMethod: 'iam_role',
    icon: 'aws',
  },
  azure: {
    displayName: 'Microsoft Azure',
    accent: '#0078d4',
    accentBg: 'bg-[#0078d4]/10',
    authMethod: 'azure_sp',
    icon: 'cloud',
  },
  gcp: {
    displayName: 'Google Cloud Platform',
    accent: '#4285f4',
    accentBg: 'bg-[#4285f4]/10',
    authMethod: 'gcp_sa',
    icon: 'cloud',
  },
  oracle: {
    displayName: 'Oracle Cloud Infrastructure',
    accent: '#c4161c',
    accentBg: 'bg-[#c4161c]/10',
    authMethod: 'oci_config',
    icon: 'cloud',
  },
};

// ── Common Regions ──

const AWS_REGIONS = [
  'us-east-1', 'us-east-2', 'us-west-1', 'us-west-2',
  'eu-west-1', 'eu-west-2', 'eu-central-1',
  'ap-southeast-1', 'ap-southeast-2', 'ap-northeast-1',
];

const ORACLE_REGIONS = [
  'us-ashburn-1', 'us-phoenix-1', 'eu-frankfurt-1',
  'eu-amsterdam-1', 'uk-london-1', 'ap-tokyo-1',
  'ap-mumbai-1', 'ap-sydney-1',
];

// ── Shared styles ──

const inputClass =
  'bg-[#0a1a1d] border border-[#224349] rounded-lg text-white text-sm placeholder-[#4a6670] focus:outline-none focus:border-[#07b6d5] transition-colors';

const labelClass = 'block text-xs font-medium text-[#8fc3cc] mb-1';

// ── Status badge ──

function statusBadge(status: string) {
  if (status === 'connected') {
    return (
      <span className="flex items-center gap-1.5 text-xs text-green-400">
        <span className="w-2 h-2 rounded-full bg-green-400" />
        Connected
      </span>
    );
  }
  if (status === 'conn_error') {
    return (
      <span className="flex items-center gap-1.5 text-xs text-red-400">
        <span className="w-2 h-2 rounded-full bg-red-400" />
        Error
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1.5 text-xs text-[#4a6670]">
      <span className="w-2 h-2 rounded-full bg-[#4a6670]" />
      Not Configured
    </span>
  );
}

// ── Region Chips ──

function RegionChips({
  regions,
  available,
  onChange,
}: {
  regions: string[];
  available: string[];
  onChange: (regions: string[]) => void;
}) {
  const [showDropdown, setShowDropdown] = useState(false);
  const remaining = available.filter((r) => !regions.includes(r));

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {regions.map((r) => (
        <span
          key={r}
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-[#07b6d5]/10 text-[#07b6d5] text-xs"
        >
          {r}
          <button
            onClick={() => onChange(regions.filter((x) => x !== r))}
            className="hover:text-white ml-0.5"
          >
            ×
          </button>
        </span>
      ))}
      <div className="relative">
        <button
          onClick={() => setShowDropdown(!showDropdown)}
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border border-dashed border-[#224349] text-[#4a6670] text-xs hover:border-[#07b6d5] hover:text-[#07b6d5] transition-colors"
        >
          <span className="material-symbols-outlined text-xs">add</span>
          Add
        </button>
        {showDropdown && remaining.length > 0 && (
          <div className="absolute top-7 left-0 z-50 bg-[#0a1a1d] border border-[#224349] rounded-lg shadow-xl max-h-40 overflow-y-auto min-w-[140px]">
            {remaining.map((r) => (
              <button
                key={r}
                onClick={() => {
                  onChange([...regions, r]);
                  setShowDropdown(false);
                }}
                className="block w-full text-left px-3 py-1.5 text-xs text-[#8fc3cc] hover:bg-[#07b6d5]/10 hover:text-white"
              >
                {r}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── AWS Fields ──

function AWSFields({
  creds,
  config,
  hasExisting,
  onCredsChange,
  onConfigChange,
}: {
  creds: Record<string, string>;
  config: Record<string, unknown>;
  hasExisting: boolean;
  onCredsChange: (c: Record<string, string>) => void;
  onConfigChange: (c: Record<string, unknown>) => void;
}) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={labelClass}>Access Key ID *</label>
          <input
            type="text"
            value={creds.access_key_id || ''}
            onChange={(e) => onCredsChange({ ...creds, access_key_id: e.target.value })}
            className={`${inputClass} w-full px-3 py-2`}
            placeholder={hasExisting ? '••••••••••••' : 'AKIA...'}
          />
        </div>
        <div>
          <label className={labelClass}>Secret Access Key *</label>
          <input
            type="password"
            value={creds.secret_access_key || ''}
            onChange={(e) => onCredsChange({ ...creds, secret_access_key: e.target.value })}
            className={`${inputClass} w-full px-3 py-2`}
            placeholder={hasExisting ? '••••••••••••' : 'wJal...'}
          />
        </div>
      </div>
      <div>
        <label className={labelClass}>IAM Role ARN (optional — for cross-account access)</label>
        <input
          type="text"
          value={creds.role_arn || ''}
          onChange={(e) => onCredsChange({ ...creds, role_arn: e.target.value })}
          className={`${inputClass} w-full px-3 py-2`}
          placeholder="arn:aws:iam::123456789:role/DebugDuck"
        />
      </div>
      {creds.role_arn && (
        <div>
          <label className={labelClass}>External ID (optional)</label>
          <input
            type="text"
            value={creds.external_id || ''}
            onChange={(e) => onCredsChange({ ...creds, external_id: e.target.value })}
            className={`${inputClass} w-full px-3 py-2`}
            placeholder="External ID for assume-role"
          />
        </div>
      )}
      <div>
        <label className={labelClass}>Session Token (optional — for temporary credentials)</label>
        <input
          type="password"
          value={creds.session_token || ''}
          onChange={(e) => onCredsChange({ ...creds, session_token: e.target.value })}
          className={`${inputClass} w-full px-3 py-2`}
          placeholder={hasExisting ? '••••••••••••' : 'FwoGZX...'}
        />
      </div>
      <div>
        <label className={labelClass}>Regions</label>
        <RegionChips
          regions={(config.regions as string[]) || []}
          available={AWS_REGIONS}
          onChange={(regions) => onConfigChange({ ...config, regions })}
        />
      </div>
    </div>
  );
}

// ── Azure Fields ──

function AzureFields({
  creds,
  config,
  hasExisting,
  onCredsChange,
  onConfigChange,
}: {
  creds: Record<string, string>;
  config: Record<string, unknown>;
  hasExisting: boolean;
  onCredsChange: (c: Record<string, string>) => void;
  onConfigChange: (c: Record<string, unknown>) => void;
}) {
  const [subInput, setSubInput] = useState('');
  const subscriptions = (config.subscriptions as string[]) || [];

  return (
    <div className="space-y-3">
      <div>
        <label className={labelClass}>Tenant ID *</label>
        <input
          type="text"
          value={creds.tenant_id || ''}
          onChange={(e) => onCredsChange({ ...creds, tenant_id: e.target.value })}
          className={`${inputClass} w-full px-3 py-2`}
          placeholder={hasExisting ? '••••••••••••' : 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx'}
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={labelClass}>Client ID *</label>
          <input
            type="text"
            value={creds.client_id || ''}
            onChange={(e) => onCredsChange({ ...creds, client_id: e.target.value })}
            className={`${inputClass} w-full px-3 py-2`}
            placeholder={hasExisting ? '••••••••••••' : 'xxxxxxxx-xxxx-...'}
          />
        </div>
        <div>
          <label className={labelClass}>Client Secret *</label>
          <input
            type="password"
            value={creds.client_secret || ''}
            onChange={(e) => onCredsChange({ ...creds, client_secret: e.target.value })}
            className={`${inputClass} w-full px-3 py-2`}
            placeholder={hasExisting ? '••••••••••••' : 'Client secret value'}
          />
        </div>
      </div>
      <div>
        <label className={labelClass}>Subscriptions (optional)</label>
        <div className="flex flex-wrap items-center gap-1.5">
          {subscriptions.map((s) => (
            <span
              key={s}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-[#07b6d5]/10 text-[#07b6d5] text-xs"
            >
              {s}
              <button
                onClick={() =>
                  onConfigChange({ ...config, subscriptions: subscriptions.filter((x) => x !== s) })
                }
                className="hover:text-white ml-0.5"
              >
                ×
              </button>
            </span>
          ))}
          <input
            type="text"
            value={subInput}
            onChange={(e) => setSubInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && subInput.trim()) {
                onConfigChange({
                  ...config,
                  subscriptions: [...subscriptions, subInput.trim()],
                });
                setSubInput('');
              }
            }}
            className={`${inputClass} px-2 py-0.5 text-xs w-32`}
            placeholder="Add subscription ID..."
          />
        </div>
      </div>
    </div>
  );
}

// ── GCP Fields ──

function GCPFields({
  creds,
  config,
  hasExisting,
  onCredsChange,
  onConfigChange,
}: {
  creds: Record<string, string>;
  config: Record<string, unknown>;
  hasExisting: boolean;
  onCredsChange: (c: Record<string, string>) => void;
  onConfigChange: (c: Record<string, unknown>) => void;
}) {
  const handleJsonChange = (value: string) => {
    onCredsChange({ _raw_json: value });
    try {
      const parsed = JSON.parse(value);
      if (parsed.project_id) {
        onConfigChange({ ...config, project_id: parsed.project_id });
      }
    } catch {
      // Not valid JSON yet — fine while typing
    }
  };

  return (
    <div className="space-y-3">
      <div>
        <label className={labelClass}>Service Account JSON Key *</label>
        <textarea
          value={creds._raw_json || ''}
          onChange={(e) => handleJsonChange(e.target.value)}
          className={`${inputClass} w-full px-3 py-2 h-32 font-mono text-xs`}
          placeholder={
            hasExisting
              ? 'Credentials saved. Paste new JSON to replace.'
              : '{\n  "type": "service_account",\n  "project_id": "...",\n  ...\n}'
          }
        />
      </div>
      {config.project_id && (
        <div>
          <label className={labelClass}>Project ID (auto-detected)</label>
          <input
            type="text"
            value={(config.project_id as string) || ''}
            readOnly
            className={`${inputClass} w-full px-3 py-2 opacity-60 cursor-not-allowed`}
          />
        </div>
      )}
    </div>
  );
}

// ── Oracle Fields ──

function OracleFields({
  creds,
  config,
  hasExisting,
  onCredsChange,
  onConfigChange,
}: {
  creds: Record<string, string>;
  config: Record<string, unknown>;
  hasExisting: boolean;
  onCredsChange: (c: Record<string, string>) => void;
  onConfigChange: (c: Record<string, unknown>) => void;
}) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={labelClass}>Tenancy OCID *</label>
          <input
            type="text"
            value={creds.tenancy_ocid || ''}
            onChange={(e) => onCredsChange({ ...creds, tenancy_ocid: e.target.value })}
            className={`${inputClass} w-full px-3 py-2`}
            placeholder={hasExisting ? '••••••••••••' : 'ocid1.tenancy.oc1...'}
          />
        </div>
        <div>
          <label className={labelClass}>User OCID *</label>
          <input
            type="text"
            value={creds.user_ocid || ''}
            onChange={(e) => onCredsChange({ ...creds, user_ocid: e.target.value })}
            className={`${inputClass} w-full px-3 py-2`}
            placeholder={hasExisting ? '••••••••••••' : 'ocid1.user.oc1...'}
          />
        </div>
      </div>
      <div>
        <label className={labelClass}>API Key Fingerprint *</label>
        <input
          type="text"
          value={creds.fingerprint || ''}
          onChange={(e) => onCredsChange({ ...creds, fingerprint: e.target.value })}
          className={`${inputClass} w-full px-3 py-2`}
          placeholder="aa:bb:cc:dd:..."
        />
      </div>
      <div>
        <label className={labelClass}>Private Key (PEM) *</label>
        <textarea
          value={creds.private_key || ''}
          onChange={(e) => onCredsChange({ ...creds, private_key: e.target.value })}
          className={`${inputClass} w-full px-3 py-2 h-24 font-mono text-xs`}
          placeholder={
            hasExisting
              ? 'Key saved. Paste new key to replace.'
              : '-----BEGIN RSA PRIVATE KEY-----\n...'
          }
        />
      </div>
      <div>
        <label className={labelClass}>Regions</label>
        <RegionChips
          regions={(config.regions as string[]) || []}
          available={ORACLE_REGIONS}
          onChange={(regions) => onConfigChange({ ...config, regions })}
        />
      </div>
    </div>
  );
}

// ── Provider Card ──

function ProviderCard({
  provider,
  integration,
  onUpdate,
  onTest,
  testing,
}: {
  provider: CloudProvider;
  integration: GlobalIntegration | undefined;
  onUpdate: (id: string, data: Record<string, unknown>) => void;
  onTest: (id: string) => Promise<void>;
  testing: boolean;
}) {
  const meta = PROVIDER_META[provider];
  const [expanded, setExpanded] = useState(false);
  const [creds, setCreds] = useState<Record<string, string>>({});
  const [config, setConfig] = useState<Record<string, unknown>>(integration?.config || {});
  const [dirty, setDirty] = useState(false);

  const handleCredsChange = useCallback((c: Record<string, string>) => {
    setCreds(c);
    setDirty(true);
  }, []);

  const handleConfigChange = useCallback((c: Record<string, unknown>) => {
    setConfig(c);
    setDirty(true);
  }, []);

  const handleSave = useCallback(() => {
    if (!integration) return;

    let authData: string | undefined;
    if (provider === 'gcp' && creds._raw_json) {
      authData = creds._raw_json;
    } else if (Object.values(creds).some((v) => v)) {
      const { _raw_json: _, ...cleanCreds } = creds;
      authData = JSON.stringify(cleanCreds);
    }

    const update: Record<string, unknown> = {
      auth_method: meta.authMethod,
      config,
    };
    if (authData) {
      update.auth_data = authData;
    }

    onUpdate(integration.id, update);
    setDirty(false);
  }, [integration, creds, config, meta.authMethod, onUpdate, provider]);

  const hasExisting = integration?.has_credentials || false;
  const status = integration?.status || 'not_linked';

  const FieldsComponent = {
    aws: AWSFields,
    azure: AzureFields,
    gcp: GCPFields,
    oracle: OracleFields,
  }[provider];

  return (
    <div
      className="rounded-xl border border-[#224349] bg-[#0f2023] overflow-hidden transition-all"
      style={{ borderTopColor: meta.accent, borderTopWidth: '2px' }}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-[#0a1a1d]/50 transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className={`w-8 h-8 rounded-lg ${meta.accentBg} flex items-center justify-center`}>
            <span className="material-symbols-outlined text-lg" style={{ color: meta.accent }}>
              cloud
            </span>
          </div>
          <div className="text-left">
            <div className="text-sm font-semibold text-white">{meta.displayName}</div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {statusBadge(status)}
          <span
            className="material-symbols-outlined text-[#4a6670] text-lg transition-transform"
            style={{ transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)' }}
          >
            expand_more
          </span>
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 border-t border-[#224349]">
          <div className="pt-3">
            <FieldsComponent
              creds={creds}
              config={config}
              hasExisting={hasExisting}
              onCredsChange={handleCredsChange}
              onConfigChange={handleConfigChange}
            />
          </div>
          <div className="flex items-center justify-end gap-3 mt-4 pt-3 border-t border-[#224349]/50">
            <button
              onClick={() => integration && onTest(integration.id)}
              disabled={testing}
              className="px-4 py-1.5 rounded-lg text-xs font-medium border border-[#224349] text-[#8fc3cc] hover:border-[#07b6d5] hover:text-[#07b6d5] transition-colors disabled:opacity-30"
            >
              {testing ? (
                <span className="flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-sm animate-spin">progress_activity</span>
                  Testing...
                </span>
              ) : (
                'Test Connection'
              )}
            </button>
            <button
              onClick={handleSave}
              disabled={!dirty}
              className="px-4 py-1.5 rounded-lg text-xs font-bold bg-[#07b6d5] text-[#0f2023] hover:bg-[#07b6d5]/80 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            >
              Save
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main Section ──

interface CloudProvidersSectionProps {
  integrations: GlobalIntegration[];
  onUpdate: (id: string, data: Record<string, unknown>) => void;
  onTest: (id: string) => Promise<void>;
  testingId: string | null;
}

const CloudProvidersSection: React.FC<CloudProvidersSectionProps> = ({
  integrations,
  onUpdate,
  onTest,
  testingId,
}) => {
  const cloudIntegrations = integrations.filter((gi) =>
    CLOUD_PROVIDERS.includes(gi.service_type as CloudProvider)
  );

  const getIntegration = (provider: CloudProvider) =>
    cloudIntegrations.find((gi) => gi.service_type === provider);

  return (
    <div className="mt-8">
      <div className="flex items-center gap-2 mb-4">
        <span className="material-symbols-outlined text-[#07b6d5]">cloud</span>
        <h3 className="text-lg font-bold text-white">Cloud Providers</h3>
      </div>
      <p className="text-sm text-[#8fc3cc] mb-4">
        Configure credentials for cloud infrastructure discovery and monitoring.
      </p>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {CLOUD_PROVIDERS.map((provider) => (
          <ProviderCard
            key={provider}
            provider={provider}
            integration={getIntegration(provider)}
            onUpdate={onUpdate}
            onTest={onTest}
            testing={testingId === getIntegration(provider)?.id}
          />
        ))}
      </div>
    </div>
  );
};

export default CloudProvidersSection;
