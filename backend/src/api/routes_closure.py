"""
Incident Closure API — 6 endpoints for the phased closure workflow.

Router prefix: /api/v4/session/{session_id}/closure
"""

import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from src.models.closure_models import (
    ClosurePhase,
    ClosureStatusResponse,
    ConfluencePublishRequest,
    IncidentClosureState,
    IntegrationAvailability,
    JiraActionResult,
    JiraCreateRequest,
    JiraLinkRequest,
    RemedyActionResult,
    RemedyCreateRequest,
    ConfluenceActionResult,
)
from src.utils.logger import get_logger

logger = get_logger("routes_closure")

router = APIRouter(prefix="/api/v4/session", tags=["closure"])


def _get_session(session_id: str) -> dict:
    """Retrieve session dict or raise 404."""
    from src.api.routes_v4 import sessions

    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return sessions[session_id]


def _ensure_closure_state(state) -> IncidentClosureState:
    """Lazily initialize closure_state on the DiagnosticState."""
    if state.closure_state is None:
        state.closure_state = IncidentClosureState()
    return state.closure_state


def _get_connection_config(session: dict):
    """Resolve connection config for this session's profile."""
    from src.integrations.connection_config import resolve_active_profile

    profile_id = session.get("profile_id")
    try:
        return resolve_active_profile(profile_id)
    except Exception as e:
        logger.warning("Could not resolve profile config: %s", e)
        return None


def _severity_to_jira_priority(severity_result) -> str:
    if not severity_result:
        return "High"
    mapping = {"P1": "Highest", "P2": "High", "P3": "Medium", "P4": "Low"}
    return mapping.get(severity_result.recommended_severity, "High")


def _severity_to_remedy_urgency(severity_result) -> str:
    if not severity_result:
        return "2-High"
    mapping = {"P1": "1-Critical", "P2": "2-High", "P3": "3-Medium", "P4": "4-Low"}
    return mapping.get(severity_result.recommended_severity, "2-High")


def _build_jira_description(state) -> str:
    """Build a Jira description from DiagnosticState."""
    parts: list[str] = []
    parts.append(f"*Service:* {state.service_name}")
    parts.append(f"*Incident ID:* {state.incident_id}")

    if state.severity_result:
        parts.append(f"*Severity:* {state.severity_result.recommended_severity}")

    if state.blast_radius_result:
        br = state.blast_radius_result
        parts.append(f"*Blast Radius:* {br.scope.replace('_', ' ')}")
        if br.estimated_user_impact:
            parts.append(f"*User Impact:* {br.estimated_user_impact}")

    # Top 3 findings
    if state.all_findings:
        parts.append("\n*Top Findings:*")
        for f in state.all_findings[:3]:
            parts.append(f"- [{f.severity}] {f.summary}")

    # Primary error pattern
    if state.log_analysis and state.log_analysis.primary_pattern:
        pp = state.log_analysis.primary_pattern
        parts.append(f"\n*Root Cause Pattern:* {{code}}{pp.exception_type}{{code}}")
        parts.append(f"_{pp.error_message}_")

    # PR link
    if state.fix_result and state.fix_result.pr_url:
        parts.append(f"\n*Fix PR:* {state.fix_result.pr_url}")

    return "\n".join(parts)


def _build_jira_summary(state) -> str:
    """Build a Jira issue summary from DiagnosticState."""
    incident_id = state.incident_id or state.session_id[:8]
    exception_type = ""
    if state.log_analysis and state.log_analysis.primary_pattern:
        exception_type = state.log_analysis.primary_pattern.exception_type
    if exception_type:
        return f"[{incident_id}] {exception_type} in {state.service_name}"
    return f"[{incident_id}] Incident in {state.service_name}"


def _mock_id_from_session(session_id: str, prefix: str, modulus: int = 100000) -> str:
    """Generate a deterministic mock ID from a session ID."""
    h = int(hashlib.sha256(session_id.encode()).hexdigest()[:8], 16)
    return f"{prefix}-{h % modulus}"


# ── Endpoints ─────────────────────────────────────────────────────────────


