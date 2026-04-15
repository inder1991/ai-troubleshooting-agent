import React from 'react';
import { motion } from 'framer-motion';
import { sectionFadeUp } from './howItWorksAnimations';

/* ------------------------------------------------------------------ */
/*  Colors                                                             */
/* ------------------------------------------------------------------ */

const C = {
  red: '#ef4444',
  gold: '#e09f3e',
  orange: '#f97316',
  purple: '#a78bfa',
  emerald: '#10b981',
  blue: '#3b82f6',
  yellow: '#eab308',
  gray: '#8a7e6b',
} as const;

/* ------------------------------------------------------------------ */
/*  Data                                                               */
/* ------------------------------------------------------------------ */

const flowBoxes: { label: string; small: string; color: string }[] = [
  { label: 'User Reports', small: 'Incident Form', color: C.gray },
  { label: 'FastAPI', small: 'Session + WS', color: C.gold },
  { label: 'Supervisor', small: 'State Machine', color: C.emerald },
];

const agentCluster: { label: string; color: string }[] = [
  { label: 'Log', color: C.red },
  { label: 'Metrics', color: C.gold },
  { label: 'K8s', color: C.orange },
  { label: 'Tracing', color: C.purple },
  { label: 'Change', color: C.emerald },
];

const postAgentBoxes: { label: string; small: string; color: string }[] = [
  { label: 'Code Agent', small: 'Convergence', color: C.blue },
  { label: 'Critic', small: 'Validation', color: C.purple },
  { label: 'Human Gate', small: 'Attestation', color: C.yellow },
  { label: 'Fix → PR', small: 'GitHub', color: C.emerald },
];

const agents = [
  {
    num: 1,
    name: 'Log Analyzer',
    color: C.red,
    pattern: 'Direct LLM + LogFingerprinter',
    desc: 'Queries Elasticsearch for ERROR/WARN logs. Deduplicates via template fingerprinting. Outputs: primary error pattern, patient zero, service dependencies.',
  },
  {
    num: 2,
    name: 'Metrics Agent',
    color: C.gold,
    pattern: 'ReAct (5 iter) / Two-pass',
    desc: 'Queries Prometheus for RED metrics + saturation. Spike detection via Median Absolute Deviation (MAD) — more robust than stddev for noisy time series.',
  },
  {
    num: 3,
    name: 'K8s Probe',
    color: C.orange,
    pattern: 'ReAct (5 iter) / Turn-based batching',
    desc: 'Turn 1: discover pods + events. Turn 2: deep-dive deployments. Turn 3: synthesize HPA and resource analysis. Detects crashloops, OOMKills, probe failures.',
  },
  {
    num: 4,
    name: 'Tracing Agent',
    color: C.purple,
    pattern: 'ReAct (6 iter) / Two-pass',
    desc: 'Analyzes distributed traces from Jaeger. Identifies slow spans, error propagation paths, and latency bottlenecks across service boundaries.',
  },
  {
    num: 5,
    name: 'Change Intel',
    color: C.emerald,
    pattern: 'ReAct (4 iter) / Two-pass optimized',
    desc: 'Pass 1 (Triage): identify high-risk SHAs. Pass 2 (Analyze): fetch diffs for flagged commits. Stack trace files get automatic risk_score ≥ 0.9.',
  },
  {
    num: 6,
    name: 'Code Navigator',
    color: C.blue,
    pattern: 'ReAct (15 iter) / Two-pass — Convergence',
    desc: 'Receives enriched context from ALL prior agents. Uses GitHub API to navigate codebase. Produces root cause location, call chain, and Mermaid dependency diagram.',
  },
];

const phases = [
  { num: 0, name: 'Session Start', sub: 'User → API', color: C.gray },
  { num: 1, name: 'Log Analysis', sub: 'Direct LLM', color: C.red },
  { num: 2, name: 'Parallel Telemetry', sub: 'asyncio.gather', color: C.gold },
  { num: 3, name: 'Reasoning Chain', sub: 'Causal narrative', color: C.emerald },
  { num: 4, name: 'Code Analysis', sub: 'ReAct 15 iter', color: C.blue },
  { num: 5, name: 'Critic', sub: 'Cross-validate', color: C.purple },
  { num: 6, name: 'Attestation', sub: 'Human gate', color: C.yellow },
  { num: 7, name: 'Fix & PR', sub: '6-step pipeline', color: C.emerald },
];

