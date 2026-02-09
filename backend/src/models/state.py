"""
State definitions for the troubleshooting system
"""

from typing import TypedDict, Annotated, List, Optional, Dict, Any
import operator


class TroubleshootingState(TypedDict):
    """
    Central state that flows through the graph.
    LangGraph automatically manages this state across nodes.
    """
    # Input
    raw_logs: str
    elk_index: str
    github_repo: str
    timeframe: str
    error_filter: Optional[str]
    repo_path: str
    
    # Agent 1 outputs (Log Analysis)
    correlation_id: Optional[str]
    exception_type: Optional[str]
    exception_message: Optional[str]
    stack_trace: Optional[str]
    preliminary_rca: Optional[str]
    affected_components: List[str]
    log_count: int
    aggregated_logs: Optional[str]
    
    # Agent 2 outputs (Code Navigation)
    root_cause_location: Optional[str]
    call_chain: List[str]
    relevant_files: List[str]
    code_snippets: Dict[str, str]
    flowchart_mermaid: Optional[str]
    dependencies: List[str]
    
    # Agent 3 outputs (Fix Generation)
    proposed_changes: Dict[str, str]
    fix_explanation: Optional[str]
    test_suggestions: List[str]
    pr_description: Optional[str]
    pr_title: Optional[str]
    
    # Control flow
    next_action: Optional[str]
    human_approval_required: bool
    confidence_score: float
    error_occurred: bool
    error_message: Optional[str]
    
    # Conversation history
    messages: Annotated[List[Any], operator.add]
