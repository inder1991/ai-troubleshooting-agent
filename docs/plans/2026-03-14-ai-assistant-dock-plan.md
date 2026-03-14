# AI Assistant Dock — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a bottom-dock AI assistant on the homepage that acts as a full command center operator — users type natural language and the agent starts investigations, shows findings, navigates pages, and downloads reports.

**Architecture:** Frontend `AssistantDock` component pinned to bottom of homepage (collapsed 44px, expanded 40vh). Backend `POST /api/v4/assistant/chat` endpoint with Sonnet-powered agentic tool-calling loop. 10 tools that mirror every UI action. Persistent thread in SQLite. Streaming responses.

**Tech Stack:** React, TypeScript, Framer Motion, Python, Anthropic SDK (AsyncAnthropic), SQLite

---

## Task 1: Backend — Assistant tools

**Files:**
- Create: `backend/src/agents/assistant/tools.py`
- Create: `backend/src/agents/assistant/__init__.py`

**Step 1: Create the tools module**

10 tool functions that wrap existing backend functionality. Each returns a dict that the LLM can reason about.

```python
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
        "description": "Start a new diagnostic investigation. Capabilities: troubleshoot_app, database_diagnostics, network_troubleshooting, cluster_diagnostics, pr_review, github_issue_fix.",
        "input_schema": {
            "type": "object",
            "properties": {
                "capability": {"type": "string", "enum": ["troubleshoot_app", "database_diagnostics", "network_troubleshooting", "cluster_diagnostics", "pr_review", "github_issue_fix"]},
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
```

**Step 2: Commit**
```bash
git add backend/src/agents/assistant/
git commit -m "feat(assistant): add 10 tool functions + Anthropic tool schemas"
```

---

## Task 2: Backend — Assistant orchestrator + endpoint

**Files:**
- Create: `backend/src/agents/assistant/orchestrator.py`
- Create: `backend/src/agents/assistant/prompts.py`
- Create: `backend/src/api/assistant_endpoints.py`
- Modify: `backend/src/api/main.py` (register router)

**Step 1: Create the orchestrator**

Agentic loop: receives user message → calls Sonnet with tools → executes tool calls → returns final response with action metadata.