const fixSteps: { name: string; sub: string; color: string; type?: 'no-llm' | 'human' }[] = [
  { name: 'Fix Generator', sub: 'LLM — multi-file', color: C.emerald },
  { name: 'Static Validator', sub: 'No LLM — AST + ruff', color: C.gray, type: 'no-llm' },
  { name: 'Cross-Agent Reviewer', sub: 'LLM — peer review', color: C.emerald },
  { name: 'Impact Assessor', sub: 'LLM + heuristic', color: C.emerald },
  { name: 'PR Stager', sub: 'No LLM — git ops', color: C.gray, type: 'no-llm' },
  { name: 'Human Approval', sub: 'Approve / Reject', color: C.yellow, type: 'human' },
];

const gates: { name: string; when: string; why: string }[] = [
  { name: 'Repo Confirmation', when: 'After metrics', why: 'User confirms which repos to analyze' },
  { name: 'Code Agent Questions', when: 'During code analysis', why: 'Agent asks for disambiguation via ask_human' },
  { name: 'Discovery Attestation', when: 'After all agents', why: 'User reviews findings before remediation' },
  { name: 'Fix Approval', when: 'After fix generated', why: 'User approves, rejects, or provides feedback' },
  { name: 'Campaign Execute', when: 'All repos approved', why: 'Master gate before creating PRs' },
];

const components: { num: number; name: string; pattern: string; llm: string }[] = [
  { num: 0, name: 'Intent Detector', pattern: 'Direct LLM', llm: 'Yes (Ollama)' },
  { num: 1, name: 'Log Analyzer', pattern: 'Direct LLM + Fingerprinter', llm: 'Yes' },
  { num: 2, name: 'Code Agent', pattern: 'ReAct (15 iter) / Two-pass', llm: 'Yes' },
  { num: 3, name: 'Change Agent', pattern: 'ReAct (4 iter) / Two-pass', llm: 'Yes' },
  { num: 4, name: 'Metrics Agent', pattern: 'ReAct (5 iter) / Two-pass', llm: 'Yes' },
  { num: 5, name: 'K8s Agent', pattern: 'ReAct (5 iter) / Two-pass', llm: 'Yes' },
  { num: 6, name: 'Tracing Agent', pattern: 'ReAct (6 iter) / Two-pass', llm: 'Yes' },
  { num: 7, name: 'Critic Agent', pattern: 'Direct LLM', llm: 'Yes' },
  { num: 8, name: 'Fix Generator', pattern: 'Two-phase workflow', llm: 'Yes' },
  { num: 9, name: 'Impact Assessor', pattern: 'LLM + heuristic', llm: 'Yes' },
  { num: 10, name: 'Cross-Agent Reviewer', pattern: 'LLM + heuristic', llm: 'Yes' },
  { num: 11, name: 'Static Validator', pattern: 'AST + ruff', llm: 'No' },
  { num: 12, name: 'PR Stager', pattern: 'Git operations', llm: 'No' },
  { num: 13, name: 'Supervisor', pattern: 'State machine orchestrator', llm: 'No (routes)' },
];

const stack = [
  { label: 'Backend', items: 'Python FastAPI, async/await' },
  { label: 'LLM', items: 'Anthropic Claude (configurable)' },
  { label: 'Frontend', items: 'React + TS + Vite + Tailwind' },
  { label: 'Real-time', items: 'WebSocket for events & HITL' },
  { label: 'Telemetry', items: 'Elasticsearch, Prometheus, K8s, Jaeger' },
  { label: 'Code Ops', items: 'GitHub API, git subprocess' },
  { label: 'Validation', items: 'Python AST, ruff linter' },
  { label: 'Campaign', items: 'Multi-repo with per-repo approval' },
];

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

const Arrow = () => <span className="text-slate-400 text-xs font-bold select-none">&rarr;</span>;

const SectionTitle: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <h3 className="text-sm font-bold text-slate-300 uppercase tracking-wider mb-3">{children}</h3>
);

const FlowBox: React.FC<{ label: string; small: string; color: string }> = ({ label, small, color }) => (
  <div
    className="px-3 py-1.5 rounded border text-center"
    style={{ borderColor: color, backgroundColor: `${color}10` }}
  >
    <span className="text-xs font-mono font-bold block" style={{ color }}>{label}</span>
    <span className="text-body-xs text-slate-400 block leading-tight">{small}</span>
  </div>
);

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

