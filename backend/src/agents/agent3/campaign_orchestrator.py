"""
Campaign Orchestrator: Multi-repo fix generation coordinator.

Delegates to existing Agent3FixGenerator per repo, managing the lifecycle
of each repo's fix through cloning, generation, review, and PR creation.
"""

import os
import tempfile
from typing import Optional, Any

from src.models.campaign import RemediationCampaign, CampaignRepoFix, CampaignRepoStatus
from src.models.schemas import DiagnosticState, FixedFile
from src.utils.event_emitter import EventEmitter
from src.utils.logger import get_logger

logger = get_logger(__name__)


class CampaignOrchestrator:
    """Coordinates multi-repo fix generation across a remediation campaign."""

    def __init__(self, llm_client: Any, event_emitter: EventEmitter, connection_config: Any = None):
        self.llm_client = llm_client
        self.event_emitter = event_emitter
        self.connection_config = connection_config
        self.repo_agents: dict[str, Any] = {}  # repo_url → Agent3FixGenerator
        self.repo_paths: dict[str, str] = {}   # repo_url → cloned tmp path

    async def run_campaign(self, state: DiagnosticState, campaign: RemediationCampaign) -> None:
        """Sequential fix generation across repos."""
        campaign.overall_status = "in_progress"
        self._emit_campaign_update(campaign)

        for repo_url, repo_fix in campaign.repos.items():
            try:
                # 1. Clone repo
                repo_fix.status = CampaignRepoStatus.CLONING
                self._emit_campaign_update(campaign)
                cloned_path = await self._clone_repo(repo_url, state.session_id)
                repo_fix.cloned_path = cloned_path
                self.repo_paths[repo_url] = cloned_path

                # 2. Create per-repo Agent3 instance
                from src.agents.agent3.fix_generator import Agent3FixGenerator
                agent3 = Agent3FixGenerator(
                    repo_path=cloned_path,
                    llm_client=self.llm_client,
                    event_emitter=self.event_emitter,
                )
                self.repo_agents[repo_url] = agent3

                # 3. Generate fixes
                repo_fix.status = CampaignRepoStatus.GENERATING
                self._emit_campaign_update(campaign)
                generated_fixes = await agent3.generate_fix(state, "", self.event_emitter)

                # 4. Build per-repo fix data
                fixed_files_data: list[dict] = []
                combined_diffs: list[str] = []
                for fp, fixed_code in generated_fixes.items():
                    try:
                        orig, resolved = agent3._read_original_file(fp)
                        if resolved != fp:
                            fp = resolved
                    except (FileNotFoundError, ValueError):
                        orig = ""
                    d = agent3._generate_diff(orig, fixed_code)
                    fixed_files_data.append({
                        "file_path": fp,
                        "diff": d,
                        "original_code": orig,
                        "fixed_code": fixed_code,
                    })
                    combined_diffs.append(f"--- {fp} ---\n{d}")

                repo_fix.fixed_files = fixed_files_data
                repo_fix.target_files = list(generated_fixes.keys())
                repo_fix.diff = "\n".join(combined_diffs)
                repo_fix.fix_explanation = self._build_fix_explanation(repo_fix, state)
                repo_fix.status = CampaignRepoStatus.AWAITING_REVIEW
                self._emit_campaign_update(campaign)

                # 5. Emit chat message for this repo's fix
                await self._emit_fix_proposal_chat(repo_fix, campaign)

            except Exception as e:
                logger.error("Campaign fix generation failed for %s: %s", repo_url, e, exc_info=True)
                repo_fix.status = CampaignRepoStatus.ERROR
                repo_fix.error_message = str(e)
                self._emit_campaign_update(campaign)

        campaign.overall_status = "awaiting_approvals"
        self._emit_campaign_update(campaign)

    async def approve_repo(self, campaign: RemediationCampaign, repo_url: str, state: DiagnosticState) -> None:
        """Mark a repo as approved."""
        repo_fix = campaign.repos.get(repo_url)
        if not repo_fix:
            return
        repo_fix.status = CampaignRepoStatus.APPROVED
        campaign.approved_count = sum(
            1 for r in campaign.repos.values()
            if r.status in (CampaignRepoStatus.APPROVED, CampaignRepoStatus.PR_CREATED)
        )
        self._emit_campaign_update(campaign)

    async def reject_repo(self, campaign: RemediationCampaign, repo_url: str) -> None:
        """Mark a repo as rejected."""
        repo_fix = campaign.repos.get(repo_url)
        if not repo_fix:
            return
        repo_fix.status = CampaignRepoStatus.REJECTED
        self._emit_campaign_update(campaign)

    async def revoke_repo(self, campaign: RemediationCampaign, repo_url: str) -> None:
        """Revoke attestation — return approved repo back to awaiting_review."""
        repo_fix = campaign.repos.get(repo_url)
        if not repo_fix:
            return
        if repo_fix.status == CampaignRepoStatus.APPROVED:
            repo_fix.status = CampaignRepoStatus.AWAITING_REVIEW
            campaign.approved_count = sum(
                1 for r in campaign.repos.values()
                if r.status in (CampaignRepoStatus.APPROVED, CampaignRepoStatus.PR_CREATED)
            )
            self._emit_campaign_update(campaign)

    async def execute_campaign(
        self, campaign: RemediationCampaign, state: DiagnosticState
    ) -> dict:
        """
        Master Gate: coordinated PR creation + merge in topological order.
        Only callable when all repos are approved.
        Returns {status, merged_prs, failed_repos}.
        """
        merged_prs: list[dict] = []
        failed_repos: list[str] = []

        # Order: root_cause first, then cascading, then correlated
        role_priority = {"root_cause": 0, "cascading": 1, "correlated": 2}
        ordered_repos = sorted(
            campaign.repos.items(),
            key=lambda kv: role_priority.get(kv[1].causal_role, 2),
        )

        token = self._get_github_token()

        for repo_url, repo_fix in ordered_repos:
            if repo_fix.status not in (CampaignRepoStatus.APPROVED, CampaignRepoStatus.PR_CREATED):
                continue
            try:
                agent3 = self.repo_agents.get(repo_url)
                if not agent3:
                    failed_repos.append(repo_url)
                    continue

                # Run verification phase if not already done
                if repo_fix.status == CampaignRepoStatus.APPROVED:
                    generated_fixes = {
                        f["file_path"]: f["fixed_code"]
                        for f in repo_fix.fixed_files
                    }
                    pr_data = await agent3.run_verification_phase(state, generated_fixes)

                    # Create PR
                    pr_result = await agent3.create_pr(
                        branch_name=pr_data.get("branch_name", ""),
                        pr_title=pr_data.get("pr_title", ""),
                        pr_body=pr_data.get("pr_body", ""),
                        token=token,
                    )
                    repo_fix.pr_url = pr_result.get("pr_url", "")
                    repo_fix.pr_number = pr_result.get("pr_number")
                    repo_fix.branch_name = pr_data.get("branch_name", "")
                    repo_fix.status = CampaignRepoStatus.PR_CREATED

                merged_prs.append({
                    "repo_url": repo_url,
                    "service_name": repo_fix.service_name,
                    "pr_url": repo_fix.pr_url,
                    "pr_number": repo_fix.pr_number,
                    "merge_status": "created",
                })
            except Exception as e:
                logger.error("Campaign PR creation failed for %s: %s", repo_url, e, exc_info=True)
                repo_fix.status = CampaignRepoStatus.ERROR
                repo_fix.error_message = str(e)
                failed_repos.append(repo_url)

        if failed_repos:
            campaign.overall_status = "partial_failure"
            status = "partial_failure"
        else:
            campaign.overall_status = "completed"
            status = "executed"

        self._emit_campaign_update(campaign)
        return {"status": status, "merged_prs": merged_prs, "failed_repos": failed_repos}

    # ── Private helpers ──────────────────────────────────────────────────

    async def _clone_repo(self, repo_url: str, session_id: str) -> str:
        """Clone a repository to a temp directory."""
        from src.utils.repo_manager import RepoManager

        token = self._get_github_token()
        owner_repo = self._parse_owner_repo(repo_url)
        if not owner_repo:
            raise ValueError(f"Cannot parse repo URL: {repo_url}")

        tmp_path = tempfile.mkdtemp(prefix=f"campaign_{session_id[:8]}_")
        clone_result = RepoManager.clone_repo(owner_repo, tmp_path, shallow=False, token=token)
        if not clone_result["success"]:
            raise RuntimeError(f"Clone failed for {repo_url}: {clone_result.get('error', 'unknown')}")
        return tmp_path

    def _parse_owner_repo(self, repo_url: str) -> Optional[str]:
        """Extract owner/repo from a GitHub URL."""
        import re
        patterns = [
            r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$",
            r"^([^/]+/[^/]+)$",
        ]
        for pat in patterns:
            m = re.search(pat, repo_url)
            if m:
                return m.group(1)
        return None

    def _get_github_token(self) -> str:
        token = ""
        if self.connection_config and hasattr(self.connection_config, "github_token"):
            token = self.connection_config.github_token or ""
        if not token:
            token = os.getenv("GITHUB_TOKEN", "")
        return token

    def _build_fix_explanation(self, repo_fix: CampaignRepoFix, state: DiagnosticState) -> str:
        """Build a human-readable fix explanation for a repo."""
        parts = [f"Fix for {repo_fix.service_name}"]
        if repo_fix.causal_role:
            parts.append(f"(role: {repo_fix.causal_role})")
        parts.append(f"— {len(repo_fix.fixed_files)} file(s) modified")
        return " ".join(parts)

    def _emit_campaign_update(self, campaign: RemediationCampaign) -> None:
        """Emit campaign state via WebSocket (fire-and-forget)."""
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.event_emitter.emit(
                "campaign_orchestrator", "campaign_update",
                f"Campaign {campaign.campaign_id}: {campaign.overall_status}",
                details={
                    "campaign_id": campaign.campaign_id,
                    "overall_status": campaign.overall_status,
                    "approved_count": campaign.approved_count,
                    "total_count": campaign.total_count,
                    "repos": {
                        url: {
                            "status": fix.status.value,
                            "service_name": fix.service_name,
                            "causal_role": fix.causal_role,
                            "diff": fix.diff[:500] if fix.diff else "",
                            "fix_explanation": fix.fix_explanation,
                            "pr_url": fix.pr_url,
                            "pr_number": fix.pr_number,
                            "error_message": fix.error_message,
                            "fixed_files": [f.get("file_path", "") for f in fix.fixed_files],
                        }
                        for url, fix in campaign.repos.items()
                    },
                },
            ))
        except RuntimeError:
            pass

    async def _emit_fix_proposal_chat(
        self, repo_fix: CampaignRepoFix, campaign: RemediationCampaign
    ) -> None:
        """Emit a chat message for a completed repo fix proposal via WebSocket."""
        from datetime import datetime, timezone
        if self.event_emitter._websocket_manager:
            await self.event_emitter._websocket_manager.send_message(
                campaign.session_id,
                {
                    "type": "chat_response",
                    "data": {
                        "role": "assistant",
                        "content": f"Fix ready for **{repo_fix.service_name}** ({repo_fix.repo_url}). Review the changes below.",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "metadata": {
                            "type": "campaign_fix_proposal",
                            "repo_url": repo_fix.repo_url,
                            "service_name": repo_fix.service_name,
                            "causal_role": repo_fix.causal_role,
                            "fix_explanation": repo_fix.fix_explanation,
                            "fixed_files": [f.get("file_path", "") for f in repo_fix.fixed_files],
                        },
                    },
                },
            )
