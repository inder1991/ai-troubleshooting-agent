import React from 'react';

interface TopologyToolbarProps {
  onSave: () => void;
  onLoad: () => void;
  onImportIPAM: () => void;
  onAdapterStatus: () => void;
  saving?: boolean;
  loading?: boolean;
}

const TopologyToolbar: React.FC<TopologyToolbarProps> = ({
  onSave,
  onLoad,
  onImportIPAM,
  onAdapterStatus,
  saving,
  loading,
}) => {
  const buttons: { label: string; icon: string; onClick: () => void; disabled?: boolean }[] = [
    { label: saving ? 'Saving...' : 'Save', icon: 'save', onClick: onSave, disabled: saving },
    { label: loading ? 'Loading...' : 'Load', icon: 'folder_open', onClick: onLoad, disabled: loading },
    { label: 'Import IPAM', icon: 'upload_file', onClick: onImportIPAM },
    { label: 'Adapter Status', icon: 'hub', onClick: onAdapterStatus },
  ];

  return (
    <div
      className="flex items-center gap-2 px-4 py-2 border-b"
      style={{ backgroundColor: '#0f2023', borderColor: '#224349' }}
    >
      <span
        className="material-symbols-outlined text-lg mr-2"
        style={{ fontFamily: 'Material Symbols Outlined', color: '#07b6d5' }}
      >
        device_hub
      </span>
      <span className="text-sm font-mono font-semibold mr-4" style={{ color: '#e2e8f0' }}>
        Topology Editor
      </span>

      <div className="w-px h-5 mx-1" style={{ backgroundColor: '#224349' }} />

      {buttons.map((btn) => (
        <button
          key={btn.label}
          onClick={btn.onClick}
          disabled={btn.disabled}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-mono border transition-colors hover:border-[#07b6d5]/40 disabled:opacity-50 disabled:cursor-not-allowed"
          style={{
            backgroundColor: '#162a2e',
            borderColor: '#224349',
            color: '#e2e8f0',
          }}
        >
          <span
            className="material-symbols-outlined text-sm"
            style={{ fontFamily: 'Material Symbols Outlined', color: '#07b6d5' }}
          >
            {btn.icon}
          </span>
          {btn.label}
        </button>
      ))}
    </div>
  );
};

export default TopologyToolbar;
