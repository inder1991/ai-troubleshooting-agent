# DebugDuck AI Assistant — Command Center Operator

## Overview

A bottom-dock AI assistant on the homepage that acts as a full command center operator. Users type natural language and the agent takes real actions: start investigations, show findings, explain root causes, navigate pages, download reports. It replaces clicking buttons — voice-of-the-system.

## Architecture

**Frontend:** `AssistantDock` component pinned to bottom of homepage. Collapsed = 44px input bar. Expanded = 40% viewport height chat panel. Triggered by click or ⌘K.

**Backend:** `POST /api/v4/assistant/chat` endpoint with general-purpose agentic loop. Uses `AnthropicClient.chat_with_tools()` with ~10 tools that mirror every UI action. Persistent thread per user stored in SQLite.

**LLM:** Claude Sonnet (tool-calling, good reasoning). Not Haiku — assistant needs strong multi-step reasoning.

**Data flow:**
```
User types → Frontend sends message → /api/v4/assistant/chat
  → Sonnet with tools → tool calls (list_sessions, start_investigation, etc.)
  → tool results fed back to LLM → final response with action metadata
  → streamed back to frontend → rendered in dock with action buttons
```

## Tools (10 total)

| Tool | Purpose | Backend Source |
|---|---|---|
| `list_sessions` | List all investigations with status/findings | `sessions` dict |
| `get_session_detail` | Get findings, dossier, events for one session | session state + emitter |
| `start_investigation` | Start any capability (app/db/network/cluster/pr/issue) | `start_session()` |
| `cancel_investigation` | Cancel a running session | `cancel_session()` |
| `get_environment_health` | Get system health status | `fetchEnvironmentHealth()` |
| `search_sessions` | Search by service name, incident ID, status | filter sessions dict |
| `get_fix_recommendations` | Get fix SQL + warnings for a session | session dossier |
| `navigate_to` | Tell frontend to navigate to a page | Frontend action via metadata |
| `download_report` | Generate dossier markdown | Frontend action via metadata |
| `get_agent_status` | Get agent fleet status | agent registry |

## Frontend Component: AssistantDock

### Collapsed (always visible, 44px)
```
┌──────────────────────────────────────────────────────────┐
│ 🐛  Ask DebugDuck anything...                     ⌘K  ▲ │
└──────────────────────────────────────────────────────────┘
```

### Expanded (chatting, 40% viewport)
```
┌──────────────────────────────────────────────────────────┐
│ 🐛 DebugDuck Assistant                    [Clear] [▼]   │
├──────────────────────────────────────────────────────────┤
│ User: what's wrong with prod-orders?                     │
│                                                          │
│ Agent: Last scan (INC-A3F2, 2h ago) found 2 critical:   │
│   1. Connection pool at 87% utilization                  │
│   2. 3 deadlocks detected                               │
│   [View Investigation] [Run Fresh Scan]                  │
├──────────────────────────────────────────────────────────┤
│ 🐛 Ask DebugDuck...                            [Send]   │
└──────────────────────────────────────────────────────────┘
```

### Interaction States
- **Collapsed:** Input bar only. Click or ⌘K to expand.
- **Expanded idle:** Chat history + input. ▼ or Escape to collapse.
- **Streaming:** Agent response types character-by-character. Input disabled during stream.
- **Tool executing:** Shows "🔧 Starting investigation..." status while backend runs tools.

## Message Types

| Type | Rendering |
|---|---|
| Text | Normal text, markdown-supported |
| Action buttons | Clickable buttons: View, Scan, Download, Navigate |
| Data table | Compact formatted session/findings list |
| Code block | Monospace with copy button (SQL recommendations) |
| Status | ✓/⚠/✗ colored status lines |
| Tool progress | "🔧 Calling list_sessions..." with spinner |

## System Prompt

```
You are DebugDuck, an AI SRE assistant. You help operators:
- Check system health and investigation status
- Start diagnostic investigations (application, database, network, cluster)
- Review findings and fix recommendations
- Navigate the platform

You have tools to take real actions. When asked to do something, DO IT.
Don't ask for confirmation unless destructive (cancelling investigations).

Be concise. Use bullet points. Include incident IDs. Suggest next steps.
Stay focused on SRE operations — you are NOT a general chatbot.
```

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| ⌘K / Ctrl+K | Toggle dock |
| Escape | Collapse |
| Enter | Send |
| Shift+Enter | New line |

## Thread Persistence

- Thread stored in SQLite (`assistant_threads` table)
- One thread per user (or per browser session if no auth)
- Thread survives page refresh
- [Clear] button resets thread
- Thread auto-clears after 24h of inactivity

## Files to Create

**Frontend:**
- `frontend/src/components/Assistant/AssistantDock.tsx` — main dock component
- `frontend/src/components/Assistant/AssistantMessage.tsx` — message bubble renderer
- `frontend/src/hooks/useAssistantChat.ts` — chat state + API calls + streaming
- Add to `HomePage.tsx` — render `<AssistantDock>` at bottom

**Backend:**
- `backend/src/api/assistant_endpoints.py` — `/api/v4/assistant/chat` endpoint
- `backend/src/agents/assistant/orchestrator.py` — agentic tool-calling loop
- `backend/src/agents/assistant/tools.py` — 10 tool implementations
- `backend/src/agents/assistant/prompts.py` — system prompt

## Non-Goals (YAGNI)

- Multi-user threads (single user for now)
- File upload / image analysis
- Voice input
- Plugin/custom tool system
- Chat history export
- Agent personality customization
