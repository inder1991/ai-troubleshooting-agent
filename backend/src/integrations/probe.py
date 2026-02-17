import asyncio
import shlex
from typing import Optional, Tuple
from pydantic import BaseModel, Field
from .models import IntegrationConfig


class EndpointProbeResult(BaseModel):
    """Result from probing a single endpoint."""
    name: str
    reachable: bool = False
    discovered_url: Optional[str] = None
    latency_ms: Optional[float] = None
    error: Optional[str] = None


class ProbeResult(BaseModel):
    reachable: bool = False
    prometheus_url: Optional[str] = None
    elasticsearch_url: Optional[str] = None
    cluster_version: Optional[str] = None
    errors: list[str] = []
    endpoint_results: dict[str, EndpointProbeResult] = Field(default_factory=dict)


async def run_command(cmd: str) -> Tuple[int, str, str]:
    proc = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await proc.communicate()
    return proc.returncode, stdout.decode().strip(), stderr.decode().strip()


def _safe_cli_args(server: str, token: str) -> str:
    """Build CLI args with shell-escaped values to prevent injection."""
    return f"--server={shlex.quote(server)} --token={shlex.quote(token)}"


class ClusterProbe:
    def get_cli_tool(self, cluster_type: str) -> str:
        return "oc" if cluster_type == "openshift" else "kubectl"

    async def probe(self, config: IntegrationConfig) -> ProbeResult:
        result = ProbeResult()
        cli = self.get_cli_tool(config.cluster_type)
        safe_args = _safe_cli_args(config.cluster_url, config.auth_data)

        if config.cluster_type == "openshift":
            # 1. Discover Prometheus via route
            code, stdout, stderr = await run_command(
                f"{cli} get route prometheus-k8s -n openshift-monitoring "
                f"{safe_args} "
                f"-o jsonpath='{{.spec.host}}' --insecure-skip-tls-verify"
            )
            ep_prom = EndpointProbeResult(name="openshift_api")
            if code != 0:
                if "Unable to connect" in stderr:
                    result.errors.append(stderr)
                    ep_prom.error = stderr
                    result.endpoint_results["openshift_api"] = ep_prom
                    return result  # reachable stays False
            else:
                result.reachable = True
                ep_prom.reachable = True
                host = stdout.strip("'")
                result.prometheus_url = f"https://{host}" if not host.startswith("http") else host
                ep_prom.discovered_url = result.prometheus_url

            result.endpoint_results["openshift_api"] = ep_prom

            # 2. Discover ELK
            ep_elk = EndpointProbeResult(name="elasticsearch")
            code, stdout, stderr = await run_command(
                f"{cli} get route kibana -n openshift-logging "
                f"{safe_args} "
                f"-o jsonpath='{{.spec.host}}' --insecure-skip-tls-verify"
            )
            if code == 0:
                host = stdout.strip("'")
                result.elasticsearch_url = f"https://{host}" if not host.startswith("http") else host
                ep_elk.reachable = True
                ep_elk.discovered_url = result.elasticsearch_url
            else:
                ep_elk.error = stderr or "Route not found"
            result.endpoint_results["elasticsearch"] = ep_elk

            # 3. Version
            code, stdout, stderr = await run_command(
                f"{cli} version {safe_args} "
                f"-o jsonpath='{{.openshiftVersion}}' --insecure-skip-tls-verify"
            )
            if code == 0:
                result.cluster_version = stdout.strip("'")

        else:  # kubernetes
            ep_api = EndpointProbeResult(name="kubernetes_api")
            code, stdout, stderr = await run_command(
                f"{cli} get svc prometheus-server -n monitoring "
                f"{safe_args} "
                f"-o jsonpath='{{.metadata.name}}.{{.metadata.namespace}}.svc.cluster.local' "
                f"--insecure-skip-tls-verify"
            )
            if code != 0 and "Unable to connect" in stderr:
                result.errors.append(stderr)
                ep_api.error = stderr
                result.endpoint_results["kubernetes_api"] = ep_api
                return result
            elif code == 0:
                result.reachable = True
                ep_api.reachable = True
                result.prometheus_url = f"http://{stdout}:9090"
            result.endpoint_results["kubernetes_api"] = ep_api

            ep_elk = EndpointProbeResult(name="elasticsearch")
            code, stdout, stderr = await run_command(
                f"{cli} get svc elasticsearch -n logging "
                f"{safe_args} "
                f"-o jsonpath='{{.metadata.name}}.{{.metadata.namespace}}.svc.cluster.local' "
                f"--insecure-skip-tls-verify"
            )
            if code == 0:
                result.elasticsearch_url = f"http://{stdout}:9200"
                ep_elk.reachable = True
                ep_elk.discovered_url = result.elasticsearch_url
            else:
                ep_elk.error = stderr or "Service not found"
            result.endpoint_results["elasticsearch"] = ep_elk

            code, stdout, stderr = await run_command(
                f"{cli} version {safe_args} "
                f"-o jsonpath='{{.serverVersion.gitVersion}}' --insecure-skip-tls-verify"
            )
            if code == 0:
                result.cluster_version = stdout.strip("'")

        return result


class GlobalProbe:
    """Test connectivity for global integrations (ELK, Jira, Confluence, Remedy)."""

    async def test_connection(
        self, service_type: str, url: str, auth_method: str, credentials: Optional[str] = None
    ) -> EndpointProbeResult:
        import httpx
        import time

        ep = EndpointProbeResult(name=service_type)
        if not url:
            ep.error = "No URL configured"
            return ep

        headers = self._build_auth_headers(auth_method, credentials)
        test_path = self._get_test_path(service_type)
        test_url = f"{url.rstrip('/')}{test_path}"

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
                resp = await client.get(test_url, headers=headers)
                ep.latency_ms = round((time.monotonic() - start) * 1000, 1)
                if resp.status_code < 400:
                    ep.reachable = True
                    ep.discovered_url = url
                else:
                    ep.error = f"HTTP {resp.status_code}"
        except httpx.ConnectError as e:
            ep.error = f"Connection failed: {e}"
        except httpx.TimeoutException:
            ep.error = "Connection timed out"
        except Exception as e:
            ep.error = str(e)

        return ep

    def _get_test_path(self, service_type: str) -> str:
        paths = {
            "elk": "/",
            "jira": "/rest/api/2/serverInfo",
            "confluence": "/rest/api/space",
            "remedy": "/api/arsys/v1",
        }
        return paths.get(service_type, "/")

    def _build_auth_headers(
        self, auth_method: str, credentials: Optional[str]
    ) -> dict:
        if not credentials:
            return {}
        if auth_method == "bearer_token":
            return {"Authorization": f"Bearer {credentials}"}
        if auth_method == "api_token":
            return {"Authorization": f"Bearer {credentials}"}
        if auth_method == "basic_auth":
            import base64
            encoded = base64.b64encode(credentials.encode()).decode()
            return {"Authorization": f"Basic {encoded}"}
        if auth_method == "cloud_id":
            return {"Authorization": f"Bearer {credentials}"}
        return {}
