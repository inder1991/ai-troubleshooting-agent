import { useEffect, useMemo, useState } from 'react';
import type {
  StepSpec,
  CatalogAgentSummary,
  CatalogAgentDetail,
  MappingExpr,
  PredicateExpr,
  RefExpr,
} from '../../../types';
import { getAgentVersion } from '../../../services/catalog';
import { InputMappingField } from './InputMapping/InputMappingField';
import { PredicateBuilder } from './PredicateBuilder/index';
import type { RefSource } from './RefPicker/RefPicker';

// ---- Props ----

interface StepDrawerProps {
  step: StepSpec;
  catalog: CatalogAgentSummary[];
  allSteps: StepSpec[];
  onChange: (step: StepSpec) => void;
  onDelete: () => void;
  onClose: () => void;
}

// ---- Collapsible Section ----

function Section({
  title,
  summary,
  defaultOpen = false,
  children,
}: {
  title: string;
  summary?: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-b border-wr-border">
      <button
        type="button"
        aria-label={title}
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-4 py-3 text-left text-sm font-medium text-wr-text hover:bg-wr-elevated"
      >
        <span className="text-xs text-wr-text-muted">{open ? '▾' : '▸'}</span>
        <span>{title}</span>
        {!open && summary && (
          <span className="ml-auto truncate text-xs text-wr-text-muted">{summary}</span>
        )}
      </button>
      {open && <div className="px-4 pb-4">{children}</div>}
    </div>
  );
}

// ---- Main Component ----

