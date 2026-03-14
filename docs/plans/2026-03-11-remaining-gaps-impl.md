# Remaining Gaps (P1 + P2) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close the 6 remaining gaps from the gap audit — 1 P1 (related_sessions backend) and 5 P2 (summary header, fontFamily cleanup, db_session_endpoints extraction, Pydantic evidence models, GraphEmbedder).

**Architecture:** Backend changes touch `routes_v4.py` (session linking + endpoint extraction), `graph_v2.py` (Pydantic evidence models), and a new `graph_embedder.py`. Frontend changes touch `SurgicalTelescope.tsx` (summary header) and bulk `fontFamily` → Tailwind class replacements.

**Tech Stack:** Python/FastAPI, Pydantic, LangGraph TypedDict, React/TypeScript, Tailwind CSS, gensim (Node2Vec)

---

### Task 1: Bidirectional `related_sessions` linking (P1-3.4)

**Files:**
- Modify: `backend/src/api/models.py:99-106` — add fields to `SessionSummary`
- Modify: `backend/src/api/routes_v4.py:121` — add helper for session linking
- Modify: `backend/src/api/routes_v4.py:327-367` — store `parent_session_id` and link back
- Modify: `backend/src/api/routes_v4.py:791-803` — return new fields in listing
- Modify: `backend/src/api/routes_v4.py:806-844` — return new fields in status

**Step 1: Add `capability`, `investigation_mode`, and `related_sessions` to `SessionSummary`**

In `backend/src/api/models.py`, update the `SessionSummary` model:

```python
class SessionSummary(BaseModel):
    session_id: str
    service_name: Optional[str] = None
    incident_id: Optional[str] = None
    phase: str
    confidence: int
    created_at: str
    capability: Optional[str] = None
    investigation_mode: Optional[str] = None
    related_sessions: list[str] = []
```

**Step 2: Add `_link_sessions` helper and wire bidirectional linking at session creation**

In `routes_v4.py`, after the `sessions` dict declaration (~line 122), add:

```python
def _link_sessions(session_a: str, session_b: str):
    """Bidirectionally link two sessions."""
    for src, dst in [(session_a, session_b), (session_b, session_a)]:
        sess = sessions.get(src)
        if sess:
            related = sess.setdefault("related_sessions", [])
            if dst not in related:
                related.append(dst)
```

In the `database_diagnostics` session creation block (~line 331), after storing the session dict, add the bidirectional link:

```python
sessions[session_id] = { ... }  # existing

# Bidirectional session linking
parent_sid = extra.get("parent_session_id")
if parent_sid and parent_sid in sessions:
    _link_sessions(session_id, parent_sid)
    sessions[session_id]["investigation_mode"] = "contextual"
else:
    sessions[session_id]["investigation_mode"] = "standalone"
```

**Step 3: Update `list_sessions` to include new fields**

```python
@router_v4.get("/sessions", response_model=list[SessionSummary])
async def list_sessions():
    return [
        SessionSummary(
            session_id=sid,
            service_name=data["service_name"],
            incident_id=data.get("incident_id"),
            phase=data["phase"],
            confidence=data["confidence"],
            created_at=data["created_at"],
            capability=data.get("capability"),
            investigation_mode=data.get("investigation_mode"),
            related_sessions=data.get("related_sessions", []),
        )
        for sid, data in sessions.items()
    ]
```

**Step 4: Update `get_session_status` to include new fields**

In the `result` dict construction (~line 815), add:

```python
result = {
    ...existing fields...
    "capability": session.get("capability"),
    "investigation_mode": session.get("investigation_mode"),
    "related_sessions": session.get("related_sessions", []),
}
```

**Step 5: Wire `context_loader` to fetch parent findings**

In `graph_v2.py:100-116`, replace the TODO stub:

