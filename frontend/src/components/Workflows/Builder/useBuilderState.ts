import { useCallback, useMemo, useReducer } from 'react';
import type { WorkflowDag, StepSpec } from '../../../types';
import type { ValidationError } from './builderTypes';

// ---- Public interface ----

export interface BuilderState {
  draftDag: WorkflowDag;
  baseVersion: number | null;
  clientErrors: ValidationError[];
  dirty: boolean;
  selectedStepId: string | null;

  setDraftDag(dag: WorkflowDag): void;
  addStep(agent: string, agentVersion: number): void;
  updateStep(id: string, patch: Partial<StepSpec>): void;
  removeStep(id: string): void;
  reorderSteps(newSteps: StepSpec[]): void;
  selectStep(id: string | null): void;
  loadVersion(dag: WorkflowDag, version: number): void;
  markClean(): void;
}

// ---- Internal state / actions ----

interface InternalState {
  draftDag: WorkflowDag;
  baseVersion: number | null;
  dirty: boolean;
  selectedStepId: string | null;
}

type Action =
  | { type: 'SET_DAG'; dag: WorkflowDag }
  | { type: 'ADD_STEP'; agent: string; agentVersion: number; generatedId: string }
  | { type: 'UPDATE_STEP'; id: string; patch: Partial<StepSpec> }
  | { type: 'REMOVE_STEP'; id: string }
  | { type: 'REORDER_STEPS'; steps: StepSpec[] }
  | { type: 'SELECT_STEP'; id: string | null }
  | { type: 'LOAD_VERSION'; dag: WorkflowDag; version: number }
  | { type: 'MARK_CLEAN' };

function generateStepId(): string {
  return `step_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
}

function reducer(state: InternalState, action: Action): InternalState {
  switch (action.type) {
    case 'SET_DAG':
      return { ...state, draftDag: action.dag, dirty: true };

    case 'ADD_STEP': {
      const newStep: StepSpec = {
        id: action.generatedId,
        agent: action.agent,
        agent_version: action.agentVersion,
        inputs: {},
      };
      return {
        ...state,
        draftDag: {
          ...state.draftDag,
          steps: [...state.draftDag.steps, newStep],
        },
        dirty: true,
        selectedStepId: action.generatedId,
      };
    }

    case 'UPDATE_STEP': {
      const steps = state.draftDag.steps.map((s) =>
        s.id === action.id ? { ...s, ...action.patch } : s,
      );
      return {
        ...state,
        draftDag: { ...state.draftDag, steps },
        dirty: true,
      };
    }

    case 'REMOVE_STEP': {
      const steps = state.draftDag.steps.filter((s) => s.id !== action.id);
      const selectedStepId =
        state.selectedStepId === action.id ? null : state.selectedStepId;
      return {
        ...state,
        draftDag: { ...state.draftDag, steps },
        dirty: true,
        selectedStepId,
      };
    }

    case 'REORDER_STEPS':
      return {
        ...state,
        draftDag: { ...state.draftDag, steps: action.steps },
        dirty: true,
      };

    case 'SELECT_STEP':
      return { ...state, selectedStepId: action.id };

    case 'LOAD_VERSION':
      return {
        ...state,
        draftDag: action.dag,
        baseVersion: action.version,
        dirty: false,
        selectedStepId: null,
      };

    case 'MARK_CLEAN':
      return { ...state, dirty: false };

    default:
      return state;
  }
}

function computeClientErrors(dag: WorkflowDag): ValidationError[] {
  const errors: ValidationError[] = [];

  if (dag.steps.length === 0) {
    errors.push({
      path: 'steps',
      message: 'Add at least one step',
    });
    return errors;
  }

  const seenIds = new Set<string>();
  const allIds = new Set(dag.steps.map((s) => s.id));

  for (let i = 0; i < dag.steps.length; i++) {
    const step = dag.steps[i];

    if (!step.id) {
      errors.push({
        path: `steps[${i}].id`,
        message: 'Step id must not be empty',
      });
    } else if (seenIds.has(step.id)) {
      errors.push({
        path: `steps[${i}].id`,
        message: `Duplicate step id: ${step.id}`,
      });
    } else {
      seenIds.add(step.id);
    }

    if (!step.agent) {
      errors.push({
        path: `steps[${i}].agent`,
        message: 'Step agent must not be empty',
      });
    }

    if (step.fallback_step_id && !allIds.has(step.fallback_step_id)) {
      errors.push({
        path: `steps[${i}].fallback_step_id`,
        message: `Fallback step "${step.fallback_step_id}" does not exist`,
      });
    }
  }

  return errors;
}

// ---- Hook ----

const INITIAL_STATE: InternalState = {
  draftDag: { inputs_schema: {}, steps: [] },
  baseVersion: null,
  dirty: false,
  selectedStepId: null,
};

export function useBuilderState(): BuilderState {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE);

  const clientErrors = useMemo(
    () => computeClientErrors(state.draftDag),
    [state.draftDag],
  );

  const setDraftDag = useCallback(
    (dag: WorkflowDag) => dispatch({ type: 'SET_DAG', dag }),
    [],
  );

  const addStep = useCallback(
    (agent: string, agentVersion: number) =>
      dispatch({ type: 'ADD_STEP', agent, agentVersion, generatedId: generateStepId() }),
    [],
  );

  const updateStep = useCallback(
    (id: string, patch: Partial<StepSpec>) =>
      dispatch({ type: 'UPDATE_STEP', id, patch }),
    [],
  );

  const removeStep = useCallback(
    (id: string) => dispatch({ type: 'REMOVE_STEP', id }),
    [],
  );

  const reorderSteps = useCallback(
    (newSteps: StepSpec[]) => dispatch({ type: 'REORDER_STEPS', steps: newSteps }),
    [],
  );

  const selectStep = useCallback(
    (id: string | null) => dispatch({ type: 'SELECT_STEP', id }),
    [],
  );

  const loadVersion = useCallback(
    (dag: WorkflowDag, version: number) =>
      dispatch({ type: 'LOAD_VERSION', dag, version }),
    [],
  );

  const markClean = useCallback(() => dispatch({ type: 'MARK_CLEAN' }), []);

  return {
    draftDag: state.draftDag,
    baseVersion: state.baseVersion,
    clientErrors,
    dirty: state.dirty,
    selectedStepId: state.selectedStepId,
    setDraftDag,
    addStep,
    updateStep,
    removeStep,
    reorderSteps,
    selectStep,
    loadVersion,
    markClean,
  };
}
