import React from 'react';
import { motion } from 'framer-motion';
import { WF_COLORS } from './workflowConfigs';

/* ─── Types ─── */

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

/* ─── Data ─── */

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
    borderColor: WF_COLORS.amber,
    icon: 'troubleshoot',
    text: 'checkout-frontend returning 5xx errors to users. Page loads timing out after 10+ seconds. Downstream services (payment, user, inventory, notification) appear healthy.',
  },
  {
    title: 'Impact',
    borderColor: '#ef4444',
    icon: 'warning',
    text: '88.9% of checkout attempts failing. Revenue loss estimated at ~$12K/min. Customer support tickets surging. SLA breach imminent if not resolved within 30 minutes.',
  },
  {
    title: 'Initial Hypothesis',
    borderColor: '#10b981',
    icon: 'psychology',
    text: 'Issue isolated to checkout-frontend → checkout-service path. Downstream services healthy with low error rates. Likely cause in checkout-service or its database layer.',
  },
];

/* ─── Service Node ─── */

const ServiceNode: React.FC<{ service: Service }> = ({ service }) => (
  <div
    className={`min-w-[150px] rounded-lg p-3 border${service.isPatientZero ? ' animate-pulse-red' : ''}`}
    style={{
      borderColor: service.borderColor,
      backgroundColor: WF_COLORS.cardBg,
    }}
  >
    <p
      className="text-xs font-bold truncate"
      style={{ color: WF_COLORS.labelText, fontFamily: 'DM Sans, Inter, system-ui, sans-serif' }}
    >
      {service.name}
    </p>
    <span
      className="inline-block mt-1 text-[10px] font-semibold uppercase tracking-wide"
      style={{ color: service.badgeColor }}
    >
      {service.badge}
    </span>
    <div className="mt-2 space-y-0.5">
      {service.metrics.map((m) => (
        <div key={m.label} className="flex justify-between text-[10px]">
          <span style={{ color: WF_COLORS.mutedText }}>{m.label}</span>
          <span style={{ color: STATUS_COLORS[m.status] }}>{m.value}</span>
        </div>
      ))}
    </div>
  </div>
);

/* ─── Fade-in animation ─── */

const fadeUp = {
  hidden: { opacity: 0, y: 16 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.12, duration: 0.4, ease: 'easeOut' },
  }),
};

/* ─── Main Component ─── */

