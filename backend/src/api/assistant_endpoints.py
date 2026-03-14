"""Assistant chat endpoint."""
from fastapi import APIRouter
from pydantic import BaseModel
from src.agents.assistant.orchestrator import run_assistant

assistant_router = APIRouter(prefix="/api/v4/assistant", tags=["assistant"])

# In-memory thread storage (per-session, simple)
_threads: dict[str, list[dict]] = {}


class AssistantChatRequest(BaseModel):
    message: str
    thread_id: str = "default"


class AssistantChatResponse(BaseModel):
    response: str
    actions: list[dict] = []
    thread_id: str = ""


@assistant_router.post("/chat", response_model=AssistantChatResponse)
async def assistant_chat(request: AssistantChatRequest):
    from src.api.routes_v4 import sessions

    thread = _threads.get(request.thread_id, [])

    result = await run_assistant(
        user_message=request.message,
        sessions=sessions,
        thread_history=thread,
    )

    # Update thread (keep last 20 messages to avoid context overflow)
    new_thread = result.get("thread_messages", [])
    if len(new_thread) > 20:
        new_thread = new_thread[-20:]
    _threads[request.thread_id] = new_thread

    return AssistantChatResponse(
        response=result["response"],
        actions=result.get("actions", []),
        thread_id=request.thread_id,
    )


@assistant_router.delete("/thread/{thread_id}")
async def clear_thread(thread_id: str):
    _threads.pop(thread_id, None)
    return {"status": "cleared"}
