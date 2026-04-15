import React, { useState, useEffect, useCallback, useRef } from 'react';
import NotificationChannelsSection from './NotificationChannelsSection';

// ── localStorage keys ────────────────────────────────────────────────
const LS_TIMEZONE = 'dd-timezone';
const LS_REFRESH_INTERVAL = 'dd-refresh-interval';
const LS_SHOW_CONFIDENCE = 'dd-show-confidence';
const LS_PROMETHEUS_URL = 'dd-prometheus-url';
const LS_ELASTICSEARCH_URL = 'dd-elasticsearch-url';
const LS_K8S_URL = 'dd-k8s-url';
const LS_NOTIFICATIONS = 'dd-notifications';
const LS_SOUND_ALERTS = 'dd-sound-alerts';

// ── Timezone & interval options ──────────────────────────────────────
const TIMEZONES = [
  'UTC',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'Europe/London',
  'Asia/Tokyo',
];

const REFRESH_OPTIONS = [
  { label: '5s', value: '5' },
  { label: '10s', value: '10' },
  { label: '30s', value: '30' },
  { label: '60s', value: '60' },
  { label: 'Off', value: 'off' },
];

// ── Helpers ──────────────────────────────────────────────────────────
function readLS(key: string, fallback: string): string {
  try {
    return localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}

function writeLS(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // quota exceeded – ignore
  }
}

// ── Reusable sub-components ──────────────────────────────────────────

/** Section card wrapper */
const SectionCard: React.FC<{ icon: string; title: string; children: React.ReactNode }> = ({ icon, title, children }) => (
  <div
    className="rounded-lg border p-5 mb-6"
    style={{ backgroundColor: 'rgba(15,32,35,0.6)', borderColor: '#3d3528' }}
  >
    <div className="flex items-center gap-2 mb-4">
      <span
        className="material-symbols-outlined text-lg"
        style={{ color: '#e09f3e' }}
      >
        {icon}
      </span>
      <h2 className="text-sm font-bold text-white uppercase tracking-wider">{title}</h2>
    </div>
    {children}
  </div>
);

/** Toggle switch */
const Toggle: React.FC<{ checked: boolean; onChange: (v: boolean) => void; label: string }> = ({
  checked,
  onChange,
  label,
}) => (
  <label className="flex items-center justify-between cursor-pointer group py-2">
    <span className="text-sm text-slate-300 group-hover:text-white transition-colors">{label}</span>
    <button
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors duration-200 focus:outline-none"
      style={{ backgroundColor: checked ? '#e09f3e' : '#334155' }}
    >
      <span
        className="inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform duration-200"
        style={{ transform: checked ? 'translateX(18px)' : 'translateX(3px)' }}
      />
    </button>
  </label>
);

/** Select dropdown */
const LabeledSelect: React.FC<{
  label: string;
  value: string;
  options: { label: string; value: string }[];
  onChange: (v: string) => void;
}> = ({ label, value, options, onChange }) => (
  <div className="flex items-center justify-between py-2">
    <span className="text-sm text-slate-300">{label}</span>
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="rounded-md px-3 py-1.5 text-sm text-white outline-none cursor-pointer font-mono"
      style={{ backgroundColor: 'rgba(30,47,51,0.6)', border: '1px solid #3d3528' }}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  </div>
);

/** URL input with test button */
const URLInput: React.FC<{
  label: string;
  value: string;
  placeholder: string;
  onChange: (v: string) => void;
  testStatus: 'idle' | 'pass' | 'fail';
  onTest: () => void;
}> = ({ label, value, placeholder, onChange, testStatus, onTest }) => (
  <div className="py-2">
    <label className="block text-sm text-slate-300 mb-1.5">{label}</label>
    <div className="flex gap-2">
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="flex-1 rounded-md px-3 py-1.5 text-sm text-white placeholder:text-slate-500 outline-none font-mono"
        style={{ backgroundColor: 'rgba(30,47,51,0.6)', border: '1px solid #3d3528' }}
      />
      <button
        onClick={onTest}
        className="flex items-center gap-1 rounded-md px-3 py-1.5 text-xs font-bold uppercase tracking-wide transition-colors"
        style={{
          border: '1px solid #3d3528',
          backgroundColor: 'rgba(30,47,51,0.4)',
          color: testStatus === 'pass' ? '#10b981' : testStatus === 'fail' ? '#ef4444' : '#8a7e6b',
        }}
      >
        {testStatus === 'pass' && (
          <span
            className="material-symbols-outlined text-sm"
            style={{ color: '#10b981' }}
          >
            check_circle
          </span>
        )}
        {testStatus === 'fail' && (
          <span
            className="material-symbols-outlined text-sm"
            style={{ color: '#ef4444' }}
          >
            cancel
          </span>
        )}
        {testStatus === 'idle' && 'Test'}
        {testStatus === 'pass' && 'OK'}
        {testStatus === 'fail' && 'Fail'}
      </button>
    </div>
  </div>
);