const DemoScenarioTab: React.FC = () => {
  return (
    <div
      className="h-full overflow-y-auto p-6 space-y-6"
      style={{ backgroundColor: WF_COLORS.pageBg }}
    >
      {/* SEV-1 Banner */}
      <motion.div
        variants={fadeUp}
        initial="hidden"
        animate="visible"
        custom={0}
      >
        <div
          className="rounded-lg p-4 border-l-4"
          style={{
            borderLeftColor: '#ef4444',
            background: `linear-gradient(135deg, rgba(239,68,68,0.08) 0%, ${WF_COLORS.pageBg} 100%)`,
          }}
        >
          <div className="flex items-center gap-2">
            <span
              className="text-[10px] font-bold uppercase px-2 py-0.5 rounded"
              style={{ backgroundColor: 'rgba(239,68,68,0.15)', color: '#ef4444' }}
            >
              SEV-1 &mdash; Critical Incident
            </span>
            <span className="material-symbols-outlined text-base" style={{ color: '#ef4444' }}>
              emergency
            </span>
          </div>
          <h3
            className="text-lg font-bold text-white mt-2"
            style={{ fontFamily: 'DM Sans, Inter, system-ui, sans-serif' }}
          >
            E-Commerce Checkout Failures &amp; Slowness
          </h3>
          <p className="text-sm mt-2 leading-relaxed" style={{ color: WF_COLORS.mutedText }}>
            Multiple users reporting{' '}
            <strong style={{ color: WF_COLORS.labelText }}>failed checkouts</strong> and{' '}
            <strong style={{ color: WF_COLORS.labelText }}>extreme slowness</strong> on the
            e-commerce platform. The checkout-frontend is showing{' '}
            <strong style={{ color: WF_COLORS.labelText }}>88.9% error rate</strong> and{' '}
            <strong style={{ color: WF_COLORS.labelText }}>10.3s latency</strong>. This incident
            requires immediate investigation.
          </p>
        </div>
      </motion.div>

      {/* OpenShift Cluster Container */}
      <motion.div
        variants={fadeUp}
        initial="hidden"
        animate="visible"
        custom={1}
      >
        <div
          className="rounded-lg border overflow-hidden"
          style={{ borderColor: WF_COLORS.border, backgroundColor: `${WF_COLORS.cardBg}80` }}
        >
          {/* Cluster header bar */}
          <div
            className="flex items-center gap-2.5 px-4 py-2.5 border-b"
            style={{ borderColor: WF_COLORS.border, backgroundColor: WF_COLORS.panelBg }}
          >
            <span className="material-symbols-outlined text-base" style={{ color: '#ef4444' }}>
              hub
            </span>
            <span
              className="text-xs font-bold"
              style={{ color: WF_COLORS.labelText, fontFamily: 'DM Sans, Inter, system-ui, sans-serif' }}
            >
              OpenShift Cluster
            </span>
            <span
              className="text-[10px] px-2 py-0.5 rounded font-semibold"
              style={{
                backgroundColor: `${WF_COLORS.amber}15`,
                color: WF_COLORS.amber,
                border: `1px solid ${WF_COLORS.amber}4d`,
              }}
            >
              ecommerce-prod
            </span>
          </div>

          {/* Service topology */}
          <div className="flex items-center gap-0 overflow-x-auto p-6">
            <ServiceNode service={patientZero} />
            <div className="w-8 h-0.5 shrink-0" style={{ backgroundColor: '#ef4444' }} />
            <ServiceNode service={degraded} />
            <svg
              width="70"
              height="260"
              viewBox="0 0 70 260"
              fill="none"
              className="shrink-0"
            >
              <line x1="0" y1="130" x2="68" y2="15" stroke={WF_COLORS.border} strokeWidth="1.5" />
              <line x1="0" y1="130" x2="68" y2="87" stroke={WF_COLORS.border} strokeWidth="1.5" />
              <line x1="0" y1="130" x2="68" y2="170" stroke={WF_COLORS.border} strokeWidth="1.5" />
              <line x1="0" y1="130" x2="68" y2="245" stroke={WF_COLORS.border} strokeWidth="1.5" />
            </svg>
            <div className="flex flex-col gap-2">
              {downstreamServices.map((svc) => (
                <ServiceNode key={svc.name} service={svc} />
              ))}
            </div>
          </div>
        </div>
      </motion.div>

      {/* Context Cards */}
      <motion.div
        variants={fadeUp}
        initial="hidden"
        animate="visible"
        custom={2}
      >
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5">
          {contextCards.map((card) => (
            <div
              key={card.title}
              className="rounded-lg p-4 border"
              style={{
                backgroundColor: WF_COLORS.cardBg,
                borderColor: WF_COLORS.border,
                borderTop: `3px solid ${card.borderColor}`,
              }}
            >
              <div className="flex items-center gap-2 mb-3">
                <span
                  className="material-symbols-outlined text-base"
                  style={{ color: card.borderColor }}
                >
                  {card.icon}
                </span>
                <h4
                  className="text-sm font-bold"
                  style={{ color: WF_COLORS.labelText, fontFamily: 'DM Sans, Inter, system-ui, sans-serif' }}
                >
                  {card.title}
                </h4>
              </div>
              <p className="text-sm leading-relaxed" style={{ color: WF_COLORS.mutedText }}>
                {card.text}
              </p>
            </div>
          ))}
        </div>
      </motion.div>
    </div>
  );
};

export default DemoScenarioTab;
