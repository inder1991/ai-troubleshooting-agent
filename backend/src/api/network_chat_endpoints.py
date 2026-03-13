"""FastAPI router for network AI chat — /api/v4/network/chat."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from src.agents.network.orchestrator import NetworkAgentOrchestrator
from src.database.network_chat_store import NetworkChatStore
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class NetworkChatRequest(BaseModel):
    message: str
    view: str
    visible_data_summary: dict = {}
    thread_id: str | None = None
    user_id: str = "default"


class NetworkChatResponse(BaseModel):
    response: str
    thread_id: str
    tool_calls: list[dict] = []


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

network_chat_router = APIRouter(
    prefix="/api/v4/network/chat", tags=["network-chat"]
)

# ---------------------------------------------------------------------------
# Lazy singletons
# ---------------------------------------------------------------------------

_orchestrator: NetworkAgentOrchestrator | None = None
_store: NetworkChatStore | None = None


def _get_orchestrator() -> NetworkAgentOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = NetworkAgentOrchestrator()
    return _orchestrator


def _get_store() -> NetworkChatStore:
    global _store
    if _store is None:
        _store = NetworkChatStore()
    return _store


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@network_chat_router.post("", response_model=NetworkChatResponse)
async def post_chat_message(req: NetworkChatRequest) -> NetworkChatResponse:
    """Send a user message and get an AI-generated response.

    The orchestrator resolves (or creates) a chat thread, runs the
    tool-calling loop, and returns the assistant reply together with
    any tool invocations that were made.
    """
    logger.info(
        "chat request: view=%s thread=%s user=%s",
        req.view,
        req.thread_id,
        req.user_id,
    )
    orchestrator = _get_orchestrator()
    result = await orchestrator.handle_message(
        user_id=req.user_id,
        view=req.view,
        message=req.message,
        visible_data_summary=req.visible_data_summary,
        thread_id=req.thread_id,
    )
    return NetworkChatResponse(**result)


@network_chat_router.get("/threads/{thread_id}/messages")
async def get_thread_messages(
    thread_id: str,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict[str, Any]]:
    """Retrieve messages for a given chat thread.

    Returns up to *limit* most-recent messages in chronological order.
    """
    store = _get_store()
    return store.list_messages(thread_id, limit=limit)
