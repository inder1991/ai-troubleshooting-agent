import React from 'react';
import { motion } from 'framer-motion';
import { sectionFadeUp } from './howItWorksAnimations';

interface ScenarioTabProps {
  onSwitchToFlow: () => void;
}

type MetricStatus = 'bad' | 'warning' | 'ok';

interface ServiceMetric {
  label: string;
  value: string;
  status: MetricStatus;
}

interface Service {
  name: string;
  badge: string;
  borderColor: string;
  badgeColor: string;
  isPatientZero?: boolean;
  metrics: ServiceMetric[];
}

const STATUS_COLORS: Record<MetricStatus, string> = {
  bad: '#ef4444',
  warning: '#f97316',
  ok: '#10b981',
};

const patientZero: Service = {
  name: 'checkout-frontend',
  badge: 'Patient Zero',
  borderColor: '#ef4444',
  badgeColor: '#ef4444',
  isPatientZero: true,
  metrics: [
    { label: 'req/s', value: '< 0.01', status: 'bad' },
    { label: 'latency', value: '10.3s', status: 'bad' },
    { label: 'error', value: '88.9%', status: 'bad' },
  ],
};

const degraded: Service = {
  name: 'checkout-service',
  badge: 'Degraded',
  borderColor: '#f97316',
  badgeColor: '#f97316',
  metrics: [
    { label: 'req/s', value: '0.07', status: 'ok' },
    { label: 'latency', value: '7.18s', status: 'warning' },
    { label: 'error', value: '1.23%', status: 'warning' },
  ],
};

const downstreamServices: Service[] = [
  {
    name: 'notification-service',
    badge: 'Healthy',
    borderColor: '#10b981',
    badgeColor: '#10b981',
    metrics: [
      { label: 'req/s', value: '0.07', status: 'ok' },
      { label: 'latency', value: '1.19s', status: 'ok' },
      { label: 'error', value: '0.11%', status: 'ok' },
    ],
  },
  {
    name: 'payment-service',
    badge: 'Healthy',
    borderColor: '#10b981',
    badgeColor: '#10b981',
    metrics: [
      { label: 'req/s', value: '0.07', status: 'ok' },
      { label: 'latency', value: '208ms', status: 'ok' },
      { label: 'error', value: '0.21%', status: 'ok' },
    ],
  },
  {
    name: 'user-service',
    badge: 'Healthy',
    borderColor: '#10b981',
    badgeColor: '#10b981',
    metrics: [
      { label: 'req/s', value: '0.07', status: 'ok' },
      { label: 'latency', value: '428ms', status: 'ok' },
      { label: 'error', value: '0%', status: 'ok' },
    ],
  },
  {
    name: 'inventory-service',
    badge: 'Healthy',
    borderColor: '#10b981',
    badgeColor: '#10b981',
    metrics: [
      { label: 'req/s', value: '0.07', status: 'ok' },
      { label: 'latency', value: '1.23s', status: 'ok' },
      { label: 'error', value: '0%', status: 'ok' },
    ],
  },
];

const contextCards = [
  {
    title: 'Symptoms',
    borderColor: '#e09f3e',
    icon: 'troubleshoot',
    body: (
      <p className="text-sm text-slate-400 leading-relaxed">
        <strong className="text-white">checkout-frontend</strong> returning 5xx
        errors to users. Page loads timing out after 10+ seconds. Downstream
        services (payment, user, inventory, notification) appear healthy.
      </p>
    ),
  },
  {
    title: 'Impact',
    borderColor: '#ef4444',
    icon: 'warning',
    body: (
      <p className="text-sm text-slate-400 leading-relaxed">
        <strong className="text-white">88.9% of checkout attempts failing.</strong>{' '}
        Revenue loss estimated at ~$12K/min. Customer support tickets surging.
        SLA breach imminent if not resolved within 30 minutes.
      </p>
    ),
  },
  {
    title: 'Initial Hypothesis',
    borderColor: '#10b981',
    icon: 'psychology',
    body: (
      <p className="text-sm text-slate-400 leading-relaxed">
        Issue isolated to{' '}
        <strong className="text-white">
          checkout-frontend &rarr; checkout-service
        </strong>{' '}
        path. Downstream services healthy with low error rates. Likely cause in
        checkout-service or its database layer.
      </p>
    ),
  },
];

/* ---------- Service Node ---------- */

const ServiceNode: React.FC<{ service: Service }> = ({ service }) => (
  <div
    className={`min-w-[150px] rounded-lg p-3 border${service.isPatientZero ? ' animate-pulse-red' : ''}`}
    style={{
      borderColor: service.borderColor,
      background: 'rgba(15, 32, 35, 0.6)',
    }}
  >
    <p className="text-xs font-mono font-bold text-white truncate">
      {service.name}
    </p>
    <span
      className="inline-block mt-1 text-body-xs font-semibold uppercase tracking-wide"
      style={{ color: service.badgeColor }}
    >
      {service.badge}
    </span>
    <div className="mt-2 space-y-0.5">
      {service.metrics.map((m) => (
        <div key={m.label} className="flex justify-between text-body-xs">
          <span className="text-slate-400">{m.label}</span>
          <span style={{ color: STATUS_COLORS[m.status] }}>{m.value}</span>
        </div>
      ))}
    </div>
  </div>
);