```python
async def context_loader(state: DBDiagnosticStateV2) -> dict:
    """Load parent app session findings if in contextual mode."""
    emitter = state.get("_emitter")
    parent_id = state.get("parent_session_id")

    if state.get("investigation_mode") != "contextual" or not parent_id:
        if emitter:
            await emitter.emit("context_loader", "success", "Standalone mode — no app context")
        return {"app_context": {}, "investigation_mode": "standalone"}

    if emitter:
        await emitter.emit("context_loader", "started",
                          f"Loading context from app session {parent_id}")

    # Fetch findings from parent session's in-memory state
    app_context = {"parent_session_id": parent_id}
    try:
        from src.api.routes_v4 import sessions as v4_sessions
        parent = v4_sessions.get(parent_id)
        if parent and parent.get("state"):
            pstate = parent["state"]
            if hasattr(pstate, "all_findings"):
                app_context["findings_summary"] = [
                    {"finding_id": f.finding_id, "summary": f.summary, "severity": f.severity}
                    for f in pstate.all_findings[:10]
                ]
            if hasattr(pstate, "incident_id"):
                app_context["incident_id"] = pstate.incident_id
    except Exception as e:
        logger.warning("Failed to load parent context: %s", e)

    if emitter:
        await emitter.emit("context_loader", "success",
                          f"Loaded context ({len(app_context.get('findings_summary', []))} findings)")
    return {"app_context": app_context}
```

**Step 6: Commit**

```bash
git add backend/src/api/models.py backend/src/api/routes_v4.py backend/src/agents/database/graph_v2.py
git commit -m "feat: add bidirectional related_sessions linking (P1-3.4)"
```

---

### Task 2: Summary header with insertions/deletions count (P2-1.3)

**Files:**
- Modify: `frontend/src/components/Investigation/SurgicalTelescope.tsx:94-100`

**Step 1: Compute totals and update the header**

Replace lines 97-100 with a `useMemo` that sums per-file diffs:

```tsx
{/* File tree sidebar */}
{files.length > 1 && (
  <div className="w-[200px] shrink-0 border-r border-slate-800/40 overflow-y-auto bg-slate-950/30">
    <div className="px-3 py-2 text-[9px] text-slate-500 border-b border-slate-800/30">
      {files.length} files changed
      {(() => {
        const totals = files.reduce((acc, f) => {
          const diff = f.diff || '';
          acc.add += (diff.match(/^\+[^+]/gm) || []).length;
          acc.del += (diff.match(/^-[^-]/gm) || []).length;
          return acc;
        }, { add: 0, del: 0 });
        return <>, <span className="text-emerald-500">{totals.add} insertions(+)</span>, <span className="text-red-400">{totals.del} deletions(-)</span></>;
      })()}
    </div>
```

**Step 2: Commit**

```bash
git add frontend/src/components/Investigation/SurgicalTelescope.tsx
git commit -m "fix: add insertions/deletions count to SurgicalTelescope summary header (P2-1.3)"
```

---

### Task 3: Replace inline `fontFamily` with Tailwind classes (P2-2.4)

**Files:**
- Modify: ~40 files in `frontend/src/components/` — bulk replacement

There are 3 categories of `fontFamily` values to replace:

**Step 1: Replace `fontFamily: 'Material Symbols Outlined'` (~190 occurrences)**

These are icon spans. The pattern is:
```tsx
// Before:
<span style={{ fontFamily: 'Material Symbols Outlined', fontSize: 18 }}>icon_name</span>

// After (use the existing CSS class pattern):
<span className="material-symbols-outlined text-[18px]">icon_name</span>
```

The `material-symbols-outlined` class is already defined in `index.css` with `font-family: 'Material Symbols Outlined'`. Convert each instance — move `fontSize` to a Tailwind `text-[Npx]` class, drop the `style` prop entirely if empty after removal.

Process files in this order (highest count first):
1. `EvidenceFindings.tsx` (~30)
2. `AISupervisor.tsx` (~20)
3. `FixPipelinePanel.tsx` (~17)
4. `EvidenceStack.tsx` (~17)
5. `Investigator.tsx` (~16)
6. `PostMortemDossierView.tsx` (~13)
7. All remaining files (~80)

