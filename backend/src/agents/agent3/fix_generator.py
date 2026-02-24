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
        generated_fixes: dict[str, str] | str,
        verification_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute Phase 1: Verification for one or more files.

        Steps:
        1. Static validation (AST, linting, imports) per file
        2. PR staging (local branch + commit for all files)
        3. Prepare PR data

        Code review and impact assessment are handled upstream by
        _verify_fix_with_code_agent() — results passed via verification_result.

        Args:
            state: DiagnosticState with session context and agent results
            generated_fixes: dict[file_path → fixed_code] or single string (backward compat)
            verification_result: Output from code_agent verification

        Returns:
            PR data for user review
        """
        logger.info("\n" + "=" * 80)
        logger.info("AGENT 3: PHASE 1 - VERIFICATION")
        logger.info("=" * 80)

        # Normalize to dict (backward compat: single string → primary file)
        if isinstance(generated_fixes, str):
            primary_file = self._resolve_target_file(state)
            fixes = {primary_file: generated_fixes}
        else:
            fixes = generated_fixes

        # Build context dicts from state for downstream components
        agent1_analysis = self._build_agent1_context(state)
        agent2_analysis = self._build_agent2_context(state)

        # ---- STEP 1: STATIC VALIDATION (per file) ----

        await self._emit_progress("validation", f"Validating {len(fixes)} file(s)...")

        all_passed = True
        for fp, code in list(fixes.items()):
            validation = self.validator.validate_all(fp, code)
            if not validation["passed"]:
                logger.info("Validation failed for %s, attempting self-correction...", fp)
                code = await self._self_correct(code, validation)
                fixes[fp] = code
                validation = self.validator.validate_all(fp, code)
                if not validation["passed"]:
                    all_passed = False

        # Use primary file's validation for PR template
        primary_file = list(fixes.keys())[0]
        primary_code = fixes[primary_file]
        validation_result_static = self.validator.validate_all(primary_file, primary_code)
        validation_result_static["passed"] = all_passed

        # Merge code_agent verification into validation for PR template
        vr = verification_result or {}
        validation_result_static["agent2_approved"] = vr.get("verdict", "approve") != "reject"
        validation_result_static["agent2_confidence"] = (vr.get("confidence", 75)) / 100.0

        # Build impact report from code_agent verification (no separate LLM call)
        impact_report = {
            "side_effects": vr.get("suggestions", []),
            "security_review": "Reviewed by code agent" if vr else "No review available",
            "regression_risk": "High" if vr.get("regression_risks") else "Low",
            "affected_functions": [],
            "diff_lines": 0,
            "files_changed": len(fixes),
        }
        if vr.get("issues_found"):
            impact_report["side_effects"] = vr["issues_found"] + vr.get("suggestions", [])
        if vr.get("regression_risks"):
            impact_report["side_effects"] += [f"Regression risk: {r}" for r in vr["regression_risks"]]

        # ---- STEP 2: PR STAGING (all files) ----

        await self._emit_progress("staging", f"Staging {len(fixes)} file(s) for PR...")

        # Read originals and resolve paths for all files
        file_diffs: dict[str, str] = {}
        total_diff_lines = 0
        resolved_fixes: dict[str, str] = {}

        for fp, code in fixes.items():
            try:
                original_code, resolved_path = self._read_original_file(fp)
                if resolved_path != fp:
                    logger.info("Resolved staging path: %s → %s", fp, resolved_path)
                    fp = resolved_path
            except (FileNotFoundError, ValueError):
                original_code = ""
            resolved_fixes[fp] = code
            diff = self._generate_diff(original_code, code)
            file_diffs[fp] = diff
            total_diff_lines += len(diff.splitlines())

        branch_name = self.stager.create_branch(
            agent1_analysis.get("incident_id", "incident"),
            agent1_analysis.get("bug_id", "bug"),
        )

        for fp, code in resolved_fixes.items():
            self.stager.stage_changes(fp, code)

        commit_sha = self.stager.create_commit(
            agent1_analysis.get("incident_id", "incident"),
            agent1_analysis.get("bug_id", "bug"),
            agent1_analysis,
            agent2_analysis,
        )

        # Combine diffs for display
        combined_diff = "\n".join(
            f"--- {fp} ---\n{d}" for fp, d in file_diffs.items()
        )
        impact_report["diff_lines"] = total_diff_lines

        pr_body = self.stager.generate_pr_template(
            agent1_analysis, agent2_analysis, impact_report, validation_result_static
        )

        # ---- STEP 3: PREPARE PR DATA ----

        summary = agent1_analysis.get("diagnostic_summary", "Fix issue")[:60]
        file_list = list(resolved_fixes.keys())
        pr_data = {
            "branch_name": branch_name,
            "commit_sha": commit_sha,
            "pr_title": f"fix: {summary}",
            "pr_body": pr_body,
            "diff": combined_diff,
            "file_diffs": file_diffs,
            "validation": validation_result_static,
            "impact": impact_report,
            "fixed_files": file_list,
            "fixed_code": primary_code,  # backward compat
            "status": "awaiting_approval",
            "token_usage": self.llm_client.get_total_usage().model_dump(),
        }

        # ---- STEP 4: NOTIFY ----

        await self._emit_progress(
            "verification_complete",
            f"Verification complete. Branch: {branch_name} ({len(file_list)} file(s))",
        )

        logger.info(f"\nPHASE 1 COMPLETE")
        logger.info(f"   Branch: {branch_name}")
        logger.info(f"   Commit: {commit_sha[:7]}")
        logger.info(f"   Files: {', '.join(file_list)}")
        logger.info(f"   Validation: {'Passed' if validation_result_static['passed'] else 'Issues'}")
        logger.info(f"   Code agent verdict: {vr.get('verdict', 'N/A')}")
        logger.info(f"   Awaiting user approval...")
        logger.info("=" * 80 + "\n")

        return pr_data

    # =========================================================================
    # FULL-CONTEXT FIX GENERATION
    # =========================================================================

    def _collect_fix_targets(self, state) -> list[str]:
        """Collect all unique file paths that need fixing from diagnostic evidence.

        Gathers files from suggested_fix_areas, must_fix impacted_files, and
        the root_cause_location, deduplicates, and returns in priority order
        (root cause first).
        """
        seen: set[str] = set()
        targets: list[str] = []

        def _add(fp: str) -> None:
            if fp and fp != "unknown" and fp not in seen:
                seen.add(fp)
                targets.append(fp)

        # Root cause file first
        if state.code_analysis and state.code_analysis.root_cause_location:
            _add(state.code_analysis.root_cause_location.file_path)

        # All suggested fix areas
        if state.code_analysis:
            for fa in (state.code_analysis.suggested_fix_areas or []):
                _add(fa.file_path)

        # Must-fix impacted files
        if state.code_analysis:
            for imp in (state.code_analysis.impacted_files or []):
                if imp.fix_relevance == "must_fix":
                    _add(imp.file_path)

        return targets

    async def generate_fix(
        self,
        state: DiagnosticState,
        human_guidance: str = "",
        event_emitter: Optional[EventEmitter] = None,
    ) -> dict[str, str]:
        """
        Generate fixes for ALL affected files using a single LLM call.

        Builds a comprehensive LLM prompt from log, metrics, k8s, trace,
        code, and change analysis. Returns dict of file_path → fixed_code.
        """
        emitter = event_emitter or self.event_emitter

        # Collect all files that need fixing
        target_files = self._collect_fix_targets(state)
        if not target_files:
            # Fallback: resolve single target from broader evidence
            single = self._resolve_target_file(state)
            if single and single != "unknown":
                target_files = [single]
            else:
                raise ValueError("No target files identified in code analysis")

        # Read original code for each target file
        file_originals: dict[str, str] = {}  # resolved_path → original_code
        resolved_targets: list[str] = []     # resolved paths in order
        repo_context = ""
        for tf in target_files:
            try:
                original_code, resolved_path = self._read_original_file(tf)
                file_originals[resolved_path] = original_code
                if resolved_path not in resolved_targets:
                    resolved_targets.append(resolved_path)
                # Update state with resolved path
                if resolved_path != tf and state.code_analysis:
                    if state.code_analysis.root_cause_location and state.code_analysis.root_cause_location.file_path == tf:
                        state.code_analysis.root_cause_location.file_path = resolved_path
                    for fa in (state.code_analysis.suggested_fix_areas or []):
                        if fa.file_path == tf:
                            fa.file_path = resolved_path
            except FileNotFoundError:
                logger.warning("Target file not found in repo: %s", tf)
                if not repo_context:
                    repo_context = self._build_repo_context(tf)
                # Keep original name — LLM will identify from repo context
                if tf not in resolved_targets:
                    resolved_targets.append(tf)

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

        is_multi = len(resolved_targets) > 1

        if is_multi:
            system_prompt = (
                "You are an expert SRE generating production-ready code fixes. "
                "Given a comprehensive incident analysis, generate fixes for ALL affected files. "
                "Output each file using this exact format:\n\n"
                "### FILE: path/to/file.py\n"
                "<complete fixed source code>\n\n"
                "### FILE: path/to/other.py\n"
                "<complete fixed source code>\n\n"
                "Output ONLY the file markers and code — no explanations, no markdown fences."
            )
        else:
            system_prompt = (
                "You are an expert SRE generating production-ready code fixes. "
                "Given a comprehensive incident analysis and recommendations from 6 diagnostic agents, "
                "generate the complete fixed file. Output ONLY the complete fixed source code — "
                "no markdown fences, no explanations, no comments about what changed."
            )

        # Build user prompt with all target files
        file_sections = []
        for fp in resolved_targets:
            orig = file_originals.get(fp, "")
            if orig:
                file_sections.append(f"### File: `{fp}`\n```\n{orig}\n```")
            else:
                file_sections.append(f"### File: `{fp}` (not found in repo — identify from repo context)")

        files_text = "\n\n".join(file_sections)

        if repo_context:
            user_prompt = (
                f"## Target Files\n{files_text}\n\n"
                f"**Some files were not found in the cloned repo.** "
                f"The full repository contents are provided below.\n\n"
                f"{repo_context}\n\n"
                f"## Diagnostic Evidence\n{evidence_text}\n\n"
                f"Generate the complete fixed version of each file:"
            )
        else:
            user_prompt = (
                f"## Target Files\n{files_text}\n\n"
                f"## Diagnostic Evidence\n{evidence_text}\n\n"
                f"Generate the complete fixed version of {'each file' if is_multi else 'the file'}:"
            )

        file_list = ", ".join(resolved_targets)
        if emitter:
            await emitter.emit(
                agent_name=self.AGENT_NAME,
                event_type="progress",
                message=f"Generating fix for {file_list}",
                details={"stage": "generating", "file_count": len(resolved_targets)},
            )

        response = await self.llm_client.chat(
            prompt=user_prompt,
            system=system_prompt,
            max_tokens=16384 if is_multi else 8192,
        )

        raw_output = response.text

        # Parse output into per-file fixes
        fixes = self._parse_multi_file_output(raw_output, resolved_targets, is_multi)

        logger.info("Fix generated for %d files (%s)", len(fixes),
                     ", ".join(f"{k}: {len(v)} chars" for k, v in fixes.items()))
        return fixes

    @staticmethod
    def _parse_multi_file_output(
        raw: str, expected_files: list[str], is_multi: bool
    ) -> dict[str, str]:
        """Parse LLM output into per-file fixed code.

        For multi-file output, expects `### FILE: path` markers.
        For single-file output, returns the whole output keyed to the one file.
        """
        import re

        def _strip_fences(code: str) -> str:
            """Remove markdown fences if present."""
            fence_match = re.search(r'```\w*\n(.*?)```', code, re.DOTALL)
            if fence_match:
                return fence_match.group(1).strip()
            if "```" in code:
                parts = code.split("```")
                if len(parts) >= 3:
                    content = parts[1]
                    first_nl = content.find('\n')
                    if first_nl != -1 and content[:first_nl].strip().isalpha():
                        content = content[first_nl + 1:]
                    return content.strip()
            return code.strip()

        if not is_multi or len(expected_files) == 1:
            return {expected_files[0]: _strip_fences(raw)}

        # Split on ### FILE: markers
        sections = re.split(r'###\s*FILE:\s*', raw, flags=re.IGNORECASE)
        fixes: dict[str, str] = {}

        for section in sections:
            section = section.strip()
            if not section:
                continue
            # First line is the file path (may have backticks)
            first_nl = section.find('\n')
            if first_nl == -1:
                continue
            file_path = section[:first_nl].strip().strip('`').strip()
            code = section[first_nl + 1:]

            # Match to expected files (exact or basename match)
            matched = None
            for ef in expected_files:
                if ef == file_path or ef.endswith(file_path) or file_path.endswith(ef):
                    matched = ef
                    break
            if not matched:
                # Try basename matching
                from pathlib import Path
                for ef in expected_files:
                    if Path(ef).name == Path(file_path).name:
                        matched = ef
                        break
            if matched:
                fixes[matched] = _strip_fences(code)

        # If parsing failed, fall back: assign full output to primary file
        if not fixes:
            logger.warning("Multi-file parsing failed, assigning full output to primary file")
            fixes[expected_files[0]] = _strip_fences(raw)

        return fixes

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

    def _resolve_target_file(self, state) -> str:
        """Resolve actual target file path from multiple evidence sources.

        When the code_agent fails to return a proper file_path (defaulting to
        "unknown"), we try progressively less-specific sources to find it.
        """
        # Priority 1: root_cause_location.file_path
        if state.code_analysis and state.code_analysis.root_cause_location:
            fp = state.code_analysis.root_cause_location.file_path
            if fp and fp != "unknown":
                return fp

        # Priority 2: suggested_fix_areas (code_agent's targeted fix suggestions)
        if state.code_analysis and state.code_analysis.suggested_fix_areas:
            for fa in state.code_analysis.suggested_fix_areas:
                if fa.file_path and fa.file_path != "unknown":
                    return fa.file_path

        # Priority 3: impacted_files (code_agent's broader impact analysis)
        if state.code_analysis and state.code_analysis.impacted_files:
            for imp in state.code_analysis.impacted_files:
                if imp.file_path and imp.file_path != "unknown" and imp.fix_relevance == "must_fix":
                    return imp.file_path
            # If none are must_fix, take first non-unknown
            for imp in state.code_analysis.impacted_files:
                if imp.file_path and imp.file_path != "unknown":
                    return imp.file_path

        # Priority 4: extract file paths from stack traces
        if state.log_analysis and state.log_analysis.primary_pattern:
            import re
            for trace in (state.log_analysis.primary_pattern.stack_traces or []):
                # Match common stack trace file patterns: File "path.py", at path.py:123
                matches = re.findall(r'(?:File "([^"]+\.py)"|at\s+([^\s:]+\.\w+))', trace)
                for m in matches:
                    path = m[0] or m[1]
                    # Skip stdlib/framework paths
                    if path and not any(skip in path for skip in [
                        "site-packages", "/lib/python", "importlib", "<frozen",
                    ]):
                        return path

        return "unknown"

    def _read_original_file(self, file_path: str) -> tuple[str, str]:
        """Read original file content with path containment check.

        Handles container paths (/app/src/main.py) that don't match repo
        layout (backend/src/main.py) by falling back to a filename search.

        Returns:
            (file_content, resolved_relative_path) — the resolved path is the
            actual repo-relative path found on disk, which may differ from the
            input when container-path normalization or filename search was used.
        """
        normalized_path = file_path.lstrip("/")
        for prefix in ["app/", "usr/src/app/", "opt/app/", "home/app/"]:
            if normalized_path.startswith(prefix):
                normalized_path = normalized_path[len(prefix):]

        full_path = (self.repo_path / normalized_path).resolve()

        # Ensure path stays within repo directory
        if not full_path.is_relative_to(self.repo_path.resolve()):
            raise ValueError(f"Path traversal blocked: {file_path} resolves outside repo")

        if not full_path.exists():
            # Fallback: search repo for the filename (handles container→repo path mismatch)
            from pathlib import Path
            filename = Path(normalized_path).name
            if not filename or filename == "unknown":
                raise FileNotFoundError(f"File not found: {file_path} (no valid filename to search)")
            candidates = sorted(self.repo_path.rglob(filename))
            # Filter to files within repo and prefer shortest path (closest to root)
            candidates = [
                c for c in candidates
                if c.is_file() and c.resolve().is_relative_to(self.repo_path.resolve())
            ]
            if candidates:
                full_path = candidates[0]
            else:
                raise FileNotFoundError(f"File not found: {file_path} (searched repo for {filename})")

        resolved_relative = str(full_path.relative_to(self.repo_path))

        with open(full_path, "r") as f:
            return f.read(), resolved_relative

    def _build_repo_context(self, target_file: str, max_total_chars: int = 30000) -> str:
        """Build a repo file tree + source file contents for LLM context.

        When the target file path (from container runtime) doesn't match the
        cloned repo structure, we give the LLM the full picture so it can
        identify the correct file itself.

        Args:
            target_file: The file path we were looking for (for relevance scoring)
            max_total_chars: Budget for total source content to avoid token overflow
        """
        from pathlib import Path

        # Collect all files (skip .git, __pycache__, node_modules, .venv)
        skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv", ".tox", ".mypy_cache"}
        source_exts = {".py", ".java", ".go", ".js", ".ts", ".rb", ".rs", ".c", ".cpp", ".h", ".cs", ".kt", ".scala", ".yaml", ".yml", ".toml", ".json", ".cfg", ".ini"}

        all_files: list[Path] = []
        for p in sorted(self.repo_path.rglob("*")):
            # Skip hidden/build directories
            if any(part in skip_dirs for part in p.parts):
                continue
            if p.is_file():
                all_files.append(p)

        # Build tree listing (relative paths)
        tree_lines = ["## Repository File Tree"]
        for f in all_files:
            rel = f.relative_to(self.repo_path)
            tree_lines.append(f"  {rel}")
        tree_text = "\n".join(tree_lines)

        # Identify source files to include (prioritize by relevance to target)
        target_name = Path(target_file).name
        target_stem = Path(target_file).stem

        source_files: list[tuple[int, Path]] = []
        for f in all_files:
            if f.suffix.lower() not in source_exts:
                continue
            # Score: 0 = exact name match, 1 = stem match, 2 = same extension, 3 = other source
            if f.name == target_name:
                score = 0
            elif f.stem == target_stem:
                score = 1
            elif f.suffix == Path(target_file).suffix:
                score = 2
            else:
                score = 3
            source_files.append((score, f))

        source_files.sort(key=lambda x: (x[0], str(x[1])))

        # Read file contents within budget
        content_parts = ["## Repository Source Files"]
        chars_used = 0
        files_included = 0

        for _score, f in source_files:
            if chars_used >= max_total_chars:
                content_parts.append(f"\n... ({len(source_files) - files_included} more source files omitted due to size limit)")
                break
            try:
                text = f.read_text(errors="replace")
            except Exception:
                continue

            remaining = max_total_chars - chars_used
            if len(text) > remaining:
                text = text[:remaining] + "\n... (truncated)"

            rel = f.relative_to(self.repo_path)
            content_parts.append(f"\n### {rel}\n```\n{text}\n```")
            chars_used += len(text)
            files_included += 1

        logger.info("Built repo context: %d files in tree, %d source files included (%d chars)",
                     len(all_files), files_included, chars_used)

        return f"{tree_text}\n\n{''.join(content_parts)}"

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