/* ---------- Main Component ---------- */

const ScenarioTab: React.FC<ScenarioTabProps> = ({ onSwitchToFlow }) => {
  return (
    <div className="space-y-6">
      {/* ---- SEV-1 Banner ---- */}
      <motion.div
        variants={sectionFadeUp}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, amount: 0.2 }}
        custom={0}
      >
        <div
          className="rounded-lg p-4 border-l-4 border-red-500"
          style={{
            background:
              'linear-gradient(135deg, rgba(239,68,68,0.1) 0%, rgba(15,32,35,0.8) 100%)',
          }}
        >
          <div className="flex items-center gap-2">
            <span className="bg-wr-severity-high/20 text-red-400 text-body-xs font-bold uppercase px-2 py-0.5 rounded">
              SEV-1 &mdash; Critical Incident
            </span>
            <span className="material-symbols-outlined text-red-400 text-base">
              emergency
            </span>
          </div>
          <h3 className="text-lg font-bold text-white mt-2">
            E-Commerce Checkout Failures &amp; Slowness
          </h3>
          <p className="text-sm text-slate-400 mt-2 leading-relaxed">
            Multiple users reporting{' '}
            <strong className="text-white">failed checkouts</strong> and{' '}
            <strong className="text-white">extreme slowness</strong> on the
            e-commerce platform. The checkout-frontend is showing{' '}
            <strong className="text-white">88.9% error rate</strong> and{' '}
            <strong className="text-white">10.3s latency</strong>. This incident
            requires immediate investigation.
          </p>
        </div>
      </motion.div>

      {/* ---- Service Topology ---- */}
      <motion.div
        variants={sectionFadeUp}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, amount: 0.2 }}
        custom={1}
      >
        <div className="flex items-center gap-0 overflow-x-auto py-4">
          {/* Patient Zero */}
          <ServiceNode service={patientZero} />

          {/* Connector: checkout-frontend -> checkout-service */}
          <div className="w-8 h-0.5 bg-red-500 shrink-0" />

          {/* Degraded */}
          <ServiceNode service={degraded} />

          {/* Fan-out SVG */}
          <svg
            width="70"
            height="260"
            viewBox="0 0 70 260"
            fill="none"
            className="shrink-0"
          >
            <line
              x1="0"
              y1="130"
              x2="68"
              y2="15"
              stroke="#475569"
              strokeWidth="1.5"
            />
            <line
              x1="0"
              y1="130"
              x2="68"
              y2="87"
              stroke="#475569"
              strokeWidth="1.5"
            />
            <line
              x1="0"
              y1="130"
              x2="68"
              y2="170"
              stroke="#475569"
              strokeWidth="1.5"
            />
            <line
              x1="0"
              y1="130"
              x2="68"
              y2="245"
              stroke="#475569"
              strokeWidth="1.5"
            />
          </svg>

          {/* Downstream services stacked vertically */}
          <div className="flex flex-col gap-2">
            {downstreamServices.map((svc) => (
              <ServiceNode key={svc.name} service={svc} />
            ))}
          </div>
        </div>
      </motion.div>

      {/* ---- Context Cards ---- */}
      <motion.div
        variants={sectionFadeUp}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, amount: 0.2 }}
        custom={2}
      >
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5">
          {contextCards.map((card) => (
            <div
              key={card.title}
              className="bg-wr-bg/50 border border-[#3d3528] rounded-lg p-4"
              style={{ borderTop: `3px solid ${card.borderColor}` }}
            >
              <div className="flex items-center gap-2 mb-3">
                <span
                  className="material-symbols-outlined text-base"
                  style={{ color: card.borderColor }}
                >
                  {card.icon}
                </span>
                <h4 className="text-sm font-bold text-white">{card.title}</h4>
              </div>
              {card.body}
            </div>
          ))}
        </div>
      </motion.div>

      {/* ---- CTA ---- */}
      <motion.div
        variants={sectionFadeUp}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, amount: 0.2 }}
        custom={3}
      >
        <div className="bg-wr-bg/50 border border-[#3d3528] rounded-lg p-6 text-center max-w-md mx-auto">
          <p className="text-sm text-slate-400">
            Ready to watch the AI agents investigate and resolve this incident
            in real-time?
          </p>
          <button
            onClick={onSwitchToFlow}
            className="mt-3 px-5 py-2.5 rounded-lg bg-[#e09f3e] hover:bg-[#e09f3e]/80 text-white text-sm font-bold transition-colors"
          >
            Launch Investigation Flow &rarr;
          </button>
        </div>
      </motion.div>
    </div>
  );
};

export default ScenarioTab;
