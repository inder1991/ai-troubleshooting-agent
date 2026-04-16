"""InvestigationExecutor: conductor that dispatches agent steps through WorkflowExecutor
as 1-node DAGs, maintains an append-only virtual DAG, and emits canonical events."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from src.workflows.compiler import CompiledStep, CompiledWorkflow
from src.workflows.event_schema import StepStatus, ErrorDetail
from src.workflows.investigation_types import (
    InvestigationStepSpec,
    StepResult,
    VirtualStep,
    VirtualDag,
)
from src.workflows.investigation_store import InvestigationStore
from src.workflows.investigation_event_adapter import InvestigationEventAdapter
from src.utils.logger import get_logger

logger = get_logger(__name__)


class InvestigationExecutor:
    def __init__(
        self,
        run_id: str,
        emitter: Any,
        store: InvestigationStore,
        workflow_executor: Any,
    ):
        self._run_id = run_id
        self._dag = VirtualDag(run_id=run_id)
        self._store = store
        self._workflow_executor = workflow_executor
        self._adapter = InvestigationEventAdapter(run_id=run_id, emitter=emitter)

    async def run_step(self, spec: InvestigationStepSpec) -> StepResult:
        now_iso = datetime.now(timezone.utc).isoformat()

        vstep = VirtualStep(
            step_id=spec.step_id,
            agent=spec.agent,
            depends_on=spec.depends_on,
            status=StepStatus.PENDING,
            round=spec.metadata.round if spec.metadata else 0,
            group=spec.metadata.group if spec.metadata else None,
            triggered_by=spec.metadata.hypothesis_id if spec.metadata else None,
            reason=spec.metadata.reason if spec.metadata else None,
        )
        self._dag.append_step(vstep)

        # Mark running and emit
        vstep.status = StepStatus.RUNNING
        vstep.started_at = now_iso
        seq = self._dag.next_sequence()
        await self._adapter.emit_step_update(vstep, sequence_number=seq)
        await self._store.save_dag(self._dag)

        start_mono = time.monotonic()
        try:
            compiled = self._build_single_step_workflow(spec)
            run_result = await self._workflow_executor.run(
                compiled,
                inputs=spec.input_data or {},
            )

            elapsed_ms = round((time.monotonic() - start_mono) * 1000)
            end_iso = datetime.now(timezone.utc).isoformat()

            node_state = run_result.node_states.get(spec.step_id)
            if node_state and node_state.status == "COMPLETED":
                vstep.status = StepStatus.SUCCESS
                vstep.output = node_state.output
                vstep.ended_at = end_iso
                vstep.duration_ms = elapsed_ms
                result = StepResult(
                    step_id=spec.step_id,
                    status=StepStatus.SUCCESS,
                    output=node_state.output,
                    error=None,
                    started_at=vstep.started_at,
                    ended_at=end_iso,
                    duration_ms=elapsed_ms,
                )
            else:
                error_dict = (node_state.error if node_state else None) or run_result.error or {}
                error_detail = ErrorDetail(
                    message=error_dict.get("message", "Unknown error"),
                    type=error_dict.get("type"),
                )
                vstep.status = StepStatus.FAILED
                vstep.error = error_detail
                vstep.ended_at = end_iso
                vstep.duration_ms = elapsed_ms
                result = StepResult(
                    step_id=spec.step_id,
                    status=StepStatus.FAILED,
                    output=None,
                    error=error_detail,
                    started_at=vstep.started_at,
                    ended_at=end_iso,
                    duration_ms=elapsed_ms,
                )

        except Exception as e:
            elapsed_ms = round((time.monotonic() - start_mono) * 1000)
            end_iso = datetime.now(timezone.utc).isoformat()
            error_detail = ErrorDetail(message=str(e), type=type(e).__name__)
            vstep.status = StepStatus.FAILED
            vstep.error = error_detail
            vstep.ended_at = end_iso
            vstep.duration_ms = elapsed_ms
            result = StepResult(
                step_id=spec.step_id,
                status=StepStatus.FAILED,
                output=None,
                error=error_detail,
                started_at=vstep.started_at,
                ended_at=end_iso,
                duration_ms=elapsed_ms,
            )

        # Emit final status and persist
        seq = self._dag.next_sequence()
        await self._adapter.emit_step_update(vstep, sequence_number=seq)
        await self._store.save_dag(self._dag)

        return result

    async def run_steps(self, specs: list[InvestigationStepSpec]) -> list[StepResult]:
        results = []
        for spec in specs:
            results.append(await self.run_step(spec))
        return results

    def get_dag(self) -> VirtualDag:
        return self._dag

    async def cancel(self) -> None:
        self._dag.status = "cancelled"
        seq = self._dag.next_sequence()
        await self._adapter.emit_run_update(status="cancelled", sequence_number=seq)
        await self._store.save_dag(self._dag)

    def _build_single_step_workflow(self, spec: InvestigationStepSpec) -> CompiledWorkflow:
        step = CompiledStep(
            id=spec.step_id,
            agent=spec.agent,
            agent_version=1,
            inputs=spec.input_data or {},
            when=None,
            on_failure="continue",
            fallback_step_id=None,
            parallel_group=None,
            concurrency_group=None,
            timeout_seconds=300.0,
            retry_on=[],
            upstream_ids=[],
        )
        return CompiledWorkflow(
            topo_order=[spec.step_id],
            steps={spec.step_id: step},
            inputs_schema={},
        )
