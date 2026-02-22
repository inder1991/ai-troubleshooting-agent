import json
import os
import re
import base64
from pathlib import Path
from typing import Any

import httpx

from src.agents.react_base import ReActAgent
from src.models.schemas import ImpactedFile, LineRange, FixArea, CodeAnalysisResult, TokenUsage
from src.utils.logger import get_logger

logger = get_logger(__name__)


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
    "shared_resource_conflicts": [],
    "suggested_fix_areas": [{"file_path": "...", "description": "...", "suggested_change": "..."}],
    "diff_analysis": [{"file": "...", "commit_sha": "...", "verdict": "likely_cause|unrelated|contributing", "reasoning": "..."}],
    "cross_repo_findings": [{"repo": "org/service", "role": "upstream_trigger|downstream_failure", "evidence": "..."}],
    "cross_service_trace": {"caller_service": "...", "target_endpoint": "...", "entry_point_file": "...", "entry_point_function": "..."},
    "mermaid_diagram": "graph TD; A-->B;",
    "overall_confidence": 85
}"""

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
            source_type="human",
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
