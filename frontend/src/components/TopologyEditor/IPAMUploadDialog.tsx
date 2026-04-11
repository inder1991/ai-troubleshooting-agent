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
  const [importedData, setImportedData] = useState<{ nodes: unknown[]; edges: unknown[] } | null>(null);
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
        setImportedData({ nodes: data.nodes, edges: data.edges });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  }, [file]);

  const handleCloseAndView = () => {
    if (importedData) {
      onImported(importedData);
    }
    handleClose();
  };

  const handleClose = () => {
    setFile(null);
    setProgress(0);
    setError(null);
    setResult(null);
    setWarnings([]);
    setImportedData(null);
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
        style={{ backgroundColor: '#1a1814', borderColor: '#3d3528' }}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-sm font-mono font-semibold" style={{ color: '#e8e0d4' }}>
            Import IPAM Data
          </h3>
          <button
            onClick={handleClose}
            className="p-1 rounded transition-colors hover:bg-white/5"
          >
            <span
              className="material-symbols-outlined text-lg"
              style={{ color: '#64748b' }}
            >
              close
            </span>
          </button>
        </div>

        {/* Sample CSV Download */}
        <div className="flex items-center gap-1 mb-2">
          <span
            className="material-symbols-outlined text-sm"
            style={{ color: '#e09f3e' }}
          >
            download
          </span>
          <button
            onClick={handleDownloadSample}
            className="text-body-xs font-mono underline underline-offset-2 transition-colors hover:brightness-125"
            style={{ color: '#e09f3e', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
          >
            Download Sample CSV
          </button>
          <span className="text-body-xs font-mono" style={{ color: '#64748b' }}>
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
            borderColor: dragOver ? '#e09f3e' : '#3d3528',
            backgroundColor: dragOver ? 'rgba(224,159,62,0.05)' : '#0a0f13',
          }}
        >
          <span
            className="material-symbols-outlined text-3xl"
            style={{ color: '#64748b' }}
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
            <div className="w-full h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: '#1e1b15' }}>
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{ width: `${progress}%`, backgroundColor: '#e09f3e' }}
              />
            </div>
            <p className="text-body-xs font-mono mt-1" style={{ color: '#64748b' }}>
              Processing... {progress}%
            </p>
          </div>
        )}

        {/* Result */}
        {result && (
          <div
            className="mt-4 p-3 rounded border text-xs font-mono flex items-start gap-2"
            style={{ backgroundColor: '#1e1b15', borderColor: '#3d3528', color: '#22c55e' }}
          >
            <span
              className="material-symbols-outlined text-base flex-shrink-0"
              style={{ color: '#22c55e' }}
            >
              check_circle
            </span>
            <div>
              <div>{result.devices} devices imported, {result.subnets} subnets imported</div>
              {warnings.length > 0 && (
                <div className="mt-1" style={{ color: '#f59e0b' }}>
                  {warnings.length} warning{warnings.length !== 1 ? 's' : ''}
                </div>
              )}
            </div>
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
                style={{ color: '#f59e0b' }}
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
          {result ? (
            <button
              onClick={handleCloseAndView}
              className="px-4 py-2 rounded text-xs font-mono font-semibold transition-colors"
              style={{ backgroundColor: '#22c55e', color: '#0a0f13' }}
            >
              Close &amp; View
            </button>
          ) : (
            <>
              <button
                onClick={handleClose}
                className="px-4 py-2 rounded text-xs font-mono border transition-colors"
                style={{ borderColor: '#3d3528', color: '#64748b', backgroundColor: 'transparent' }}
              >
                Cancel
              </button>
              <button
                onClick={handleUpload}
                disabled={!file || uploading}
                className="px-4 py-2 rounded text-xs font-mono font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                style={{ backgroundColor: '#e09f3e', color: '#0a0f13' }}
              >
                {uploading ? 'Uploading...' : 'Upload & Parse'}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default IPAMUploadDialog;