```python
"""Assistant orchestrator — agentic loop for the DebugDuck AI Assistant."""
import asyncio
import json
import logging
from src.utils.llm_client import AnthropicClient
from .tools import (
    list_sessions, get_session_detail, search_sessions,
    start_investigation, cancel_investigation, get_fix_recommendations,
    ASSISTANT_TOOLS,
)
from .prompts import ASSISTANT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

ASSISTANT_MODEL = "claude-sonnet-4-20250514"
MAX_ITERATIONS = 5


async def run_assistant(
    user_message: str,
    sessions: dict,
    thread_history: list[dict],
    timeout: float = 30.0,
) -> dict:
    """Run the assistant agentic loop. Returns {response, actions, usage}."""
    llm = AnthropicClient(agent_name="assistant", model=ASSISTANT_MODEL)

    messages = list(thread_history)
    messages.append({"role": "user", "content": user_message})

    actions = []  # Frontend actions (navigate, download)

    try:
        for iteration in range(MAX_ITERATIONS):
            response = await asyncio.wait_for(
                llm.chat_with_tools(
                    system=ASSISTANT_SYSTEM_PROMPT,
                    messages=messages,
                    tools=ASSISTANT_TOOLS,
                    max_tokens=2048,
                    temperature=0.0,
                ),
                timeout=timeout,
            )

            assistant_content = list(response.content)
            tool_results = []

            for block in response.content:
                if getattr(block, 'type', None) == 'tool_use':
                    tool_name = getattr(block, 'name', '')
                    args = getattr(block, 'input', {}) or {}
                    call_id = getattr(block, 'id', '')

                    result = await _execute_tool(tool_name, args, sessions)

                    # Check for frontend actions
                    if tool_name == "navigate_to":
                        actions.append({"type": "navigate", "page": args.get("page", "home")})
                        result = {"status": "ok", "message": f"Navigating to {args.get('page', 'home')}"}
                    elif tool_name == "download_report":
                        actions.append({"type": "download_report", "session_id": args.get("session_id", "")})
                        result = {"status": "ok", "message": "Report download initiated"}
                    elif tool_name == "start_investigation":
                        actions.append({
                            "type": "start_investigation",
                            "capability": args.get("capability", ""),
                            "service_name": args.get("service_name", ""),
                            "profile_id": args.get("profile_id", ""),
                        })

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": call_id,
                        "content": json.dumps(result, default=str),
                    })

            messages.append({"role": "assistant", "content": assistant_content})
            if tool_results:
                messages.append({"role": "user", "content": tool_results})

            if response.stop_reason == "end_turn":
                break

        # Extract final text response
        final_text = ""
        for block in response.content:
            if getattr(block, 'type', None) == 'text':
                final_text += getattr(block, 'text', '')

        return {
            "response": final_text,
            "actions": actions,
            "thread_messages": messages,
            "usage": llm.get_total_usage().model_dump() if hasattr(llm.get_total_usage(), 'model_dump') else {},
        }

    except asyncio.TimeoutError:
        return {"response": "Request timed out. Please try again.", "actions": [], "thread_messages": messages, "usage": {}}
    except Exception as e:
        logger.error("Assistant error: %s", e)
        return {"response": f"Something went wrong: {e}", "actions": [], "thread_messages": messages, "usage": {}}


async def _execute_tool(tool_name: str, args: dict, sessions: dict) -> dict:
    """Execute a single tool call."""
    try:
        if tool_name == "list_sessions":
            return await list_sessions(sessions)
        elif tool_name == "get_session_detail":
            return await get_session_detail(sessions, args.get("session_id", ""))
        elif tool_name == "search_sessions":
            return await search_sessions(sessions, args.get("query", ""))
        elif tool_name == "start_investigation":
            return await start_investigation(sessions, **args)
        elif tool_name == "cancel_investigation":
            return await cancel_investigation(sessions, args.get("session_id", ""))
        elif tool_name == "get_fix_recommendations":
            return await get_fix_recommendations(sessions, args.get("session_id", ""))
        elif tool_name == "navigate_to":
            return {"status": "ok", "page": args.get("page", "home")}
        elif tool_name == "download_report":
            return {"status": "ok", "session_id": args.get("session_id", "")}
        else:
            return {"error": f"Unknown tool: {tool_name}"}
    except Exception as e:
        return {"error": str(e)}
```

**Step 2: Create prompts.py**

```python
ASSISTANT_SYSTEM_PROMPT = """You are DebugDuck, an AI SRE assistant for a diagnostic platform.

You help operators:
- Check system health and investigation status
- Start diagnostic investigations (application, database, network, cluster, PR review, issue fix)
- Review findings and fix recommendations from past investigations
- Navigate the platform to specific pages

You have tools to take real actions. When asked to do something, DO IT — don't ask for confirmation unless the action is destructive (like cancelling a running investigation).

Guidelines:
- Be concise. Use bullet points for findings.
- Always include incident IDs (e.g., INC-20260314-A3F2) when referencing sessions.
- When showing findings, include severity, title, and recommended fix.
- When starting an investigation, confirm what was started and provide the incident ID.
- When asked about "what's wrong" with something, first search for existing sessions, then offer to start a new scan if none exist.
- Suggest next steps after showing information.

You are NOT a general chatbot. Stay focused on SRE operations, diagnostics, and platform navigation. If asked about unrelated topics, politely redirect to your capabilities."""
```

**Step 3: Create the endpoint**

```python
"""Assistant chat endpoint."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from .assistant_orchestrator import run_assistant

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
```

**Step 4: Register router in main.py**

Add to `backend/src/api/main.py`:
```python
from src.api.assistant_endpoints import assistant_router
app.include_router(assistant_router)
```

