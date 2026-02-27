import asyncio
import json
import os
import re
import base64
from pathlib import Path
from typing import Any

import httpx

from src.agents.react_base import ReActAgent
from src.models.schemas import ImpactedFile, LineRange, FixArea, CodeAnalysisResult, TokenUsage
from src.utils.event_emitter import EventEmitter
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Max chars of file content to include in pre-fetch (prevents token overflow)
_PREFETCH_FILE_BUDGET = 40_000
# Max files to read in batch fetch from Call 1 plan
_BATCH_FETCH_MAX_FILES = 10
_BATCH_FETCH_MAX_SEARCHES = 5


class CodeNavigatorAgent(ReActAgent):
    """ReAct agent for multi-file code impact analysis with GitHub API support."""

    def __init__(self, max_iterations: int = 15, connection_config=None):
        super().__init__(
            agent_name="code_agent",
            max_iterations=max_iterations,
            connection_config=connection_config,
            budget_overrides={
                "max_llm_calls": 20,
                "max_tokens": 150_000,
                "max_tool_calls": 40,
            },
        )
        self._connection_config = connection_config
        self.repo_path: str = ""
        self._repo_url: str = ""
        self._owner_repo: str = ""
        self._github_token: str = ""
        self._high_priority_files: list[dict] = []
        self._stack_traces: list[str] = []
        self._repo_map: dict[str, str] = {}
        self._verification_mode: bool = False
        self._ask_human_callback = None
        self._event_emitter = None
        self._state = None

    # =========================================================================
    # TWO-PASS MODE: 2 LLM calls instead of 5-15 ReAct iterations
    # =========================================================================

    async def run_two_pass(self, context: dict, event_emitter: EventEmitter | None = None) -> dict:
        """Execute code analysis in exactly 2 LLM calls (Plan + Analyze).

        Phase 0: Pre-fetch — gather repo tree, high-priority files, stack trace
                 files, error searches. Zero LLM calls.
        Call 1:  Plan — LLM sees all pre-fetched data, requests additional files.
                 If it can already produce a final answer, returns it (1 call total).
        Phase 1b: Batch-fetch — read additional files requested by Call 1. Zero LLM calls.
        Call 2:  Analyze — LLM sees everything, produces final CodeAnalysisResult JSON.
        """
        # Initialize agent state from context (same as ReAct mode)
        self._repo_url = context.get("repo_url", "")
        self.repo_path = context.get("repo_path", "")
        self._owner_repo = self._parse_repo_url(self._repo_url) or ""
        self._github_token = context.get("github_token") or os.getenv("GITHUB_TOKEN", "")
        self._high_priority_files = context.get("high_priority_files", [])
        self._stack_traces = context.get("stack_traces", [])
        self._ask_human_callback = context.get("_ask_human_callback")
        self._event_emitter = context.get("_event_emitter")
        self._state = context.get("_state")

        # Multi-repo map
        for svc, url in context.get("repo_map", {}).items():
            parsed = self._parse_repo_url(url)
            if parsed:
                self._repo_map[svc] = parsed

        if event_emitter:
            await event_emitter.emit(self.agent_name, "started", "Code agent starting two-pass analysis")

        # ── Phase 0: Pre-fetch (0 LLM calls) ────────────────────────────
        if event_emitter:
            await event_emitter.emit(self.agent_name, "tool_call", "Pre-fetching repo structure and key files")

        prefetched = await self._prefetch_context(context)
        logger.info("Pre-fetch complete", extra={
            "agent_name": self.agent_name, "action": "prefetch_complete",
            "extra": {
                "tree_files": prefetched.get("tree_file_count", 0),
                "files_read": len(prefetched.get("file_contents", {})),
                "search_results": len(prefetched.get("search_results", {})),
            },
        })

        # ── Call 1: Plan ─────────────────────────────────────────────────
        if event_emitter:
            await event_emitter.emit(self.agent_name, "tool_call", "LLM Call 1: Planning analysis")

        investigation_context = self._build_investigation_context(context)
        plan_prompt = self._build_plan_prompt(investigation_context, prefetched)

        plan_response = await self.llm_client.chat(
            prompt=plan_prompt,
            system=self._two_pass_system_prompt(),
            max_tokens=4096,
        )

        plan = self._parse_plan_response(plan_response.text)
        logger.info("Call 1 (Plan) complete", extra={
            "agent_name": self.agent_name, "action": "plan_complete",
            "extra": {
                "additional_files": len(plan.get("additional_files_needed", [])),
                "additional_searches": len(plan.get("additional_searches", [])),
                "can_produce_final": plan.get("can_produce_final_answer", False),
            },
        })

        # If Call 1 already produced a final answer, return it directly (1 call total)
        if plan.get("can_produce_final_answer") and plan.get("final_answer"):
            logger.info("Call 1 produced final answer — skipping Call 2", extra={
                "agent_name": self.agent_name, "action": "early_finish",
            })
            if event_emitter:
                await event_emitter.emit(self.agent_name, "success", "Code agent completed analysis (1 call)")
            result = self._parse_final_response(json.dumps(plan["final_answer"]))
            return result

        # ── Phase 1b: Batch-fetch (0 LLM calls) ─────────────────────────
        additional_data = await self._batch_fetch(plan)
        if event_emitter and (additional_data.get("file_contents") or additional_data.get("search_results")):
            await event_emitter.emit(
                self.agent_name, "tool_call",
                f"Fetched {len(additional_data.get('file_contents', {}))} additional files, "
                f"{len(additional_data.get('search_results', {}))} searches"
            )

        # ── Call 2: Analyze ──────────────────────────────────────────────
        if event_emitter:
            await event_emitter.emit(self.agent_name, "tool_call", "LLM Call 2: Final analysis")

        analyze_prompt = self._build_analyze_prompt(
            investigation_context, prefetched, additional_data, plan
        )

        analyze_response = await self.llm_client.chat(
            prompt=analyze_prompt,
            system=self._two_pass_analysis_system_prompt(),
            max_tokens=8192,
        )

        if event_emitter:
            await event_emitter.emit(self.agent_name, "success", "Code agent completed analysis")

        result = self._parse_final_response(analyze_response.text)
        result["mode"] = "two_pass"
        result["llm_calls"] = 1 if plan.get("can_produce_final_answer") else 2
        logger.info("Two-pass analysis complete", extra={
            "agent_name": self.agent_name, "action": "complete",
            "extra": {"confidence": result.get("overall_confidence", 0)},
        })
        return result

    # ── Pre-fetch helpers ────────────────────────────────────────────────

    async def _prefetch_context(self, context: dict) -> dict:
        """Gather repo data without any LLM calls."""
        result: dict[str, Any] = {
            "file_tree": [],
            "tree_file_count": 0,
            "file_contents": {},
            "search_results": {},
            "diff_results": {},
        }
        chars_used = 0

        # Decide if we're using GitHub API or local filesystem
        use_github = bool(self._owner_repo)

        # 1. Repo file tree
        try:
            if use_github:
                tree_json = await self._github_list_files({"owner_repo": self._owner_repo})
                tree_data = json.loads(tree_json)
                result["file_tree"] = tree_data.get("files", [])
            else:
                repo = Path(self.repo_path)
                skip = {".git", "__pycache__", "node_modules", ".venv", "venv"}
                files = []
                for p in sorted(repo.rglob("*")):
                    if any(part in skip for part in p.parts):
                        continue
                    if p.is_file():
                        files.append(str(p.relative_to(repo)))
                result["file_tree"] = files[:200]
            result["tree_file_count"] = len(result["file_tree"])
        except Exception as e:
            logger.warning("Pre-fetch: file tree failed: %s", e)

        # 2. High-priority files (from change analysis)
        for hpf in self._high_priority_files[:5]:
            fp = hpf.get("file_path", "")
            if not fp or chars_used >= _PREFETCH_FILE_BUDGET:
                break
            content = await self._read_file_safe(fp, use_github)
            if content:
                result["file_contents"][fp] = content[:_PREFETCH_FILE_BUDGET - chars_used]
                chars_used += len(result["file_contents"][fp])

            # Also fetch diff if SHA available
            sha = hpf.get("sha", "")
            if sha and use_github:
                try:
                    diff_json = await self._github_get_diff({"commit_sha": sha})
                    result["diff_results"][sha[:8]] = json.loads(diff_json)
                except Exception:
                    pass

        # 3. Stack trace file paths — parse and read
        stack_files = self._extract_files_from_stack_traces()
        for sf in stack_files[:5]:
            if sf in result["file_contents"] or chars_used >= _PREFETCH_FILE_BUDGET:
                continue
            content = await self._read_file_safe(sf, use_github)
            if content:
                result["file_contents"][sf] = content[:_PREFETCH_FILE_BUDGET - chars_used]
                chars_used += len(result["file_contents"][sf])

        # 4. Search for exception type / error message
        exception_type = context.get("exception_type", "")
        error_message = context.get("error_message", "")

        search_queries = []
        if exception_type:
            search_queries.append(exception_type)
        if error_message and len(error_message) < 100:
            search_queries.append(error_message)

        for query in search_queries[:2]:
            try:
                if use_github:
                    search_json = await self._github_search_code({"query": query})
                    result["search_results"][query] = json.loads(search_json)
                else:
                    search_json = self._search_code({"pattern": re.escape(query)})
                    result["search_results"][query] = json.loads(search_json)
            except Exception:
                pass

        return result

    def _extract_files_from_stack_traces(self) -> list[str]:
        """Parse file paths from stack traces."""
        files = []
        # Python: File "path/to/file.py", line N
        py_pattern = re.compile(r'File "([^"]+\.py)"')
        # Java: at com.example.Class(File.java:N)
        java_pattern = re.compile(r'\((\w+\.java):\d+\)')
        # Go: path/to/file.go:N
        go_pattern = re.compile(r'([\w/]+\.go):\d+')
        # Generic: path/file.ext:line
        generic_pattern = re.compile(r'([\w./\\-]+\.\w{1,4}):\d+')

        for st in self._stack_traces:
            for m in py_pattern.findall(st):
                # Strip container prefixes
                clean = re.sub(r'^/(?:app|usr/src/app|opt/app)/', '', m)
                if clean not in files:
                    files.append(clean)
            for m in java_pattern.findall(st):
                if m not in files:
                    files.append(m)
            for m in go_pattern.findall(st):
                if m not in files:
                    files.append(m)
            # Fallback generic
            if not files:
                for m in generic_pattern.findall(st):
                    if m not in files and not m.startswith(("http", "/usr/lib", "/lib")):
                        files.append(m)

        return files[:10]

    async def _read_file_safe(self, file_path: str, use_github: bool) -> str | None:
        """Read a file, return content or None on failure."""
        try:
            if use_github:
                resp_json = await self._github_read_file({"path": file_path})
                data = json.loads(resp_json)
                if "error" in data:
                    return None
                return "\n".join(data.get("lines", []))
            else:
                resp_json = self._read_file({"path": file_path})
                data = json.loads(resp_json)
                if "error" in data:
                    return None
                return "\n".join(data.get("lines", []))
        except Exception:
            return None

    async def _batch_fetch(self, plan: dict) -> dict:
        """Execute additional file reads and searches from Call 1's plan."""
        result: dict[str, Any] = {"file_contents": {}, "search_results": {}}
        use_github = bool(self._owner_repo)
        chars_used = 0

        # Read additional files (parallel)
        additional_files = plan.get("additional_files_needed", [])[:_BATCH_FETCH_MAX_FILES]
        if additional_files:
            tasks = [self._read_file_safe(fp, use_github) for fp in additional_files]
            contents = await asyncio.gather(*tasks, return_exceptions=True)
            for fp, content in zip(additional_files, contents):
                if isinstance(content, str) and content:
                    budget_remaining = _PREFETCH_FILE_BUDGET - chars_used
                    if budget_remaining <= 0:
                        break
                    result["file_contents"][fp] = content[:budget_remaining]
                    chars_used += len(result["file_contents"][fp])

        # Run additional searches (parallel)
        additional_searches = plan.get("additional_searches", [])[:_BATCH_FETCH_MAX_SEARCHES]
        if additional_searches:
            async def _do_search(query: str) -> tuple[str, dict | None]:
                try:
                    if use_github:
                        resp = await self._github_search_code({"query": query})
                    else:
                        resp = self._search_code({"pattern": re.escape(query)})
                    return query, json.loads(resp)
                except Exception:
                    return query, None

            search_tasks = [_do_search(s["query"] if isinstance(s, dict) else s) for s in additional_searches]
            search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
            for item in search_results:
                if isinstance(item, tuple):
                    q, data = item
                    if data:
                        result["search_results"][q] = data

        return result

    # ── Prompt builders ──────────────────────────────────────────────────

    def _build_investigation_context(self, context: dict) -> str:
        """Build the diagnostic context section (same data as ReAct initial prompt)."""
        parts = [f"Service under investigation: {context.get('service_name', 'unknown')}"]

        if self._owner_repo:
            parts.append(f"Repository: {self._owner_repo}")
        if context.get("error_location"):
            parts.append(f"Error location: {context['error_location']}")
        if context.get("stack_trace"):
            parts.append(f"Stack trace:\n{context['stack_trace'][:2000]}")
        if self._stack_traces:
            for i, st in enumerate(self._stack_traces[:2], 1):
                parts.append(f"Additional stack trace #{i}:\n{st[:1000]}")
        if context.get("exception_type"):
            parts.append(f"Exception: {context['exception_type']}")
        if context.get("error_message"):
            parts.append(f"Error message: {context['error_message']}")
        if context.get("service_flow"):
            flow_str = " → ".join(
                f"{s.get('service', '?')}({s.get('operation', '?')}, {s.get('status', '?')})"
                for s in context["service_flow"]
            )
            parts.append(f"\n## Service Flow\n{flow_str}")
        if context.get("patient_zero"):
            pz = context["patient_zero"]
            parts.append(f"\n## Patient Zero\nService: {pz.get('service', '?')}, Evidence: {pz.get('evidence', '?')}")
        if context.get("trace_failure_point"):
            fp = context["trace_failure_point"]
            parts.append(f"\n## Trace Failure Point\nService: {fp['service']}, Operation: {fp['operation']}, Error: {fp.get('error_message', '')}")
        if context.get("trace_call_chain"):
            parts.append("\n## Trace Call Chain")
            for span in context["trace_call_chain"]:
                status_mark = "OK" if span["status"] == "ok" else f"ERROR: {span['error']}"
                parts.append(f"  {span['service']} → {span['operation']} [{status_mark}]")
        if context.get("metrics_anomalies"):
            parts.append("\n## Metrics Anomalies")
            for a in context["metrics_anomalies"]:
                parts.append(f"  - [{a['severity']}] {a['metric']}: {a['correlation']}")
        if context.get("k8s_warnings"):
            parts.append("\n## K8s Warnings")
            for w in context["k8s_warnings"]:
                parts.append(f"  - {w}")
        if context.get("inferred_dependencies"):
            parts.append("\n## Service Dependencies")
            for dep in context["inferred_dependencies"]:
                parts.append(f"  {dep.get('source', '?')} → {dep.get('target', '?')}")

        return "\n".join(parts)

    def _build_plan_prompt(self, investigation_context: str, prefetched: dict) -> str:
        """Build the Call 1 (Plan) user prompt."""
        parts = [
            "# Code Impact Analysis — Phase 1: Planning\n",
            "## Diagnostic Context\n",
            investigation_context,
            "\n## Repository File Tree\n",
        ]

        tree = prefetched.get("file_tree", [])
        if tree:
            parts.append("\n".join(f"  {f}" for f in tree[:200]))
        else:
            parts.append("  (file tree unavailable)")

        # Pre-fetched file contents
        file_contents = prefetched.get("file_contents", {})
        if file_contents:
            parts.append("\n## Pre-Fetched File Contents\n")
            for fp, content in file_contents.items():
                parts.append(f"### {fp}\n```\n{content}\n```\n")

        # Pre-fetched search results
        search_results = prefetched.get("search_results", {})
        if search_results:
            parts.append("\n## Pre-Fetched Search Results\n")
            for query, data in search_results.items():
                matches = data.get("matches", [])
                parts.append(f"### Search: `{query}` ({len(matches)} matches)")
                for m in matches[:10]:
                    parts.append(f"  - {m.get('file', m.get('path', '?'))}:{m.get('line_number', '?')}")

        # Pre-fetched diffs
        diff_results = prefetched.get("diff_results", {})
        if diff_results:
            parts.append("\n## Pre-Fetched Commit Diffs\n")
            for sha, data in diff_results.items():
                parts.append(f"### Commit {sha}: {data.get('message', '')[:80]}")
                for f in data.get("files", [])[:5]:
                    parts.append(f"  {f.get('filename', '?')} (+{f.get('additions', 0)}/-{f.get('deletions', 0)})")
                    patch = f.get("patch", "")
                    if patch:
                        parts.append(f"  ```\n  {patch[:500]}\n  ```")

        parts.append("\n## Your Task\n")
        parts.append(
            "Analyze the pre-fetched data above. Respond with JSON:\n"
            "```json\n"
            "{\n"
            '  "additional_files_needed": ["path/to/file.py", ...],  // files you need to see (max 10)\n'
            '  "additional_searches": [{"query": "search term", "reason": "why"}],  // max 5\n'
            '  "preliminary_analysis": "Your initial assessment of the root cause...",\n'
            '  "can_produce_final_answer": false,  // true ONLY if you have enough data\n'
            '  "final_answer": null  // if can_produce_final_answer=true, put full analysis JSON here\n'
            "}\n"
            "```\n\n"
            "If you already have enough evidence to identify root cause, set can_produce_final_answer=true "
            "and include the full analysis as final_answer (same JSON schema as the final output).\n"
            "The final_answer schema:\n"
            '{\n'
            '  "root_cause_location": {"file_path": "...", "impact_type": "direct_error", "relevant_lines": [{"start": 45, "end": 60}], "code_snippet": "...", "relationship": "error origin", "fix_relevance": "must_fix"},\n'
            '  "impacted_files": [...],\n'
            '  "call_chain": ["caller.py:handler()", "service.py:process()"],\n'
            '  "dependency_graph": {"service.py": ["db.py"]},\n'
            '  "shared_resource_conflicts": [],\n'
            '  "suggested_fix_areas": [{"file_path": "...", "description": "...", "suggested_change": "..."}],\n'
            '  "diff_analysis": [],\n'
            '  "mermaid_diagram": "<Debug Duck Mermaid dialect — see rules below>",\n'
            '  "overall_confidence": 85\n'
            "}\n\n"
            "### Mermaid Diagram Rules (Debug Duck dialect)\n"
            "Generate a `graph TD` flowchart showing the request/error flow between services.\n"
            "STRICT SYNTAX RULES — violating these causes parse failures:\n"
            "- Use `graph TD` (top-down) with `-->` arrows\n"
            "- Node IDs: short alphanumeric (e.g. `CS`, `IS`, `DB`)\n"
            '- Node labels: use `["label text"]` for rectangles, `[("label")]` for cylinders\n'
            "- NEVER use `<br/>` or `<br>` — use `\\n` for line breaks inside labels\n"
            "- NEVER use parentheses `()` inside label text or edge labels — write `fn_name` not `fn_name()`\n"
            "- Edge labels: `-->|label text|` — no parentheses, no HTML tags inside\n"
            "- Use `style` lines to color root-cause nodes red, impacted amber, healthy green\n"
            "- Keep to 4-10 nodes maximum"
        )

        return "\n".join(parts)

    def _build_analyze_prompt(
        self, investigation_context: str, prefetched: dict, additional: dict, plan: dict
    ) -> str:
        """Build the Call 2 (Analyze) user prompt with all gathered data."""
        parts = [
            "# Code Impact Analysis — Phase 2: Final Analysis\n",
            "## Diagnostic Context\n",
            investigation_context,
        ]

        # All file contents (pre-fetched + additional)
        all_files = {**prefetched.get("file_contents", {}), **additional.get("file_contents", {})}
        if all_files:
            parts.append("\n## Source Files\n")
            for fp, content in all_files.items():
                parts.append(f"### {fp}\n```\n{content}\n```\n")

        # All search results
        all_searches = {**prefetched.get("search_results", {}), **additional.get("search_results", {})}
        if all_searches:
            parts.append("\n## Code Search Results\n")
            for query, data in all_searches.items():
                matches = data.get("matches", [])
                parts.append(f"### Search: `{query}` ({len(matches)} matches)")
                for m in matches[:10]:
                    parts.append(f"  - {m.get('file', m.get('path', '?'))}:{m.get('line_number', '?')} — {m.get('line', '')[:100]}")

        # Diffs
        diff_results = prefetched.get("diff_results", {})
        if diff_results:
            parts.append("\n## Commit Diffs\n")
            for sha, data in diff_results.items():
                parts.append(f"### Commit {sha}: {data.get('message', '')[:80]}")
                for f in data.get("files", [])[:5]:
                    patch = f.get("patch", "")
                    parts.append(f"  {f.get('filename', '?')} (+{f.get('additions', 0)}/-{f.get('deletions', 0)})")
                    if patch:
                        parts.append(f"  ```\n  {patch[:800]}\n  ```")

        # Repo tree for reference
        tree = prefetched.get("file_tree", [])
        if tree:
            parts.append("\n## Repository File Tree\n")
            parts.append("\n".join(f"  {f}" for f in tree[:150]))

        # Preliminary analysis from Call 1
        if plan.get("preliminary_analysis"):
            parts.append(f"\n## Preliminary Analysis (from Phase 1)\n{plan['preliminary_analysis']}")

        parts.append(
            "\n## Your Task\n"
            "Using ALL the evidence above, produce your final analysis as JSON:\n"
            "```json\n"
            "{\n"
            '  "root_cause_location": {"file_path": "...", "impact_type": "direct_error", "relevant_lines": [{"start": 45, "end": 60}], "code_snippet": "...", "relationship": "error origin", "fix_relevance": "must_fix"},\n'
            '  "impacted_files": [{"file_path": "...", "impact_type": "caller|callee|config", "relationship": "..."}],\n'
            '  "call_chain": ["caller.py:handler()", "service.py:process()", "db.py:query()"],\n'
            '  "dependency_graph": {"service.py": ["db.py", "cache.py"]},\n'
            '  "shared_resource_conflicts": ["description of any shared resource issues"],\n'
            '  "suggested_fix_areas": [{"file_path": "...", "description": "...", "suggested_change": "..."}],\n'
            '  "diff_analysis": [{"file": "...", "commit_sha": "...", "verdict": "likely_cause|unrelated|contributing", "reasoning": "..."}],\n'
            '  "mermaid_diagram": "<Debug Duck Mermaid dialect — see rules below>",\n'
            '  "overall_confidence": 85\n'
            "}\n"
            "```\n\n"
            "### Mermaid Diagram Rules (Debug Duck dialect)\n"
            "Generate a `graph TD` flowchart showing the request/error flow between services.\n"
            "STRICT SYNTAX RULES — violating these causes parse failures:\n"
            "- Use `graph TD` (top-down) with `-->` arrows\n"
            "- Node IDs: short alphanumeric (e.g. `CS`, `IS`, `DB`)\n"
            '- Node labels: use `["label text"]` for rectangles, `[("label")]` for cylinders\n'
            "- NEVER use `<br/>` or `<br>` — use `\\n` for line breaks inside labels\n"
            "- NEVER use parentheses `()` inside label text or edge labels — write `fn_name` not `fn_name()`\n"
            "- Edge labels: `-->|label text|` — no parentheses, no HTML tags inside\n"
            "- Use `style` lines to color root-cause nodes red, impacted amber, healthy green\n"
            "- Keep to 4-10 nodes maximum\n\n"
            "GOOD example:\n"
            "```\n"
            'graph TD\n'
            '    User["Client"] -->|POST /checkout| CS["checkout-service\\nsrc/main.py"]\n'
            '    CS -->|POST /reserve\\ncall_inventory| IS["inventory-service:8002"]\n'
            '    IS -->|stock check| Redis[("Redis")]\n'
            '    IS -->|503 health fail| K8s["Kubernetes"]\n'
            '    style Redis fill:#ff4444,stroke:#cc0000,color:#fff\n'
            '    style IS fill:#ff8800,stroke:#cc6600,color:#fff\n'
            "```"
        )

        return "\n".join(parts)

    def _two_pass_system_prompt(self) -> str:
        """System prompt for Call 1 (Plan)."""
        return (
            "You are a Code Navigator Agent for SRE troubleshooting.\n\n"
            "You are given pre-fetched repository data (file tree, file contents, search results, diffs) "
            "along with diagnostic context from other agents (logs, metrics, traces, k8s).\n\n"
            "Your job in this phase is to:\n"
            "1. Review what data you already have\n"
            "2. Determine if you need any additional files or searches to complete your analysis\n"
            "3. If you already have enough data, produce your final analysis directly\n\n"
            "Be efficient — request only files that are directly relevant to the root cause. "
            "You have a budget of 10 additional files and 5 additional searches."
        )

    def _two_pass_analysis_system_prompt(self) -> str:
        """System prompt for Call 2 (Analyze)."""
        return (
            "You are a Code Navigator Agent for SRE troubleshooting.\n\n"
            "You have been given all relevant source files, search results, commit diffs, "
            "and diagnostic context from 5 other agents (log, metrics, trace, k8s, change).\n\n"
            "Produce a comprehensive root cause analysis as JSON. Include:\n"
            "- root_cause_location: the exact file and lines causing the issue\n"
            "- impacted_files: other files affected by the bug or fix\n"
            "- call_chain: the execution path leading to the error\n"
            "- suggested_fix_areas: specific code changes to fix the issue\n"
            "- diff_analysis: whether recent changes contributed to the incident\n"
            "- overall_confidence: 0-100 based on evidence strength\n\n"
            "Be precise. Cite specific files and line numbers from the data provided."
        )

    def _parse_plan_response(self, text: str) -> dict:
        """Parse Call 1's JSON response."""
        try:
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = json.loads(text)
            # Ensure required keys exist
            data.setdefault("additional_files_needed", [])
            data.setdefault("additional_searches", [])
            data.setdefault("preliminary_analysis", "")
            data.setdefault("can_produce_final_answer", False)
            data.setdefault("final_answer", None)
            return data
        except (json.JSONDecodeError, AttributeError):
            logger.warning("Failed to parse plan response, treating as no additional data needed")
            return {
                "additional_files_needed": [],
                "additional_searches": [],
                "preliminary_analysis": text[:500],
                "can_produce_final_answer": False,
                "final_answer": None,
            }

    async def _define_tools(self) -> list[dict]:
        if self.repo_path and not self.repo_path.startswith(("http://", "https://", "git@")):
            return self._local_tools()
        return [
            {
                "name": "github_read_file",
                "description": "Read a file from a GitHub repository.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "owner_repo": {"type": "string", "description": "GitHub owner/repo (defaults to primary repo)"},
                        "path": {"type": "string", "description": "File path relative to repo root"},
                        "ref": {"type": "string", "description": "Branch, tag, or commit SHA", "default": ""},
                        "start_line": {"type": "integer", "description": "Start line (1-indexed), 0=from start", "default": 0},
                        "end_line": {"type": "integer", "description": "End line, 0=to end", "default": 0},
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "github_search_code",
                "description": "Search for code across a GitHub repository.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Code search query"},
                        "owner_repo": {"type": "string", "description": "GitHub owner/repo (defaults to primary repo)"},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "github_get_diff",
                "description": "Get the diff/patch for a commit or compare two refs. Shows exact line changes.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "owner_repo": {"type": "string", "description": "GitHub owner/repo (defaults to primary repo)"},
                        "commit_sha": {"type": "string", "description": "Commit SHA to get diff for (use this OR base/head)"},
                        "base": {"type": "string", "description": "Base ref for comparison"},
                        "head": {"type": "string", "description": "Head ref for comparison"},
                    },
                    "required": [],
                },
            },
            {
                "name": "github_list_files",
                "description": "List all files in the repository tree. Use this FIRST to discover the repo structure before reading files.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "owner_repo": {"type": "string", "description": "GitHub owner/repo (defaults to primary repo)"},
                        "path": {"type": "string", "description": "Subdirectory path to list (empty = root)", "default": ""},
                    },
                    "required": [],
                },
            },
            {
                "name": "ask_human",
                "description": (
                    "Ask the human SRE a question when you need confirmation or clarification. "
                    "Use this when: (1) you inferred which downstream call caused the error and want to confirm, "
                    "(2) you found multiple matching handlers and need the human to pick one, "
                    "(3) you need to confirm a repo URL guess, "
                    "(4) you hit a fork in the call chain and want guidance on which path to follow. "
                    "The human sees your question in the chat and types a reply."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": "Clear, specific question for the human. Include what you found and what you need confirmed.",
                        },
                    },
                    "required": ["question"],
                },
            },
        ]

    def _local_tools(self) -> list[dict]:
        """Original local filesystem tools for backward compat."""
        return [
            {
                "name": "search_file",
                "description": "Search for files in the repository matching a filename pattern.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "Filename or glob pattern to search for"},
                    },
                    "required": ["pattern"],
                },
            },
            {
                "name": "read_file",
                "description": "Read the contents of a file (or a range of lines).",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path relative to repo root"},
                        "start_line": {"type": "integer", "description": "Start line (1-indexed)", "default": 1},
                        "end_line": {"type": "integer", "description": "End line (0 = entire file)", "default": 0},
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "search_code",
                "description": "Search for a pattern (regex) across all files in the repository.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "Regex pattern to search for in code"},
                        "file_glob": {"type": "string", "description": "Limit search to files matching this glob", "default": "*"},
                    },
                    "required": ["pattern"],
                },
            },
            {
                "name": "find_callers",
                "description": "Find all files/locations that call a specific function or method.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "function_name": {"type": "string"},
                    },
                    "required": ["function_name"],
                },
            },
            {
                "name": "find_callees",
                "description": "Find all functions/methods called within a specific file and function.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "function_name": {"type": "string"},
                    },
                    "required": ["path", "function_name"],
                },
            },
            {
                "name": "ask_human",
                "description": (
                    "Ask the human SRE a question when you need confirmation or clarification. "
                    "Use this when: (1) you inferred which downstream call caused the error and want to confirm, "
                    "(2) you found multiple matching handlers and need the human to pick one, "
                    "(3) you need to confirm a repo URL guess, "
                    "(4) you hit a fork in the call chain and want guidance on which path to follow. "
                    "The human sees your question in the chat and types a reply."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": "Clear, specific question for the human. Include what you found and what you need confirmed.",
                        },
                    },
                    "required": ["question"],
                },
            },
        ]

    async def _build_system_prompt(self) -> str:
        if self._verification_mode:
            return """You are a Code Verification Agent reviewing a proposed fix.
Goals:
1. Read the target file to understand context
2. Analyze the diff for correctness
3. Check callers for breakage (use github_search_code to find callers)
4. Assess regression risk

After analysis, provide your final answer as JSON:
{
    "verdict": "approve" | "reject" | "needs_changes",
    "confidence": 85,
    "issues_found": ["list of issues"],
    "regression_risks": ["list of regression risks"],
    "suggestions": ["list of improvement suggestions"],
    "reasoning": "detailed reasoning for your verdict"
}"""
        return """You are a Code Navigator Agent for SRE troubleshooting. You use the ReAct pattern.

## CROSS-SERVICE DEBUGGING STRATEGY

You are investigating a production incident. The stack trace may come from a CALLER service,
but the repo you're scanning is the TARGET service being called. Follow this strategy:

### Step 1: UNDERSTAND THE LANDSCAPE
- Read the service_flow and trace_call_chain in your context to understand which services are involved
- Identify: which service has the stack trace (caller) vs which repo you're scanning (target)
- If they're the SAME service, skip to Step 3 directly
- If they're DIFFERENT services, proceed to Step 2

### Step 2: CALL SITE EXTRACTION (only if caller repo is in repo_map)
- Read the caller's stack trace file using github_read_file with the caller's owner_repo
- Find the outgoing HTTP/gRPC/message call to the target service
- Extract: target URL/endpoint, HTTP method, request payload shape
- **ask_human** to confirm: "I found [caller] calls [method] [endpoint] on [target]. Should I investigate this endpoint?"

### Step 3: ENTRY POINT DISCOVERY
- Use github_search_code to search the TARGET repo for the endpoint string (e.g., "/reserve", "/v1/process")
- If no endpoint known, search for the error message or exception type
- If you get the repo file tree with github_list_files, scan for controller/handler/route files
- If multiple handlers match, **ask_human** which one to investigate
- You should now have a specific file + function as the entry point

### Step 4: LOGIC DRILL-DOWN
- Read the entry point handler file
- Follow the internal call chain: controller → service → repository/client
- At each level, look for:
  * Missing error handling, unchecked nulls, timeout issues
  * Resource contention (DB locks, connection pools, thread exhaustion)
  * Recent changes (use github_get_diff on high_priority_files)
- Cross-reference with metrics_anomalies and k8s_warnings in your context
- If you hit a fork with multiple code paths, **ask_human** which to follow first

### WHEN TO USE ask_human
- You inferred which downstream call caused the error → confirm before pivoting
- Found multiple matching endpoint handlers → ask which one
- Auto-derived a repo URL and want to verify → ask before reading from it
- Hit a fork in the call chain → ask which path to prioritize
- NOT for trivial decisions — use your judgment for obvious next steps

### EFFICIENCY RULES
- You have 15 iterations — use them wisely
- Asking human costs 1 iteration but saves wasted iterations on wrong paths
- If high_priority_files are provided AND match the target repo, read those first
- **CRITICAL: Do NOT speculate with github_search_code.** If a search returns 0 results, do NOT
  try variations of the same search. Instead, go back to reading files you already know about.
  Reading the next section of a file you already opened is ALWAYS more productive than guessing
  search terms that may not exist in the codebase.
- When you have a file open (e.g., read lines 1-180), continue reading the next section
  (lines 180-350, etc.) to build a complete picture BEFORE searching for other files.
- Use github_search_code ONLY when you have a specific, concrete string to search for
  (e.g., an endpoint path "/v1/reserve", an exception class name "PoolExhaustedError",
  or a function name you saw imported). Never search for generic terms like "background thread"
  or "stock" — these waste iterations.
- **Budget your iterations:** Use iterations 1-10 for reading and investigation, and ALWAYS
  reserve at least 2 iterations for producing your final JSON answer. If you are on iteration 12+,
  stop investigating and produce your answer with what you have.

After analysis, provide your final answer as JSON:
{
    "root_cause_location": {"file_path": "...", "impact_type": "direct_error", "relevant_lines": [{"start": 45, "end": 60}], "code_snippet": "...", "relationship": "error origin", "fix_relevance": "must_fix"},
    "impacted_files": [...],
    "call_chain": ["caller.py:handler()", "service.py:process()", "db.py:query()"],
    "dependency_graph": {"service.py": ["db.py", "cache.py"]},
    "shared_resource_conflicts": ["Redis connection pool exhaustion", "DB lock contention"],
    "suggested_fix_areas": [{"file_path": "...", "description": "...", "suggested_change": "..."}],
    "diff_analysis": [{"file": "...", "commit_sha": "...", "verdict": "likely_cause|unrelated|contributing", "reasoning": "..."}],
    "cross_repo_findings": [{"repo": "org/service", "role": "upstream_trigger|downstream_failure", "evidence": "..."}],
    "cross_service_trace": {"caller_service": "...", "target_endpoint": "...", "entry_point_file": "...", "entry_point_function": "..."},
    "mermaid_diagram": "<Debug Duck Mermaid — see rules below>",
    "overall_confidence": 85
}

### Mermaid Diagram Rules (Debug Duck dialect)
Generate a `graph TD` flowchart showing request/error flow between services.
STRICT SYNTAX — violating these causes frontend parse failures:
- Node IDs: short alphanumeric (CS, IS, DB). Labels: ["text"] for rectangles, [("text")] for cylinders.
- NEVER use <br/> or <br> in labels — use \\n for line breaks.
- NEVER use parentheses () inside label text or edge labels — write fn_name not fn_name().
- Edge labels: -->|label text| — no parens, no HTML inside.
- Style root-cause nodes red, impacted amber: style NodeId fill:#ff4444,stroke:#cc0000,color:#fff
- 4-10 nodes max.

GOOD:
graph TD
    User["Client"] -->|POST /checkout| CS["checkout-svc\\nsrc/main.py"]
    CS -->|call_inventory| IS["inventory-svc:8002"]
    IS -->|stock check| Redis[("Redis")]
    style Redis fill:#ff4444,stroke:#cc0000,color:#fff"""

    async def _build_initial_prompt(self, context: dict) -> str:
        self._repo_url = context.get("repo_url", "")
        self.repo_path = context.get("repo_path", "")
        self._owner_repo = self._parse_repo_url(self._repo_url) or ""
        self._github_token = context.get("github_token") or os.getenv("GITHUB_TOKEN", "")
        self._high_priority_files = context.get("high_priority_files", [])
        self._stack_traces = context.get("stack_traces", [])
        self._ask_human_callback = context.get("_ask_human_callback")
        self._event_emitter = context.get("_event_emitter")
        self._state = context.get("_state")

        self._verification_mode = context.get("verification_mode", False)
        if self._verification_mode:
            parts = ["Verify the following proposed fix for correctness and regression risk."]
            if self._owner_repo:
                parts.append(f"Repository: {self._owner_repo}")
            parts.append(f"\n## Target File\n`{context.get('fix_file', 'unknown')}`")
            parts.append(f"\n## Diff\n```\n{context.get('fix_diff', '')}\n```")
            if context.get("call_chain"):
                parts.append(f"\n## Call Chain\n{context['call_chain']}")
            if context.get("original_findings"):
                parts.append("\n## Original Findings")
                for f in context["original_findings"]:
                    parts.append(f"- {f}")
            parts.append("\nRead the target file, search for callers, and provide your verification verdict as JSON.")
            return "\n".join(parts)

        # Multi-repo map
        raw_map = context.get("repo_map", {})
        for svc, url in raw_map.items():
            parsed = self._parse_repo_url(url)
            if parsed:
                self._repo_map[svc] = parsed

        parts = [f"Analyze code impact for error in: {context.get('service_name', 'unknown')}"]
        if self._owner_repo:
            parts.append(f"Primary repository: {self._owner_repo}")
        elif self.repo_path:
            parts.append(f"Repository path: {self.repo_path}")
        if context.get("error_location"):
            parts.append(f"Error location from logs: {context['error_location']}")
        if context.get("stack_trace"):
            parts.append(f"Stack trace:\n{context['stack_trace']}")
        if self._stack_traces:
            parts.append(f"\nAdditional stack traces ({len(self._stack_traces)}):")
            for i, st in enumerate(self._stack_traces[:3], 1):
                parts.append(f"  Stack trace #{i}:\n{st[:500]}")
        if context.get("exception_type"):
            parts.append(f"Exception type: {context['exception_type']}")

        # Cross-service context
        if context.get("error_message"):
            parts.append(f"Error message: {context['error_message']}")

        if context.get("service_flow"):
            flow = context["service_flow"]
            flow_str = " → ".join(
                f"{s.get('service', '?')}({s.get('operation', '?')}, {s.get('status', '?')})"
                for s in flow
            )
            parts.append(f"\n## SERVICE FLOW (request path)\n{flow_str}")

        if context.get("patient_zero"):
            pz = context["patient_zero"]
            parts.append(f"\n## PATIENT ZERO\nService: {pz.get('service', '?')}, Evidence: {pz.get('evidence', '?')}")

        if context.get("trace_failure_point"):
            fp = context["trace_failure_point"]
            parts.append("\n## TRACE FAILURE POINT")
            parts.append(f"Service: {fp['service']}, Operation: {fp['operation']}")
            if fp.get("error_message"):
                parts.append(f"Error: {fp['error_message']}")
            http_tags = {k: v for k, v in fp.get("tags", {}).items() if k.startswith("http.")}
            if http_tags:
                parts.append(f"HTTP context: {http_tags}")

        if context.get("trace_call_chain"):
            chain = context["trace_call_chain"]
            parts.append("\n## TRACE CALL CHAIN")
            for span in chain:
                status_mark = "OK" if span["status"] == "ok" else f"ERROR: {span['error']}"
                parts.append(f"  {span['service']} → {span['operation']} [{status_mark}]")

        if context.get("metrics_anomalies"):
            parts.append("\n## METRICS ANOMALIES (cross-reference during drill-down)")
            for a in context["metrics_anomalies"]:
                parts.append(f"  - [{a['severity']}] {a['metric']}: {a['correlation']}")

        if context.get("k8s_warnings"):
            parts.append("\n## K8S WARNINGS")
            for w in context["k8s_warnings"]:
                parts.append(f"  - {w}")

        if context.get("inferred_dependencies"):
            parts.append("\n## SERVICE DEPENDENCIES")
            for dep in context["inferred_dependencies"]:
                parts.append(f"  {dep.get('source', '?')} → {dep.get('target', '?')}")

        if self._high_priority_files:
            parts.append("\n## HIGH PRIORITY FILES (from change analysis)")
            parts.append("Read these FIRST and get their diffs. Compare against the stack trace:")
            for hpf in self._high_priority_files:
                parts.append(f"  - {hpf['file_path']} (risk: {hpf.get('risk_score', 'N/A')}, commit: {hpf.get('sha', 'N/A')[:8]})")
        if context.get("files_changed"):
            parts.append(f"\nAll recently changed files: {', '.join(context['files_changed'][:20])}")
        if self._repo_map:
            parts.append("\n## MULTI-REPO CONTEXT")
            parts.append("Specify owner_repo on each tool call to read across repos:")
            for svc, repo in self._repo_map.items():
                parts.append(f"  - {svc}: {repo}")
            parts.append("Label findings as 'upstream_trigger' or 'downstream_failure'.")
        return "\n".join(parts)

    async def _handle_tool_call(self, tool_name: str, tool_input: dict) -> str:
        if tool_name == "github_list_files":
            return await self._github_list_files(tool_input)
        elif tool_name == "github_read_file":
            return await self._github_read_file(tool_input)
        elif tool_name == "github_search_code":
            return await self._github_search_code(tool_input)
        elif tool_name == "github_get_diff":
            return await self._github_get_diff(tool_input)
        elif tool_name == "ask_human":
            return await self._ask_human(tool_input)
        elif tool_name == "search_file":
            return self._search_file(tool_input)
        elif tool_name == "read_file":
            return self._read_file(tool_input)
        elif tool_name == "search_code":
            return self._search_code(tool_input)
        elif tool_name == "find_callers":
            return self._find_callers_tool(tool_input)
        elif tool_name == "find_callees":
            return self._find_callees_tool(tool_input)
        return f"Unknown tool: {tool_name}"

    async def _ask_human(self, params: dict) -> str:
        question = params.get("question", "")
        if not question:
            return "Error: question is required"
        if not self._ask_human_callback:
            return "Human-in-the-loop not available. Proceed with your best judgment."
        answer = await self._ask_human_callback(question, self._state, self._event_emitter)
        self.add_breadcrumb(
            action="ask_human",
            source_type="code",
            source_reference="code_agent_question",
            raw_evidence=f"Q: {question[:100]} | A: {answer[:100]}",
        )
        return f"Human response: {answer}"

    def _parse_final_response(self, text: str) -> dict:
        try:
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = json.loads(text)
        except (json.JSONDecodeError, AttributeError):
            return {"error": "Failed to parse response", "raw_response": text}

        result = {
            **data,
            "breadcrumbs": [b.model_dump(mode="json") for b in self.breadcrumbs],
            "negative_findings": [n.model_dump(mode="json") for n in self.negative_findings],
            "tokens_used": self.get_token_usage().model_dump(),
        }
        logger.info("Code agent complete", extra={"agent_name": self.agent_name, "action": "complete", "extra": {"impacted_files": len(data.get("impacted_files", [])), "confidence": data.get("overall_confidence", 0)}})
        return result

    # --- Helpers ---

    @staticmethod
    def _parse_repo_url(url: str) -> str | None:
        """Extract 'owner/repo' from GitHub URL."""
        if not url:
            return None
        for pattern in [r'github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$', r'^([^/]+/[^/]+)$']:
            m = re.search(pattern, url)
            if m:
                return m.group(1)
        return None

    def _github_headers(self) -> dict:
        headers = {"Accept": "application/vnd.github+json"}
        if self._github_token:
            headers["Authorization"] = f"Bearer {self._github_token}"
        return headers

    def _resolve_owner_repo(self, params: dict) -> str:
        """Resolve owner/repo from params or default."""
        explicit = params.get("owner_repo", "")
        if explicit:
            return explicit
        return self._owner_repo

    # --- GitHub API tool implementations ---

    async def _github_read_file(self, params: dict) -> str:
        owner_repo = self._resolve_owner_repo(params)
        if not owner_repo:
            return json.dumps({"error": "No owner_repo specified and no primary repo set"})

        file_path = params.get("path", "")
        ref = params.get("ref", "")
        start_line = params.get("start_line", 0)
        end_line = params.get("end_line", 0)

        url = f"https://api.github.com/repos/{owner_repo}/contents/{file_path}"
        query_params = {}
        if ref:
            query_params["ref"] = ref

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, headers=self._github_headers(), params=query_params)
                if resp.status_code == 404:
                    self.add_negative_finding(
                        what_was_checked=f"File {file_path} in {owner_repo}",
                        result="File not found (404)",
                        implication=f"File does not exist at path: {file_path}",
                        source_reference=f"github:{owner_repo}/{file_path}",
                    )
                    return json.dumps({"error": f"File not found: {file_path} in {owner_repo}"})
                resp.raise_for_status()
                data = resp.json()

            content_b64 = data.get("content", "")
            raw_content = base64.b64decode(content_b64).decode("utf-8", errors="replace")
            lines = raw_content.splitlines()

            # Slice if requested
            if start_line > 0 or end_line > 0:
                s = max(0, start_line - 1)
                e = end_line if end_line > 0 else len(lines)
                selected = lines[s:e]
            else:
                selected = lines

            # Cap at 200 lines
            truncated = False
            if len(selected) > 200:
                selected = selected[:200]
                truncated = True

            self.add_breadcrumb(
                action="github_read_file",
                source_type="code",
                source_reference=f"{owner_repo}:{file_path}",
                raw_evidence=f"Read {len(selected)} lines (total: {len(lines)})",
            )

            return json.dumps({
                "path": file_path,
                "repo": owner_repo,
                "lines": selected,
                "start_line": start_line or 1,
                "total_lines": len(lines),
                "truncated": truncated,
            })
        except httpx.HTTPStatusError as e:
            return json.dumps({"error": f"GitHub API error {e.response.status_code}: {e.response.text[:200]}"})
        except Exception as e:
            return json.dumps({"error": f"Failed to read file: {str(e)}"})

    async def _github_search_code(self, params: dict) -> str:
        owner_repo = self._resolve_owner_repo(params)
        query = params.get("query", "")
        if not query:
            return json.dumps({"error": "No query provided"})

        search_query = f"{query} repo:{owner_repo}" if owner_repo else query

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://api.github.com/search/code",
                    headers=self._github_headers(),
                    params={"q": search_query, "per_page": 20},
                )
                resp.raise_for_status()
                data = resp.json()

            items = data.get("items", [])
            matches = []
            for item in items[:20]:
                matches.append({
                    "file": item.get("path", ""),
                    "repo": item.get("repository", {}).get("full_name", owner_repo),
                    "url": item.get("html_url", ""),
                })

            self.add_breadcrumb(
                action="github_search_code",
                source_type="code",
                source_reference=f"query: {query} in {owner_repo}",
                raw_evidence=f"Found {len(matches)} matches (total: {data.get('total_count', 0)})",
            )

            return json.dumps({"matches": matches, "total_count": data.get("total_count", 0)})
        except httpx.HTTPStatusError as e:
            return json.dumps({"error": f"GitHub search error {e.response.status_code}: {e.response.text[:200]}"})
        except Exception as e:
            return json.dumps({"error": f"Search failed: {str(e)}"})

    async def _github_get_diff(self, params: dict) -> str:
        owner_repo = self._resolve_owner_repo(params)
        if not owner_repo:
            return json.dumps({"error": "No owner_repo specified and no primary repo set"})

        commit_sha = params.get("commit_sha", "")
        base_ref = params.get("base", "")
        head_ref = params.get("head", "")

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                if commit_sha:
                    # Single commit diff
                    url = f"https://api.github.com/repos/{owner_repo}/commits/{commit_sha}"
                    resp = await client.get(url, headers=self._github_headers())
                    resp.raise_for_status()
                    data = resp.json()

                    files = data.get("files", [])[:15]
                    result_files = []
                    for f in files:
                        patch = f.get("patch", "")
                        if len(patch) > 2000:
                            patch = patch[:2000] + "\n... (truncated)"
                        result_files.append({
                            "filename": f.get("filename", ""),
                            "status": f.get("status", ""),
                            "additions": f.get("additions", 0),
                            "deletions": f.get("deletions", 0),
                            "patch": patch,
                        })

                    self.add_breadcrumb(
                        action="github_get_diff",
                        source_type="code",
                        source_reference=f"{owner_repo}@{commit_sha[:8]}",
                        raw_evidence=f"Diff: {len(result_files)} files changed",
                    )

                    return json.dumps({
                        "commit_sha": commit_sha,
                        "repo": owner_repo,
                        "message": data.get("commit", {}).get("message", ""),
                        "author": data.get("commit", {}).get("author", {}).get("name", ""),
                        "files": result_files,
                    })

                elif base_ref and head_ref:
                    # Compare two refs
                    url = f"https://api.github.com/repos/{owner_repo}/compare/{base_ref}...{head_ref}"
                    resp = await client.get(url, headers=self._github_headers())
                    resp.raise_for_status()
                    data = resp.json()

                    files = data.get("files", [])[:15]
                    result_files = []
                    for f in files:
                        patch = f.get("patch", "")
                        if len(patch) > 2000:
                            patch = patch[:2000] + "\n... (truncated)"
                        result_files.append({
                            "filename": f.get("filename", ""),
                            "status": f.get("status", ""),
                            "additions": f.get("additions", 0),
                            "deletions": f.get("deletions", 0),
                            "patch": patch,
                        })

                    self.add_breadcrumb(
                        action="github_get_diff",
                        source_type="code",
                        source_reference=f"{owner_repo}:{base_ref}...{head_ref}",
                        raw_evidence=f"Compare: {len(result_files)} files, {data.get('total_commits', 0)} commits",
                    )

                    return json.dumps({
                        "base": base_ref,
                        "head": head_ref,
                        "repo": owner_repo,
                        "total_commits": data.get("total_commits", 0),
                        "files": result_files,
                    })
                else:
                    return json.dumps({"error": "Provide either commit_sha or both base and head refs"})

        except httpx.HTTPStatusError as e:
            return json.dumps({"error": f"GitHub API error {e.response.status_code}: {e.response.text[:200]}"})
        except Exception as e:
            return json.dumps({"error": f"Diff failed: {str(e)}"})

    async def _github_list_files(self, params: dict) -> str:
        """List repo tree to discover file structure before reading."""
        owner_repo = self._resolve_owner_repo(params)
        if not owner_repo:
            return json.dumps({"error": "No repository configured"})

        subdir = params.get("path", "").strip("/")
        url = f"https://api.github.com/repos/{owner_repo}/git/trees/HEAD"
        query_params = {"recursive": "1"}

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, headers=self._github_headers(), params=query_params)
                if resp.status_code != 200:
                    return json.dumps({"error": f"GitHub API error {resp.status_code}: {resp.text[:200]}"})

                tree = resp.json().get("tree", [])
                # Filter to files only (not directories), optionally by subdirectory
                files = []
                for item in tree:
                    if item.get("type") != "blob":
                        continue
                    path = item.get("path", "")
                    if subdir and not path.startswith(subdir + "/") and path != subdir:
                        continue
                    files.append(path)

                return json.dumps({
                    "repo": owner_repo,
                    "total_files": len(files),
                    "files": files[:200],  # Cap at 200 for token limit
                })
        except Exception as e:
            return json.dumps({"error": f"Failed to list files: {str(e)}"})

    # --- Local tool implementations ---

    def _search_file(self, params: dict) -> str:
        pattern = params["pattern"]
        if not self.repo_path:
            return json.dumps({"error": "No repo_path set"})

        matches = []
        repo = Path(self.repo_path)
        for path in repo.rglob(pattern):
            if ".git" in path.parts or "node_modules" in path.parts or "__pycache__" in path.parts:
                continue
            matches.append(str(path.relative_to(repo)))

        if not matches:
            self.add_negative_finding(
                what_was_checked=f"Files matching '{pattern}' in repo",
                result="No files found",
                implication=f"No files matching pattern '{pattern}' in the repository",
                source_reference=f"repo: {self.repo_path}",
            )

        self.add_breadcrumb(
            action="search_file",
            source_type="code",
            source_reference=f"pattern: {pattern}",
            raw_evidence=f"Found {len(matches)} files",
        )

        return json.dumps({"matches": matches[:50], "total": len(matches)})

    def _validate_path(self, rel_path: str) -> tuple[bool, Path, str]:
        """Validate that a relative path stays within the repo root. Returns (ok, full_path, error)."""
        if not self.repo_path:
            return False, Path(), "No repo_path set"
        repo_root = Path(self.repo_path).resolve()
        full_path = (repo_root / rel_path).resolve()
        if not full_path.is_relative_to(repo_root):
            return False, full_path, f"Path traversal blocked: {rel_path}"
        return True, full_path, ""

    def _read_file(self, params: dict) -> str:
        rel_path = params["path"]
        start = params.get("start_line", 1)
        end = params.get("end_line", 0)

        ok, full_path, err = self._validate_path(rel_path)
        if not ok:
            return json.dumps({"error": err})
        if not full_path.exists():
            return json.dumps({"error": f"File not found: {rel_path}"})

        try:
            lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()
            if end > 0:
                selected = lines[max(0, start - 1):end]
            else:
                selected = lines

            # Limit to prevent huge responses
            if len(selected) > 200:
                selected = selected[:200]
                truncated = True
            else:
                truncated = False

            self.add_breadcrumb(
                action="read_file",
                source_type="code",
                source_reference=f"{rel_path}:{start}-{end or 'EOF'}",
                raw_evidence=f"Read {len(selected)} lines",
            )

            return json.dumps({
                "path": rel_path,
                "lines": selected,
                "start_line": start,
                "total_lines": len(lines),
                "truncated": truncated,
            })

        except Exception as e:
            return json.dumps({"error": str(e)})

    def _search_code(self, params: dict) -> str:
        pattern = params["pattern"]
        file_glob = params.get("file_glob", "*")

        if not self.repo_path:
            return json.dumps({"error": "No repo_path set"})

        matches = []
        repo = Path(self.repo_path)
        try:
            regex = re.compile(pattern)
        except re.error:
            return json.dumps({"error": f"Invalid regex: {pattern}"})

        for path in repo.rglob(file_glob):
            if path.is_dir() or ".git" in path.parts or "node_modules" in path.parts:
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                for i, line in enumerate(content.splitlines(), 1):
                    if regex.search(line):
                        matches.append({
                            "file": str(path.relative_to(repo)),
                            "line_number": i,
                            "line": line.strip()[:200],
                        })
            except Exception:
                continue

        self.add_breadcrumb(
            action="search_code",
            source_type="code",
            source_reference=f"pattern: {pattern}",
            raw_evidence=f"Found {len(matches)} matches",
        )

        return json.dumps({"matches": matches[:100], "total": len(matches)})

    def _find_callers_tool(self, params: dict) -> str:
        func_name = params["function_name"]
        callers = self._find_callers(self.repo_path, func_name)

        self.add_breadcrumb(
            action="find_callers",
            source_type="code",
            source_reference=f"function: {func_name}",
            raw_evidence=f"Found {len(callers)} callers",
        )

        return json.dumps({"function": func_name, "callers": callers})

    def _find_callees_tool(self, params: dict) -> str:
        rel_path = params["path"]
        func_name = params["function_name"]

        ok, full_path, err = self._validate_path(rel_path)
        if not ok:
            return json.dumps({"error": err})
        if not full_path.exists():
            return json.dumps({"error": f"File not found: {rel_path}"})

        try:
            content = full_path.read_text(encoding="utf-8", errors="replace")
            callees = self._extract_callees(content, func_name)

            self.add_breadcrumb(
                action="find_callees",
                source_type="code",
                source_reference=f"{rel_path}:{func_name}",
                raw_evidence=f"Found {len(callees)} callees",
            )

            return json.dumps({"function": func_name, "file": rel_path, "callees": callees})

        except Exception as e:
            return json.dumps({"error": str(e)})

    # --- Pure logic ---

    @staticmethod
    def _find_callers(repo_path: str, func_name: str) -> list[dict]:
        """Find all files that call a function (simple text search)."""
        if not repo_path:
            return []

        callers = []
        repo = Path(repo_path)
        pattern = re.compile(rf'\b{re.escape(func_name)}\s*\(')

        for path in repo.rglob("*"):
            if path.is_dir() or ".git" in path.parts or "node_modules" in path.parts or "__pycache__" in path.parts:
                continue
            if path.suffix not in (".py", ".java", ".js", ".ts", ".go", ".rs", ".rb", ".kt"):
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                for i, line in enumerate(content.splitlines(), 1):
                    # Skip function definitions
                    if re.match(rf'\s*def\s+{re.escape(func_name)}', line):
                        continue
                    if re.match(rf'\s*(public|private|protected)?\s*\w+\s+{re.escape(func_name)}\s*\(', line):
                        continue
                    if pattern.search(line):
                        callers.append({
                            "file_path": str(path.relative_to(repo)),
                            "line_number": i,
                            "line": line.strip()[:200],
                        })
            except Exception:
                continue

        return callers

    @staticmethod
    def _extract_callees(content: str, func_name: str) -> list[str]:
        """Extract function calls within a specific function body."""
        lines = content.splitlines()
        in_function = False
        indent_level = 0
        callees = set()

        for line in lines:
            # Detect function start (Python-style)
            if re.match(rf'\s*def\s+{re.escape(func_name)}\s*\(', line):
                in_function = True
                indent_level = len(line) - len(line.lstrip())
                continue

            if in_function:
                # Check if we've exited the function
                if line.strip() and not line.startswith(' ' * (indent_level + 1)) and not line.strip().startswith('#'):
                    if re.match(r'\s*def\s+', line) or re.match(r'\s*class\s+', line):
                        break

                # Find function calls in the line
                calls = re.findall(r'(\w+)\s*\(', line)
                for call in calls:
                    if call not in ('if', 'for', 'while', 'with', 'except', 'print', 'return', 'def', 'class', func_name):
                        callees.add(call)

        return sorted(callees)

    @staticmethod
    def _classify_impact(description: str) -> str:
        """Classify the impact type based on a description."""
        desc_lower = description.lower()
        if "direct" in desc_lower or "error location" in desc_lower or "error origin" in desc_lower:
            return "direct_error"
        if "call" in desc_lower and ("broken" in desc_lower or "upstream" in desc_lower):
            return "caller"
        if "called by" in desc_lower or "downstream" in desc_lower or "callee" in desc_lower:
            return "callee"
        if "config" in desc_lower or "configuration" in desc_lower or "settings" in desc_lower:
            return "config"
        if "test" in desc_lower:
            return "test"
        if "shared" in desc_lower or "utility" in desc_lower or "helper" in desc_lower or "common" in desc_lower:
            return "shared_resource"
        return "shared_resource"