export function StepDrawer({
  step,
  catalog,
  allSteps,
  onChange,
  onDelete,
  onClose,
}: StepDrawerProps) {
  // ---- Agent detail state ----
  const [agentDetail, setAgentDetail] = useState<CatalogAgentDetail | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState(false);

  // Unique agent names from catalog
  const agentNames = useMemo(
    () => [...new Set(catalog.map((c) => c.name))],
    [catalog],
  );

  // Versions for the selected agent, excluding deprecated
  const availableVersions = useMemo(() => {
    const allVersions = catalog
      .filter((c) => c.name === step.agent)
      .map((c) => c.version)
      .sort((a, b) => b - a);
    if (!agentDetail) return allVersions;
    return allVersions.filter((v) => !agentDetail.deprecated_versions.includes(v));
  }, [catalog, step.agent, agentDetail]);

  // Fetch agent detail when agent or version changes
  useEffect(() => {
    let cancelled = false;
    const version =
      step.agent_version === 'latest'
        ? Math.max(...catalog.filter((c) => c.name === step.agent).map((c) => c.version), 1)
        : step.agent_version;

    getAgentVersion(step.agent, version).then((detail) => {
      if (!cancelled) setAgentDetail(detail);
    }).catch(() => {
      if (!cancelled) setAgentDetail(null);
    });

    return () => { cancelled = true; };
  }, [step.agent, step.agent_version, catalog]);

  // ---- RefSources ----
  const refSources: RefSource[] = useMemo(() => {
    const sources: RefSource[] = [
      { kind: 'input', label: 'Workflow Input', schema: {} },
    ];
    const selfIdx = allSteps.findIndex((s) => s.id === step.id);
    for (let i = 0; i < selfIdx; i++) {
      const up = allSteps[i];
      sources.push({
        kind: 'node',
        label: up.id,
        nodeId: up.id,
        schema: {},
      });
    }
    sources.push({ kind: 'env', label: 'Environment', schema: { properties: {} } });
    return sources;
  }, [allSteps, step.id]);

  // ---- Schema stub for PredicateBuilder ----
  const schemaByRef = (_ref: RefExpr) => ({ type: 'string' });

  // ---- Input schema properties ----
  const inputProperties = useMemo(() => {
    if (!agentDetail?.input_schema) return {};
    const schema = agentDetail.input_schema as { properties?: Record<string, Record<string, unknown>> };
    return schema.properties ?? {};
  }, [agentDetail]);

  // ---- Agent section handlers ----
  function handleAgentChange(name: string) {
    // Find latest version for the new agent
    const versions = catalog
      .filter((c) => c.name === name)
      .map((c) => c.version)
      .sort((a, b) => b - a);
    const latestVersion = versions[0] ?? 1;
    onChange({ ...step, agent: name, agent_version: latestVersion, inputs: {} });
  }

  function handleVersionChange(version: number) {
    onChange({ ...step, agent_version: version, inputs: {} });
  }

  // ---- Failure policy ----
  const failurePolicy = step.on_failure ?? 'fail';
  const otherSteps = allSteps.filter((s) => s.id !== step.id);

  // ---- Timeout validation ----
  const contractMax = agentDetail?.timeout_seconds ?? undefined;
  const timeoutValue = step.timeout_seconds_override ?? '';
  const timeoutExceeds =
    contractMax != null &&
    step.timeout_seconds_override != null &&
    step.timeout_seconds_override > contractMax;

  // ---- Fallback validation ----
  const fallbackInvalid =
    failurePolicy === 'fallback' &&
    step.fallback_step_id != null &&
    !allSteps.some((s) => s.id === step.fallback_step_id);

  return (
    <div className="fixed right-0 top-0 z-30 flex h-full w-[400px] flex-col border-l border-wr-border bg-wr-surface-2">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-wr-border px-4 py-3">
        <h2 className="text-sm font-semibold text-wr-text">Step: {step.id}</h2>
        <button
          type="button"
          aria-label="Close"
          onClick={onClose}
          className="text-wr-text-muted hover:text-wr-text"
        >
          &times;
        </button>
      </div>

      {/* Scrollable body */}
      <div className="flex-1 overflow-y-auto">
        {/* Section 1: Agent */}
        <Section
          title="Agent"
          defaultOpen
          summary={`${step.agent} v${step.agent_version}`}
        >
          <div className="flex flex-col gap-3">
            <label className="flex flex-col gap-1 text-xs text-wr-text-muted">
              <span>Select Agent</span>
              <select
                aria-label="Select Agent"
                value={step.agent}
                onChange={(e) => handleAgentChange(e.target.value)}
                className="rounded-md border border-wr-border bg-wr-surface px-2 py-1.5 text-sm text-wr-text"
              >
                {agentNames.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs text-wr-text-muted">
              <span>Version</span>
              <select
                aria-label="Version"
                value={step.agent_version === 'latest' ? '' : step.agent_version}
                onChange={(e) => handleVersionChange(Number(e.target.value))}
                className="rounded-md border border-wr-border bg-wr-surface px-2 py-1.5 text-sm text-wr-text"
              >
                {availableVersions.map((v) => (
                  <option key={v} value={v}>
                    v{v}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </Section>

        {/* Section 2: Inputs */}
        <Section title="Inputs" defaultOpen>
          <div className="flex flex-col gap-4">
            {Object.entries(inputProperties).length === 0 && (
              <p className="text-xs text-wr-text-muted">No input fields available.</p>
            )}
            {Object.entries(inputProperties).map(([fieldName, fieldSchema]) => (
              <InputMappingField
                key={fieldName}
                fieldName={fieldName}
                fieldSchema={fieldSchema as { type?: string; enum?: unknown[] } & Record<string, unknown>}
                value={step.inputs[fieldName]}
                onChange={(v: MappingExpr) =>
                  onChange({ ...step, inputs: { ...step.inputs, [fieldName]: v } })
                }
                refSources={refSources}
              />
            ))}
          </div>
        </Section>

        {/* Section 3: Trigger (When) */}
        <Section title="Trigger">
          <PredicateBuilder
            value={step.when}
            onChange={(when: PredicateExpr | undefined) => onChange({ ...step, when })}
            refSources={refSources}
            schemaByRef={schemaByRef}
          />
        </Section>

        {/* Section 4: Failure Policy */}
        <Section title="Failure Policy">
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-2">
              {(['fail', 'continue', 'fallback'] as const).map((policy) => (
                <label key={policy} className="flex items-center gap-2 text-sm text-wr-text">
                  <input
                    type="radio"
                    name="on_failure"
                    value={policy}
                    checked={failurePolicy === policy}
                    aria-label={policy}
                    onChange={() => {
                      onChange({
                        ...step,
                        on_failure: policy,
                        fallback_step_id: policy === 'fallback' ? (step.fallback_step_id ?? otherSteps[0]?.id) : undefined,
                      });
                    }}
                    className="accent-wr-accent"
                  />
                  <span className="capitalize">{policy}</span>
                </label>
              ))}
            </div>

            {failurePolicy === 'fallback' && (
              <label className="flex flex-col gap-1 text-xs text-wr-text-muted">
                <span>Fallback Step</span>
                <select
                  aria-label="Fallback Step"
                  value={step.fallback_step_id ?? ''}
                  onChange={(e) =>
                    onChange({ ...step, on_failure: 'fallback', fallback_step_id: e.target.value })
                  }
                  className="rounded-md border border-wr-border bg-wr-surface px-2 py-1.5 text-sm text-wr-text"
                >
                  {otherSteps.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.id}
                    </option>
                  ))}
                </select>
              </label>
            )}

            {fallbackInvalid && (
              <p className="text-xs text-wr-status-error">
                Fallback target &quot;{step.fallback_step_id}&quot; does not exist.
              </p>
            )}
          </div>
        </Section>

        {/* Section 5: Execution */}
        <Section title="Execution">
          <div className="flex flex-col gap-4">
            {/* Timeout */}
            <label className="flex flex-col gap-1 text-xs text-wr-text-muted">
              <span>Timeout (seconds)</span>
              <input
                type="number"
                aria-label="Timeout"
                value={timeoutValue}
                min={1}
                onChange={(e) => {
                  const raw = e.target.value;
                  if (raw === '') {
                    onChange({ ...step, timeout_seconds_override: undefined });
                    return;
                  }
                  const n = parseInt(raw, 10);
                  if (!Number.isNaN(n) && n > 0) {
                    onChange({ ...step, timeout_seconds_override: n });
                  }
                }}
                className="rounded-md border border-wr-border bg-wr-surface px-2 py-1.5 text-sm text-wr-text"
              />
              {contractMax != null && (
                <span className="text-xs text-wr-text-muted">Max: {contractMax}s</span>
              )}
              {timeoutExceeds && (
                <span className="text-xs text-wr-status-error">
                  Value exceeds contract max of {contractMax}s
                </span>
              )}
            </label>

            {/* Retry override */}
            {agentDetail?.retry_on && agentDetail.retry_on.length > 0 && (
              <fieldset className="flex flex-col gap-2">
                <legend className="text-xs text-wr-text-muted">Retry On Override</legend>
                {agentDetail.retry_on.map((reason) => (
                  <label key={reason} className="flex items-center gap-2 text-sm text-wr-text">
                    <input
                      type="checkbox"
                      checked={(step.retry_on_override ?? []).includes(reason)}
                      onChange={(e) => {
                        const current = step.retry_on_override ?? [];
                        const next = e.target.checked
                          ? [...current, reason]
                          : current.filter((r) => r !== reason);
                        onChange({ ...step, retry_on_override: next.length > 0 ? next : undefined });
                      }}
                      className="accent-wr-accent"
                    />
                    <span>{reason}</span>
                  </label>
                ))}
              </fieldset>
            )}

            {/* Concurrency group */}
            <label className="flex flex-col gap-1 text-xs text-wr-text-muted">
              <span>Concurrency Group</span>
              <input
                type="text"
                aria-label="Concurrency Group"
                value={step.concurrency_group ?? ''}
                onChange={(e) =>
                  onChange({
                    ...step,
                    concurrency_group: e.target.value || undefined,
                  })
                }
                className="rounded-md border border-wr-border bg-wr-surface px-2 py-1.5 text-sm text-wr-text"
              />
            </label>
          </div>
        </Section>
      </div>

      {/* Footer: Delete */}
      <div className="border-t border-wr-border px-4 py-3">
        {!deleteConfirm ? (
          <button
            type="button"
            aria-label="Delete"
            onClick={() => setDeleteConfirm(true)}
            className="rounded-md bg-red-600 px-3 py-1.5 text-sm text-white hover:bg-red-700"
          >
            Delete Step
          </button>
        ) : (
          <div className="flex items-center gap-2">
            <span className="text-xs text-wr-text">Are you sure?</span>
            <button
              type="button"
              aria-label="Confirm delete"
              onClick={() => {
                setDeleteConfirm(false);
                onDelete();
              }}
              className="rounded-md bg-red-600 px-3 py-1.5 text-sm text-white hover:bg-red-700"
            >
              Confirm
            </button>
            <button
              type="button"
              onClick={() => setDeleteConfirm(false)}
              className="rounded-md border border-wr-border bg-wr-surface px-3 py-1.5 text-sm text-wr-text hover:bg-wr-elevated"
            >
              Cancel
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default StepDrawer;