**Step 2: Replace `fontFamily: 'monospace'` (~25 occurrences)**

```tsx
// Before:
<span style={{ fontFamily: 'monospace' }}>192.168.1.1</span>

// After:
<span className="font-mono">192.168.1.1</span>
```

For SVG `<text>` elements, keep inline `fontFamily` since Tailwind classes don't work on SVG text elements.

**Step 3: Replace `fontFamily: 'Inter, system-ui, sans-serif'` (2 occurrences in NDMTopologyTab.tsx)**

These are SVG `fontFamily` attributes — keep as-is (SVG requires inline font declarations).

**Step 4: Commit**

```bash
git add frontend/src/components/
git commit -m "refactor: replace inline fontFamily with Tailwind classes (P2-2.4)"
```

---

### Task 4: Extract `db_session_endpoints.py` from `routes_v4.py` (P2-3.1)

**Files:**
- Create: `backend/src/api/db_session_endpoints.py`
- Modify: `backend/src/api/routes_v4.py` — remove extracted code, import new router
- Modify: `backend/src/api/main.py` — mount new router

**Step 1: Create `db_session_endpoints.py`**

Extract DB-session-specific code from `routes_v4.py`:
- The `database_diagnostics` branch from `start_session` → new `POST /api/v4/db/session/start`
- The `run_db_diagnosis` background function
- DB-specific branches from `get_session_status` and `get_findings`

```python
"""Database diagnostics session endpoints — extracted from routes_v4.py."""

from fastapi import APIRouter, BackgroundTasks, HTTPException
import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

db_session_router = APIRouter(prefix="/api/v4", tags=["v4-db-sessions"])
```

Move `run_db_diagnosis()` function and the DB-diagnostics branch of `start_session` into this file. Import `sessions`, `session_locks`, `_link_sessions` from `routes_v4` (they remain the shared session store).

**Step 2: Update `routes_v4.py`**

Remove the `database_diagnostics` branch from `start_session`. Remove `run_db_diagnosis`. Add import comment pointing to new file.

**Step 3: Mount in `main.py`**

```python
from src.api.db_session_endpoints import db_session_router
app.include_router(db_session_router)
```

**Step 4: Commit**

```bash
git add backend/src/api/db_session_endpoints.py backend/src/api/routes_v4.py backend/src/api/main.py
git commit -m "refactor: extract db_session_endpoints.py from routes_v4 (P2-3.1)"
```

---

### Task 5: Use Pydantic `DBFindingV2` in graph_v2 evidence pipeline (P2-3.5)

**Files:**
- Modify: `backend/src/agents/database/graph_v2.py:16-56` — change TypedDict finding types
- Modify: `backend/src/agents/database/graph_v2.py:138-151` — use `DBFindingV2` in query_analyst
- Modify: `backend/src/agents/database/graph_v2.py:185-241` — use `DBFindingV2` in health_analyst
- Modify: `backend/src/agents/database/graph_v2.py:263-267` — schema_analyst

**Step 1: Update `DBDiagnosticStateV2` type annotations**

LangGraph's `TypedDict` state can't hold Pydantic models directly in the type annotation (it uses dict merge), so keep `list[dict]` in the TypedDict but validate at creation time:

```python
from src.database.models import DBFindingV2
```

**Step 2: Create findings via `DBFindingV2` in each analyst node**

In `query_analyst` (~line 138), replace raw dict with:

```python
finding = DBFindingV2(
    finding_id=f"f-qa-{q.pid}",
    agent="query_analyst",
    category="slow_query",
    title=f"Slow query (pid={q.pid}, {q.duration_ms}ms)",
    severity=severity,
    confidence_raw=0.9,
    confidence_calibrated=0.85,
    detail=f"Query running for {q.duration_ms}ms: {q.query[:200]}",
    recommendation="Review query plan and consider adding indexes",
    remediation_available=True,
    rule_check=f"duration_ms={q.duration_ms} > 5000",
)
findings.append(finding.model_dump())
```

