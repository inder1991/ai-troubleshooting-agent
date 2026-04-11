"""Tools for the DebugDuck AI Assistant."""
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def list_sessions(sessions: dict) -> dict:
    """List all investigation sessions with status and findings."""
    result = []
    for sid, data in sessions.items():
        state = data.get("state")
        findings_count = 0
        critical_count = 0
        if state and isinstance(state, dict):
            findings = state.get("findings", [])
            findings_count = len(findings)
            critical_count = sum(1 for f in findings if f.get("severity") == "critical")
        elif state and hasattr(state, "all_findings"):
            findings_count = len(state.all_findings)
            critical_count = sum(1 for f in state.all_findings if getattr(f, "severity", "") == "critical")

        result.append({
            "session_id": sid,
            "incident_id": data.get("incident_id", ""),
            "service_name": data.get("service_name", ""),
            "phase": data.get("phase", ""),
            "confidence": data.get("confidence", 0),
            "capability": data.get("capability", ""),
            "created_at": data.get("created_at", ""),
            "findings_count": findings_count,
            "critical_count": critical_count,
        })
    return {"sessions": result, "total": len(result)}


async def get_session_detail(sessions: dict, session_id: str) -> dict:
    """Get detailed findings and dossier for a specific session."""
    session = sessions.get(session_id)
    if not session:
        return {"error": f"Session {session_id} not found"}

    state = session.get("state")
    dossier = state.get("dossier") if isinstance(state, dict) else None
    fix_recs = state.get("fix_recommendations", []) if isinstance(state, dict) else []
    findings = state.get("findings", []) if isinstance(state, dict) else []

    return {
        "session_id": session_id,
        "incident_id": session.get("incident_id", ""),
        "service_name": session.get("service_name", ""),
        "phase": session.get("phase", ""),
        "confidence": session.get("confidence", 0),
        "findings_count": len(findings),
        "findings_summary": [
            {"title": f.get("title", ""), "severity": f.get("severity", ""), "recommendation": f.get("recommendation", "")}
            for f in findings[:10]
        ],
        "root_cause": dossier.get("root_cause_analysis", {}).get("primary_root_cause", "") if dossier else "",
        "fix_recommendations": [
            {"title": r.get("title", ""), "sql": r.get("sql", ""), "warning": r.get("warning", "")}
            for r in fix_recs[:5]
        ],
    }


async def search_sessions(sessions: dict, query: str) -> dict:
    """Search sessions by service name, incident ID, or capability."""
    query_lower = query.lower()
    matches = []
    for sid, data in sessions.items():
        if (query_lower in data.get("service_name", "").lower()
            or query_lower in data.get("incident_id", "").lower()
            or query_lower in data.get("capability", "").lower()
            or query_lower in sid.lower()):
            matches.append({
                "session_id": sid,
                "incident_id": data.get("incident_id", ""),
                "service_name": data.get("service_name", ""),
                "phase": data.get("phase", ""),
                "capability": data.get("capability", ""),
            })
    return {"matches": matches[:10], "total": len(matches)}


async def get_environment_health(health_fn) -> dict:
    """Get current system health status."""
    try:
        # This would call the same logic as fetchEnvironmentHealth
        from src.api.routes_v4 import sessions
        total = 0
        # Simplified — in production, wire to real health data
        return {"status": "operational", "total_systems": 18, "healthy": 16, "issues": 2}
    except Exception as e:
        return {"error": str(e)}


async def start_investigation(sessions: dict, capability: str, service_name: str = "", profile_id: str = "", **kwargs) -> dict:
    """Start a new investigation. Returns the session ID and incident ID."""
    # This will be called by the orchestrator which has access to the real start_session logic
    return {
        "action": "start_investigation",
        "capability": capability,
        "service_name": service_name,
        "profile_id": profile_id,
        "params": kwargs,
    }


async def cancel_investigation(sessions: dict, session_id: str) -> dict:
    """Cancel a running investigation."""
    session = sessions.get(session_id)
    if not session:
        return {"error": f"Session {session_id} not found"}
    if session.get("phase") in ("complete", "error", "cancelled"):
        return {"error": f"Session already {session.get('phase')}"}
    session["phase"] = "cancelled"
    session["_cancelled"] = True
    return {"status": "cancelled", "session_id": session_id}


async def get_fix_recommendations(sessions: dict, session_id: str) -> dict:
    """Get fix recommendations with SQL for a session."""
    session = sessions.get(session_id)
    if not session:
        return {"error": f"Session {session_id} not found"}
    state = session.get("state")
    if not state or not isinstance(state, dict):
        return {"fixes": []}
    fixes = state.get("fix_recommendations", [])
    return {"fixes": fixes[:10], "total": len(fixes)}


# Tool definitions for Anthropic API
ASSISTANT_TOOLS = [
    {
        "name": "list_sessions",
        "description": "List all investigation sessions with their status, findings count, and critical count. Use to answer questions about what investigations exist.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_session_detail",
        "description": "Get detailed findings, root cause, and fix recommendations for a specific investigation session. Use when the user asks about a specific investigation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "The session ID or incident ID to look up"},
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "search_sessions",
        "description": "Search investigations by service name, incident ID, or capability type. Use when the user asks about a specific service or incident.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term (service name, incident ID, or capability)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "start_investigation",
        "description": "Start a new diagnostic investigation. Capabilities: troubleshoot_app, database_diagnostics, network_troubleshooting, cluster_diagnostics, pr_review, github_issue_fix, troubleshoot_pipeline.",
        "input_schema": {
            "type": "object",
            "properties": {
                "capability": {"type": "string", "enum": ["troubleshoot_app", "database_diagnostics", "network_troubleshooting", "cluster_diagnostics", "pr_review", "github_issue_fix", "troubleshoot_pipeline"]},
                "service_name": {"type": "string", "description": "Name of the service/database/cluster to investigate"},
                "profile_id": {"type": "string", "description": "Profile ID for database diagnostics (optional)"},
            },
            "required": ["capability"],
        },
    },
    {
        "name": "cancel_investigation",
        "description": "Cancel a running investigation session.",
        "input_schema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "The session ID to cancel"},
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "get_fix_recommendations",
        "description": "Get SQL fix recommendations and warnings for a completed investigation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "The session ID to get fixes for"},
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "navigate_to",
        "description": "Navigate the user to a specific page in the application. Pages: home, sessions, app-diagnostics, db-diagnostics, network-topology, k8s-clusters, settings, integrations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "page": {"type": "string", "description": "Page identifier to navigate to"},
            },
            "required": ["page"],
        },
    },
    {
        "name": "download_report",
        "description": "Generate and download a diagnostic report for a completed investigation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "The session ID to generate report for"},
            },
            "required": ["session_id"],
        },
    },
]
