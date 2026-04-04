"""Proactive cluster analysis — 8 extensible checks that run outside LangGraph.

To add a new check:
  1. Append a CheckDefinition to PROACTIVE_CHECKS.
  2. Write an evaluator function: _check_<name>(data) -> list[ProactiveFinding].
  3. Map check_id -> evaluator in _EVALUATORS.
No other changes needed.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from src.agents.cluster.state import ProactiveFinding
from src.agents.cluster_client.base import ClusterClient, QueryResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Check definition schema
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SeverityRule:
    """Single threshold -> severity mapping."""
    field: str
    op: str        # "<=", ">=", "==", "in"
    value: Any
    severity: str  # "critical" | "high" | "medium" | "low"


@dataclass(frozen=True)
class CheckDefinition:
    """Declarative check metadata. The evaluator function does the real work."""
    check_id: str
    name: str
    category: str        # "security" | "reliability" | "lifecycle" | "capacity"
    data_source: str     # ClusterClient method name
    severity_rules: tuple[SeverityRule, ...]


# ---------------------------------------------------------------------------
# 8 check definitions
# ---------------------------------------------------------------------------

PROACTIVE_CHECKS: list[CheckDefinition] = [
    CheckDefinition(
        check_id="cert_expiry",
        name="TLS Certificate Expiry",
        category="security",
        data_source="list_tls_secrets",
        severity_rules=(
            SeverityRule(field="days_remaining", op="<=", value=7, severity="critical"),
            SeverityRule(field="days_remaining", op="<=", value=14, severity="high"),
            SeverityRule(field="days_remaining", op="<=", value=30, severity="medium"),
        ),
    ),
    CheckDefinition(
        check_id="deprecated_api",
        name="Deprecated Kubernetes API Versions",
        category="lifecycle",
        data_source="list_api_versions_in_use",
        severity_rules=(
            SeverityRule(field="api_version", op="in", value=["v1alpha1", "v1beta1", "v2beta1", "v2beta2"], severity="high"),
            SeverityRule(field="api_version", op="in", value=["v1beta2"], severity="medium"),
        ),
    ),
    CheckDefinition(
        check_id="image_stale",
        name="Stale or Unpinned Container Images",
        category="reliability",
        data_source="list_pods",
        severity_rules=(
            SeverityRule(field="tag", op="==", value="latest", severity="high"),
            SeverityRule(field="digest", op="==", value="", severity="medium"),
        ),
    ),
    CheckDefinition(
        check_id="security_posture",
        name="Security Posture Violations",
        category="security",
        data_source="list_pods",
        severity_rules=(
            SeverityRule(field="privileged", op="==", value=True, severity="critical"),
            SeverityRule(field="run_as_root", op="==", value=True, severity="high"),
            SeverityRule(field="default_sa", op="==", value=True, severity="medium"),
        ),
    ),
    CheckDefinition(
        check_id="quota_pressure",
        name="Resource Quota Pressure",
        category="capacity",
        data_source="list_resource_quotas",
        severity_rules=(
            SeverityRule(field="usage_pct", op=">=", value=90, severity="high"),
            SeverityRule(field="usage_pct", op=">=", value=80, severity="medium"),
        ),
    ),
    CheckDefinition(
        check_id="pdb_blocking",
        name="PodDisruptionBudget Blocking Evictions",
        category="reliability",
        data_source="list_pdbs",
        severity_rules=(
            SeverityRule(field="disruptions_allowed", op="==", value=0, severity="high"),
        ),
    ),
    CheckDefinition(
        check_id="node_os_patch",
        name="Node OS / Kernel Patch Level",
        category="security",
        data_source="get_node_os_info",
        severity_rules=(
            SeverityRule(field="kernel_age_days", op=">=", value=180, severity="high"),
            SeverityRule(field="kernel_age_days", op=">=", value=90, severity="medium"),
        ),
    ),
    CheckDefinition(
        check_id="hpa_vpa_limits",
        name="HPA/VPA Scaling Limits",
        category="capacity",
        data_source="list_hpas",
        severity_rules=(
            SeverityRule(field="at_max_replicas", op="==", value=True, severity="high"),
            SeverityRule(field="vpa_ignored", op="==", value=True, severity="medium"),
        ),
    ),
]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _fid() -> str:
    return str(uuid.uuid4())


def _severity_order(s: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(s, 4)


# ---------------------------------------------------------------------------
# Evaluator functions — one per check_id
# ---------------------------------------------------------------------------

def _check_cert_expiry(data: list[dict[str, Any]]) -> list[ProactiveFinding]:
    """Flag TLS secrets approaching expiry."""
    findings: list[ProactiveFinding] = []
    now = datetime.now(timezone.utc)

    for secret in data:
        not_after_str = secret.get("not_after", "")
        if not not_after_str:
            continue

        try:
            not_after = datetime.fromisoformat(not_after_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue

        days_remaining = (not_after - now).days
        name = secret.get("name", "unknown")
        ns = secret.get("namespace", "default")
        resource_key = f"secret/{ns}/{name}"

        if days_remaining <= 7:
            severity = "critical"
        elif days_remaining <= 14:
            severity = "high"
        elif days_remaining <= 30:
            severity = "medium"
        else:
            continue

        findings.append(ProactiveFinding(
            finding_id=_fid(),
            check_type="cert_expiry",
            severity=severity,
            lifecycle_state="NEW",
            title=f"TLS certificate '{name}' expires in {days_remaining} days",
            description=(
                f"Secret {resource_key} has a TLS certificate expiring on "
                f"{not_after.strftime('%Y-%m-%d')}. "
                f"Services relying on this certificate will fail after expiry."
            ),
            affected_resources=[resource_key],
            affected_workloads=secret.get("used_by", []),
            days_until_impact=max(days_remaining, 0),
            recommendation=f"Renew the TLS certificate for secret '{name}' in namespace '{ns}'.",
            commands=[
                f"kubectl get secret {name} -n {ns} -o jsonpath='{{.data.tls\\.crt}}' | base64 -d | openssl x509 -noout -dates",
                f"kubectl delete secret {name} -n {ns}  # then recreate with renewed cert",
            ],
            dry_run_command=f"kubectl get secret {name} -n {ns} -o yaml",
            confidence=0.95,
            source="proactive",
        ))

    return findings


def _check_deprecated_api(data: list[dict[str, Any]]) -> list[ProactiveFinding]:
    """Flag resources using deprecated / alpha / beta API versions."""
    findings: list[ProactiveFinding] = []
    deprecated_markers = {"alpha", "beta"}

    for resource in data:
        api_version = resource.get("api_version", "")
        kind = resource.get("kind", "")
        name = resource.get("name", "unknown")
        ns = resource.get("namespace", "")

        is_deprecated = any(marker in api_version.lower() for marker in deprecated_markers)
        if not is_deprecated:
            continue

        resource_key = f"{kind}/{ns}/{name}" if ns else f"{kind}/{name}"
        severity = "high" if ("alpha" in api_version.lower()) else "medium"

        findings.append(ProactiveFinding(
            finding_id=_fid(),
            check_type="deprecated_api",
            severity=severity,
            lifecycle_state="NEW",
            title=f"{kind} '{name}' uses deprecated API {api_version}",
            description=(
                f"Resource {resource_key} is using API version '{api_version}' which "
                f"contains alpha/beta markers and may be removed in future Kubernetes releases."
            ),
            affected_resources=[resource_key],
            affected_workloads=[f"{kind}/{ns}/{name}"] if ns else [f"{kind}/{name}"],
            days_until_impact=-1,
            recommendation=(
                f"Migrate {kind} '{name}' from '{api_version}' to the stable GA API version. "
                f"Run `kubectl convert` or update the manifest manually."
            ),
            commands=[
                f"kubectl get {kind.lower()} {name}" + (f" -n {ns}" if ns else "") + f" -o yaml | grep apiVersion",
            ],
            dry_run_command=f"kubectl get {kind.lower()} {name}" + (f" -n {ns}" if ns else "") + " -o yaml",
            confidence=0.90,
            source="proactive",
        ))

    return findings


def _check_image_staleness(data: list[dict[str, Any]]) -> list[ProactiveFinding]:
    """Flag pods using :latest tag or images without a digest pin."""
    findings: list[ProactiveFinding] = []

    for pod in data:
        pod_name = pod.get("name", "unknown")
        ns = pod.get("namespace", "default")
        containers = pod.get("containers", [])
        if not containers:
            # Flatten: sometimes data is already per-container
            containers = [pod]

        for c in containers:
            image: str = c.get("image", "")
            if not image:
                continue

            tag = ""
            digest = c.get("image_id", "") or c.get("digest", "")
            if ":" in image and "@" not in image:
                tag = image.rsplit(":", 1)[-1]
            elif "@" not in image:
                tag = "latest"  # implicit latest

            resource_key = f"pod/{ns}/{pod_name}"
            container_name = c.get("container_name", c.get("name", ""))

            if tag == "latest":
                findings.append(ProactiveFinding(
                    finding_id=_fid(),
                    check_type="image_stale",
                    severity="high",
                    lifecycle_state="NEW",
                    title=f"Container '{container_name}' in pod '{pod_name}' uses :latest tag",
                    description=(
                        f"Image '{image}' in {resource_key} uses the ':latest' tag. "
                        f"This makes deployments non-reproducible and can pull unexpected versions."
                    ),
                    affected_resources=[resource_key],
                    affected_workloads=pod.get("owner_references", []),
                    days_until_impact=-1,
                    recommendation=(
                        f"Pin container '{container_name}' to a specific image tag or digest. "
                        f"Example: '{image.rsplit(':', 1)[0]}:v1.2.3'."
                    ),
                    commands=[
                        f"kubectl get pod {pod_name} -n {ns} -o jsonpath='{{.spec.containers[*].image}}'",
                    ],
                    dry_run_command=f"kubectl get pod {pod_name} -n {ns} -o yaml",
                    confidence=0.95,
                    source="proactive",
                ))
            elif not digest:
                findings.append(ProactiveFinding(
                    finding_id=_fid(),
                    check_type="image_stale",
                    severity="medium",
                    lifecycle_state="NEW",
                    title=f"Container '{container_name}' in pod '{pod_name}' has no digest pin",
                    description=(
                        f"Image '{image}' in {resource_key} does not include a digest (sha256). "
                        f"Tags are mutable and the image content may change unexpectedly."
                    ),
                    affected_resources=[resource_key],
                    affected_workloads=pod.get("owner_references", []),
                    days_until_impact=-1,
                    recommendation=(
                        f"Pin image to a digest: '{image}@sha256:<digest>'."
                    ),
                    commands=[
                        f"kubectl get pod {pod_name} -n {ns} -o jsonpath='{{.status.containerStatuses[*].imageID}}'",
                    ],
                    dry_run_command=f"kubectl get pod {pod_name} -n {ns} -o yaml",
                    confidence=0.70,
                    source="proactive",
                ))

    return findings


def _check_security_posture(data: list[dict[str, Any]]) -> list[ProactiveFinding]:
    """Flag pods running as root, privileged, or with the default service account."""
    findings: list[ProactiveFinding] = []

    for pod in data:
        pod_name = pod.get("name", "unknown")
        ns = pod.get("namespace", "default")
        resource_key = f"pod/{ns}/{pod_name}"
        sa = pod.get("service_account", pod.get("serviceAccountName", ""))
        security_context = pod.get("security_context", {})
        containers = pod.get("containers", [])

        # Check pod-level security context
        run_as_user = security_context.get("runAsUser")
        run_as_non_root = security_context.get("runAsNonRoot", False)

        is_root = (run_as_user == 0) or (not run_as_non_root and run_as_user is None)

        # Check container-level contexts for privileged
        privileged = False
        for c in containers:
            csc = c.get("security_context", c.get("securityContext", {}))
            if csc.get("privileged", False):
                privileged = True
                break
            c_run_as = csc.get("runAsUser")
            if c_run_as == 0:
                is_root = True

        owner_refs = pod.get("owner_references", [])

        if privileged:
            findings.append(ProactiveFinding(
                finding_id=_fid(),
                check_type="security_posture",
                severity="critical",
                lifecycle_state="NEW",
                title=f"Pod '{pod_name}' runs in privileged mode",
                description=(
                    f"{resource_key} has a container running in privileged mode, "
                    f"granting full host access. This is a critical security risk."
                ),
                affected_resources=[resource_key],
                affected_workloads=owner_refs,
                days_until_impact=-1,
                recommendation=(
                    f"Remove 'privileged: true' from the security context of pod '{pod_name}'. "
                    f"Use specific capabilities instead."
                ),
                commands=[
                    f"kubectl get pod {pod_name} -n {ns} -o jsonpath='{{.spec.containers[*].securityContext}}'",
                ],
                dry_run_command=f"kubectl get pod {pod_name} -n {ns} -o yaml",
                confidence=0.98,
                source="proactive",
            ))

        if is_root:
            findings.append(ProactiveFinding(
                finding_id=_fid(),
                check_type="security_posture",
                severity="high",
                lifecycle_state="NEW",
                title=f"Pod '{pod_name}' may run as root",
                description=(
                    f"{resource_key} does not enforce runAsNonRoot and may execute as UID 0. "
                    f"Compromised containers with root access can escalate to host."
                ),
                affected_resources=[resource_key],
                affected_workloads=owner_refs,
                days_until_impact=-1,
                recommendation=(
                    f"Set 'runAsNonRoot: true' and 'runAsUser: 1000' in the pod security context."
                ),
                commands=[
                    f"kubectl get pod {pod_name} -n {ns} -o jsonpath='{{.spec.securityContext}}'",
                ],
                dry_run_command=f"kubectl get pod {pod_name} -n {ns} -o yaml",
                confidence=0.85,
                source="proactive",
            ))

        if sa == "default":
            findings.append(ProactiveFinding(
                finding_id=_fid(),
                check_type="security_posture",
                severity="medium",
                lifecycle_state="NEW",
                title=f"Pod '{pod_name}' uses the default service account",
                description=(
                    f"{resource_key} uses the 'default' service account which may have "
                    f"broader permissions than necessary. Use a dedicated service account."
                ),
                affected_resources=[resource_key],
                affected_workloads=owner_refs,
                days_until_impact=-1,
                recommendation=(
                    f"Create a dedicated service account for the workload and set "
                    f"'automountServiceAccountToken: false' if API access is not needed."
                ),
                commands=[
                    f"kubectl get pod {pod_name} -n {ns} -o jsonpath='{{.spec.serviceAccountName}}'",
                ],
                dry_run_command=f"kubectl get pod {pod_name} -n {ns} -o yaml",
                confidence=0.80,
                source="proactive",
            ))

    return findings


def _check_quota_pressure(data: list[dict[str, Any]]) -> list[ProactiveFinding]:
    """Flag resource quotas approaching or exceeding limits."""
    findings: list[ProactiveFinding] = []

    for quota in data:
        quota_name = quota.get("name", "unknown")
        ns = quota.get("namespace", "default")
        resource_key = f"resourcequota/{ns}/{quota_name}"
        status = quota.get("status", {})
        hard = status.get("hard", {})
        used = status.get("used", {})

        for resource_name, hard_val_raw in hard.items():
            used_val_raw = used.get(resource_name)
            if used_val_raw is None:
                continue

            try:
                hard_val = float(str(hard_val_raw).replace("Gi", "").replace("Mi", "").replace("Ki", "").replace("m", ""))
                used_val = float(str(used_val_raw).replace("Gi", "").replace("Mi", "").replace("Ki", "").replace("m", ""))
            except (ValueError, TypeError):
                continue

            if hard_val <= 0:
                continue
            usage_pct = (used_val / hard_val) * 100

            if usage_pct >= 90:
                severity = "high"
            elif usage_pct >= 80:
                severity = "medium"
            else:
                continue

            days_estimate = -1 if usage_pct >= 100 else max(1, int((100 - usage_pct) * 3))

            findings.append(ProactiveFinding(
                finding_id=_fid(),
                check_type="quota_pressure",
                severity=severity,
                lifecycle_state="NEW",
                title=f"Quota '{quota_name}' resource '{resource_name}' at {usage_pct:.0f}%",
                description=(
                    f"ResourceQuota {resource_key}: {resource_name} usage is "
                    f"{used_val_raw}/{hard_val_raw} ({usage_pct:.1f}%). "
                    f"New workloads may be rejected when the quota is exhausted."
                ),
                affected_resources=[resource_key],
                affected_workloads=[],
                days_until_impact=days_estimate,
                recommendation=(
                    f"In namespace '{ns}', reduce '{resource_name}' consumption or increase the quota limit. "
                    f"Run 'kubectl top pods -n {ns}' to identify the highest consumers, "
                    f"then lower resource requests on over-provisioned deployments "
                    f"or edit quota '{quota_name}' to raise the '{resource_name}' limit."
                ),
                commands=[
                    f"kubectl describe resourcequota {quota_name} -n {ns}",
                    f"kubectl top pods -n {ns} --sort-by=cpu",
                    f"kubectl get pods -n {ns} --sort-by='.metadata.creationTimestamp'",
                ],
                dry_run_command=f"kubectl get resourcequota {quota_name} -n {ns} -o yaml",
                confidence=0.90,
                source="proactive",
            ))

    return findings


def _check_pdb_blocking(data: list[dict[str, Any]]) -> list[ProactiveFinding]:
    """Flag PDBs that block all voluntary evictions."""
    findings: list[ProactiveFinding] = []

    for pdb in data:
        pdb_name = pdb.get("name", "unknown")
        ns = pdb.get("namespace", "default")
        status = pdb.get("status", {})
        disruptions_allowed = status.get("disruptionsAllowed", status.get("disruptions_allowed"))

        if disruptions_allowed is None:
            continue

        try:
            disruptions_allowed = int(disruptions_allowed)
        except (ValueError, TypeError):
            continue

        if disruptions_allowed != 0:
            continue

        resource_key = f"pdb/{ns}/{pdb_name}"
        current_healthy = status.get("currentHealthy", "?")
        desired_healthy = status.get("desiredHealthy", "?")

        findings.append(ProactiveFinding(
            finding_id=_fid(),
            check_type="pdb_blocking",
            severity="high",
            lifecycle_state="NEW",
            title=f"PDB '{pdb_name}' blocks all evictions (0 disruptions allowed)",
            description=(
                f"PodDisruptionBudget {resource_key} has disruptionsAllowed=0 "
                f"(currentHealthy={current_healthy}, desiredHealthy={desired_healthy}). "
                f"Node drains, cluster upgrades, and voluntary evictions will be blocked."
            ),
            affected_resources=[resource_key],
            affected_workloads=pdb.get("matched_pods", []),
            days_until_impact=-1,
            recommendation=(
                f"Ensure enough healthy replicas so the PDB allows at least 1 disruption. "
                f"Consider adjusting minAvailable/maxUnavailable or scaling the workload."
            ),
            commands=[
                f"kubectl describe pdb {pdb_name} -n {ns}",
                f"kubectl get pods -n {ns} -l {_label_selector_str(pdb.get('selector', {}))}",
            ],
            dry_run_command=f"kubectl get pdb {pdb_name} -n {ns} -o yaml",
            confidence=0.95,
            source="proactive",
        ))

    return findings


def _label_selector_str(selector: dict[str, Any]) -> str:
    """Convert a matchLabels dict to a CLI-friendly label selector."""
    match_labels = selector.get("matchLabels", selector)
    if isinstance(match_labels, dict) and match_labels:
        return ",".join(f"{k}={v}" for k, v in match_labels.items())
    return "app=<unknown>"


def _parse_kernel_major_minor(kernel_version: str) -> tuple[int, int] | None:
    """Parse kernel version string like '5.15.0-78-generic' → (5, 15). Returns None if unparseable."""
    match = re.match(r'^(\d+)\.(\d+)', kernel_version.strip())
    if not match:
        return None
    return (int(match.group(1)), int(match.group(2)))


_MIN_KERNEL_BY_OS: dict[str, tuple[int, int]] = {
    # Ubuntu — minimum supported LTS kernel versions
    "ubuntu 18": (4, 15),
    "ubuntu 20": (5, 4),
    "ubuntu 22": (5, 15),
    # RHEL/CentOS/Rocky/Alma
    "red hat enterprise linux 8": (4, 18),
    "red hat enterprise linux 9": (5, 14),
    "centos": (3, 10),
    "rocky": (4, 18),
    "alma": (4, 18),
    # CoreOS / Fedora (used by OpenShift)
    "fedora coreos": (5, 14),
    "red hat enterprise linux coreos": (5, 14),
}


def _check_node_os_patch(data: list[dict[str, Any]]) -> list[ProactiveFinding]:
    """Flag nodes running a kernel older than the OS-specific minimum supported version."""
    findings: list[ProactiveFinding] = []

    for node in data:
        node_name = node.get("name", "unknown")
        resource_key = f"node/{node_name}"
        kernel_version = node.get("kernel_version", "")
        os_image = node.get("os_image", "").lower()

        # Skip if kernel version is absent or unparseable
        parsed = _parse_kernel_major_minor(kernel_version)
        if parsed is None:
            continue

        # Find minimum kernel for this OS by checking if any known key appears in os_image
        min_kernel: tuple[int, int] | None = None
        for os_key, min_ver in _MIN_KERNEL_BY_OS.items():
            if os_key in os_image:
                min_kernel = min_ver
                break

        # Skip nodes with an OS not in our known list — never guess
        if min_kernel is None:
            continue

        # Compare (major, minor) tuples lexicographically
        if parsed < min_kernel:
            findings.append(ProactiveFinding(
                finding_id=_fid(),
                check_type="node_os_patch",
                severity="high",
                lifecycle_state="NEW",
                title=f"Node '{node_name}' kernel {kernel_version} is below minimum for {os_image}",
                description=(
                    f"Node {resource_key} is running kernel '{kernel_version}' "
                    f"(OS: {os_image}). The minimum supported kernel for this OS is "
                    f"{min_kernel[0]}.{min_kernel[1]}. Security patches may be missing."
                ),
                affected_resources=[resource_key],
                affected_workloads=[],
                days_until_impact=-1,
                recommendation=(
                    f"Schedule a maintenance window to patch node '{node_name}'. "
                    f"Cordon, drain, update the OS/kernel, and uncordon."
                ),
                commands=[
                    f"kubectl cordon {node_name}",
                    f"kubectl drain {node_name} --ignore-daemonsets --delete-emptydir-data",
                ],
                dry_run_command=f"kubectl drain {node_name} --ignore-daemonsets --delete-emptydir-data --dry-run=client",
                confidence=0.75,
                source="proactive",
            ))

    return findings


def _check_hpa_vpa_limits(data: list[dict[str, Any]]) -> list[ProactiveFinding]:
    """Flag HPAs at max replicas and VPA recommendations being ignored."""
    findings: list[ProactiveFinding] = []

    for hpa in data:
        hpa_name = hpa.get("name", "unknown")
        ns = hpa.get("namespace", "default")
        resource_key = f"hpa/{ns}/{hpa_name}"
        status = hpa.get("status", {})

        current_replicas = status.get("currentReplicas", status.get("current_replicas", 0))
        max_replicas = hpa.get("spec", {}).get("maxReplicas", hpa.get("max_replicas", 0))

        try:
            current_replicas = int(current_replicas)
            max_replicas = int(max_replicas)
        except (ValueError, TypeError):
            current_replicas, max_replicas = 0, 0

        if max_replicas > 0 and current_replicas >= max_replicas:
            findings.append(ProactiveFinding(
                finding_id=_fid(),
                check_type="hpa_vpa_limits",
                severity="high",
                lifecycle_state="NEW",
                title=f"HPA '{hpa_name}' is at maximum replicas ({current_replicas}/{max_replicas})",
                description=(
                    f"HorizontalPodAutoscaler {resource_key} has scaled to its maximum of "
                    f"{max_replicas} replicas. The workload cannot absorb additional load."
                ),
                affected_resources=[resource_key],
                affected_workloads=[hpa.get("target_ref", "")],
                days_until_impact=-1,
                recommendation=(
                    f"Increase maxReplicas for HPA '{hpa_name}' or optimize the workload "
                    f"to handle more load per replica."
                ),
                commands=[
                    f"kubectl describe hpa {hpa_name} -n {ns}",
                    f"kubectl patch hpa {hpa_name} -n {ns} -p '{{\"spec\":{{\"maxReplicas\":{max_replicas + 5}}}}}'",
                ],
                dry_run_command=(
                    f"kubectl patch hpa {hpa_name} -n {ns} "
                    f"-p '{{\"spec\":{{\"maxReplicas\":{max_replicas + 5}}}}}' --dry-run=client"
                ),
                confidence=0.90,
                source="proactive",
            ))

        # Check for VPA recommendation present but ignored
        vpa_recommendation = hpa.get("vpa_recommendation")
        vpa_mode = hpa.get("vpa_update_mode", "")
        if vpa_recommendation and vpa_mode in ("Off", "Initial", ""):
            findings.append(ProactiveFinding(
                finding_id=_fid(),
                check_type="hpa_vpa_limits",
                severity="medium",
                lifecycle_state="NEW",
                title=f"VPA recommendation for '{hpa_name}' target is not applied",
                description=(
                    f"A VerticalPodAutoscaler has recommendations for the target of HPA "
                    f"'{hpa_name}' but updateMode is '{vpa_mode or 'Off'}'. "
                    f"Resource requests may be sub-optimal."
                ),
                affected_resources=[resource_key],
                affected_workloads=[hpa.get("target_ref", "")],
                days_until_impact=-1,
                recommendation=(
                    f"Review VPA recommendations and either apply them manually or set "
                    f"updateMode to 'Auto'. Be cautious combining HPA and VPA on the same metric."
                ),
                commands=[
                    f"kubectl get vpa -n {ns} -o wide",
                ],
                dry_run_command=f"kubectl get vpa -n {ns} -o yaml",
                confidence=0.70,
                source="proactive",
            ))

    return findings


# ---------------------------------------------------------------------------
# Evaluator registry — maps check_id -> evaluator function
# ---------------------------------------------------------------------------

_EVALUATORS: dict[str, Callable[[list[dict[str, Any]]], list[ProactiveFinding]]] = {
    "cert_expiry": _check_cert_expiry,
    "deprecated_api": _check_deprecated_api,
    "image_stale": _check_image_staleness,
    "security_posture": _check_security_posture,
    "quota_pressure": _check_quota_pressure,
    "pdb_blocking": _check_pdb_blocking,
    "node_os_patch": _check_node_os_patch,
    "hpa_vpa_limits": _check_hpa_vpa_limits,
}


# ---------------------------------------------------------------------------
# Data fetching helper
# ---------------------------------------------------------------------------

async def _fetch_data(client: ClusterClient, data_source: str) -> list[dict[str, Any]]:
    """Call the appropriate ClusterClient method and return its data list."""
    method = getattr(client, data_source, None)
    if method is None:
        logger.warning("ClusterClient has no method '%s', skipping", data_source)
        return []

    result: QueryResult = await method()
    return result.data if result and result.data else []


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_proactive_analysis(client: ClusterClient) -> list[ProactiveFinding]:
    """Execute all proactive checks against the cluster and return sorted findings.

    Each check is independent — a failure in one does not affect the others.
    Findings are sorted by severity (critical first), then by days_until_impact.
    """
    all_findings: list[ProactiveFinding] = []

    # Deduplicate data sources so we don't fetch the same data twice
    source_to_checks: dict[str, list[CheckDefinition]] = {}
    for check in PROACTIVE_CHECKS:
        source_to_checks.setdefault(check.data_source, []).append(check)

    # Fetch data per unique source
    source_data: dict[str, list[dict[str, Any]]] = {}
    for data_source in source_to_checks:
        try:
            source_data[data_source] = await _fetch_data(client, data_source)
        except Exception:
            logger.exception("Failed to fetch data from '%s'", data_source)
            source_data[data_source] = []

    # Run each check's evaluator
    for check in PROACTIVE_CHECKS:
        evaluator = _EVALUATORS.get(check.check_id)
        if evaluator is None:
            logger.warning("No evaluator for check_id='%s', skipping", check.check_id)
            continue

        data = source_data.get(check.data_source, [])
        if not data:
            continue

        try:
            findings = evaluator(data)
            all_findings.extend(findings)
        except Exception:
            logger.exception("Evaluator for '%s' raised an exception", check.check_id)

    # Sort: critical first, then by days_until_impact ascending (-1 = already impacting = first)
    all_findings.sort(key=lambda f: (_severity_order(f.severity), f.days_until_impact))

    return all_findings