Apply same pattern in `health_analyst` for each finding construction.

**Step 3: Commit**

```bash
git add backend/src/agents/database/graph_v2.py
git commit -m "refactor: validate findings via DBFindingV2 Pydantic model (P2-3.5)"
```

---

### Task 6: GraphEmbedder with Node2Vec (P2-4.3)

**Files:**
- Create: `backend/src/agents/graph_embedder.py`
- Modify: `backend/requirements.txt` — add `gensim>=4.3.0`

**Step 1: Add gensim dependency**

```
gensim>=4.3.0
```

**Step 2: Create `graph_embedder.py`**

```python
"""Graph embedding using Node2Vec-style random walks for incident fingerprinting."""

import random
import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Minimum incidents before switching from Jaccard to embedding-based similarity
MIN_INCIDENTS_FOR_EMBEDDINGS = 10


class GraphEmbedder:
    """Generate fixed-size vector embedding of an incident graph."""

    def __init__(self, dim: int = 64):
        self.dim = dim

    def embed(self, graph) -> np.ndarray:
        """Node2Vec-style embedding: random walks -> Word2Vec -> mean-pool.

        Walks use node_type + severity as tokens (not raw IDs) so embeddings
        generalize across incidents with different node identifiers.
        """
        if len(graph.nodes) == 0:
            return np.zeros(self.dim)

        walks = self._random_walks(graph, num_walks=10, walk_length=20)
        if not walks:
            return np.zeros(self.dim)

        word_sequences = [
            [self._node_token(graph, n) for n in walk]
            for walk in walks
        ]

        try:
            from gensim.models import Word2Vec
            model = Word2Vec(
                word_sequences,
                vector_size=self.dim,
                window=5,
                min_count=1,
                sg=1,
                workers=1,
                epochs=5,
            )
            vectors = [
                model.wv[self._node_token(graph, n)]
                for n in graph.nodes
                if self._node_token(graph, n) in model.wv
            ]
            return np.mean(vectors, axis=0) if vectors else np.zeros(self.dim)
        except ImportError:
            logger.warning("gensim not installed — falling back to zero vector")
            return np.zeros(self.dim)

    def _node_token(self, graph, node) -> str:
        """Token = node_type:severity (generalizes across incidents)."""
        data = graph.nodes[node]
        node_type = data.get("type", "unknown")
        severity = data.get("severity", "none")
        return f"{node_type}:{severity}"

    def _random_walks(self, graph, num_walks: int, walk_length: int) -> list[list]:
        """Generate random walks over the graph."""
        walks = []
        nodes = list(graph.nodes)
        for _ in range(num_walks):
            for start in nodes:
                walk = [start]
                current = start
                for _ in range(walk_length - 1):
                    neighbors = list(graph.successors(current))
                    if not neighbors:
                        neighbors = list(graph.predecessors(current))
                    if not neighbors:
                        break
                    current = random.choice(neighbors)
                    walk.append(current)
                walks.append(walk)
        return walks

    def cosine_similarity(self, vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        """Cosine similarity between two embeddings."""
        norm_a = np.linalg.norm(vec_a)
        norm_b = np.linalg.norm(vec_b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(vec_a, vec_b) / (norm_a * norm_b))
```

**Step 3: Commit**

```bash
git add backend/src/agents/graph_embedder.py backend/requirements.txt
git commit -m "feat: add GraphEmbedder with Node2Vec-style incident fingerprinting (P2-4.3)"
```

---

## Execution Order

1. **Task 1** (P1-3.4) — related_sessions backend — highest priority
2. **Task 5** (P2-3.5) — Pydantic evidence models — touches same graph_v2.py file
3. **Task 4** (P2-3.1) — extract db_session_endpoints — touches same routes_v4.py file
4. **Task 2** (P2-1.3) — summary header — independent frontend
5. **Task 3** (P2-2.4) — fontFamily cleanup — independent frontend, largest scope
6. **Task 6** (P2-4.3) — GraphEmbedder — independent new file
