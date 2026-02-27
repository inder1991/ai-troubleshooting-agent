import asyncio
import json
import os
import re as _re
import shlex

from src.agents.react_base import ReActAgent
from src.utils.event_emitter import EventEmitter
from src.utils.logger import get_logger

logger = get_logger(__name__)

NOISE_FILE_PATTERN = _re.compile(
    r'(^docs?/|README|__pycache__|\.pyc$|'
    r'\.eslintrc|\.prettierrc|\.editorconfig|\.babelrc|'
    r'test_\w+\.py$|_test\.go$|\.test\.[tj]sx?$|'
    r'\.gitignore$|\.dockerignore$|\.lock$|'
    r'LICENSE|CHANGELOG|CONTRIBUTING|'
    r'\.flake8$|\.isort\.cfg$|\.pre-commit|\.coveragerc|\.pylintrc|mypy\.ini$|'
    r'tsconfig.*\.json$|jest\.config|webpack\.config|vite\.config)',
    _re.IGNORECASE,
)


class ChangeAgent(ReActAgent):
    """Investigates recent changes that may correlate with a production incident."""

    def __init__(self, connection_config=None):
        super().__init__(
            agent_name="change_agent",
            max_iterations=4,
            connection_config=connection_config,
        )
        self._connection_config = connection_config
        self._repo_url = ""
        self._namespace = ""
        self._incident_start = None
        self._cli_tool = "kubectl"
        self._github_token = ""

    # =========================================================================
    # TWO-PASS MODE: 2 LLM calls instead of up to 4 ReAct iterations
    # =========================================================================

    async def run_two_pass(self, context: dict, event_emitter: EventEmitter | None = None) -> dict:
        """Execute change analysis in exactly 1-2 LLM calls.

        Phase 0:  Pre-fetch — GitHub commits, deployment history, config diff.
                  Zero LLM calls, pure API.
        Call 1:   Triage — LLM sees all commits + context, identifies which
                  commits need detailed diffs. If trivial, produces final answer.
        Phase 1b: Batch-fetch diffs for flagged commits. Zero LLM calls.
        Call 2:   Analyze — LLM sees commits + diffs, produces final JSON.
        """
        # Initialize state from context
        self._repo_url = context.get("repo_url", "")
        self._github_token = context.get("github_token") or os.getenv("GITHUB_TOKEN", "")
        self._namespace = context.get("namespace", "default")
        self._incident_start = context.get("incident_start")
        self._cli_tool = context.get("cli_tool", "kubectl")
        self._stack_trace_files = context.get("stack_trace_files", [])

        logger.info("Change agent two-pass starting", extra={
            "agent_name": self.agent_name, "action": "two_pass_start",
            "extra": {
                "repo_url": self._repo_url or "(none)",
                "namespace": self._namespace,
                "stack_trace_files": len(self._stack_trace_files),
            },
        })

        if event_emitter:
            await event_emitter.emit(self.agent_name, "started", "Change agent starting two-pass analysis")

        # ── Phase 0: Pre-fetch (0 LLM calls) ────────────────────────────
        if event_emitter:
            await event_emitter.emit(self.agent_name, "tool_call", "Pre-fetching commits, deployments, and config")

        prefetched = await self._prefetch_changes(context)
        logger.info("Pre-fetch complete", extra={
            "agent_name": self.agent_name, "action": "prefetch_complete",
            "extra": {
                "commits": len(prefetched.get("commits", [])),
                "has_deployments": bool(prefetched.get("deployment_history")),
                "has_config": bool(prefetched.get("config_diff")),
            },
        })

        # ── Call 1: Triage ───────────────────────────────────────────────
        if event_emitter:
            await event_emitter.emit(self.agent_name, "tool_call", "LLM Call 1: Triaging commits")

        triage_prompt = self._build_triage_prompt(context, prefetched)
        triage_response = await self.llm_client.chat(
            prompt=triage_prompt,
            system=self._two_pass_triage_system_prompt(),
            max_tokens=1536,
        )

        triage = self._parse_triage_response(triage_response.text)
        logger.info("Call 1 (Triage) complete", extra={
            "agent_name": self.agent_name, "action": "triage_complete",
            "extra": {
                "commits_to_diff": len(triage.get("commits_to_diff", [])),
                "can_produce_final": triage.get("can_produce_final_answer", False),
            },
        })

        # If Call 1 already produced a final answer (e.g. no commits, or all trivial)
        if triage.get("can_produce_final_answer") and triage.get("final_answer"):
            logger.info("Call 1 produced final answer — skipping Call 2", extra={
                "agent_name": self.agent_name, "action": "early_finish",
            })
            if event_emitter:
                await event_emitter.emit(self.agent_name, "success", "Change agent completed (1 call)")
            result = self._parse_final_response(json.dumps(triage["final_answer"]))
            result["mode"] = "two_pass"
            result["llm_calls"] = 1
            return result

        # ── Phase 1b: Batch-fetch diffs (0 LLM calls) ───────────────────
        commits_to_diff = triage.get("commits_to_diff", [])[:3]
        diff_results = {}
        if commits_to_diff:
            if event_emitter:
                await event_emitter.emit(
                    self.agent_name, "tool_call",
                    f"Fetching diffs for {len(commits_to_diff)} commits"
                )

            async def _fetch_diff(sha: str) -> tuple[str, str]:
                result_json = await self._get_commit_diff({"commit_sha": sha})
                return sha, result_json

            tasks = [_fetch_diff(sha) for sha in commits_to_diff]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for item in results:
                if isinstance(item, tuple):
                    sha, diff_json = item
                    diff_results[sha] = diff_json

        # ── Call 2: Analyze ──────────────────────────────────────────────
        if event_emitter:
            await event_emitter.emit(self.agent_name, "tool_call", "LLM Call 2: Final analysis")

        analyze_prompt = self._build_change_analyze_prompt(context, prefetched, diff_results, triage)
        analyze_response = await self.llm_client.chat(
            prompt=analyze_prompt,
            system=self._two_pass_analyze_system_prompt(),
            max_tokens=2048,
        )

        if event_emitter:
            await event_emitter.emit(self.agent_name, "success", "Change agent completed analysis")

        result = self._parse_final_response(analyze_response.text)
        result["mode"] = "two_pass"
        result["llm_calls"] = 2
        logger.info("Two-pass change analysis complete", extra={
            "agent_name": self.agent_name, "action": "complete",
            "extra": {"correlations": len(result.get("change_correlations", []))},
        })
        return result

    # ── Pre-fetch ────────────────────────────────────────────────────────

    async def _prefetch_changes(self, context: dict) -> dict:
        """Gather all change data without LLM calls."""
        result: dict = {
            "commits": [],
            "commits_raw": "",
            "deployment_history": "",
            "config_diff": "",
        }

        # Parallel fetch: commits + deployment history + config diff
        async def _fetch_commits():
            if self._repo_url:
                return await self._get_github_commits({"repo_url": self._repo_url, "since_hours": 24})
            return ""

        async def _fetch_deployments():
            try:
                return await self._get_deployment_history({"namespace": self._namespace})
            except Exception as e:
                logger.warning("Pre-fetch deployment history failed: %s", e)
                return ""

        async def _fetch_config():
            try:
                return await self._get_config_diff({"namespace": self._namespace})
            except Exception as e:
                logger.warning("Pre-fetch config diff failed: %s", e)
                return ""

        commits_raw, deployments, config = await asyncio.gather(
            _fetch_commits(), _fetch_deployments(), _fetch_config(),
            return_exceptions=True,
        )

        if isinstance(commits_raw, str) and commits_raw:
            result["commits_raw"] = commits_raw
            try:
                result["commits"] = json.loads(commits_raw)
            except (json.JSONDecodeError, TypeError):
                pass

        if isinstance(deployments, str):
            result["deployment_history"] = deployments
        if isinstance(config, str):
            result["config_diff"] = config

        return result

    # ── Prompt builders ──────────────────────────────────────────────────

    def _two_pass_triage_system_prompt(self) -> str:
        return (
            "You are a Change Intelligence agent investigating recent changes "
            "that may correlate with a production incident.\n\n"
            "You are given pre-fetched data: recent commits, deployment history, "
            "and configuration state. Your job is to:\n"
            "1. Review the commits and identify which 1-3 are highest-risk\n"
            "2. Return their SHAs so we can fetch detailed diffs\n"
            "3. If there are NO commits or all are clearly unrelated, produce the final answer directly\n\n"
            "Risk scoring rules:\n"
            "- Commit touching a file in STACK TRACE FILES → risk >= 0.9\n"
            "- Commit touching same module/package as the error → risk >= 0.6\n"
            "- Commit only touching docs, tests, README, .lock, linting config → risk <= 0.1\n"
        )

    def _two_pass_analyze_system_prompt(self) -> str:
        return (
            "You are a Change Intelligence agent. You have all the data: "
            "commits, detailed diffs, deployment history, and config state.\n\n"
            "Produce your final analysis as JSON (no markdown, no extra text):\n"
            "```json\n"
            "{\n"
            '  "change_correlations": [\n'
            "    {\n"
            '      "sha": "commit short sha",\n'
            '      "description": "max 80 chars — one sentence",\n'
            '      "author": "who",\n'
            '      "date": "when",\n'
            '      "risk_score": 0.0-1.0,\n'
            '      "correlation_type": "code_change|config_change|deployment",\n'
            '      "files_changed": ["file1.py"],\n'
            '      "reasoning": "max 120 chars — why this correlates"\n'
            "    }\n"
            "  ],\n"
            '  "summary": "max 200 chars — one paragraph executive summary"\n'
            "}\n"
            "```\n\n"
            "BREVITY RULES:\n"
            "- description: 1 sentence, max 80 characters\n"
            "- reasoning: 1 sentence, max 120 characters\n"
            "- summary: 1 short paragraph, max 200 characters\n"
            "- Include only the top 5 most relevant changes. Skip doc/test/config-only commits.\n"
            "- Populate files_changed from the diffs provided."
        )

    def _build_triage_prompt(self, context: dict, prefetched: dict) -> str:
        parts = [
            "# Change Analysis — Phase 1: Triage\n",
            f"Service: {context.get('service_name', 'unknown')}",
            f"Namespace: {self._namespace}",
            f"Incident start: {self._incident_start or 'unknown'}",
        ]

        if context.get("exception_type"):
            parts.append(f"Exception: {context['exception_type']}")

        if self._stack_trace_files:
            parts.append("\n## Stack Trace Files (from error logs)")
            for f in self._stack_trace_files[:10]:
                parts.append(f"  - {f}")

        # Commits
        commits = prefetched.get("commits", [])
        if commits:
            parts.append(f"\n## Recent Commits ({len(commits)} found)")
            for c in commits:
                parts.append(
                    f"  - `{c.get('sha', '?')}` by {c.get('author', '?')} "
                    f"({c.get('date', '?')}): {c.get('message', '')[:150]}"
                )
        elif prefetched.get("commits_raw"):
            parts.append(f"\n## Commits Raw\n{prefetched['commits_raw'][:3000]}")
        else:
            parts.append("\n## Commits\nNo commits found in the last 24 hours.")

        # Deployment history
        if prefetched.get("deployment_history"):
            parts.append(f"\n## Deployment History\n{prefetched['deployment_history'][:800]}")

        # Config
        if prefetched.get("config_diff"):
            parts.append(f"\n## ConfigMap State\n{prefetched['config_diff'][:800]}")

        parts.append(
            "\n## Your Task\n"
            "Respond with JSON:\n"
            "```json\n"
            "{\n"
            '  "commits_to_diff": ["sha1", "sha2"],  // max 3 highest-risk SHAs needing detailed diffs\n'
            '  "preliminary_risk_assessment": "Brief assessment...",\n'
            '  "can_produce_final_answer": false,  // true ONLY if no diffs needed\n'
            '  "final_answer": null  // if true above, put full change_correlations JSON here\n'
            "}\n"
            "```\n"
            "If there are no commits or all are clearly low-risk (docs/tests only), "
            "set can_produce_final_answer=true and include the full analysis as final_answer."
        )

        return "\n".join(parts)

    def _build_change_analyze_prompt(
        self, context: dict, prefetched: dict, diff_results: dict, triage: dict,
    ) -> str:
        parts = [
            "# Change Analysis — Phase 2: Final Analysis\n",
            f"Service: {context.get('service_name', 'unknown')}",
            f"Namespace: {self._namespace}",
            f"Incident start: {self._incident_start or 'unknown'}",
        ]

        if context.get("exception_type"):
            parts.append(f"Exception: {context['exception_type']}")

        if self._stack_trace_files:
            parts.append("\n## Stack Trace Files")
            for f in self._stack_trace_files[:10]:
                parts.append(f"  - {f}")

        # All commits
        commits = prefetched.get("commits", [])
        if commits:
            parts.append(f"\n## All Recent Commits ({len(commits)})")
            for c in commits:
                parts.append(
                    f"  - `{c.get('sha', '?')}` by {c.get('author', '?')} "
                    f"({c.get('date', '?')}): {c.get('message', '')[:150]}"
                )

        # Detailed diffs
        if diff_results:
            parts.append(f"\n## Detailed Commit Diffs ({len(diff_results)} commits)")
            for sha, diff_json in diff_results.items():
                try:
                    diff_data = json.loads(diff_json)
                    parts.append(f"\n### Commit {sha[:8]}: {diff_data.get('message', '')[:100]}")
                    parts.append(f"Author: {diff_data.get('author', 'unknown')}")
                    for f in diff_data.get("files", []):
                        parts.append(f"  {f.get('filename', '?')} (+{f.get('additions', 0)}/-{f.get('deletions', 0)})")
                        patch = f.get("patch", "")
                        if patch:
                            parts.append(f"  ```\n{patch[:500]}\n  ```")
                except (json.JSONDecodeError, TypeError):
                    parts.append(f"\n### Commit {sha[:8]}\n{diff_json[:500]}")

        # Deployment + config
        if prefetched.get("deployment_history"):
            parts.append(f"\n## Deployment History\n{prefetched['deployment_history'][:800]}")
        if prefetched.get("config_diff"):
            parts.append(f"\n## ConfigMap State\n{prefetched['config_diff'][:800]}")

        # Triage context
        if triage.get("preliminary_risk_assessment"):
            parts.append(f"\n## Preliminary Assessment (from Phase 1)\n{triage['preliminary_risk_assessment']}")

        parts.append(
            "\n## Your Task\n"
            "Produce the final change correlation analysis as JSON. "
            "Focus on the top 5 highest-risk commits. Use files_changed from the diffs."
        )

        return "\n".join(parts)

    def _parse_triage_response(self, text: str) -> dict:
        """Parse Call 1's triage JSON response."""
        try:
            json_match = _re.search(r'\{[\s\S]*\}', text)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = json.loads(text)
            data.setdefault("commits_to_diff", [])
            data.setdefault("preliminary_risk_assessment", "")
            data.setdefault("can_produce_final_answer", False)
            data.setdefault("final_answer", None)
            return data
        except (json.JSONDecodeError, AttributeError):
            logger.warning("Failed to parse triage response")
            return {
                "commits_to_diff": [],
                "preliminary_risk_assessment": text[:500],
                "can_produce_final_answer": False,
                "final_answer": None,
            }

    async def _define_tools(self) -> list[dict]:
        return [
            {
                "name": "github_recent_commits",
                "description": "Get recent commits from a GitHub repository",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "repo_url": {"type": "string"},
                        "since_hours": {"type": "integer", "default": 24},
                    },
                    "required": ["repo_url"],
                },
            },
            {
                "name": "deployment_history",
                "description": "Get deployment rollout history from the cluster",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "namespace": {"type": "string"},
                        "deployment_name": {"type": "string"},
                    },
                    "required": ["namespace"],
                },
            },
            {
                "name": "config_diff",
                "description": "Check for recent ConfigMap or Secret changes",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "namespace": {"type": "string"},
                        "resource_name": {"type": "string"},
                    },
                    "required": ["namespace"],
                },
            },
            {
                "name": "github_get_commit_diff",
                "description": (
                    "Get the file-level diff for a specific commit SHA. "
                    "Returns filenames, additions, deletions, and patch hunks. "
                    "Use this on HIGH-RISK commits to see exactly what code changed."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "repo_url": {"type": "string"},
                        "commit_sha": {"type": "string", "description": "The full or short commit SHA"},
                    },
                    "required": ["commit_sha"],
                },
            },
        ]

    async def _build_system_prompt(self) -> str:
        return (
            "You are a Change Intelligence agent investigating recent changes "
            "that may correlate with a production incident. Check GitHub commits, "
            "deployment history, and configuration changes.\n\n"
            "IMPORTANT: When you finish your analysis, you MUST respond with a JSON object "
            "(no markdown, no extra text) in this exact format:\n"
            "```json\n"
            "{\n"
            '  "change_correlations": [\n'
            "    {\n"
            '      "sha": "commit short sha or change id",\n'
            '      "description": "max 80 chars — one sentence",\n'
            '      "author": "who",\n'
            '      "date": "when",\n'
            '      "risk_score": 0.0-1.0,\n'
            '      "correlation_type": "code_change|config_change|deployment",\n'
            '      "files_changed": ["file1.py", "file2.yaml"],\n'
            '      "reasoning": "max 120 chars — why this correlates"\n'
            "    }\n"
            "  ],\n"
            '  "summary": "max 200 chars — one paragraph executive summary"\n'
            "}\n"
            "```\n\n"
            "BREVITY RULES:\n"
            "- description: 1 sentence, max 80 characters\n"
            "- reasoning: 1 sentence, max 120 characters\n"
            "- summary: 1 short paragraph, max 200 characters\n"
            "- Include only the top 5 most relevant changes. Skip doc/test/config-only commits.\n"
            "- If no changes found, return empty change_correlations array.\n\n"
            "Score risk_score from 0.0 (unrelated) to 1.0 (very likely cause).\n\n"
            "Risk scoring rules:\n"
            "- Changed file in STACK TRACE FILES list -> risk_score >= 0.9\n"
            "- Same module/package as the error -> risk_score >= 0.6\n"
            "- For the 1-2 highest-risk commits, use github_get_commit_diff to verify\n"
            "- Include filenames from the diff in 'files_changed'\n\n"
            "Budget strategy (limited iterations):\n"
            "1. github_recent_commits to get commit list\n"
            "2. Identify 1-2 highest-risk commits\n"
            "3. github_get_commit_diff ONLY on those 1-2\n"
            "4. Final response: JSON with files_changed from diffs\n"
            "Do NOT diff every commit. Only diff the most likely to correlate.\n"
        )

    async def _build_initial_prompt(self, context: dict) -> str:
        self._repo_url = context.get("repo_url", "")
        self._github_token = context.get("github_token") or os.getenv("GITHUB_TOKEN", "")
        self._namespace = context.get("namespace", "default")
        self._incident_start = context.get("incident_start")
        self._cli_tool = context.get("cli_tool", "kubectl")
        self._stack_trace_files = context.get("stack_trace_files", [])
        logger.info("Change agent context", extra={
            "agent_name": self.agent_name, "action": "context_loaded",
            "extra": {
                "repo_url": self._repo_url or "(none)",
                "has_github_token": bool(self._github_token),
                "namespace": self._namespace,
                "incident_start": self._incident_start or "(unknown)",
                "cli_tool": self._cli_tool,
                "stack_trace_files": len(self._stack_trace_files),
            },
        })

        parts = [
            f"Investigate recent changes for service in namespace '{self._namespace}'. "
            f"Repository: {self._repo_url or 'not specified'}. "
            f"Incident start: {self._incident_start or 'unknown'}. "
            f"Look for deployments, code changes, and config modifications in the last 24 hours."
        ]

        if self._stack_trace_files:
            parts.append(
                "\n## STACK TRACE FILES (from production error logs)\n"
                "These files appear in the error stack trace:\n"
                + "\n".join(f"  - {f}" for f in self._stack_trace_files[:10])
                + "\n\nCRITICAL: If any commit touches these files, set risk_score >= 0.9. "
                "Use github_get_commit_diff to verify the actual code changes."
            )
        if context.get("exception_type"):
            parts.append(f"\nException type from logs: {context['exception_type']}")

        return "\n".join(parts)

    async def _handle_tool_call(self, tool_name: str, tool_input: dict) -> str:
        if tool_name == "github_recent_commits":
            return await self._get_github_commits(tool_input)
        elif tool_name == "deployment_history":
            return await self._get_deployment_history(tool_input)
        elif tool_name == "config_diff":
            return await self._get_config_diff(tool_input)
        elif tool_name == "github_get_commit_diff":
            return await self._get_commit_diff(tool_input)
        return f"Unknown tool: {tool_name}"

    async def _get_github_commits(self, params: dict) -> str:
        import httpx
        from datetime import datetime, timezone, timedelta

        repo_url = params.get("repo_url", self._repo_url)
        since_hours = params.get("since_hours", 24)

        if not repo_url:
            return "No repository URL provided"

        owner_repo = self._parse_repo_url(repo_url)
        if not owner_repo:
            return f"Could not parse repository URL: {repo_url}"

        token = self._github_token or os.getenv("GITHUB_TOKEN", "")
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        since_iso = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).isoformat()
        url = f"https://api.github.com/repos/{owner_repo}/commits"

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # First try: commits within the time window
                resp = await client.get(url, headers=headers, params={"per_page": 20, "since": since_iso})
                if resp.status_code == 401:
                    return "GitHub API error: authentication required — set GITHUB_TOKEN env var"
                if resp.status_code == 404:
                    return f"GitHub API error: repository not found — {owner_repo}"
                resp.raise_for_status()
                commits = resp.json()

                # Fallback: if no commits in time window, fetch last 10 commits
                if not commits:
                    resp = await client.get(url, headers=headers, params={"per_page": 10})
                    resp.raise_for_status()
                    commits = resp.json()
                    if commits:
                        logger.info("No commits in last %dh, falling back to last %d commits", since_hours, len(commits))
        except httpx.HTTPStatusError as e:
            return f"GitHub API error: {e.response.status_code} {e.response.text[:200]}"
        except httpx.ConnectError:
            return "GitHub API error: connection failed — check network"
        except httpx.TimeoutException:
            return "GitHub API error: request timed out"

        def _fmt(c: dict) -> dict:
            return {
                "sha": c["sha"][:8],
                "author": c["commit"]["author"]["name"],
                "date": c["commit"]["author"]["date"],
                "message": c["commit"]["message"][:200],
            }

        result = [_fmt(c) for c in commits]
        if not result:
            return f"No commits found in repository {owner_repo}"

        result_json = json.dumps(result, indent=2)
        self.add_breadcrumb(
            action="fetch_commits",
            source_type="code",
            source_reference=owner_repo,
            raw_evidence=result_json,
        )
        return result_json

    async def _get_commit_diff(self, params: dict) -> str:
        """Fetch file-level diff for a commit. Ported from code_agent pattern."""
        import httpx

        repo_url = params.get("repo_url", self._repo_url)
        commit_sha = params.get("commit_sha", "")
        if not commit_sha:
            return "No commit SHA provided"

        owner_repo = self._parse_repo_url(repo_url)
        if not owner_repo:
            return f"Could not parse repository URL: {repo_url}"

        token = self._github_token or os.getenv("GITHUB_TOKEN", "")
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        url = f"https://api.github.com/repos/{owner_repo}/commits/{commit_sha}"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 404:
                    return f"Commit not found: {commit_sha}"
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            return f"GitHub API error: {e.response.status_code}"
        except (httpx.ConnectError, httpx.TimeoutException):
            return "GitHub API error: connection failed or timed out"

        files = data.get("files", [])[:15]
        result_files = []
        for f in files:
            patch = f.get("patch", "")
            if len(patch) > 1500:
                patch = patch[:1500] + "\n... (truncated)"
            result_files.append({
                "filename": f.get("filename", ""),
                "status": f.get("status", ""),
                "additions": f.get("additions", 0),
                "deletions": f.get("deletions", 0),
                "patch": patch,
            })

        result = {
            "commit_sha": commit_sha,
            "message": data.get("commit", {}).get("message", "")[:200],
            "author": data.get("commit", {}).get("author", {}).get("name", ""),
            "files": result_files,
        }
        result_json = json.dumps(result, indent=2)

        self.add_breadcrumb(
            action="fetch_commit_diff",
            source_type="code",
            source_reference=f"{owner_repo}@{commit_sha[:8]}",
            raw_evidence=f"Diff: {len(result_files)} files changed",
        )
        return result_json

    @staticmethod
    def _map_correlation_type(raw: str) -> str:
        """Map LLM correlation types to frontend-expected change_type values."""
        mapping = {
            "code_change": "code_deploy",
            "config_change": "config_change",
            "deployment": "code_deploy",
            "infra_change": "infra_change",
            "dependency_update": "dependency_update",
        }
        return mapping.get(raw, "code_deploy")

    def _extract_correlations_from_text(self, text: str) -> list[dict]:
        """Fallback: extract commit-like correlations from unstructured LLM text."""
        import re
        correlations = []
        # Look for commit SHA patterns with surrounding context
        sha_pattern = re.compile(
            r'(?:commit|sha|hash)[:\s]*[`"]?([0-9a-f]{7,8})[`"]?'
            r'[^\n]*?(?:by|author)[:\s]*([^\n,]+)?'
            r'.*?(?:message|description|:)[:\s]*["`]?([^\n"`]{10,200})',
            re.IGNORECASE | re.DOTALL,
        )
        for m in sha_pattern.finditer(text):
            correlations.append({
                "sha": m.group(1),
                "author": (m.group(2) or "unknown").strip(),
                "description": m.group(3).strip(),
                "risk_score": 0.5,
                "correlation_type": "code_change",
                "files_changed": [],
                "reasoning": "Extracted from unstructured agent response",
            })

        # Also try: lines that look like commit entries from the tool output
        # Pattern: "sha: XXXXXXXX" from earlier tool calls stored in breadcrumbs
        if not correlations and self.breadcrumbs:
            for bc in self.breadcrumbs:
                if bc.source_type in ("github_api", "code"):
                    try:
                        commits = json.loads(bc.raw_evidence)
                        if isinstance(commits, list):
                            for c in commits[:5]:
                                correlations.append({
                                    "sha": c.get("sha", "")[:8],
                                    "author": c.get("author", "unknown"),
                                    "date": c.get("date", ""),
                                    "description": c.get("message", "")[:200],
                                    "risk_score": 0.5,
                                    "correlation_type": "code_change",
                                    "files_changed": [],
                                    "reasoning": "Extracted from commit data (LLM did not return structured JSON)",
                                })
                    except (json.JSONDecodeError, TypeError):
                        pass

        return correlations

    def _parse_repo_url(self, url: str) -> str | None:
        """Extract 'owner/repo' from various GitHub URL formats."""
        import re
        patterns = [
            r'github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$',
            r'^([^/]+/[^/]+)$',
        ]
        for pattern in patterns:
            m = re.search(pattern, url)
            if m:
                return m.group(1)
        return None

    async def _get_deployment_history(self, params: dict) -> str:
        from src.integrations.probe import run_command

        ns = shlex.quote(params.get("namespace", self._namespace))
        dep = shlex.quote(params.get("deployment_name", ""))
        cli = shlex.quote(self._cli_tool)
        if dep and dep != "''":
            cmd = f"{cli} rollout history deployment/{dep} -n {ns}"
        else:
            cmd = f"{cli} rollout history deployment -n {ns}"
        code, stdout, stderr = await run_command(cmd)
        return stdout if code == 0 else f"Error: {stderr}"

    async def _get_config_diff(self, params: dict) -> str:
        from src.integrations.probe import run_command

        ns = shlex.quote(params.get("namespace", self._namespace))
        name = shlex.quote(params.get("resource_name", ""))
        cli = shlex.quote(self._cli_tool)
        if name and name != "''":
            cmd = f"{cli} get configmap {name} -n {ns} -o yaml"
        else:
            cmd = f"{cli} get configmap -n {ns}"
        code, stdout, stderr = await run_command(cmd)
        return stdout if code == 0 else f"Error: {stderr}"

    def _parse_final_response(self, text: str) -> dict:
        import re

        logger.info("Parsing final response", extra={
            "agent_name": self.agent_name, "action": "parse_response",
            "extra": {"text_length": len(text) if text else 0, "preview": (text[:300] if text else "(empty)")},
        })

        data = {}
        # Strategy 1: JSON in code block
        json_match = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', text or "")
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                logger.info("Parsed JSON from code block", extra={
                    "agent_name": self.agent_name, "action": "parse_success",
                    "extra": {"method": "code_block", "keys": list(data.keys())},
                })
            except json.JSONDecodeError as e:
                logger.warning("Code block JSON parse failed: %s", e)

        # Strategy 2: Raw JSON object in text
        if not data:
            try:
                json_match = re.search(r'\{[\s\S]*\}', text or "")
                if json_match:
                    data = json.loads(json_match.group())
                    logger.info("Parsed JSON from raw text", extra={
                        "agent_name": self.agent_name, "action": "parse_success",
                        "extra": {"method": "raw_json", "keys": list(data.keys())},
                    })
            except (json.JSONDecodeError, TypeError, AttributeError) as e:
                logger.warning("Raw JSON parse failed: %s", e)

        # Strategy 3: If no JSON parsed, try to extract correlations from markdown
        if not data.get("change_correlations"):
            correlations = self._extract_correlations_from_text(text or "")
            if correlations:
                data["change_correlations"] = correlations
                logger.info("Extracted correlations from markdown", extra={
                    "agent_name": self.agent_name, "action": "parse_success",
                    "extra": {"method": "markdown_extract", "count": len(correlations)},
                })

        # Normalize field names to match frontend ChangeCorrelation interface
        normalized = []
        for corr in data.get("change_correlations", []):
            normalized.append({
                "change_id": corr.get("sha", corr.get("change_id", "")),
                "change_type": self._map_correlation_type(corr.get("correlation_type", corr.get("change_type", "code_deploy"))),
                "risk_score": corr.get("risk_score", 0.5),
                "temporal_correlation": corr.get("temporal_correlation", corr.get("risk_score", 0.5)),
                "author": corr.get("author", "unknown"),
                "description": corr.get("description", ""),
                "files_changed": corr.get("files_changed", []),
                "timestamp": corr.get("date", corr.get("timestamp")),
                "reasoning": corr.get("reasoning", ""),
                "service_name": corr.get("service_name", ""),
            })

        # Build high_priority_files for downstream hand-off, filtering noise
        high_priority = []
        for corr in normalized:
            risk = corr.get("risk_score", 0)
            sha = corr.get("change_id", "")
            for f in corr.get("files_changed", []):
                if NOISE_FILE_PATTERN.search(f):
                    continue
                high_priority.append({
                    "file_path": f, "risk_score": risk,
                    "sha": sha, "description": corr.get("description", "")[:100],
                })
        high_priority.sort(key=lambda x: x["risk_score"], reverse=True)

        result = {
            "change_correlations": normalized,
            "high_priority_files": high_priority[:5],
            "summary": data.get("summary", text[:200] if text else "No changes found"),
            "breadcrumbs": [b.model_dump(mode="json") for b in self.breadcrumbs],
            "negative_findings": [n.model_dump(mode="json") for n in self.negative_findings],
            "tokens_used": self.get_token_usage().model_dump(),
        }
        logger.info("Change agent complete", extra={"agent_name": self.agent_name, "action": "complete", "extra": {"correlations": len(result["change_correlations"]), "high_priority_files": len(high_priority[:5])}})
        return result
