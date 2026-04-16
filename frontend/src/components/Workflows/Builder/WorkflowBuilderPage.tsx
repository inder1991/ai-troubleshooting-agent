import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import type {
  WorkflowDetail,
  VersionSummary,
  CatalogAgentSummary,
  StepSpec,
} from '../../../types';
import {
  getWorkflow,
  listVersions,
  getVersion,
  createVersion,
  CompileError,
} from '../../../services/workflows';
import { listAgents } from '../../../services/catalog';
import { useBuilderState } from './useBuilderState';
import { WorkflowHeader } from '../Shared/WorkflowHeader';
import { ValidationBanner } from '../Shared/ValidationBanner';
import type { ValidationError } from '../Shared/ValidationBanner';
import { StepList } from './StepList';
import { StepDrawer } from './StepDrawer';
import { InputsForm } from '../Runs/InputsForm';
import { createRun, InputsInvalidError } from '../../../services/runs';

export function WorkflowBuilderPage() {
  const { workflowId } = useParams<{ workflowId: string }>();
  const navigate = useNavigate();

  // API-fetched data
  const [workflow, setWorkflow] = useState<WorkflowDetail | null>(null);
  const [versions, setVersions] = useState<VersionSummary[]>([]);
  const [catalog, setCatalog] = useState<CatalogAgentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Save state
  const [saving, setSaving] = useState(false);
  const [serverErrors, setServerErrors] = useState<ValidationError[]>([]);
  const [successBanner, setSuccessBanner] = useState(false);
  const successTimer = useRef<ReturnType<typeof setTimeout>>();

  // Run modal
  const [showRunModal, setShowRunModal] = useState(false);
  const [runErrors, setRunErrors] = useState<string[]>([]);

  // Dirty confirm dialog
  const [pendingVersionSwitch, setPendingVersionSwitch] = useState<number | null>(null);

  // Add step dropdown
  const [addStepOpen, setAddStepOpen] = useState(false);

  const builder = useBuilderState();

  // Load workflow, versions, catalog on mount
  useEffect(() => {
    if (!workflowId) return;

    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        const [wf, vers, agents] = await Promise.all([
          getWorkflow(workflowId!),
          listVersions(workflowId!),
          listAgents(),
        ]);

        if (cancelled) return;
        setWorkflow(wf);
        setVersions(vers);
        setCatalog(agents);

        // Load latest version
        if (vers.length > 0) {
          const sorted = [...vers].sort((a, b) => b.version - a.version);
          const latest = sorted[0];
          const versionDetail = await getVersion(workflowId!, latest.version);
          if (!cancelled) {
            builder.loadVersion(versionDetail.dag, latest.version);
          }
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load workflow');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowId]);

  // Cleanup success timer
  useEffect(() => {
    return () => {
      if (successTimer.current) clearTimeout(successTimer.current);
    };
  }, []);

  // ---- Handlers ----

  const handleSave = useCallback(async () => {
    if (!workflowId || saving) return;
    setSaving(true);
    setServerErrors([]);

    try {
      const newVersion = await createVersion(workflowId, builder.draftDag);
      // Refresh versions
      const updatedVersions = await listVersions(workflowId);
      setVersions(updatedVersions);

      // Load the new version
      const versionDetail = await getVersion(workflowId, newVersion.version);
      builder.loadVersion(versionDetail.dag, newVersion.version);

      // Show success
      setSuccessBanner(true);
      successTimer.current = setTimeout(() => setSuccessBanner(false), 3000);
    } catch (err) {
      if (err instanceof CompileError) {
        const mapped: ValidationError[] = [];
        if (err.errors && Array.isArray(err.errors)) {
          for (const e of err.errors) {
            mapped.push({
              path: (e as { path?: string }).path || err.path || 'dag',
              message:
                (e as { message?: string }).message || err.message,
            });
          }
        }
        if (mapped.length === 0) {
          mapped.push({
            path: err.path || 'dag',
            message: err.message,
          });
        }
        setServerErrors(mapped);
      }
    } finally {
      setSaving(false);
    }
  }, [workflowId, saving, builder]);

  const handleRun = useCallback(() => {
    setRunErrors([]);
    setShowRunModal(true);
  }, []);

  const handleRunSubmit = useCallback(
    async (
      inputs: Record<string, unknown>,
      opts: { idempotency_key?: string },
    ) => {
      if (!workflowId) return;
      try {
        const run = await createRun(workflowId, {
          inputs,
          idempotency_key: opts.idempotency_key,
        });
        setShowRunModal(false);
        navigate(`/workflows/runs/${run.id}`, { state: { workflowId } });
      } catch (err) {
        if (err instanceof InputsInvalidError) {
          setRunErrors([err.message, ...err.errors.map((e) => e.message ?? '')].filter(Boolean));
        } else {
          setRunErrors([err instanceof Error ? err.message : 'Failed to create run']);
        }
      }
    },
    [workflowId, navigate],
  );

  const handleVersionSelect = useCallback(
    (version: number) => {
      // This is called by VersionSwitcher's onSelect (View button)
      if (builder.dirty) {
        setPendingVersionSwitch(version);
        return;
      }
      doVersionSwitch(version);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [builder.dirty, workflowId],
  );

  const handleVersionFork = useCallback(
    (version: number) => {
      if (builder.dirty) {
        setPendingVersionSwitch(version);
        return;
      }
      doVersionSwitch(version);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [builder.dirty, workflowId],
  );

  async function doVersionSwitch(version: number) {
    if (!workflowId) return;
    try {
      const versionDetail = await getVersion(workflowId, version);
      builder.loadVersion(versionDetail.dag, version);
      setPendingVersionSwitch(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load version');
    }
  }

  const handleConfirmSwitch = useCallback(() => {
    if (pendingVersionSwitch !== null) {
      doVersionSwitch(pendingVersionSwitch);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingVersionSwitch, workflowId]);

  const handleCancelSwitch = useCallback(() => {
    setPendingVersionSwitch(null);
  }, []);

  const handleAddStep = useCallback(
    (agent: CatalogAgentSummary) => {
      builder.addStep(agent.name, agent.version);
      setAddStepOpen(false);
    },
    [builder],
  );

  const handleStepChange = useCallback(
    (updatedStep: StepSpec) => {
      builder.updateStep(updatedStep.id, updatedStep);
    },
    [builder],
  );

  const handleStepDelete = useCallback(() => {
    if (builder.selectedStepId) {
      builder.removeStep(builder.selectedStepId);
    }
  }, [builder]);

  const handleDrawerClose = useCallback(() => {
    builder.selectStep(null);
  }, [builder]);

  // ---- Derived data ----

  const selectedStep = builder.draftDag.steps.find(
    (s) => s.id === builder.selectedStepId,
  );

  const allErrors = [...builder.clientErrors, ...serverErrors];

  // Build errorsByStepId for StepList
  const errorsByStepId: Record<string, ValidationError[]> = {};
  for (const err of allErrors) {
    // Extract step index from path like "steps[0].agent"
    const match = err.path.match(/^steps\[(\d+)\]/);
    if (match) {
      const idx = parseInt(match[1], 10);
      const step = builder.draftDag.steps[idx];
      if (step) {
        if (!errorsByStepId[step.id]) errorsByStepId[step.id] = [];
        errorsByStepId[step.id].push(err);
      }
    }
  }

  // ---- Render ----

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-wr-text-muted">
        Loading workflow...
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center text-wr-status-error">
        {error}
      </div>
    );
  }

  if (!workflow) {
    return (
      <div className="flex h-full items-center justify-center text-wr-text-muted">
        Workflow not found
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col bg-wr-bg">
      {/* Header */}
      <WorkflowHeader
        workflow={workflow}
        versions={versions}
        activeVersion={versions.length > 0 ? Math.max(...versions.map((v) => v.version)) : undefined}
        selectedVersion={builder.baseVersion ?? undefined}
        baseVersion={builder.dirty ? (builder.baseVersion ?? undefined) : undefined}
        canSave={builder.dirty && !saving}
        onSelectVersion={handleVersionSelect}
        onForkVersion={handleVersionFork}
        onSave={handleSave}
        onRun={handleRun}
        saving={saving}
      />

      {/* Success banner */}
      {successBanner && (
        <div
          data-testid="save-success-banner"
          className="border-b border-wr-border bg-emerald-500/10 px-6 py-2 text-sm text-emerald-400"
          role="status"
        >
          Version saved successfully
        </div>
      )}

      {/* Dirty confirm dialog */}
      {pendingVersionSwitch !== null && (
        <div className="border-b border-wr-border bg-wr-surface px-6 py-3">
          <p className="text-sm text-wr-text">
            You have unsaved changes. Switch version?
          </p>
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              onClick={handleConfirmSwitch}
              className="rounded-md border border-wr-border bg-wr-accent px-3 py-1 text-sm text-wr-on-accent hover:bg-wr-accent-hover"
            >
              Discard &amp; switch
            </button>
            <button
              type="button"
              onClick={handleCancelSwitch}
              className="rounded-md border border-wr-border bg-wr-surface px-3 py-1 text-sm text-wr-text hover:bg-wr-elevated"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Main area: step list + drawer */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left panel: step list + add button */}
        <div className="flex w-1/3 min-w-64 flex-col border-r border-wr-border bg-wr-bg p-4">
          <div className="flex-1 overflow-y-auto">
            <StepList
              steps={builder.draftDag.steps}
              selectedId={builder.selectedStepId ?? undefined}
              onSelect={builder.selectStep}
              onReorder={builder.reorderSteps}
              errorsByStepId={errorsByStepId}
            />
          </div>

          {/* Add step dropdown */}
          <div className="relative mt-4">
            <button
              type="button"
              data-testid="add-step-btn"
              onClick={() => setAddStepOpen((o) => !o)}
              className="w-full rounded-md border border-dashed border-wr-border bg-wr-surface px-3 py-2 text-sm text-wr-text-muted hover:border-wr-accent hover:text-wr-text"
              aria-label="Add step"
            >
              + Add step
            </button>
            {addStepOpen && (
              <div className="absolute bottom-full left-0 mb-1 w-full rounded-md border border-wr-border bg-wr-surface shadow-lg z-10">
                {catalog.map((agent) => (
                  <button
                    key={`${agent.name}-${agent.version}`}
                    type="button"
                    data-testid={`agent-option-${agent.name}`}
                    onClick={() => handleAddStep(agent)}
                    className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-wr-text hover:bg-wr-elevated"
                  >
                    <span>{agent.name}</span>
                    <span className="text-xs text-wr-text-muted">v{agent.version}</span>
                  </button>
                ))}
                {catalog.length === 0 && (
                  <div className="px-3 py-2 text-sm text-wr-text-muted">
                    No agents available
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Right panel: step drawer or placeholder */}
        <div className="flex-1 overflow-y-auto bg-wr-bg" data-testid="drawer-panel">
          {selectedStep ? (
            <div data-testid="step-drawer">
              <StepDrawer
                step={selectedStep}
                catalog={catalog}
                allSteps={builder.draftDag.steps}
                onChange={handleStepChange}
                onDelete={handleStepDelete}
                onClose={handleDrawerClose}
              />
            </div>
          ) : (
            <div className="flex h-full items-center justify-center text-wr-text-muted">
              Select a step to edit
            </div>
          )}
        </div>
      </div>

      {/* Validation banner */}
      {allErrors.length > 0 && (
        <div className="border-t border-wr-border px-6 py-3">
          <ValidationBanner
            errors={allErrors}
            onJump={(stepId) => builder.selectStep(stepId)}
          />
        </div>
      )}

      {/* Run modal */}
      {showRunModal && (
        <InputsForm
          schema={builder.draftDag.inputs_schema as Record<string, unknown>}
          onSubmit={handleRunSubmit}
          onCancel={() => {
            setShowRunModal(false);
            setRunErrors([]);
          }}
          persistKey={`wf-inputs-${workflowId}`}
          serverErrors={runErrors}
        />
      )}
    </div>
  );
}

export default WorkflowBuilderPage;
