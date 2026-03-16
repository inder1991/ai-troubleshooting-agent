import React, { memo } from 'react';

/**
 * Large environment label node for the topology canvas.
 * Renders as a prominent banner with icon + text.
 * Used for: ON-PREMISES DC, AWS, AZURE, ORACLE CLOUD, etc.
 */

const ENV_ICONS: Record<string, string> = {
  onprem: 'domain',         // Building/data center
  aws: 'cloud',             // Cloud
  azure: 'cloud',           // Cloud
  oci: 'cloud',             // Cloud
  gcp: 'cloud',             // Cloud
  branch: 'business',       // Office building
};

interface EnvironmentLabelProps {
  data: {
    label: string;
    envType: string;
    accent: string;
    deviceCount: number;
  };
}

const EnvironmentLabel: React.FC<EnvironmentLabelProps> = memo(({ data }) => {
  const icon = ENV_ICONS[data.envType] || 'cloud';

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '6px 16px',
      background: `${data.accent}15`,
      border: `2px solid ${data.accent}60`,
      borderRadius: 10,
      pointerEvents: 'none',
    }}>
      <span className="material-symbols-outlined" style={{
        fontSize: 24,
        color: data.accent,
      }}>
        {icon}
      </span>
      <div>
        <div style={{
          fontSize: 16,
          fontWeight: 800,
          color: data.accent,
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          lineHeight: 1.2,
        }}>
          {data.label}
        </div>
        <div style={{
          fontSize: 10,
          color: `${data.accent}99`,
          marginTop: 1,
        }}>
          {data.deviceCount} device{data.deviceCount !== 1 ? 's' : ''}
        </div>
      </div>
    </div>
  );
});

EnvironmentLabel.displayName = 'EnvironmentLabel';
export default EnvironmentLabel;