@router.get("/{session_id}/closure/status")
async def get_closure_status(session_id: str):
    """Integration availability + closure state + pre-filled form data."""
    session = _get_session(session_id)
    state = session.get("state")
    if not state:
        raise HTTPException(status_code=400, detail="Session not ready")

    config = _get_connection_config(session)
    closure = _ensure_closure_state(state)

    # Build integration availability — mock-available when real creds are absent
    def _avail(url_attr: str, cred_attr: str) -> dict:
        has_real = bool(config and getattr(config, url_attr, None) and getattr(config, cred_attr, None))
        if has_real:
            return IntegrationAvailability(
                configured=True, status="connected", has_credentials=True,
            ).model_dump()
        return IntegrationAvailability(
            configured=True, status="mock_available", has_credentials=False,
        ).model_dump()

    integrations = {
        "jira": _avail("jira_url", "jira_credentials"),
        "confluence": _avail("confluence_url", "confluence_credentials"),
        "remedy": _avail("remedy_url", "remedy_credentials"),
    }

    can_start = True  # always startable — mock mode handles missing creds

    pre_filled = {
        "jira_summary": _build_jira_summary(state),
        "jira_description": _build_jira_description(state),
        "jira_priority": _severity_to_jira_priority(state.severity_result),
        "remedy_summary": "",
        "remedy_urgency": _severity_to_remedy_urgency(state.severity_result),
        "confluence_title": f"Post-Mortem: {state.incident_id or state.session_id[:8]} — {state.service_name}",
    }
    if state.log_analysis and state.log_analysis.primary_pattern:
        msg = state.log_analysis.primary_pattern.error_message
        pre_filled["remedy_summary"] = f"Auto-detected: {msg[:100]}"

    return ClosureStatusResponse(
        closure_state=closure,
        integrations=integrations,
        can_start_closure=can_start,
        pre_filled=pre_filled,
    ).model_dump(mode="json")


@router.post("/{session_id}/closure/jira/create")
async def create_jira(session_id: str, request: JiraCreateRequest):
    """Create a Jira issue from DiagnosticState."""
    session = _get_session(session_id)
    state = session.get("state")
    if not state:
        raise HTTPException(status_code=400, detail="Session not ready")

    config = _get_connection_config(session)
    is_mock = not config or not config.jira_url or not config.jira_credentials
    closure = _ensure_closure_state(state)

    if is_mock:
        issue_key = _mock_id_from_session(session_id, "INC")
        issue_url = f"https://jira.example.com/browse/{issue_key}"
        closure.jira_result = JiraActionResult(
            status="success",
            issue_key=issue_key,
            issue_url=issue_url,
            created_at=datetime.now(timezone.utc),
        )
        closure.phase = ClosurePhase.TRACKING
        emitter = session.get("emitter")
        if emitter:
            await emitter.emit("closure", "success", f"Mock Jira issue {issue_key} created")
        return closure.jira_result.model_dump(mode="json")

    # Real Jira logic
    # Auto-fill empty fields
    summary = request.summary or _build_jira_summary(state)
    description = request.description or _build_jira_description(state)
    priority = request.priority or _severity_to_jira_priority(state.severity_result)

    from src.integrations.jira_client import JiraClient

    client = JiraClient(config.jira_url, config.jira_credentials)
    try:
        result = await client.create_issue(
            project_key=request.project_key,
            summary=summary,
            description=description,
            issue_type=request.issue_type,
            priority=priority,
        )

        issue_key = result.get("key", "")
        issue_url = f"{config.jira_url}/browse/{issue_key}" if issue_key else ""

        # Link PR if available
        if state.fix_result and state.fix_result.pr_url and issue_key:
            try:
                await client.add_remote_link(issue_key, state.fix_result.pr_url, "Fix PR")
            except Exception as e:
                logger.warning("Failed to link PR to Jira issue: %s", e)

        closure.jira_result = JiraActionResult(
            status="success",
            issue_key=issue_key,
            issue_url=issue_url,
            created_at=datetime.now(timezone.utc),
        )
        closure.phase = ClosurePhase.TRACKING

        # Emit WebSocket event
        emitter = session.get("emitter")
        if emitter:
            await emitter.emit("closure", "success", f"Jira issue {issue_key} created")

        return closure.jira_result.model_dump(mode="json")

    except Exception as e:
        logger.error("Jira issue creation failed: %s", e)
        closure.jira_result = JiraActionResult(
            status="failed",
            error=str(e),
        )
        raise HTTPException(status_code=502, detail=f"Jira API error: {e}")


