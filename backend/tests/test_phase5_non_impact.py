"""Phase 5 non-impact: verify existing systems are untouched."""


def test_workflow_executor_import_unchanged():
    from src.workflows.executor import WorkflowExecutor, NodeState, RunResult
    assert WorkflowExecutor is not None
    assert NodeState is not None


def test_workflow_compiler_import_unchanged():
    from src.workflows.compiler import CompiledStep, CompiledWorkflow
    assert CompiledStep is not None


def test_supervisor_still_works_without_executor():
    from src.agents.supervisor import SupervisorAgent
    s = SupervisorAgent(connection_config={})
    assert s._investigation_executor is None


def test_event_emitter_unchanged():
    from src.utils.event_emitter import EventEmitter
    e = EventEmitter(session_id="test")
    assert hasattr(e, 'emit')
    assert hasattr(e, 'get_all_events')


def test_redis_store_unchanged():
    from src.utils.redis_store import RedisSessionStore
    assert hasattr(RedisSessionStore, 'save')
    assert hasattr(RedisSessionStore, 'load')


def test_new_modules_importable():
    from src.workflows.event_schema import EventEnvelope, StepPayload, RunPayload, StepStatus
    from src.workflows.investigation_types import InvestigationStepSpec, StepResult, VirtualDag, VirtualStep
    from src.workflows.investigation_store import InvestigationStore
    from src.workflows.investigation_executor import InvestigationExecutor
    from src.workflows.investigation_event_adapter import InvestigationEventAdapter
    from src.workflows.runners.investigation_runner import InvestigationAgentRunner
    assert True