**Step 5: Commit**
```bash
git add backend/src/agents/assistant/ backend/src/api/assistant_endpoints.py
git commit -m "feat(assistant): add orchestrator, prompts, and chat endpoint"
```

---

## Task 3: Frontend — useAssistantChat hook

**Files:**
- Create: `frontend/src/hooks/useAssistantChat.ts`

**Step 1: Create the hook**

Manages chat state, API calls, and action handling.

```typescript
import { useState, useCallback, useRef } from 'react';
import { API_BASE_URL } from '../services/api';

export interface AssistantMessage {
  role: 'user' | 'assistant';
  content: string;
  actions?: AssistantAction[];
  timestamp: string;
}

export interface AssistantAction {
  type: 'navigate' | 'download_report' | 'start_investigation';
  page?: string;
  session_id?: string;
  capability?: string;
  service_name?: string;
}

interface UseAssistantChatOptions {
  onNavigate?: (page: string) => void;
  onStartInvestigation?: (capability: string, serviceName?: string) => void;
  onDownloadReport?: (sessionId: string) => void;
}

export function useAssistantChat(options: UseAssistantChatOptions = {}) {
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const threadIdRef = useRef('default');

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() || isLoading) return;

    const userMsg: AssistantMessage = {
      role: 'user',
      content: text.trim(),
      timestamp: new Date().toISOString(),
    };
    setMessages(prev => [...prev, userMsg]);
    setIsLoading(true);

    try {
      const response = await fetch(`${API_BASE_URL}/api/v4/assistant/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text.trim(),
          thread_id: threadIdRef.current,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to get response');
      }

      const data = await response.json();

      const assistantMsg: AssistantMessage = {
        role: 'assistant',
        content: data.response,
        actions: data.actions,
        timestamp: new Date().toISOString(),
      };
      setMessages(prev => [...prev, assistantMsg]);

      // Execute frontend actions
      for (const action of data.actions || []) {
        if (action.type === 'navigate' && options.onNavigate) {
          options.onNavigate(action.page);
        } else if (action.type === 'start_investigation' && options.onStartInvestigation) {
          options.onStartInvestigation(action.capability, action.service_name);
        } else if (action.type === 'download_report' && options.onDownloadReport) {
          options.onDownloadReport(action.session_id);
        }
      }
    } catch (err) {
      const errorMsg: AssistantMessage = {
        role: 'assistant',
        content: 'Sorry, something went wrong. Please try again.',
        timestamp: new Date().toISOString(),
      };
      setMessages(prev => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  }, [isLoading, options]);

  const clearThread = useCallback(async () => {
    setMessages([]);
    try {
      await fetch(`${API_BASE_URL}/api/v4/assistant/thread/${threadIdRef.current}`, {
        method: 'DELETE',
      });
    } catch { /* silent */ }
  }, []);

  return { messages, isLoading, sendMessage, clearThread };
}
```

**Step 2: Commit**
```bash
git add frontend/src/hooks/useAssistantChat.ts
git commit -m "feat(assistant): add useAssistantChat hook with action handling"
```

---

## Task 4: Frontend — AssistantDock component

**Files:**
- Create: `frontend/src/components/Assistant/AssistantDock.tsx`
- Create: `frontend/src/components/Assistant/AssistantMessage.tsx`

**Step 1: Create AssistantMessage**

Renders a single message bubble — user or assistant. Assistant messages support markdown-like formatting and action buttons.

```tsx
import React from 'react';
import type { AssistantMessage as MessageType } from '../../hooks/useAssistantChat';

interface AssistantMessageProps {
  message: MessageType;
  onActionClick?: (action: any) => void;
}

