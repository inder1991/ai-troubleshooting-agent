import asyncio
import os
import shlex
import tempfile
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


def _build_auth_args(server: str, auth_method: str, auth_data: str, kubeconfig_path: Optional[str] = None) -> str:
    """Build CLI args based on auth method.

    For kubeconfig: uses --kubeconfig=<path> + --server= (server overrides kubeconfig context).
    For token/service_account: uses --server= --token=.
    """
    if auth_method == "kubeconfig" and kubeconfig_path:
        return f"--kubeconfig={shlex.quote(kubeconfig_path)} --server={shlex.quote(server)}"
    # token and service_account both use --server + --token
    return f"--server={shlex.quote(server)} --token={shlex.quote(auth_data)}"


class ClusterProbe:
    def get_cli_tool(self, cluster_type: str) -> str:
        return "oc" if cluster_type == "openshift" else "kubectl"

    async def probe(self, config: IntegrationConfig) -> ProbeResult:
        result = ProbeResult()
        cli = self.get_cli_tool(config.cluster_type)

        # Write kubeconfig to a temp file if needed
        kubeconfig_path: Optional[str] = None
        try:
            if config.auth_method == "kubeconfig" and config.auth_data:
                fd, kubeconfig_path = tempfile.mkstemp(suffix=".kubeconfig", prefix="probe_")
                os.write(fd, config.auth_data.encode())
                os.close(fd)

            safe_args = _build_auth_args(
                config.cluster_url, config.auth_method, config.auth_data, kubeconfig_path
            )

            if config.cluster_type == "openshift":
                result = await self._probe_openshift(cli, safe_args, result)
            else:
                result = await self._probe_kubernetes(cli, safe_args, result)
        finally:
            if kubeconfig_path and os.path.exists(kubeconfig_path):
                os.unlink(kubeconfig_path)

        return result

    async def _check_connectivity(self, cli: str, safe_args: str, result: ProbeResult, api_name: str, version_key: str) -> bool:
        """Check basic cluster connectivity via 'version' command.

        Returns True if the cluster API is reachable (authenticated successfully).
        A 'NotFound' or 'Forbidden' from the server still means the API is reachable.
        Uses -o json since kubectl version doesn't support jsonpath output.
        """
        import json as _json

        ep_api = EndpointProbeResult(name=api_name)
        code, stdout, stderr = await run_command(
            f"{cli} version {safe_args} -o json --insecure-skip-tls-verify"
        )
        if code == 0:
            result.reachable = True
            ep_api.reachable = True
            try:
                version_data = _json.loads(stdout)
                version = version_data.get("serverVersion", {}).get("gitVersion", "")
                if version_key == "openshiftVersion":
                    version = version_data.get("openshiftVersion", version)
                if version:
                    result.cluster_version = version
            except _json.JSONDecodeError:
                pass
        elif self._is_server_response(stderr):
            # Server responded (e.g. Forbidden, Unauthorized) — cluster is reachable
            # but may have auth issues for version endpoint
            result.reachable = True
            ep_api.reachable = True
            ep_api.error = stderr
        else:
            # Genuine connection failure
            error_msg = stderr or f"Command failed with exit code {code}"
            result.errors.append(error_msg)
            ep_api.error = error_msg
            result.endpoint_results[api_name] = ep_api
            return False

        result.endpoint_results[api_name] = ep_api
        return True

    def _is_server_response(self, stderr: str) -> bool:
        """Check if stderr indicates the server actually responded (vs connection failure).

        'Error from server (NotFound)' = server responded, cluster is reachable.
        'Unable to connect to the server' = connection failure, cluster is NOT reachable.
        """
        # Connection failures — NOT a server response
        connection_failures = [
            "Unable to connect",
            "dial tcp",
            "no such host",
            "connection refused",
            "i/o timeout",
        ]
        if any(fail in stderr for fail in connection_failures):
            return False

        # Server actually responded with an API error
        server_indicators = [
            "Error from server",
            "Forbidden",
            "Unauthorized",
            "NotFound",
            "forbidden",
        ]
        return any(indicator in stderr for indicator in server_indicators)

    async def _discover_svc_by_label(self, cli: str, safe_args: str, label: str, port: int) -> Optional[str]:
        """Find a service across all namespaces using a label selector.

        Returns the cluster-local URL (name.namespace.svc.cluster.local:port) or None.
        """
        code, stdout, stderr = await run_command(
            f"{cli} get svc -A -l {shlex.quote(label)} "
            f"{safe_args} "
            f"-o jsonpath='{{.items[0].metadata.name}}.{{.items[0].metadata.namespace}}.svc.cluster.local' "
            f"--insecure-skip-tls-verify"
        )
        if code == 0 and stdout.strip("'") and ".." not in stdout:
            return f"http://{stdout.strip(chr(39))}:{port}"
        return None

    async def _discover_svc_by_name(self, cli: str, safe_args: str, name: str, namespace: str, port: int) -> Optional[str]:
        """Find a service by exact name and namespace.

        Returns the cluster-local URL or None.
        """
        code, stdout, stderr = await run_command(
            f"{cli} get svc {shlex.quote(name)} -n {shlex.quote(namespace)} "
            f"{safe_args} "
            f"-o jsonpath='{{.metadata.name}}.{{.metadata.namespace}}.svc.cluster.local' "
            f"--insecure-skip-tls-verify"
        )
        if code == 0 and stdout.strip("'"):
            return f"http://{stdout.strip(chr(39))}:{port}"
        return None

    async def _discover_prometheus_k8s(self, cli: str, safe_args: str) -> Optional[str]:
        """Try multiple strategies to find Prometheus on Kubernetes."""
        # Strategy 1: Label selector (works for all Helm charts)
        for label in [
            "app.kubernetes.io/name=prometheus",
            "app=prometheus",
            "app=prometheus-server",
            "app=kube-prometheus-stack-prometheus",
        ]:
            url = await self._discover_svc_by_label(cli, safe_args, label, 9090)
            if url:
                return url

        # Strategy 2: Common service names across common namespaces
        common_names = [
            "prometheus-server", "prometheus", "prometheus-operated",
            "prometheus-kube-prometheus-prometheus",
        ]
        common_namespaces = ["monitoring", "prometheus", "observability", "kube-monitoring", "default"]
        for svc_name in common_names:
            for ns in common_namespaces:
                url = await self._discover_svc_by_name(cli, safe_args, svc_name, ns, 9090)
                if url:
                    return url
        return None

    async def _discover_elasticsearch_k8s(self, cli: str, safe_args: str) -> Optional[str]:
        """Try multiple strategies to find Elasticsearch on Kubernetes."""
        for label in [
            "app.kubernetes.io/name=elasticsearch",
            "app=elasticsearch",
        ]:
            url = await self._discover_svc_by_label(cli, safe_args, label, 9200)
            if url:
                return url

        common_names = ["elasticsearch", "elasticsearch-master", "elasticsearch-coordinating"]
        common_namespaces = ["logging", "elastic", "observability", "elk", "default"]
        for svc_name in common_names:
            for ns in common_namespaces:
                url = await self._discover_svc_by_name(cli, safe_args, svc_name, ns, 9200)
                if url:
                    return url
        return None

    async def _discover_route(self, cli: str, safe_args: str, route_name: str, namespace: str) -> Optional[str]:
        """Discover a service URL via OpenShift route."""
        code, stdout, stderr = await run_command(
            f"{cli} get route {shlex.quote(route_name)} -n {shlex.quote(namespace)} "
            f"{safe_args} "
            f"-o jsonpath='{{.spec.host}}' --insecure-skip-tls-verify"
        )
        if code == 0 and stdout.strip("'"):
            host = stdout.strip("'")
            return f"https://{host}" if not host.startswith("http") else host
        return None

    async def _probe_openshift(self, cli: str, safe_args: str, result: ProbeResult) -> ProbeResult:
        # 1. Check cluster connectivity
        reachable = await self._check_connectivity(
            cli, safe_args, result, "openshift_api", "openshiftVersion"
        )
        if not reachable:
            return result

        # 2. Discover Prometheus via route (optional)
        ep_prom = EndpointProbeResult(name="prometheus")
        prom_url = await self._discover_route(cli, safe_args, "prometheus-k8s", "openshift-monitoring")
        if prom_url:
            result.prometheus_url = prom_url
            ep_prom.reachable = True
            ep_prom.discovered_url = prom_url
        else:
            ep_prom.error = "Prometheus route not found in openshift-monitoring"
        result.endpoint_results["prometheus"] = ep_prom

        # 3. Discover ELK via route (optional)
        ep_elk = EndpointProbeResult(name="elasticsearch")
        elk_url = await self._discover_route(cli, safe_args, "kibana", "openshift-logging")
        if elk_url:
            result.elasticsearch_url = elk_url
            ep_elk.reachable = True
            ep_elk.discovered_url = elk_url
        else:
            ep_elk.error = "Kibana route not found in openshift-logging"
        result.endpoint_results["elasticsearch"] = ep_elk

        return result

    async def _probe_kubernetes(self, cli: str, safe_args: str, result: ProbeResult) -> ProbeResult:
        # 1. Check cluster connectivity
        reachable = await self._check_connectivity(
            cli, safe_args, result, "kubernetes_api", "gitVersion"
        )
        if not reachable:
            return result

        # 2. Discover Prometheus (label selectors → common names → all namespaces)
        ep_prom = EndpointProbeResult(name="prometheus")
        prom_url = await self._discover_prometheus_k8s(cli, safe_args)
        if prom_url:
            result.prometheus_url = prom_url
            ep_prom.reachable = True
            ep_prom.discovered_url = prom_url
        else:
            ep_prom.error = "Prometheus service not found (searched by labels and common names)"
        result.endpoint_results["prometheus"] = ep_prom

        # 3. Discover Elasticsearch (label selectors → common names → all namespaces)
        ep_elk = EndpointProbeResult(name="elasticsearch")
        elk_url = await self._discover_elasticsearch_k8s(cli, safe_args)
        if elk_url:
            result.elasticsearch_url = elk_url
            ep_elk.reachable = True
            ep_elk.discovered_url = elk_url
        else:
            ep_elk.error = "Elasticsearch service not found (searched by labels and common names)"
        result.endpoint_results["elasticsearch"] = ep_elk

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
            "github": "/user",
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
