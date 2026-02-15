from langgraph.graph import StateGraph, END
from typing import TypedDict, Optional, Annotated, Any
import operator


class WorkflowState(TypedDict):
    """LangGraph state for the diagnostic workflow."""
    session_id: str
    service_name: str
    trace_id: Optional[str]
    time_start: str
    time_end: str
    namespace: Optional[str]
    cluster_url: Optional[str]
    repo_url: Optional[str]
    elk_index: str

    # Results accumulate
    phase: str
    agents_completed: Annotated[list[str], operator.add]
    results: dict[str, Any]
    overall_confidence: int
    is_complete: bool


def supervisor_node(state: WorkflowState) -> dict:
    """Supervisor node — determines next step."""
    # This is a thin wrapper. The actual orchestration happens in SupervisorAgent.
    # In the LangGraph wiring, the Supervisor node routes to the appropriate agent.
    return state


def log_agent_node(state: WorkflowState) -> dict:
    """Log Agent node placeholder — actual execution via SupervisorAgent._dispatch_agent."""
    return {"agents_completed": ["log_agent"], "phase": "logs_analyzed"}


def metrics_agent_node(state: WorkflowState) -> dict:
    return {"agents_completed": ["metrics_agent"], "phase": "metrics_analyzed"}


def k8s_agent_node(state: WorkflowState) -> dict:
    return {"agents_completed": ["k8s_agent"], "phase": "k8s_analyzed"}


def tracing_agent_node(state: WorkflowState) -> dict:
    return {"agents_completed": ["tracing_agent"], "phase": "tracing_analyzed"}


def code_agent_node(state: WorkflowState) -> dict:
    return {"agents_completed": ["code_agent"], "phase": "code_analyzed"}


def critic_node(state: WorkflowState) -> dict:
    return state


def route_from_supervisor(state: WorkflowState) -> str:
    """Conditional routing from supervisor based on state."""
    if state.get("is_complete", False):
        return END

    phase = state.get("phase", "initial")
    completed = state.get("agents_completed", [])

    if phase == "initial":
        return "log_agent"
    elif phase == "logs_analyzed" and "metrics_agent" not in completed:
        return "metrics_agent"
    elif phase == "metrics_analyzed":
        if state.get("trace_id") and "tracing_agent" not in completed:
            return "tracing_agent"
        if state.get("repo_url") and "code_agent" not in completed:
            return "code_agent"
        return END
    elif phase == "k8s_analyzed":
        if state.get("trace_id") and "tracing_agent" not in completed:
            return "tracing_agent"
        if state.get("repo_url") and "code_agent" not in completed:
            return "code_agent"
        return END
    elif phase == "tracing_analyzed":
        if state.get("repo_url") and "code_agent" not in completed:
            return "code_agent"
        return END
    elif phase == "code_analyzed":
        return END

    return END


def build_workflow() -> StateGraph:
    """Build the LangGraph workflow."""
    workflow = StateGraph(WorkflowState)

    # Add nodes
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("log_agent", log_agent_node)
    workflow.add_node("metrics_agent", metrics_agent_node)
    workflow.add_node("k8s_agent", k8s_agent_node)
    workflow.add_node("tracing_agent", tracing_agent_node)
    workflow.add_node("code_agent", code_agent_node)
    workflow.add_node("critic", critic_node)

    # Set entry point
    workflow.set_entry_point("supervisor")

    # Add conditional edges from supervisor
    workflow.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "log_agent": "log_agent",
            "metrics_agent": "metrics_agent",
            "k8s_agent": "k8s_agent",
            "tracing_agent": "tracing_agent",
            "code_agent": "code_agent",
            END: END,
        },
    )

    # Each agent goes to critic, critic goes back to supervisor
    for agent in ["log_agent", "metrics_agent", "k8s_agent", "tracing_agent", "code_agent"]:
        workflow.add_edge(agent, "critic")
    workflow.add_edge("critic", "supervisor")

    return workflow