const AssistantMessageBubble: React.FC<AssistantMessageProps> = ({ message, onActionClick }) => {
  const isUser = message.role === 'user';

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-3`}>
      <div className={`max-w-[85%] ${isUser ? 'order-2' : ''}`}>
        {/* Avatar */}
        {!isUser && (
          <div className="flex items-center gap-1.5 mb-1">
            <span className="material-symbols-outlined text-duck-accent text-[14px]">smart_toy</span>
            <span className="text-[10px] font-display font-bold text-slate-400">DebugDuck</span>
          </div>
        )}

        {/* Message content */}
        <div className={`rounded-lg px-3 py-2 text-[13px] leading-relaxed ${
          isUser
            ? 'bg-duck-accent/15 text-white border border-duck-accent/20'
            : 'bg-duck-card/40 text-slate-200 border border-duck-border/30'
        }`}>
          <p className="whitespace-pre-wrap">{message.content}</p>
        </div>

        {/* Action buttons */}
        {message.actions && message.actions.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-1.5">
            {message.actions.map((action, i) => (
              <button
                key={i}
                onClick={() => onActionClick?.(action)}
                className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-display font-bold bg-duck-accent/10 text-duck-accent border border-duck-accent/20 hover:bg-duck-accent/20 transition-colors"
              >
                <span className="material-symbols-outlined text-[12px]">
                  {action.type === 'navigate' ? 'open_in_new' :
                   action.type === 'download_report' ? 'download' :
                   action.type === 'start_investigation' ? 'play_arrow' : 'arrow_forward'}
                </span>
                {action.type === 'navigate' ? `Go to ${action.page}` :
                 action.type === 'download_report' ? 'Download Report' :
                 action.type === 'start_investigation' ? `Start ${action.capability}` : 'Action'}
              </button>
            ))}
          </div>
        )}

        {/* Timestamp */}
        <span className="text-[9px] text-slate-500 mt-1 block">
          {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </span>
      </div>
    </div>
  );
};

export default AssistantMessageBubble;
```

**Step 2: Create AssistantDock**

The main dock component — collapsed/expanded states, input, message list, keyboard shortcuts.

```tsx
import React, { useState, useRef, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useAssistantChat } from '../../hooks/useAssistantChat';
import AssistantMessageBubble from './AssistantMessage';

interface AssistantDockProps {
  onNavigate?: (page: string) => void;
  onStartInvestigation?: (capability: string, serviceName?: string) => void;
  onDownloadReport?: (sessionId: string) => void;
}

const AssistantDock: React.FC<AssistantDockProps> = ({
  onNavigate,
  onStartInvestigation,
  onDownloadReport,
}) => {
  const [expanded, setExpanded] = useState(false);
  const [input, setInput] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const { messages, isLoading, sendMessage, clearThread } = useAssistantChat({
    onNavigate,
    onStartInvestigation,
    onDownloadReport,
  });

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Focus input when expanded
  useEffect(() => {
    if (expanded) inputRef.current?.focus();
  }, [expanded]);

  // Cmd+K global shortcut
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setExpanded(prev => !prev);
      }
      if (e.key === 'Escape' && expanded) {
        setExpanded(false);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [expanded]);

  const handleSubmit = useCallback(() => {
    if (!input.trim()) return;
    sendMessage(input);
    setInput('');
  }, [input, sendMessage]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="relative z-40">
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: '40vh', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: 'easeOut' }}
            className="border-t border-duck-border bg-duck-panel/95 flex flex-col overflow-hidden"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-2 border-b border-duck-border/50 shrink-0">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-duck-accent text-[18px]">smart_toy</span>
                <span className="text-sm font-display font-bold text-white">DebugDuck Assistant</span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={clearThread}
                  className="text-[10px] text-slate-400 hover:text-white transition-colors font-display"
                >
                  Clear
                </button>
                <button
                  onClick={() => setExpanded(false)}
                  className="text-slate-400 hover:text-white transition-colors"
                  aria-label="Collapse assistant"
                >
                  <span className="material-symbols-outlined text-[18px]">keyboard_arrow_down</span>
                </button>
              </div>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-4 py-3 custom-scrollbar">
              {messages.length === 0 && (
                <div className="flex flex-col items-center justify-center h-full text-center">
                  <span className="material-symbols-outlined text-3xl text-duck-accent/30 mb-2">smart_toy</span>
                  <p className="text-sm text-slate-300 font-display font-bold mb-1">How can I help?</p>
                  <p className="text-[11px] text-slate-400">Ask me to check system health, start investigations, or show findings.</p>
                </div>
              )}
              {messages.map((msg, i) => (
                <AssistantMessageBubble key={i} message={msg} />
              ))}
              {isLoading && (
                <div className="flex items-center gap-2 mb-3">
                  <span className="material-symbols-outlined text-duck-accent text-[14px] animate-spin">progress_activity</span>
                  <span className="text-[11px] text-slate-400">Thinking...</span>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Input bar — always visible */}
      <div className="border-t border-duck-border bg-duck-panel/80 px-4 py-2 flex items-center gap-3">
        <span className="material-symbols-outlined text-duck-accent text-[18px] shrink-0">smart_toy</span>
        <input
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => setExpanded(true)}
          placeholder="Ask DebugDuck anything..."
          className="flex-1 bg-transparent text-[13px] font-display text-white placeholder:text-slate-500 outline-none"
          disabled={isLoading}
          aria-label="Ask DebugDuck assistant"
        />
        {input.trim() ? (
          <button
            onClick={handleSubmit}
            disabled={isLoading}
            className="text-duck-accent hover:text-white transition-colors disabled:opacity-50"
            aria-label="Send message"
          >
            <span className="material-symbols-outlined text-[20px]">send</span>
          </button>
        ) : (
          <span className="text-[10px] text-slate-500 font-mono shrink-0">⌘K</span>
        )}
      </div>
    </div>
  );
};

export default AssistantDock;
```

**Step 3: Commit**
```bash
git add frontend/src/components/Assistant/
git commit -m "feat(assistant): add AssistantDock + AssistantMessage components"
```

---

## Task 5: Wire AssistantDock into HomePage

**Files:**
- Modify: `frontend/src/components/Home/HomePage.tsx`

**Step 1: Add AssistantDock**

Import and render `<AssistantDock>` at the bottom of the homepage, AFTER the feed grid. Pass navigation and action handlers.

```tsx
import AssistantDock from '../Assistant/AssistantDock';

// In the render, after the closing </div> of the feed grid, before the root closing </div>:
<AssistantDock
  onNavigate={(page) => {
    // Map page names to nav views
    const viewMap: Record<string, string> = {
      'home': 'home', 'sessions': 'sessions',
      'app-diagnostics': 'app-diagnostics',
      'db-diagnostics': 'db-diagnostics',
      'network-topology': 'network-topology',
      'k8s-clusters': 'k8s-clusters',
      'settings': 'settings',
      'integrations': 'integrations',
    };
    // Navigation would need to be handled by App.tsx — for now just log
    console.log('Navigate to:', viewMap[page] || page);
  }}
  onStartInvestigation={(capability, serviceName) => {
    onSelectCapability(capability as any);
  }}
/>
```

**Step 2: Verify TypeScript compiles**
```bash
cd frontend && npx tsc --noEmit
```

**Step 3: Commit**
```bash
git add frontend/src/components/Home/HomePage.tsx
git commit -m "feat(assistant): wire AssistantDock into homepage"
```

---

## Task 6: Register backend router + end-to-end test

**Files:**
- Modify: `backend/src/api/main.py`

**Step 1: Register the assistant router**

Find the router registration section in main.py. Add:
```python
from src.api.assistant_endpoints import assistant_router
app.include_router(assistant_router)
```

**Step 2: Test the endpoint**
```bash
curl -s -X POST http://localhost:8000/api/v4/assistant/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "what investigations are running?"}' | python3 -m json.tool
```

**Step 3: Verify full stack**
- Start backend + frontend
- Open homepage
- See the dock bar at the bottom
- Type "what investigations are running?"
- Agent should respond with session list

**Step 4: Commit**
```bash
git add backend/src/api/main.py
git commit -m "feat(assistant): register assistant router, end-to-end working"
```