const ArchitectureTab: React.FC = () => {
  return (
    <div className="space-y-10">

      {/* ---- 1. High-Level Flow ---- */}
      <motion.div
        variants={sectionFadeUp}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, amount: 0.2 }}
        custom={0}
      >
        <SectionTitle>High-Level Flow</SectionTitle>
        <div className="flex items-center gap-2 flex-wrap">
          {/* Pre-agent boxes */}
          {flowBoxes.map((box, i) => (
            <React.Fragment key={box.label}>
              {i > 0 && <Arrow />}
              <FlowBox label={box.label} small={box.small} color={box.color} />
            </React.Fragment>
          ))}

          <Arrow />

          {/* Agent cluster */}
          <span className="flex items-center gap-1.5 px-2 py-1 rounded border border-[#3d3528] bg-wr-bg/50">
            {agentCluster.map((a) => (
              <span
                key={a.label}
                className="px-3 py-1.5 rounded text-xs font-mono font-bold border"
                style={{
                  color: a.color,
                  borderColor: a.color,
                  backgroundColor: `${a.color}15`,
                }}
              >
                {a.label}
              </span>
            ))}
          </span>

          <Arrow />

          {/* Post-agent boxes */}
          {postAgentBoxes.map((box, i) => (
            <React.Fragment key={box.label}>
              {i > 0 && <Arrow />}
              <FlowBox label={box.label} small={box.small} color={box.color} />
            </React.Fragment>
          ))}
        </div>
      </motion.div>

      {/* ---- 2. Investigation Agents ---- */}
      <motion.div
        variants={sectionFadeUp}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, amount: 0.2 }}
        custom={1}
      >
        <SectionTitle>6 Investigation Agents</SectionTitle>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3.5">
          {agents.map((agent) => (
            <div
              key={agent.num}
              className="rounded-lg p-3.5 bg-wr-bg/50 border border-[#3d3528]"
              style={{ borderTopWidth: 3, borderTopColor: agent.color }}
            >
              <div className="flex items-center gap-2.5 mb-2">
                <span
                  className="w-6 h-6 rounded-full flex items-center justify-center text-body-xs font-bold text-white shrink-0"
                  style={{ backgroundColor: agent.color }}
                >
                  {agent.num}
                </span>
                <span className="text-sm font-bold text-white">{agent.name}</span>
              </div>
              <p className="text-body-xs font-mono text-slate-400 mb-1.5">{agent.pattern}</p>
              <p className="text-xs text-slate-400 leading-relaxed">{agent.desc}</p>
            </div>
          ))}
        </div>
      </motion.div>

      {/* ---- 3. Execution Phases (connected pipeline) ---- */}
      <motion.div
        variants={sectionFadeUp}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, amount: 0.2 }}
        custom={2}
      >
        <SectionTitle>Execution Phases</SectionTitle>
        <div className="flex flex-wrap" style={{ gap: 0 }}>
          {phases.map((phase, i) => {
            const isFirst = i === 0;
            const isLast = i === phases.length - 1;
            return (
              <div
                key={phase.num}
                className={`flex items-center gap-2 px-3 py-2 bg-wr-bg/50 border border-[#3d3528] ${
                  isFirst ? 'rounded-l-lg' : ''
                } ${isLast ? 'rounded-r-lg' : ''}`}
                style={{ borderLeftWidth: isFirst ? 1 : 0 }}
              >
                <span
                  className="w-5 h-5 rounded-full flex items-center justify-center text-body-xs font-bold text-white shrink-0"
                  style={{ backgroundColor: phase.color }}
                >
                  {phase.num}
                </span>
                <div className="flex flex-col">
                  <span className="text-xs font-bold text-slate-200 leading-tight">{phase.name}</span>
                  <span className="text-body-xs text-slate-400 leading-tight">{phase.sub}</span>
                </div>
                {!isLast && (
                  <span className="text-slate-400 text-sm font-bold ml-1 select-none">&rsaquo;</span>
                )}
              </div>
            );
          })}
        </div>
      </motion.div>

      {/* ---- 4. Fix Generation Pipeline ---- */}
      <motion.div
        variants={sectionFadeUp}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, amount: 0.2 }}
        custom={3}
      >
        <SectionTitle>Fix Generation Pipeline</SectionTitle>
        <div className="flex flex-wrap items-center gap-2">
          {fixSteps.map((step, i) => {
            const isNoLlm = step.type === 'no-llm';
            const isHuman = step.type === 'human';
            return (
              <React.Fragment key={step.name}>
                {i > 0 && <Arrow />}
                <div
                  className={`px-3 py-2 rounded border text-center ${
                    isNoLlm
                      ? 'border-wr-border-strong bg-wr-surface/60'
                      : isHuman
                        ? 'border-yellow-700 bg-yellow-950/30'
                        : 'bg-wr-bg/50 border-[#3d3528]'
                  }`}
                  style={{
                    borderColor: isNoLlm ? undefined : step.color,
                  }}
                >
                  <span
                    className="text-xs font-bold block"
                    style={{ color: step.color }}
                  >
                    {step.name}
                  </span>
                  <span className="text-body-xs text-slate-400 block leading-tight">{step.sub}</span>
                </div>
              </React.Fragment>
            );
          })}
        </div>
      </motion.div>

      {/* ---- 5. Human-in-the-Loop Gates ---- */}
      <motion.div
        variants={sectionFadeUp}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, amount: 0.2 }}
        custom={4}
      >
        <SectionTitle>Human-in-the-Loop Gates</SectionTitle>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2.5">
          {gates.map((gate, i) => (
            <div
              key={gate.name}
              className="bg-wr-bg/50 border border-[#3d3528] rounded-lg p-3"
              style={{ borderTopWidth: 3, borderTopColor: C.yellow }}
            >
              <div className="flex items-center gap-2 mb-2">
                <span
                  className="w-5 h-5 rounded-full flex items-center justify-center text-body-xs font-bold text-white shrink-0"
                  style={{ backgroundColor: C.yellow }}
                >
                  {i + 1}
                </span>
                <span className="text-xs font-bold text-slate-200">{gate.name}</span>
              </div>
              <p className="text-body-xs text-slate-400 mb-0.5">
                <span className="font-semibold text-slate-400">When:</span> {gate.when}
              </p>
              <p className="text-body-xs text-slate-400">
                <span className="font-semibold text-slate-400">Why:</span> {gate.why}
              </p>
            </div>
          ))}
        </div>
      </motion.div>

      {/* ---- 6. Components Table ---- */}
      <motion.div
        variants={sectionFadeUp}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, amount: 0.2 }}
        custom={5}
      >
        <SectionTitle>14 Total Components</SectionTitle>
        <div className="overflow-x-auto rounded-lg border border-[#3d3528]">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-[#e09f3e]/10 text-[#e09f3e]">
                <th className="px-3 py-2 text-left font-bold">#</th>
                <th className="px-3 py-2 text-left font-bold">Component</th>
                <th className="px-3 py-2 text-left font-bold">Pattern</th>
                <th className="px-3 py-2 text-left font-bold">LLM?</th>
              </tr>
            </thead>
            <tbody>
              {components.map((c) => (
                <tr
                  key={c.num}
                  className={c.num % 2 === 0 ? 'bg-wr-bg/60' : 'bg-wr-bg/30'}
                >
                  <td className="px-3 py-2 text-slate-400 font-mono">{c.num}</td>
                  <td className="px-3 py-2 text-slate-200 font-semibold">{c.name}</td>
                  <td className="px-3 py-2 text-slate-400 font-mono">{c.pattern}</td>
                  <td className="px-3 py-2">
                    {c.llm.startsWith('Yes') ? (
                      <span className="text-[#e09f3e] font-bold">{c.llm}</span>
                    ) : (
                      <span className="text-slate-500">{c.llm}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </motion.div>

      {/* ---- 7. Tech Stack ---- */}
      <motion.div
        variants={sectionFadeUp}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, amount: 0.2 }}
        custom={6}
      >
        <SectionTitle>Tech Stack</SectionTitle>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
          {stack.map((s) => (
            <div
              key={s.label}
              className="bg-wr-bg/50 border border-[#3d3528] rounded-lg p-3"
            >
              <span className="text-xs font-bold text-white block mb-1">{s.label}</span>
              <span className="text-xs text-slate-400">{s.items}</span>
            </div>
          ))}
        </div>
      </motion.div>

    </div>
  );
};

export default ArchitectureTab;