@router.post("/{session_id}/closure/jira/link")
async def link_jira(session_id: str, request: JiraLinkRequest):
    """Link an existing Jira issue key without creating a new one."""
    session = _get_session(session_id)
    state = session.get("state")
    if not state:
        raise HTTPException(status_code=400, detail="Session not ready")

    config = _get_connection_config(session)
    closure = _ensure_closure_state(state)

    issue_url = ""
    if config and config.jira_url:
        issue_url = f"{config.jira_url}/browse/{request.issue_key}"

    closure.jira_result = JiraActionResult(
        status="success",
        issue_key=request.issue_key,
        issue_url=issue_url,
        created_at=datetime.now(timezone.utc),
    )
    closure.phase = ClosurePhase.TRACKING

    emitter = session.get("emitter")
    if emitter:
        await emitter.emit("closure", "success", f"Linked Jira issue {request.issue_key}")

    return closure.jira_result.model_dump(mode="json")


@router.post("/{session_id}/closure/remedy/create")
async def create_remedy(session_id: str, request: RemedyCreateRequest):
    """Create a Remedy/Helix ITSM incident."""
    session = _get_session(session_id)
    state = session.get("state")
    if not state:
        raise HTTPException(status_code=400, detail="Session not ready")

    config = _get_connection_config(session)
    is_mock = not config or not config.remedy_url or not config.remedy_credentials
    closure = _ensure_closure_state(state)

    if is_mock:
        incident_number = _mock_id_from_session(session_id, "CHG")
        incident_url = f"https://remedy.example.com/arsys/forms/{incident_number}"
        closure.remedy_result = RemedyActionResult(
            status="success",
            incident_number=incident_number,
            incident_url=incident_url,
            created_at=datetime.now(timezone.utc),
        )
        closure.phase = ClosurePhase.TRACKING
        emitter = session.get("emitter")
        if emitter:
            await emitter.emit("closure", "success", f"Mock Remedy incident {incident_number} created")
        return closure.remedy_result.model_dump(mode="json")

    # Real Remedy logic
    summary = request.summary
    if not summary and state.log_analysis and state.log_analysis.primary_pattern:
        summary = f"Auto-detected: {state.log_analysis.primary_pattern.error_message[:100]}"
    if not summary:
        summary = f"Incident in {state.service_name}"

    description = _build_jira_description(state)  # reuse the rich description
    urgency = request.urgency or _severity_to_remedy_urgency(state.severity_result)

    from src.integrations.remedy_client import RemedyClient

    client = RemedyClient(config.remedy_url, config.remedy_credentials)
    try:
        result = await client.create_incident(
            summary=summary,
            description=description,
            urgency=urgency,
            assigned_group=request.assigned_group,
            service_ci=request.service_ci,
        )

        incident_number = result.get("values", {}).get("Incident Number", "")
        incident_url = f"{config.remedy_url}/arsys/forms/helpdesk/best-practice/{incident_number}" if incident_number else ""

        closure.remedy_result = RemedyActionResult(
            status="success",
            incident_number=incident_number,
            incident_url=incident_url,
            created_at=datetime.now(timezone.utc),
        )
        closure.phase = ClosurePhase.TRACKING

        emitter = session.get("emitter")
        if emitter:
            await emitter.emit("closure", "success", f"Remedy incident {incident_number} created")

        return closure.remedy_result.model_dump(mode="json")

    except Exception as e:
        logger.error("Remedy incident creation failed: %s", e)
        closure.remedy_result = RemedyActionResult(
            status="failed",
            error=str(e),
        )
        raise HTTPException(status_code=502, detail=f"Remedy API error: {e}")


