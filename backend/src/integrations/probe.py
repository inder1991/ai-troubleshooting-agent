import asyncio
from typing import Optional, Tuple
from pydantic import BaseModel
from .models import IntegrationConfig


class ProbeResult(BaseModel):
    reachable: bool = False
    prometheus_url: Optional[str] = None
    elasticsearch_url: Optional[str] = None
    cluster_version: Optional[str] = None
    errors: list[str] = []


async def run_command(cmd: str) -> Tuple[int, str, str]:
    proc = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await proc.communicate()
    return proc.returncode, stdout.decode().strip(), stderr.decode().strip()


class ClusterProbe:
    def get_cli_tool(self, cluster_type: str) -> str:
        return "oc" if cluster_type == "openshift" else "kubectl"

    async def probe(self, config: IntegrationConfig) -> ProbeResult:
        result = ProbeResult()
        cli = self.get_cli_tool(config.cluster_type)

        if config.cluster_type == "openshift":
            # 1. Discover Prometheus via route
            code, stdout, stderr = await run_command(
                f"{cli} get route prometheus-k8s -n openshift-monitoring "
                f"--server={config.cluster_url} --token={config.auth_data} "
                f"-o jsonpath='{{.spec.host}}' --insecure-skip-tls-verify"
            )
            if code != 0:
                if "Unable to connect" in stderr:
                    result.errors.append(stderr)
                    return result  # reachable stays False
            else:
                result.reachable = True
                host = stdout.strip("'")
                result.prometheus_url = f"https://{host}" if not host.startswith("http") else host

            # 2. Discover ELK
            code, stdout, stderr = await run_command(
                f"{cli} get route kibana -n openshift-logging "
                f"--server={config.cluster_url} --token={config.auth_data} "
                f"-o jsonpath='{{.spec.host}}' --insecure-skip-tls-verify"
            )
            if code == 0:
                host = stdout.strip("'")
                result.elasticsearch_url = f"https://{host}" if not host.startswith("http") else host

            # 3. Version
            code, stdout, stderr = await run_command(
                f"{cli} version --server={config.cluster_url} --token={config.auth_data} "
                f"-o jsonpath='{{.openshiftVersion}}' --insecure-skip-tls-verify"
            )
            if code == 0:
                result.cluster_version = stdout.strip("'")

        else:  # kubernetes
            code, stdout, stderr = await run_command(
                f"{cli} get svc prometheus-server -n monitoring "
                f"--server={config.cluster_url} --token={config.auth_data} "
                f"-o jsonpath='{{.metadata.name}}.{{.metadata.namespace}}.svc.cluster.local' "
                f"--insecure-skip-tls-verify"
            )
            if code != 0 and "Unable to connect" in stderr:
                result.errors.append(stderr)
                return result
            elif code == 0:
                result.reachable = True
                result.prometheus_url = f"http://{stdout}:9090"

            code, stdout, stderr = await run_command(
                f"{cli} get svc elasticsearch -n logging "
                f"--server={config.cluster_url} --token={config.auth_data} "
                f"-o jsonpath='{{.metadata.name}}.{{.metadata.namespace}}.svc.cluster.local' "
                f"--insecure-skip-tls-verify"
            )
            if code == 0:
                result.elasticsearch_url = f"http://{stdout}:9200"

            code, stdout, stderr = await run_command(
                f"{cli} version --server={config.cluster_url} --token={config.auth_data} "
                f"-o jsonpath='{{.serverVersion.gitVersion}}' --insecure-skip-tls-verify"
            )
            if code == 0:
                result.cluster_version = stdout.strip("'")

        return result
