"""
Agent 3: Fix Generator & PR Orchestrator

Two-Phase Workflow:
- PHASE 1 (Verification): Automatic validation, peer review, impact assessment, PR staging
- PHASE 2 (Action): On-demand PR creation after user approval

Author: Production AI Team
Version: 4.0 - Anthropic migration
"""

import json
import asyncio
from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime

from .validators import StaticValidator
from .reviewers import CrossAgentReviewer
from .assessors import ImpactAssessor
from .stagers import PRStager

from src.utils.llm_client import AnthropicClient
from src.utils.event_emitter import EventEmitter
from src.models.schemas import DiagnosticState
from src.utils.logger import get_logger

logger = get_logger(__name__)


class Agent3FixGenerator:
    """
    Agent 3: Fix Generator & PR Orchestrator

    Responsibilities:
    1. Generate code fixes using LLM
    2. Validate fixes (syntax, linting, imports)
    3. Request Agent 2 peer review
    4. Assess impact and risk
    5. Stage PR locally (branch + commit)
    6. Create PR on user approval

    Two-Phase Approach:
    - Phase 1: Verification (automatic, ~30s)
    - Phase 2: Action (on-demand, ~5s)
    """

    AGENT_NAME = "fix_generator"

    def __init__(
        self,
        repo_path: str,
        llm_client: AnthropicClient,
        agent2_module: Optional[Any] = None,
        event_emitter: Optional[EventEmitter] = None,
    ):
        """
        Initialize Agent 3

        Args:
            repo_path: Path to cloned repository
            llm_client: AnthropicClient instance for LLM calls
            agent2_module: Agent 2 instance for peer review (optional)
            event_emitter: EventEmitter for progress updates (optional)
        """
        self.repo_path = Path(repo_path)
        self.llm_client = llm_client
        self.agent2_module = agent2_module
        self.event_emitter = event_emitter

        # Initialize components
        self.validator = StaticValidator(repo_path)
        self.reviewer = CrossAgentReviewer(agent2_module, llm_client=llm_client)
        self.assessor = ImpactAssessor(llm_client)
        self.stager = PRStager(repo_path)

        logger.info(f"Agent 3 initialized (repo: {repo_path})")

    # =========================================================================
    # PHASE 1: VERIFICATION (Automatic)
    # =========================================================================

    async def run_verification_phase(
        self,
        state: DiagnosticState,
        generated_fix: str,
    ) -> Dict[str, Any]:
        """
        Execute Phase 1: Verification

        Steps:
        1. Static validation (AST, linting, imports)
        2. Agent 2 peer review
        3. Impact & risk assessment
        4. PR staging (local branch + commit)
        5. Emit progress events

        Args:
            state: DiagnosticState with session context and agent results
            generated_fix: Fixed code from LLM

        Returns:
            PR data for user review
        """
        session_id = state.session_id

        logger.info("\n" + "=" * 80)
        logger.info("AGENT 3: PHASE 1 - VERIFICATION")
        logger.info("=" * 80)

        # Extract file path from code analysis in state
        file_path = ""
        if state.code_analysis and state.code_analysis.root_cause_location:
            file_path = state.code_analysis.root_cause_location.file_path

        # Build context dicts from state for downstream components
        agent1_analysis = self._build_agent1_context(state)
        agent2_analysis = self._build_agent2_context(state)

        # ---- STEP 1: STATIC VALIDATION ----

        await self._emit_progress("validation", "Running static validation...")

        validation_result = self.validator.validate_all(file_path, generated_fix)

        # Self-correct if validation fails
        if not validation_result["passed"]:
            logger.info("\nValidation failed, attempting self-correction...")
            generated_fix = await self._self_correct(generated_fix, validation_result)
            validation_result = self.validator.validate_all(file_path, generated_fix)

        # ---- STEP 2: CROSS-AGENT PEER REVIEW ----

        await self._emit_progress("review", "Agent 2 reviewing fix...")

        original_code = self._read_original_file(file_path)

        agent2_review = await self.reviewer.request_review(
            original_code, generated_fix, agent2_analysis
        )

        validation_result["agent2_approved"] = agent2_review["approved"]
        validation_result["agent2_confidence"] = agent2_review["confidence"]

        # ---- STEP 3: IMPACT & RISK ASSESSMENT ----

        await self._emit_progress("assessment", "Assessing impact...")

        call_chain = agent2_analysis.get("call_chain", [])
        impact_report = await self.assessor.assess_impact(
            file_path, original_code, generated_fix, call_chain
        )

        # ---- STEP 4: PR STAGING ----

        await self._emit_progress("staging", "Staging PR locally...")

        branch_name = self.stager.create_branch(
            agent1_analysis.get("incident_id", "incident"),
            agent1_analysis.get("bug_id", "bug"),
        )

        self.stager.stage_changes(file_path, generated_fix)

        commit_sha = self.stager.create_commit(
            agent1_analysis.get("incident_id", "incident"),
            agent1_analysis.get("bug_id", "bug"),
            agent1_analysis,
            agent2_analysis,
        )

        pr_body = self.stager.generate_pr_template(
            agent1_analysis, agent2_analysis, impact_report, validation_result
        )

        # ---- STEP 5: PREPARE PR DATA ----

        summary = agent1_analysis.get("diagnostic_summary", "Fix issue")[:60]
        pr_data = {
            "branch_name": branch_name,
            "commit_sha": commit_sha,
            "pr_title": f"fix: {summary}",
            "pr_body": pr_body,
            "diff": self._generate_diff(original_code, generated_fix),
            "validation": validation_result,
            "impact": impact_report,
            "fixed_code": generated_fix,
            "status": "awaiting_approval",
            "token_usage": self.llm_client.get_total_usage().model_dump(),
        }

        # ---- STEP 6: NOTIFY ----

        await self._emit_progress(
            "verification_complete",
            f"Verification complete. Branch: {branch_name}",
        )

        logger.info(f"\nPHASE 1 COMPLETE")
        logger.info(f"   Branch: {branch_name}")
        logger.info(f"   Commit: {commit_sha[:7]}")
        logger.info(f"   Validation: {'Passed' if validation_result['passed'] else 'Issues'}")
        logger.info(f"   Confidence: {agent2_review['confidence']:.0%}")
        logger.info(f"   Awaiting user approval...")
        logger.info("=" * 80 + "\n")

        return pr_data

    # =========================================================================
    # FULL-CONTEXT FIX GENERATION
    # =========================================================================

    async def generate_fix(
        self,
        state: DiagnosticState,
        human_guidance: str = "",
        event_emitter: Optional[EventEmitter] = None,
    ) -> str:
        """
        Generate a fix using the full DiagnosticState from all agents.

        Builds a comprehensive LLM prompt from log, metrics, k8s, trace,
        code, and change analysis. Returns the fixed code string.
        """
        emitter = event_emitter or self.event_emitter

        # Determine target file
        target_file = ""
        if state.code_analysis and state.code_analysis.root_cause_location:
            target_file = state.code_analysis.root_cause_location.file_path

        if not target_file:
            raise ValueError("No target file identified in code analysis")

        # Read original code from disk
        original_code = self._read_original_file(target_file)

        # Build comprehensive prompt from all agent findings
        evidence_parts = []

        # 1. Log analysis
        if state.log_analysis:
            p = state.log_analysis.primary_pattern
            evidence_parts.append(
                f"## Log Analysis\n"
                f"- Exception: {p.exception_type}\n"
                f"- Error: {p.error_message}\n"
                f"- Severity: {p.severity}\n"
                f"- Affected: {', '.join(p.affected_components)}"
            )
            if p.stack_traces:
                evidence_parts.append(f"- Stack trace:\n{p.stack_traces[0][:1000]}")

        # 2. Metrics analysis
        if state.metrics_analysis and state.metrics_analysis.anomalies:
            lines = ["## Metrics Analysis"]
            for a in state.metrics_analysis.anomalies[:5]:
                lines.append(f"- {a.metric_name}: peak={a.peak_value} baseline={a.baseline_value} ({a.severity})")
                lines.append(f"  Correlation: {a.correlation_to_incident}")
            evidence_parts.append("\n".join(lines))

        # 3. K8s analysis
        if state.k8s_analysis:
            lines = ["## K8s Analysis"]
            if state.k8s_analysis.is_crashloop:
                lines.append(f"- CrashLoopBackOff detected, {state.k8s_analysis.total_restarts_last_hour} restarts")
            for p in state.k8s_analysis.pod_statuses:
                if p.oom_killed:
                    lines.append(f"- Pod {p.pod_name} OOMKilled")
            evidence_parts.append("\n".join(lines))

        # 4. Trace analysis
        if state.trace_analysis:
            lines = ["## Trace Analysis"]
            if state.trace_analysis.failure_point:
                fp = state.trace_analysis.failure_point
                lines.append(f"- Failure: {fp.service_name}:{fp.operation_name} — {fp.error_message}")
            if state.trace_analysis.cascade_path:
                lines.append(f"- Cascade: {' → '.join(state.trace_analysis.cascade_path)}")
            evidence_parts.append("\n".join(lines))

        # 5. Code analysis
        if state.code_analysis:
            ca = state.code_analysis
            lines = ["## Code Analysis"]
            lines.append(f"- Root cause: {ca.root_cause_location.file_path}")
            lines.append(f"- Call chain: {' → '.join(ca.call_chain[:5])}")
            for fa in ca.suggested_fix_areas:
                lines.append(f"- Fix area: {fa.file_path} — {fa.description}")
                lines.append(f"  Suggestion: {fa.suggested_change}")
            if ca.diff_analysis:
                for da in ca.diff_analysis[:3]:
                    if da.verdict != "unrelated":
                        lines.append(f"- Diff ({da.verdict}): {da.file} — {da.reasoning}")
            evidence_parts.append("\n".join(lines))

        # 6. Change analysis
        if state.change_analysis:
            correlations = state.change_analysis.get("change_correlations", [])
            if correlations:
                lines = ["## Change Analysis"]
                for corr in correlations[:3]:
                    lines.append(f"- {corr.get('description', 'unknown')[:100]} (risk: {corr.get('risk_score', 'N/A')})")
                evidence_parts.append("\n".join(lines))

        # 7. Human guidance
        if human_guidance:
            evidence_parts.append(f"## Human Guidance\n{human_guidance}")

        # 8. Prior feedback (for regeneration loops)
        if state.fix_result and state.fix_result.human_feedback:
            evidence_parts.append(
                "## Prior Human Feedback\n" +
                "\n".join(f"- {fb}" for fb in state.fix_result.human_feedback)
            )

        evidence_text = "\n\n".join(evidence_parts)

        system_prompt = (
            "You are an expert SRE generating production-ready code fixes. "
            "Given a comprehensive incident analysis and recommendations from 6 diagnostic agents, "
            "generate the complete fixed file. Output ONLY the complete fixed source code — "
            "no markdown fences, no explanations, no comments about what changed."
        )

        user_prompt = (
            f"## Target File: {target_file}\n\n"
            f"## Original Code\n{original_code}\n\n"
            f"## Diagnostic Evidence\n{evidence_text}\n\n"
            f"Generate the complete fixed file:"
        )

        if emitter:
            await emitter.emit(
                agent_name=self.AGENT_NAME,
                event_type="progress",
                message=f"Generating fix for {target_file}",
                details={"stage": "generating"},
            )

        response = await self.llm_client.chat(
            prompt=user_prompt,
            system=system_prompt,
            max_tokens=8192,
        )

        fixed_code = response.text

        # Strip markdown fences if present (handles any language tag)
        import re
        fence_match = re.search(r'```\w*\n(.*?)```', fixed_code, re.DOTALL)
        if fence_match:
            fixed_code = fence_match.group(1)
        elif "```" in fixed_code:
            parts = fixed_code.split("```")
            if len(parts) >= 3:
                # Strip optional language tag from first line
                content = parts[1]
                first_newline = content.find('\n')
                if first_newline != -1 and content[:first_newline].strip().isalpha():
                    content = content[first_newline + 1:]
                fixed_code = content

        logger.info("Fix generated for %s (%d chars)", target_file, len(fixed_code.strip()))
        return fixed_code.strip()

    # =========================================================================
    # PHASE 2: ACTION (On-Demand)
    # =========================================================================

    async def execute_pr_creation(
        self,
        session_id: str,
        pr_data: Dict[str, Any],
        github_token: str,
    ) -> Dict[str, Any]:
        """
        Execute Phase 2: PR Creation

        Called when user clicks "Create PR" button in UI.

        Args:
            session_id: Unique session identifier
            pr_data: PR data from Phase 1
            github_token: GitHub authentication token

        Returns:
            {"html_url": str, "number": int}
        """
        logger.info("\n" + "=" * 80)
        logger.info("AGENT 3: PHASE 2 - ACTION")
        logger.info("=" * 80)

        await self._emit_progress("pushing", "Pushing branch to GitHub...")

        branch_name = pr_data["branch_name"]
        self._push_branch(branch_name)

        await self._emit_progress("creating_pr", "Creating pull request...")

        pr_result = self._create_github_pr(
            branch_name, pr_data["pr_title"], pr_data["pr_body"], github_token
        )

        logger.info(f"\nPHASE 2 COMPLETE")
        logger.info(f"   PR #{pr_result['number']}: {pr_result['html_url']}")
        logger.info("=" * 80 + "\n")

        return pr_result

    # =========================================================================
    # STATE HELPERS
    # =========================================================================

    def _build_agent1_context(self, state: DiagnosticState) -> Dict[str, Any]:
        """Extract agent1-style context dict from DiagnosticState."""
        ctx: Dict[str, Any] = {
            "incident_id": state.session_id,
            "bug_id": "auto",
            "diagnostic_summary": "",
            "filePath": "",
            "lineNumber": "",
            "functionName": "",
            "preliminaryRca": "",
            "severity": "medium",
        }

        if state.log_analysis:
            pattern = state.log_analysis.primary_pattern
            ctx["diagnostic_summary"] = pattern.error_message
            ctx["preliminaryRca"] = (
                f"{pattern.exception_type}: {pattern.error_message}"
            )
            ctx["severity"] = pattern.severity

        if state.code_analysis:
            loc = state.code_analysis.root_cause_location
            ctx["filePath"] = loc.file_path
            ctx["functionName"] = loc.relationship
            if loc.relevant_lines:
                ctx["lineNumber"] = str(loc.relevant_lines[0].start)

        return ctx

    def _build_agent2_context(self, state: DiagnosticState) -> Dict[str, Any]:
        """Extract agent2-style context dict from DiagnosticState."""
        ctx: Dict[str, Any] = {
            "recommended_fix": "",
            "root_cause_explanation": "",
            "call_chain": [],
            "confidence_score": state.overall_confidence / 100.0,
        }

        if state.code_analysis:
            ctx["call_chain"] = state.code_analysis.call_chain
            if state.code_analysis.suggested_fix_areas:
                fixes = state.code_analysis.suggested_fix_areas
                ctx["recommended_fix"] = "; ".join(
                    f"{f.file_path}: {f.description}" for f in fixes
                )

        # Aggregate findings into root cause explanation
        if state.all_findings:
            ctx["root_cause_explanation"] = " | ".join(
                f.summary for f in state.all_findings[:3]
            )

        return ctx

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _read_original_file(self, file_path: str) -> str:
        """Read original file content with path containment check."""
        normalized_path = file_path.lstrip("/")
        for prefix in ["app/", "usr/src/app/"]:
            if normalized_path.startswith(prefix):
                normalized_path = normalized_path[len(prefix):]

        full_path = (self.repo_path / normalized_path).resolve()

        # Ensure path stays within repo directory
        if not full_path.is_relative_to(self.repo_path.resolve()):
            raise ValueError(f"Path traversal blocked: {file_path} resolves outside repo")

        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {full_path}")

        with open(full_path, "r") as f:
            return f.read()

    def _generate_diff(self, original: str, fixed: str) -> str:
        """Generate unified diff."""
        import difflib

        diff = difflib.unified_diff(
            original.splitlines(keepends=True),
            fixed.splitlines(keepends=True),
            fromfile="original.py",
            tofile="fixed.py",
        )
        return "".join(diff)

    def _push_branch(self, branch_name: str) -> None:
        """Push branch to remote."""
        import subprocess
        from src.utils.repo_manager import _sanitize_stderr

        result = subprocess.run(
            ["git", "push", "-u", "origin", branch_name],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise Exception(f"Failed to push branch: {_sanitize_stderr(result.stderr)}")

    def _create_github_pr(
        self, branch: str, title: str, body: str, token: str
    ) -> Dict[str, Any]:
        """Create PR via GitHub API."""
        import requests
        import subprocess

        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise Exception("Failed to get git remote")

        remote_url = result.stdout.strip()
        if "github.com" in remote_url:
            parts = remote_url.split("github.com")[-1].strip(":/")
            repo_path = parts.replace(".git", "")
        else:
            raise Exception("Not a GitHub repository")

        # Detect default branch from GitHub API instead of hardcoding "main"
        default_branch = "main"
        try:
            repo_resp = requests.get(
                f"https://api.github.com/repos/{repo_path}",
                headers={
                    "Authorization": f"token {token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=10,
            )
            if repo_resp.status_code == 200:
                default_branch = repo_resp.json().get("default_branch", "main")
        except Exception:
            pass  # Fall back to "main" if detection fails

        response = requests.post(
            f"https://api.github.com/repos/{repo_path}/pulls",
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={
                "title": title,
                "body": body,
                "head": branch,
                "base": default_branch,
            },
        )

        if response.status_code != 201:
            raise Exception(
                f"Failed to create PR: {response.status_code} - {response.text}"
            )

        pr_data = response.json()
        return {"html_url": pr_data["html_url"], "number": pr_data["number"]}

    async def _self_correct(
        self, code: str, validation: Dict[str, Any]
    ) -> str:
        """
        Attempt to auto-correct validation issues using AnthropicClient.
        """
        logger.info("\nSelf-correcting validation issues...")

        errors = []
        if not validation["syntax"]["valid"]:
            errors.append(f"Syntax error: {validation['syntax']['error']}")
        linting_errors = validation.get("linting", {}).get("issues", {}).get("errors")
        if linting_errors:
            for error in linting_errors[:3]:
                errors.append(f"Linting error: {error}")

        system_prompt = (
            "You are a code fixer. Fix ONLY the syntax/linting errors. "
            "Output ONLY the corrected code, no explanation."
        )

        user_prompt = (
            f"Code with errors:\n```python\n{code}\n```\n\n"
            f"Errors to fix:\n{chr(10).join(errors)}\n\n"
            f"Output corrected code:"
        )

        response = await self.llm_client.chat(
            prompt=user_prompt,
            system=system_prompt,
            max_tokens=4096,
        )

        corrected = response.text
        import re as _re
        _fence_match = _re.search(r'```\w*\n(.*?)```', corrected, _re.DOTALL)
        if _fence_match:
            corrected = _fence_match.group(1)
        elif "```" in corrected:
            parts = corrected.split("```")
            if len(parts) >= 3:
                content = parts[1]
                first_nl = content.find('\n')
                if first_nl != -1 and content[:first_nl].strip().isalpha():
                    content = content[first_nl + 1:]
                corrected = content

        logger.info("   Self-correction attempted")
        return corrected.strip()

    async def _emit_progress(self, stage: str, message: str) -> None:
        """Emit progress event via EventEmitter."""
        if self.event_emitter:
            await self.event_emitter.emit(
                agent_name=self.AGENT_NAME,
                event_type="progress",
                message=message,
                details={"stage": stage},
            )