// ── Saved toast ──────────────────────────────────────────────────────
const SavedToast: React.FC<{ visible: boolean }> = ({ visible }) => (
  <div
    className="fixed bottom-6 right-6 px-4 py-2 rounded-lg text-xs font-bold text-white shadow-lg transition-all duration-300 pointer-events-none z-50"
    style={{
      backgroundColor: 'rgba(224,159,62,0.9)',
      opacity: visible ? 1 : 0,
      transform: visible ? 'translateY(0)' : 'translateY(8px)',
    }}
  >
    Saved
  </div>
);

// ── Main component ───────────────────────────────────────────────────
const SettingsView: React.FC = () => {
  // ── General ──
  const [timezone, setTimezone] = useState(() => readLS(LS_TIMEZONE, 'UTC'));
  const [refreshInterval, setRefreshInterval] = useState(() => readLS(LS_REFRESH_INTERVAL, '10'));
  const [showConfidence, setShowConfidence] = useState(() => readLS(LS_SHOW_CONFIDENCE, 'true') === 'true');

  // ── Connections ──
  const [prometheusUrl, setPrometheusUrl] = useState(() => readLS(LS_PROMETHEUS_URL, ''));
  const [elasticsearchUrl, setElasticsearchUrl] = useState(() => readLS(LS_ELASTICSEARCH_URL, ''));
  const [k8sUrl, setK8sUrl] = useState(() => readLS(LS_K8S_URL, ''));
  const [testResults, setTestResults] = useState<Record<string, 'idle' | 'pass' | 'fail'>>({
    prometheus: 'idle',
    elasticsearch: 'idle',
    k8s: 'idle',
  });

  // ── Notifications ──
  const [notifications, setNotifications] = useState(() => readLS(LS_NOTIFICATIONS, 'false') === 'true');
  const [soundAlerts, setSoundAlerts] = useState(() => readLS(LS_SOUND_ALERTS, 'false') === 'true');

  // ── Saved toast ──
  const [showSaved, setShowSaved] = useState(false);
  const savedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const flashSaved = useCallback(() => {
    setShowSaved(true);
    if (savedTimer.current) clearTimeout(savedTimer.current);
    savedTimer.current = setTimeout(() => setShowSaved(false), 1000);
  }, []);

  // Cleanup timer on unmount
  useEffect(() => {
    return () => {
      if (savedTimer.current) clearTimeout(savedTimer.current);
    };
  }, []);

  // ── Persist helpers (save + flash) ──
  const persist = useCallback(
    (key: string, value: string) => {
      writeLS(key, value);
      flashSaved();
    },
    [flashSaved],
  );

  // ── General handlers ──
  const handleTimezone = (v: string) => {
    setTimezone(v);
    persist(LS_TIMEZONE, v);
  };
  const handleRefresh = (v: string) => {
    setRefreshInterval(v);
    persist(LS_REFRESH_INTERVAL, v);
  };
  const handleConfidence = (v: boolean) => {
    setShowConfidence(v);
    persist(LS_SHOW_CONFIDENCE, String(v));
  };

  // ── Connection handlers ──
  const handlePrometheus = (v: string) => {
    setPrometheusUrl(v);
    persist(LS_PROMETHEUS_URL, v);
  };
  const handleElasticsearch = (v: string) => {
    setElasticsearchUrl(v);
    persist(LS_ELASTICSEARCH_URL, v);
  };
  const handleK8s = (v: string) => {
    setK8sUrl(v);
    persist(LS_K8S_URL, v);
  };

  const simulateTest = (key: string) => {
    setTestResults((prev) => ({ ...prev, [key]: 'idle' }));
    // Simulate a quick "test" — randomly pass/fail after a short delay
    setTimeout(() => {
      const pass = Math.random() > 0.3;
      setTestResults((prev) => ({ ...prev, [key]: pass ? 'pass' : 'fail' }));
    }, 600);
  };

  // ── Notification handlers ──
  const handleNotifications = (v: boolean) => {
    setNotifications(v);
    persist(LS_NOTIFICATIONS, String(v));
  };
  const handleSound = (v: boolean) => {
    setSoundAlerts(v);
    persist(LS_SOUND_ALERTS, String(v));
  };

  return (
    <div className="flex-1 overflow-y-auto custom-scrollbar">
      <div className="max-w-3xl mx-auto px-6 py-8">
        {/* ── Header ────────────────────────────────────────────────── */}
        <div className="flex items-center gap-2 mb-8">
          <span
            className="material-symbols-outlined text-xl"
            style={{ color: '#e09f3e' }}
          >
            settings
          </span>
          <h1 className="text-xl font-bold text-white">Settings</h1>
        </div>

        {/* ── General ───────────────────────────────────────────────── */}
        <SectionCard icon="tune" title="General">
          <LabeledSelect
            label="Timezone"
            value={timezone}
            options={TIMEZONES.map((tz) => ({ label: tz, value: tz }))}
            onChange={handleTimezone}
          />
          <div className="border-t my-1" style={{ borderColor: '#3d3528' }} />
          <LabeledSelect
            label="Auto-refresh interval"
            value={refreshInterval}
            options={REFRESH_OPTIONS}
            onChange={handleRefresh}
          />
          <div className="border-t my-1" style={{ borderColor: '#3d3528' }} />
          <Toggle
            label="Show confidence percentages"
            checked={showConfidence}
            onChange={handleConfidence}
          />
        </SectionCard>

        {/* ── Connections ────────────────────────────────────────────── */}
        <SectionCard icon="cable" title="Connections">
          <URLInput
            label="Prometheus URL"
            value={prometheusUrl}
            placeholder="http://prometheus:9090"
            onChange={handlePrometheus}
            testStatus={testResults.prometheus}
            onTest={() => simulateTest('prometheus')}
          />
          <div className="border-t my-1" style={{ borderColor: '#3d3528' }} />
          <URLInput
            label="Elasticsearch URL"
            value={elasticsearchUrl}
            placeholder="http://elasticsearch:9200"
            onChange={handleElasticsearch}
            testStatus={testResults.elasticsearch}
            onTest={() => simulateTest('elasticsearch')}
          />
          <div className="border-t my-1" style={{ borderColor: '#3d3528' }} />
          <URLInput
            label="Kubernetes API URL"
            value={k8sUrl}
            placeholder="https://kubernetes.default.svc"
            onChange={handleK8s}
            testStatus={testResults.k8s}
            onTest={() => simulateTest('k8s')}
          />
        </SectionCard>

        {/* ── Notifications ──────────────────────────────────────────── */}
        <SectionCard icon="notifications" title="Notifications">
          <Toggle
            label="Enable browser notifications"
            checked={notifications}
            onChange={handleNotifications}
          />
          <div className="border-t my-1" style={{ borderColor: '#3d3528' }} />
          <Toggle
            label="Sound alerts"
            checked={soundAlerts}
            onChange={handleSound}
          />
        </SectionCard>

        {/* ── Notification Channels & Escalation ──────────────────────── */}
        <NotificationChannelsSection />

        {/* ── About ──────────────────────────────────────────────────── */}
        <SectionCard icon="info" title="About">
          <div className="space-y-2 text-sm">
            <div className="flex items-center justify-between py-1">
              <span className="text-slate-400">Version</span>
              <span className="font-mono text-white">1.0.0-beta</span>
            </div>
            <div className="border-t" style={{ borderColor: '#3d3528' }} />
            <div className="flex items-center justify-between py-1">
              <span className="text-slate-400">Product</span>
              <span className="text-white">DebugDuck Command Center</span>
            </div>
            <div className="border-t" style={{ borderColor: '#3d3528' }} />
            <div className="flex items-center justify-between py-1">
              <span className="text-slate-400">Support</span>
              <span className="text-slate-400 cursor-default">Report issues</span>
            </div>
          </div>
        </SectionCard>
      </div>

      {/* Saved toast */}
      <SavedToast visible={showSaved} />
    </div>
  );
};

export default SettingsView;