@router.post("/{session_id}/closure/confluence/preview")
async def preview_postmortem(session_id: str):
    """Generate a post-mortem markdown preview from DiagnosticState."""
    session = _get_session(session_id)
    state = session.get("state")
    if not state:
        raise HTTPException(status_code=400, detail="Session not ready")

    from src.integrations.postmortem_renderer import PostMortemRenderer
    from src.utils.llm_client import AnthropicClient

    renderer = PostMortemRenderer()
    try:
        llm_client = AnthropicClient(agent_name="postmortem_renderer")
        result = await renderer.render_with_narrative(state, llm_client=llm_client)
    except Exception as e:
        logger.warning("LLM narrative failed, falling back to deterministic: %s", e)
        result = renderer.render_markdown(state)
        result["executive_summary"] = ""
        result["impact_statement"] = ""

    closure = _ensure_closure_state(state)
    closure.postmortem_preview = result["body_markdown"]

    return result


@router.post("/{session_id}/closure/confluence/publish")
async def publish_postmortem(session_id: str, request: ConfluencePublishRequest):
    """Publish (possibly edited) post-mortem to Confluence."""
    session = _get_session(session_id)
    state = session.get("state")
    if not state:
        raise HTTPException(status_code=400, detail="Session not ready")

    config = _get_connection_config(session)
    is_mock = not config or not config.confluence_url or not config.confluence_credentials
    closure = _ensure_closure_state(state)

    if is_mock:
        page_id = _mock_id_from_session(session_id, "PAGE")
        page_url = f"https://confluence.example.com/pages/{page_id}"
        closure.confluence_result = ConfluenceActionResult(
            status="success",
            page_id=page_id,
            page_url=page_url,
            space_key=request.space_key or "DEMO",
            created_at=datetime.now(timezone.utc),
        )
        closure.phase = ClosurePhase.KNOWLEDGE_CAPTURE
        emitter = session.get("emitter")
        if emitter:
            await emitter.emit("closure", "success", f"Mock post-mortem published (page {page_id})")
        return closure.confluence_result.model_dump(mode="json")

    # Real Confluence logic
    # Use provided markdown or fall back to cached preview
    markdown = request.body_markdown or closure.postmortem_preview
    if not markdown:
        from src.integrations.postmortem_renderer import PostMortemRenderer
        renderer = PostMortemRenderer()
        result = renderer.render_markdown(state)
        markdown = result["body_markdown"]

    title = request.title
    if not title:
        title = f"Post-Mortem: {state.incident_id or state.session_id[:8]} — {state.service_name}"

    # Convert to Confluence Storage Format
    from src.integrations.postmortem_renderer import PostMortemRenderer

    renderer = PostMortemRenderer()
    storage_format = renderer.markdown_to_storage_format(markdown)

    from src.integrations.confluence_client import ConfluenceClient

    client = ConfluenceClient(config.confluence_url, config.confluence_credentials)
    try:
        result = await client.create_page(
            space_key=request.space_key,
            title=title,
            body_storage_format=storage_format,
            parent_page_id=request.parent_page_id or None,
        )

        page_id = result.get("id", "")
        links = result.get("_links", {})
        base_url = links.get("base", config.confluence_url)
        webui = links.get("webui", "")
        page_url = f"{base_url}{webui}" if webui else ""

        closure.confluence_result = ConfluenceActionResult(
            status="success",
            page_id=page_id,
            page_url=page_url,
            space_key=request.space_key,
            created_at=datetime.now(timezone.utc),
        )
        closure.phase = ClosurePhase.KNOWLEDGE_CAPTURE

        emitter = session.get("emitter")
        if emitter:
            await emitter.emit("closure", "success", f"Post-mortem published to Confluence (page {page_id})")

        return closure.confluence_result.model_dump(mode="json")

    except Exception as e:
        logger.error("Confluence publish failed: %s", e)
        closure.confluence_result = ConfluenceActionResult(
            status="failed",
            error=str(e),
        )
        raise HTTPException(status_code=502, detail=f"Confluence API error: {e}")
