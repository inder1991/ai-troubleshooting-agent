import { useState, useCallback, useMemo } from 'react';
import { parseWorkflowYaml } from './workflowParser';
import { stateToYaml } from './workflowSerializer';
import type { ParsedWorkflow, WorkflowStep } from './workflowParser';

const LS_KEY = 'platform_workflow_builder_yaml';

export function useWorkflowState(initialYaml: string) {
  const [yaml, setYamlRaw] = useState(initialYaml);
  const [dirty, setDirty] = useState(false);

  const parsed = useMemo(() => parseWorkflowYaml(yaml), [yaml]);

  // Update YAML directly (from Code view)
  const setYaml = useCallback((newYaml: string) => {
    setYamlRaw(newYaml);
    setDirty(true);
  }, []);

  // Derive new YAML from a mutated ParsedWorkflow, update state
  const applyState = useCallback((next: ParsedWorkflow) => {
    const newYaml = stateToYaml(next);
    setYamlRaw(newYaml);
    setDirty(true);
  }, []);

  const updateWorkflowMeta = useCallback((fields: Partial<Pick<ParsedWorkflow, 'id' | 'name'>>) => {
    applyState({ ...parsed, ...fields });
  }, [parsed, applyState]);

  const addStep = useCallback((agent: string) => {
    const id = `step_${Date.now()}`;
    const newStep: WorkflowStep = {
      id,
      agent,
      depends_on: [],
      label: agent.replace(/_agent$/, '').replace(/_/g, ' '),
    };
    applyState({ ...parsed, steps: [...parsed.steps, newStep] });
    return id;
  }, [parsed, applyState]);

  const updateStep = useCallback((stepId: string, fields: Partial<WorkflowStep>) => {
    const steps = parsed.steps.map(s =>
      s.id === stepId ? { ...s, ...fields } : s
    );
    applyState({ ...parsed, steps });
  }, [parsed, applyState]);

  const removeStep = useCallback((stepId: string) => {
    const steps = parsed.steps
      .filter(s => s.id !== stepId)
      .map(s => ({
        ...s,
        depends_on: s.depends_on.filter(d => d !== stepId),
      }));
    applyState({ ...parsed, steps });
  }, [parsed, applyState]);

  const moveStep = useCallback((fromIndex: number, toIndex: number) => {
    const steps = [...parsed.steps];
    const [moved] = steps.splice(fromIndex, 1);
    steps.splice(toIndex, 0, moved);
    applyState({ ...parsed, steps });
  }, [parsed, applyState]);

  const save = useCallback(() => {
    localStorage.setItem(LS_KEY, yaml);
    setDirty(false);
    return { id: parsed.id, name: parsed.name, yaml };
  }, [yaml, parsed]);

  return {
    yaml,
    parsed,
    dirty,
    setYaml,
    updateWorkflowMeta,
    addStep,
    updateStep,
    removeStep,
    moveStep,
    save,
  };
}
