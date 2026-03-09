# Vintage Ledger Chat Drawer — Full Rebuild Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the current dual-chat system (FloatingChatWindow + CommandDrawer) with a single, architecturally clean "Vintage Ledger" Chat Drawer featuring a ChatContext provider, live-streaming markdown rendering, and a polished War Room aesthetic.

**Architecture:** Decouple chat state into a React Context provider. Replace prop drilling with context consumption. Introduce WebSocket-based streaming for AI responses. Consolidate 7 chat files into 5 focused components behind a single drawer.

**Tech Stack:** React 18, TypeScript, Framer Motion, react-markdown, rehype-highlight, Tailwind CSS, WebSocket streaming

---

## UI/UX Constraints (Non-Negotiable)

1. **PRESERVE LIVE STREAMING (CRITICAL):** `react-markdown` must handle continuously updating strings without remounting. "Aggressive Auto-Scroll" (`el.scrollHeight - el.scrollTop - el.clientHeight < 40`) tied to BOTH `messages.length` AND `streamingContent` updates. Unclosed markdown fences (like ` ```bash `) must not crash the renderer mid-stream.

2. **RESPONSIVE DRAWER:** ChatDrawer must NOT be hardcoded to `w-[420px]`. Use `w-full sm:w-[420px] max-w-[100vw]` to prevent horizontal scrollbars on smaller viewports.

3. **SLASH COMMAND OVERFLOW:** SlashCommandMenu must have `max-h-[200px] overflow-y-auto` and a z-index HIGHER than the message feed (z-[70]) to prevent clipping when 15+ commands are added.

4. **Z-INDEX ENFORCEMENT:** `z-[60]` for Drawer + Ledger Tab, `z-[55]` for Backdrop. These are calibrated against the Investigator Panel (Patient Zero Banner at z-50). Do NOT alter.

---

## Why Full Rebuild (Not Band-Aid)

| Dimension | Current Problem | After Rebuild |
|-----------|----------------|---------------|
| **Visual Identity** | Generic rectangular column, overlapping glitch at small viewports | Floating "Vintage Ledger" SVG trigger, slide-over drawer saves screen real estate |
| **Architecture** | Messy prop drilling App→InvestigationView→CommandDrawer. Two overlapping implementations (FloatingChatWindow 404L + CommandDrawer 512L) | ChatContext Provider decouples chat from layout. Any War Room panel can trigger messages |
| **Feature Gaps** | Raw text output, no markdown, no code copy, fixed-height textarea | react-markdown engine, TerminalCodeBlock with copy-to-clipboard, auto-resizing textarea |
| **Streaming** | Not implemented — backend returns complete JSON, UI shows "Processing..." spinner | WebSocket chunk streaming with live-typing effect, aggressive auto-scroll |

---

## Current State Audit

### Files to DELETE (consolidated into new system)
| File | Lines | Reason |
|------|-------|--------|
| `Chat/FloatingChatWindow.tsx` | 404 | Replaced by ChatDrawer |
| `Chat/CommandDrawer.tsx` | 512 | Replaced by ChatDrawer |
| `Chat/ChatAnchor.tsx` | 74 | Replaced by LedgerTriggerTab |
| `Chat/ChatTab.tsx` | 113 | Unused in War Room |
| `Chat/ChatMessage.tsx` | 42 | Replaced by MarkdownBubble |
| `Chat/InlineCard.tsx` | 53 | Absorbed into MarkdownBubble |
| **Total deleted** | **~1,198** | |

### Files to KEEP (untouched or minor edits)
| File | Action |
|------|--------|
| `Chat/ActionChip.tsx` (63L) | Keep, fix missing `animate-chip-success` CSS |
| `services/api.ts` | Modify `sendChatMessage` for streaming |
| `hooks/useWebSocket.ts` | Add `chat_chunk` handler |
| `types/index.ts` | Extend ChatMessage type |
| `App.tsx` | Remove chat state (moved to ChatContext) |
| `InvestigationView.tsx` | Remove chat props drilling |

---

## Architecture

### New File Map

```
frontend/src/
├── contexts/
│   └── ChatContext.tsx              NEW  ~120L  (state provider)
├── components/Chat/
│   ├── ChatDrawer.tsx               NEW  ~350L  (main drawer shell)
│   ├── LedgerTriggerTab.tsx         NEW  ~80L   (SVG icon + tab)
│   ├── MarkdownBubble.tsx           NEW  ~140L  (streaming markdown)
│   ├── TerminalCodeBlock.tsx        NEW  ~70L   (code + copy button)
│   ├── ChatInputArea.tsx            NEW  ~120L  (auto-resize + slash)
│   ├── ActionChip.tsx               KEEP ~65L   (fix CSS animation)
│   └── SlashCommandMenu.tsx         NEW  ~60L   (extracted from old code)
├── hooks/
│   └── useStreamingMessage.ts       NEW  ~50L   (chunk accumulator)
├── styles/
│   └── chat-animations.ts          NEW  ~30L   (framer variants)
```

**Net: ~1,085 new lines, ~1,198 deleted = ~113 fewer lines total**

---

## Phase 1: ChatContext Provider (Architecture Foundation)

### `contexts/ChatContext.tsx`

**Purpose:** Single source of truth for all chat state. Eliminates prop drilling through App→InvestigationView→CommandDrawer.

```typescript
interface ChatContextValue {
  // State
  messages: ChatMessage[];
  isOpen: boolean;
  isStreaming: boolean;
  streamingContent: string;        // Live-updating partial message
  unreadCount: number;
  isWaiting: boolean;              // Foreman needs operator input

  // Actions
  sendMessage: (content: string) => Promise<void>;
  toggleDrawer: () => void;
  openDrawer: () => void;
  closeDrawer: () => void;
  markRead: () => void;
}
```

**State migration from App.tsx:**
- Move `chatMessages` (Record<string, ChatMessage[]>) into context
- Move `chatOpen` (boolean) into context
- Move `handleChatResponse` and `handleNewChatMessage` into context
- Context reads `activeSessionId` from props/parent context
- WebSocket `onChatResponse` and new `onChatChunk` handlers live inside context

**Consumption pattern:**
```typescript
// Any component in War Room can now do:
const { sendMessage, openDrawer } = useChatContext();
```

**What App.tsx loses:**
- `chatMessages` state (~4 lines)
- `chatOpen` state (~2 lines)
- `handleChatResponse` callback (~10 lines)
- `handleNewChatMessage` callback (~10 lines)
- Chat-related props passed to InvestigationView (~6 lines)

**What InvestigationView.tsx loses:**
- All chat-related props from interface (~5 fields)
- Chat pass-through to CommandDrawer (~8 lines)
- Unread count effect (~10 lines)
- ChatAnchor rendering (~4 lines)

---

## Phase 2: Vintage Ledger Trigger Tab

### `LedgerTriggerTab.tsx`

**Purpose:** Replace ChatAnchor with the Vintage Ledger SVG icon and right-edge trigger tab.

**Visual spec:**
- Fixed position: `top-16 right-0 bottom-0 z-[60] w-12` (48px, slightly wider than current 40px)
- Vintage ledger SVG icon (hand-drawn book with bookmark, ~24x24)
- Vertical text: "MISSION LOG" (idle) or "INPUT REQUIRED" (waiting, amber pulse)
- Unread badge: top-left corner, amber-400 bg, mono font
- Glow effect on hover: `drop-shadow(0 0 8px rgba(7, 182, 213, 0.4))`

**SVG icon concept:**
```
┌──────┐
│ ≡≡≡≡ │  ← "pages" lines
│ ≡≡≡≡ │
│ ≡≡   │
│      │
└──┬───┘
   │      ← bookmark ribbon
```

- Stroke-based SVG (not filled), matches the terminal/wireframe aesthetic
- Color: `stroke-cyan-400` idle, `stroke-amber-400` when waiting
- Animates with subtle `strokeDashoffset` on hover (ink drawing effect)

**Interaction:**
- Click toggles `chatContext.toggleDrawer()`
- Uses context directly (no props)

---

## Phase 3: ChatDrawer Shell

### `ChatDrawer.tsx`

**Purpose:** The main drawer container — replaces both FloatingChatWindow and CommandDrawer.

**Layout:**
```
┌─────────────────────────────────────┐
│ Header: 📖 Mission_Log.v7 ● [X]    │  shrink-0, h-12
├─────────────────────────────────────┤
│ [Optional] Waiting Banner           │  shrink-0
│ "Foreman awaiting operator input"   │
├─────────────────────────────────────┤
│                                     │
│ Messages Area (scrollable)          │  flex-1
│  ┌─ MarkdownBubble (assistant) ──┐  │
│  │ Agent badge + markdown content │  │
│  └───────────────────────────────┘  │
│        ┌── MarkdownBubble (user) ─┐ │
│        │ OPERATOR + raw text      │ │
│        └──────────────────────────┘ │
│  ┌─ MarkdownBubble (streaming) ──┐  │
│  │ Live typing... █              │  │  ← cursor blink
│  └───────────────────────────────┘  │
│                                     │
├─────────────────────────────────────┤
│ [Optional] Action Chips Ribbon      │  shrink-0
│ [Approve Fix] [Request Changes]     │
├─────────────────────────────────────┤
│ ChatInputArea                       │  shrink-0
│ ┌─────────────────────────── [▶]─┐  │
│ │ Ask the crew anything...        │  │
│ └─────────────────────────────────┘  │
│ [Optional] SlashCommandMenu         │
└─────────────────────────────────────┘
```

**Dimensions:**
- Width: `w-full sm:w-[420px] max-w-[100vw]` (responsive — full width on mobile, 420px on sm+)
- Position: `fixed top-16 right-0 bottom-0 z-[60]`
- Background: `bg-slate-900/95 backdrop-blur-xl`
- Border: `border-l-2 border-cyan-500/20` (idle) / `border-amber-500/40` (waiting)

**Animation:**
- Spring config: `{ type: 'spring', stiffness: 280, damping: 32, mass: 1.2 }`
- Entry: `x: '100%'` → `x: 0`
- Exit: `x: 0` → `x: '100%'`
- Backdrop: `bg-black/10 backdrop-blur-[2px]` at `z-[55]`, `pointer-events-none`

**State from context:**
```typescript
const { messages, isOpen, isStreaming, streamingContent, isWaiting,
        sendMessage, closeDrawer, unreadCount } = useChatContext();
```

**Auto-scroll logic (CRITICAL):**
```typescript
const scrollRef = useRef<HTMLDivElement>(null);
const [userScrolled, setUserScrolled] = useState(false);

// Track if user manually scrolled up
const handleScroll = () => {
  const el = scrollRef.current;
  if (!el) return;
  const isAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
  setUserScrolled(!isAtBottom);
};

// Aggressive auto-scroll: triggers on message count AND streaming content changes
useEffect(() => {
  if (!userScrolled) {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }
}, [messages.length, streamingContent, userScrolled]);
```

---

## Phase 4: MarkdownBubble (Streaming-Safe Markdown Renderer)

### `MarkdownBubble.tsx`

**Purpose:** Render a single chat message with full Markdown support, agent branding, and streaming safety.

**Props:**
```typescript
interface MarkdownBubbleProps {
  message: ChatMessage;
  isStreaming?: boolean;          // Show cursor, skip memoization
  streamingContent?: string;      // Live-updating content (overrides message.content)
}
```

**Agent detection:**
```typescript
const agentSignatures: Record<string, { label: string; color: string; icon: string }> = {
  log_agent:     { label: 'LOG AGENT',      color: 'red',     icon: 'search' },
  metrics_agent: { label: 'METRICS AGENT',  color: 'cyan',    icon: 'bar_chart' },
  k8s_agent:     { label: 'K8S AGENT',      color: 'orange',  icon: 'dns' },
  code_agent:    { label: 'CODE AGENT',     color: 'blue',    icon: 'code' },
  supervisor:    { label: 'SRE FOREMAN',    color: 'cyan',    icon: 'psychology' },
};
// Detect from message.metadata?.agent or content keyword matching (fallback)
```

**User messages:**
- Right-aligned, cyan tinted
- Prefix: `○ OPERATOR`
- Raw text (no markdown)

**Assistant messages:**
- Left-aligned, agent-colored left border (3px)
- Agent badge: `● AGENT_LABEL` with icon
- Content rendered via `react-markdown` with plugins:
  - `rehype-highlight` for syntax highlighting
  - `rehype-raw` for inline HTML
  - Custom `code` component → routes to `TerminalCodeBlock` for fenced blocks
- Timestamp: bottom-right, `text-[9px] text-slate-600`

**CRITICAL: Streaming + Markdown safety:**

1. **Continuous parsing:** The `react-markdown` component accepts `content` as prop. When `isStreaming=true`, pass `streamingContent` which updates every chunk. React-markdown re-renders gracefully without remounting because the key stays stable (same message ID).

2. **Unfinished markdown safeties:** react-markdown handles unclosed code fences gracefully by default. Add a safety wrapper:
   ```typescript
   const safeContent = useMemo(() => {
     if (!isStreaming) return content;
     // If streaming content ends mid-code-fence, don't crash
     const openFences = (streamingContent.match(/```/g) || []).length;
     if (openFences % 2 !== 0) {
       return streamingContent + '\n```';  // Close the fence temporarily
     }
     return streamingContent;
   }, [streamingContent, isStreaming, content]);
   ```

3. **Memoization guard:** Non-streaming messages are memoized (`React.memo` with shallow compare). Streaming message skips memoization to allow re-renders on every chunk.

4. **Cursor blink:** When `isStreaming`, append a blinking cursor span after the markdown content:
   ```css
   .streaming-cursor::after {
     content: '█';
     animation: cursor-blink 1s step-end infinite;
   }
   ```

---

## Phase 5: TerminalCodeBlock (Copy-to-Clipboard)

### `TerminalCodeBlock.tsx`

**Purpose:** Custom code block renderer for react-markdown's `code` component override.

**Props:**
```typescript
interface TerminalCodeBlockProps {
  children: string;
  className?: string;     // Contains language-xxx from markdown
  inline?: boolean;
}
```

**Inline code:** Render as `<code>` with existing prose-invert styles.

**Fenced code blocks:**
```
┌── bash ──────────────────── [📋] ─┐
│ kubectl get pods -n production     │
│ NAME           READY   STATUS     │
│ api-server-1   1/1     Running    │
└────────────────────────────────────┘
```

- Header bar: language label (left) + copy button (right)
- Background: `bg-black/40`
- Border: `border border-slate-700/50 rounded-lg`
- Font: `font-mono text-[12px]`
- Syntax highlighting via `rehype-highlight` (already in package.json)
- Copy button:
  - Icon: `content_copy` (Material Symbols)
  - On click: `navigator.clipboard.writeText(children)`
  - Feedback: icon changes to `check` for 2 seconds, then reverts
  - Color: `text-slate-500 hover:text-cyan-400`

---

## Phase 6: ChatInputArea (Smart Auto-Resize)

### `ChatInputArea.tsx`

**Purpose:** Auto-resizing textarea with slash command integration and keyboard handling.

**Props:**
```typescript
interface ChatInputAreaProps {
  onSend: (content: string) => void;
  disabled?: boolean;
  placeholder?: string;
}
```

**Auto-resize behavior:**
```typescript
const textareaRef = useRef<HTMLTextAreaElement>(null);

const adjustHeight = useCallback(() => {
  const el = textareaRef.current;
  if (!el) return;
  el.style.height = 'auto';                         // Reset
  el.style.height = `${Math.min(el.scrollHeight, 120)}px`;  // Grow up to 120px
}, []);

// Trigger on every input change
useEffect(() => {
  adjustHeight();
}, [input, adjustHeight]);
```

**Slash command menu:**
- Typing `/` at start of input opens `SlashCommandMenu` above textarea
- Commands: `/logs`, `/k8s`, `/trace`, `/fix`, `/rollback`, `/status`
- Arrow key navigation (↑/↓), Enter/Tab to select, Esc to close
- Two-stage Escape: close menu first, then close drawer
- **Overflow constraint:** `max-h-[200px] overflow-y-auto z-[70]` (higher than message feed, prevents clipping with 15+ commands)

**Keyboard:**
- `Enter` sends message (when no slash menu open)
- `Shift+Enter` inserts newline
- `Esc` closes slash menu or drawer

**Visual:**
- Background: `bg-slate-800/50`
- Border: `border border-slate-700/50` → `border-cyan-500/50` on focus
- Font: `font-mono text-sm text-slate-200`
- Send button: absolute positioned, bottom-right, cyan-600, disabled when empty/streaming

---

## Phase 7: Live Streaming Infrastructure

### Backend Changes (`backend/src/api/routes_v4.py` + `websocket.py`)

**New WebSocket message type: `chat_chunk`**

```python
# In the supervisor's handle_user_message, change from:
#   response = await llm_client.chat(messages)
#   return response.text
# To:
async for chunk in llm_client.chat_stream(messages):
    await ws_manager.send_json(session_id, {
        "type": "chat_chunk",
        "data": {
            "content": chunk,
            "done": False
        }
    })

# Final message:
await ws_manager.send_json(session_id, {
    "type": "chat_chunk",
    "data": {
        "content": "",
        "done": True,
        "full_response": full_text,
        "phase": current_phase,
        "confidence": confidence_score
    }
})
```

**Keep the HTTP `/chat` endpoint as fallback** (for non-WebSocket clients).

### Frontend Changes

**`hooks/useStreamingMessage.ts`:**
```typescript
interface StreamingState {
  isStreaming: boolean;
  content: string;           // Accumulated chunks
  messageId: string | null;  // ID of message being streamed
}

function useStreamingMessage() {
  const [state, setState] = useState<StreamingState>({
    isStreaming: false, content: '', messageId: null
  });

  const appendChunk = useCallback((chunk: string) => {
    setState(prev => ({
      ...prev,
      isStreaming: true,
      content: prev.content + chunk,
    }));
  }, []);

  const finishStream = useCallback((fullResponse: string) => {
    setState({ isStreaming: false, content: '', messageId: null });
    return fullResponse;  // Caller adds to messages array
  }, []);

  const startStream = useCallback(() => {
    setState({ isStreaming: true, content: '', messageId: crypto.randomUUID() });
  }, []);

  return { ...state, appendChunk, finishStream, startStream };
}
```

**`useWebSocket.ts` additions:**
```typescript
case 'chat_chunk':
  if (data.done) {
    handlersRef.current.onChatStreamEnd?.(data as ChatStreamEndPayload);
  } else {
    handlersRef.current.onChatChunk?.(data.content as string);
  }
  break;
```

**ChatContext integration:**
- On user send: call `startStream()`, show streaming bubble immediately
- On each `chat_chunk`: call `appendChunk(chunk)`, bubble re-renders with growing content
- On `chat_chunk` with `done: true`: call `finishStream()`, add complete message to array
- Aggressive auto-scroll fires on every `streamingContent` change

### Aggressive Auto-Scroll (CRITICAL DIRECTIVE)

The auto-scroll must trigger not just when `messages.length` changes, but also whenever `streamingContent` updates:

```typescript
// In ChatDrawer
useEffect(() => {
  if (!userScrolled && scrollRef.current) {
    scrollRef.current.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: 'smooth'
    });
  }
}, [messages.length, streamingContent, userScrolled]);
```

This creates the buttery-smooth terminal output effect where the view stays pinned as the AI types a 40-line log analysis.

---

## Phase 8: Cleanup & Integration

### Delete old files:
```bash
rm frontend/src/components/Chat/FloatingChatWindow.tsx
rm frontend/src/components/Chat/CommandDrawer.tsx
rm frontend/src/components/Chat/ChatAnchor.tsx
rm frontend/src/components/Chat/ChatTab.tsx
rm frontend/src/components/Chat/ChatMessage.tsx
rm frontend/src/components/Chat/InlineCard.tsx
```

### Fix ActionChip.tsx:
Add missing `animate-chip-success` CSS animation to `index.css`:
```css
@keyframes chip-success {
  0% { background-color: currentColor; transform: scale(1); }
  50% { background-color: #10b981; transform: scale(1.05); }
  100% { background-color: #10b981; transform: scale(1); }
}
.animate-chip-success {
  animation: chip-success 0.3s ease-out forwards;
}
```

### Update App.tsx:
- Remove chat state declarations
- Remove chat handlers
- Remove chat props from InvestigationView
- Wrap InvestigationView in `<ChatProvider sessionId={activeSessionId} wsRef={wsRef}>`

### Update InvestigationView.tsx:
- Remove all chat-related props from interface
- Remove CommandDrawer import and rendering
- Remove ChatAnchor import and rendering
- Remove unread count effect
- Add `<ChatDrawer />` and `<LedgerTriggerTab />` as self-contained components (they read from context)

### CSS additions to `index.css`:
```css
/* Streaming cursor */
@keyframes cursor-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
.streaming-cursor::after {
  content: '█';
  color: #07b6d5;
  animation: cursor-blink 1s step-end infinite;
}

/* Ledger icon ink draw effect */
@keyframes ink-draw {
  from { stroke-dashoffset: 100; }
  to { stroke-dashoffset: 0; }
}
.ledger-icon-draw {
  stroke-dasharray: 100;
  animation: ink-draw 0.6s ease-out forwards;
}

/* Action chip success (missing CSS fix) */
@keyframes chip-success {
  0% { transform: scale(1); }
  50% { background-color: #10b981; transform: scale(1.05); }
  100% { background-color: #10b981; transform: scale(1); }
}
.animate-chip-success {
  animation: chip-success 0.3s ease-out forwards;
}
```

---

## Task Execution Order

| Task | Phase | Files | Depends On | Est. Lines |
|------|-------|-------|------------|-----------|
| 1 | ChatContext Provider | `contexts/ChatContext.tsx`, `App.tsx`, `InvestigationView.tsx` | — | ~120 new, ~45 deleted |
| 2 | useStreamingMessage hook | `hooks/useStreamingMessage.ts` | Task 1 | ~50 new |
| 3 | WebSocket chat_chunk handler | `hooks/useWebSocket.ts` | Task 2 | ~15 modified |
| 4 | Backend streaming endpoint | `routes_v4.py`, `websocket.py` | — | ~40 modified |
| 5 | TerminalCodeBlock | `Chat/TerminalCodeBlock.tsx` | — | ~70 new |
| 6 | MarkdownBubble | `Chat/MarkdownBubble.tsx` | Task 5 | ~140 new |
| 7 | SlashCommandMenu | `Chat/SlashCommandMenu.tsx` | — | ~60 new |
| 8 | ChatInputArea | `Chat/ChatInputArea.tsx` | Task 7 | ~120 new |
| 9 | LedgerTriggerTab | `Chat/LedgerTriggerTab.tsx` | Task 1 | ~80 new |
| 10 | ChatDrawer shell | `Chat/ChatDrawer.tsx` | Tasks 1,6,8,9 | ~350 new |
| 11 | CSS + animations | `index.css`, `styles/chat-animations.ts` | — | ~60 new |
| 12 | Cleanup dead code | Delete 6 old files, fix ActionChip | Task 10 | ~1,198 deleted |
| 13 | Integration testing | All files | Task 12 | 0 new |

**Critical path:** Task 1 → Task 2 → Task 3 → Task 10 (context → streaming → ws → drawer)

**Parallelizable:** Tasks 4+5+7+11 can run in parallel (no dependencies between them)

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Backend LLM client may not support streaming | Check Anthropic/OpenAI client; if not available, fake streaming by splitting complete response into chunks with `asyncio.sleep(0.02)` between words |
| react-markdown re-renders flicker on rapid chunk updates | Use stable keys (message ID, not array index). Don't remount — only update content prop |
| Unclosed markdown tags mid-stream | Safety wrapper auto-closes dangling code fences |
| Auto-scroll fights user manual scrolling | Track `userScrolled` state via scroll event listener. Only auto-scroll when user is at bottom |
| Removing old chat files breaks imports | Task 12 (cleanup) runs last. Search for all imports of deleted files |

---

## Verification Plan

```bash
# TypeScript compiles
cd frontend && npx tsc --noEmit

# Production build
npx vite build

# Manual testing checklist:
# □ ChatContext provides state to drawer without prop drilling
# □ Drawer opens/closes with spring animation
# □ Vintage Ledger icon renders with ink-draw effect on hover
# □ Messages render with markdown (bold, code, lists, headers)
# □ Fenced code blocks show language label + copy button
# □ Copy button copies code and shows checkmark feedback
# □ Streaming: AI response appears character-by-character
# □ Streaming: auto-scroll follows as text grows
# □ Streaming: manually scrolling up pauses auto-scroll
# □ Streaming: scrolling back to bottom resumes auto-scroll
# □ Unclosed code fence mid-stream doesn't crash
# □ Blinking cursor appears during streaming, disappears when done
# □ Slash commands menu opens on '/', navigable with arrow keys
# □ Textarea auto-grows to 120px max, shrinks when text deleted
# □ Action chips render for fix proposals with correct styling
# □ Unread badge shows on trigger tab when drawer is closed
# □ Waiting state: amber border, "INPUT REQUIRED" label
# □ No console errors or warnings
# □ Old FloatingChatWindow and ChatAnchor imports removed cleanly
# □ War Room 3-column layout unaffected when drawer closed
```
