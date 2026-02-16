from src.integrations.probe import run_command


class DiscoveryFallback:
    def __init__(self, cli_tool: str, cluster_url: str, token: str):
        self.cli = cli_tool
        self.url = cluster_url
        self.token = token

    def _base_args(self) -> str:
        return f"--server={self.url} --token={self.token} --insecure-skip-tls-verify"

    async def discover_namespaces(self) -> list[str]:
        code, stdout, _ = await run_command(
            f"{self.cli} get namespaces -o jsonpath='{{.items[*].metadata.name}}' {self._base_args()}"
        )
        if code != 0:
            return []
        return [ns.strip() for ns in stdout.replace("'", "").split() if ns.strip()]

    async def discover_error_pods(self, namespace: str) -> list[dict]:
        code, stdout, _ = await run_command(
            f"{self.cli} get pods -n {namespace} "
            f"--field-selector=status.phase!=Running,status.phase!=Succeeded "
            f"-o custom-columns=NAME:.metadata.name,STATUS:.status.phase --no-headers "
            f"{self._base_args()}"
        )
        if code != 0:
            return []
        pods = []
        for line in stdout.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 2:
                pods.append({"name": parts[0], "status": parts[1]})
        return pods

    async def get_pod_logs(self, pod_name: str, namespace: str, tail: int = 200) -> str:
        code, stdout, _ = await run_command(
            f"{self.cli} logs {pod_name} -n {namespace} --tail={tail} {self._base_args()}"
        )
        return stdout if code == 0 else ""
