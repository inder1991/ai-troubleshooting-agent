import json

from src.agents.react_base import ReActAgent
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ChangeAgent(ReActAgent):
    """Investigates recent changes that may correlate with a production incident."""

    def __init__(self):
        super().__init__(agent_name="change_agent", max_iterations=5)
        self._repo_url = ""
        self._namespace = ""
        self._incident_start = None
        self._cli_tool = "kubectl"

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
        ]

    async def _build_system_prompt(self) -> str:
        return (
            "You are a Change Intelligence agent investigating recent changes "
            "that may correlate with a production incident. Check GitHub commits, "
            "deployment history, and configuration changes. Score each change by "
            "temporal correlation and scope overlap with the incident."
        )

    async def _build_initial_prompt(self, context: dict) -> str:
        self._repo_url = context.get("repo_url", "")
        self._namespace = context.get("namespace", "default")
        self._incident_start = context.get("incident_start")
        self._cli_tool = context.get("cli_tool", "kubectl")
        return (
            f"Investigate recent changes for service in namespace '{self._namespace}'. "
            f"Repository: {self._repo_url or 'not specified'}. "
            f"Incident start: {self._incident_start or 'unknown'}. "
            f"Look for deployments, code changes, and config modifications in the last 24 hours."
        )

    async def _handle_tool_call(self, tool_name: str, tool_input: dict) -> str:
        if tool_name == "github_recent_commits":
            return await self._get_github_commits(tool_input)
        elif tool_name == "deployment_history":
            return await self._get_deployment_history(tool_input)
        elif tool_name == "config_diff":
            return await self._get_config_diff(tool_input)
        return f"Unknown tool: {tool_name}"

    async def _get_github_commits(self, params: dict) -> str:
        from src.integrations.probe import run_command
        import re as _re

        repo_url = params.get("repo_url", self._repo_url)
        since_hours = params.get("since_hours", 24)

        if not repo_url:
            return "No repository URL provided"

        owner_repo = self._parse_repo_url(repo_url)
        if not owner_repo:
            return f"Could not parse repository URL: {repo_url}"

        # Use gh api to fetch recent commits
        jq_expr = '[.[] | {sha: .sha[:8], author: .commit.author.name, date: .commit.author.date, message: .commit.message[:200]}]'
        cmd = f"gh api \"repos/{owner_repo}/commits?per_page=20\" --jq '{jq_expr}'"
        code, stdout, stderr = await run_command(cmd)

        return stdout if code == 0 else f"GitHub API error: {stderr}"

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

        ns = params.get("namespace", self._namespace)
        dep = params.get("deployment_name", "")
        if dep:
            cmd = f"{self._cli_tool} rollout history deployment/{dep} -n {ns}"
        else:
            cmd = f"{self._cli_tool} rollout history deployment -n {ns}"
        code, stdout, stderr = await run_command(cmd)
        return stdout if code == 0 else f"Error: {stderr}"

    async def _get_config_diff(self, params: dict) -> str:
        from src.integrations.probe import run_command

        ns = params.get("namespace", self._namespace)
        name = params.get("resource_name", "")
        if name:
            cmd = f"{self._cli_tool} get configmap {name} -n {ns} -o yaml"
        else:
            cmd = f"{self._cli_tool} get configmap -n {ns}"
        code, stdout, stderr = await run_command(cmd)
        return stdout if code == 0 else f"Error: {stderr}"

    def _parse_final_response(self, text: str) -> dict:
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            data = {}
        result = {
            "change_correlations": data.get("change_correlations", []),
            "summary": data.get("summary", text[:500] if text else "No changes found"),
            "breadcrumbs": [b.model_dump(mode="json") for b in self.breadcrumbs],
            "negative_findings": [n.model_dump(mode="json") for n in self.negative_findings],
            "tokens_used": self.get_token_usage().model_dump(),
        }
        logger.info("Change agent complete", extra={"agent_name": self.agent_name, "action": "complete", "extra": {"correlations": len(result["change_correlations"])}})
        return result
