import React, { useState, useCallback, useRef } from 'react';
import { uploadIPAM } from '../../services/api';

const SAMPLE_CSV = `ip,subnet,device,zone,vlan,description,device_type
10.0.1.1,10.0.1.0/24,fw-core-01,dmz,100,Core perimeter firewall,firewall
10.0.1.2,10.0.1.0/24,rtr-edge-01,dmz,100,Edge router to ISP,router
10.0.2.10,10.0.2.0/24,sw-dist-01,internal,200,Distribution layer switch,switch
10.0.2.50,10.0.2.0/24,app-server-01,internal,200,Primary application server,host
10.0.3.5,10.0.3.0/24,sw-access-01,office,300,Office floor access switch,switch
10.0.3.100,10.0.3.0/24,workstation-42,office,300,Engineering workstation,host`;

interface IPAMUploadDialogProps {
  open: boolean;
  onClose: () => void;
  onImported: (data: { nodes: unknown[]; edges: unknown[] }) => void;
}

const IPAMUploadDialog: React.FC<IPAMUploadDialogProps> = ({ open, onClose, onImported }) => {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ devices: number; subnets: number } | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile) {
      const ext = droppedFile.name.split('.').pop()?.toLowerCase();
      if (ext === 'csv' || ext === 'xlsx') {
        setFile(droppedFile);
        setError(null);
        setResult(null);
      } else {
        setError('Only .csv and .xlsx files are accepted');
      }
    }
  }, []);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      setFile(selectedFile);
      setError(null);
      setResult(null);
    }
  }, []);

  const handleDownloadSample = useCallback(() => {
    const blob = new Blob([SAMPLE_CSV], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'ipam_sample.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, []);

  const handleUpload = useCallback(async () => {
    if (!file) return;
    setUploading(true);
    setProgress(10);
    setError(null);
    setWarnings([]);

    try {
      setProgress(40);
      const data = await uploadIPAM(file);
      setProgress(100);
      setResult({
        devices: data.devices_imported ?? 0,
        subnets: data.subnets_imported ?? 0,
      });

      if (Array.isArray(data.warnings) && data.warnings.length > 0) {
        setWarnings(data.warnings);
      }

      if (data.nodes && data.edges) {
        onImported({ nodes: data.nodes, edges: data.edges });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  }, [file, onImported]);

  const handleClose = () => {
    setFile(null);
    setProgress(0);
    setError(null);
    setResult(null);
    setWarnings([]);
    onClose();
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Overlay */}
      <div
        className="absolute inset-0"
        style={{ backgroundColor: 'rgba(0,0,0,0.7)' }}
        onClick={handleClose}
      />

      {/* Dialog */}
      <div
        className="relative w-full max-w-md rounded-xl border p-6 shadow-2xl"
        style={{ backgroundColor: '#0f2023', borderColor: '#224349' }}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-sm font-mono font-semibold" style={{ color: '#e2e8f0' }}>
            Import IPAM Data
          </h3>
          <button
            onClick={handleClose}
            className="p-1 rounded transition-colors hover:bg-white/5"
          >
            <span
              className="material-symbols-outlined text-lg"
              style={{ fontFamily: 'Material Symbols Outlined', color: '#64748b' }}
            >
              close
            </span>
          </button>
        </div>

        {/* Sample CSV Download */}
        <div className="flex items-center gap-1 mb-2">
          <span
            className="material-symbols-outlined text-sm"
            style={{ fontFamily: 'Material Symbols Outlined', color: '#07b6d5' }}
          >
            download
          </span>
          <button
            onClick={handleDownloadSample}
            className="text-[10px] font-mono underline underline-offset-2 transition-colors hover:brightness-125"
            style={{ color: '#07b6d5', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
          >
            Download Sample CSV
          </button>
          <span className="text-[10px] font-mono" style={{ color: '#64748b' }}>
            — see expected format
          </span>
        </div>

        {/* Drop Zone */}
        <div
          onDrop={handleDrop}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onClick={() => fileRef.current?.click()}
          className="flex flex-col items-center justify-center gap-3 p-8 rounded-lg border-2 border-dashed cursor-pointer transition-colors"
          style={{
            borderColor: dragOver ? '#07b6d5' : '#224349',
            backgroundColor: dragOver ? 'rgba(7,182,213,0.05)' : '#0a0f13',
          }}
        >
          <span
            className="material-symbols-outlined text-3xl"
            style={{ fontFamily: 'Material Symbols Outlined', color: '#64748b' }}
          >
            upload_file
          </span>
          <p className="text-xs font-mono text-center" style={{ color: '#64748b' }}>
            {file ? file.name : 'Drop .csv or .xlsx file here, or click to browse'}
          </p>
          <input
            ref={fileRef}
            type="file"
            accept=".csv,.xlsx"
            onChange={handleFileSelect}
            className="hidden"
          />
        </div>

        {/* Progress */}
        {uploading && (
          <div className="mt-4">
            <div className="w-full h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: '#162a2e' }}>
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{ width: `${progress}%`, backgroundColor: '#07b6d5' }}
              />
            </div>
            <p className="text-[10px] font-mono mt-1" style={{ color: '#64748b' }}>
              Processing... {progress}%
            </p>
          </div>
        )}

        {/* Result */}
        {result && (
          <div
            className="mt-4 p-3 rounded border text-xs font-mono"
            style={{ backgroundColor: '#162a2e', borderColor: '#224349', color: '#22c55e' }}
          >
            Imported {result.devices} devices and {result.subnets} subnets
          </div>
        )}

        {/* Warnings */}
        {warnings.length > 0 && (
          <div
            className="mt-4 p-3 rounded border text-xs font-mono overflow-y-auto"
            style={{
              backgroundColor: '#1a1a0f',
              borderColor: '#4a3f00',
              color: '#f59e0b',
              maxHeight: '8rem',
            }}
          >
            <div className="flex items-center gap-1 mb-1 font-semibold">
              <span
                className="material-symbols-outlined text-sm"
                style={{ fontFamily: 'Material Symbols Outlined', color: '#f59e0b' }}
              >
                warning
              </span>
              {warnings.length} warning{warnings.length !== 1 ? 's' : ''}
            </div>
            {warnings.map((w, i) => (
              <div key={i} className="ml-5 leading-relaxed">
                {w}
              </div>
            ))}
          </div>
        )}

        {/* Error */}
        {error && (
          <div
            className="mt-4 p-3 rounded border text-xs font-mono"
            style={{ backgroundColor: '#1a0f0f', borderColor: '#7f1d1d', color: '#ef4444' }}
          >
            {error}
          </div>
        )}

        {/* Actions */}
        <div className="flex justify-end gap-2 mt-5">
          <button
            onClick={handleClose}
            className="px-4 py-2 rounded text-xs font-mono border transition-colors"
            style={{ borderColor: '#224349', color: '#64748b', backgroundColor: 'transparent' }}
          >
            Cancel
          </button>
          <button
            onClick={handleUpload}
            disabled={!file || uploading}
            className="px-4 py-2 rounded text-xs font-mono font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            style={{ backgroundColor: '#07b6d5', color: '#0a0f13' }}
          >
            {uploading ? 'Uploading...' : 'Upload & Parse'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default IPAMUploadDialog;
