"""Validate kubectl commands from LLM remediation suggestions."""

from __future__ import annotations
import re
from typing import Optional
from src.utils.logger import get_logger

logger = get_logger(__name__)

VALID_VERBS = {
    "get", "describe", "logs", "top", "explain",  # Read-only
    "apply", "create", "patch", "edit", "replace",  # Mutating
    "delete", "drain", "cordon", "uncordon", "taint", "untaint",  # Destructive
    "scale", "rollout", "autoscale",  # Scaling
    "label", "annotate",  # Metadata
    "exec", "port-forward", "cp",  # Debug
    "config", "auth",  # Config
}

DESTRUCTIVE_VERBS = {"delete", "drain", "cordon", "scale"}

VALID_RESOURCE_TYPES = {
    "pod", "pods", "po",
    "deployment", "deployments", "deploy",
    "service", "services", "svc",
    "node", "nodes", "no",
    "namespace", "namespaces", "ns",
    "configmap", "configmaps", "cm",
    "secret", "secrets",
    "persistentvolumeclaim", "persistentvolumeclaims", "pvc",
    "persistentvolume", "persistentvolumes", "pv",
    "statefulset", "statefulsets", "sts",
    "daemonset", "daemonsets", "ds",
    "replicaset", "replicasets", "rs",
    "job", "jobs",
    "cronjob", "cronjobs", "cj",
    "ingress", "ingresses", "ing",
    "networkpolicy", "networkpolicies", "netpol",
    "hpa", "horizontalpodautoscaler", "horizontalpodautoscalers",
    "pdb", "poddisruptionbudget", "poddisruptionbudgets",
    "serviceaccount", "serviceaccounts", "sa",
    "role", "roles",
    "rolebinding", "rolebindings",
    "clusterrole", "clusterroles",
    "clusterrolebinding", "clusterrolebindings",
    "storageclass", "storageclasses", "sc",
}

NAMESPACED_RESOURCES = {
    "pod", "pods", "po", "deployment", "deployments", "deploy",
    "service", "services", "svc", "configmap", "configmaps", "cm",
    "secret", "secrets", "pvc", "persistentvolumeclaim", "persistentvolumeclaims",
    "statefulset", "statefulsets", "sts", "daemonset", "daemonsets", "ds",
    "replicaset", "replicasets", "rs", "job", "jobs", "cronjob", "cronjobs", "cj",
    "ingress", "ingresses", "ing", "networkpolicy", "networkpolicies", "netpol",
    "hpa", "horizontalpodautoscaler", "horizontalpodautoscalers",
    "pdb", "poddisruptionbudget", "poddisruptionbudgets",
    "serviceaccount", "serviceaccounts", "sa",
    "role", "roles", "rolebinding", "rolebindings",
}


class CommandValidationResult:
    def __init__(self):
        self.valid = True
        self.warnings: list[str] = []
        self.errors: list[str] = []
        self.is_destructive = False
        self.missing_namespace = False
        self.fixed_command: Optional[str] = None


def validate_kubectl_command(command: str, default_namespace: str = "") -> CommandValidationResult:
    """Validate a kubectl command string. Returns validation result."""
    result = CommandValidationResult()

    command = command.strip()

    # Reject shell expansion, pipes, multi-command chains
    if any(c in command for c in ["|", ";", "&&", "||", "`", "$(", "${"]):
        result.valid = False
        result.errors.append("Command contains shell operators (pipes, chains, variable expansion) — rejected for safety")
        return result

    # Must start with kubectl
    if not command.startswith("kubectl "):
        result.valid = False
        result.errors.append("Command must start with 'kubectl'")
        return result

    parts = command.split()
    if len(parts) < 2:
        result.valid = False
        result.errors.append("Command too short")
        return result

    verb = parts[1]

    # Handle compound verbs like "rollout status"
    if verb == "rollout" and len(parts) > 2:
        verb = "rollout"  # Keep as rollout

    # Validate verb
    if verb not in VALID_VERBS:
        result.valid = False
        result.errors.append(f"Unknown kubectl verb: '{verb}'")
        return result

    # Check if destructive
    if verb in DESTRUCTIVE_VERBS:
        result.is_destructive = True
        result.warnings.append(f"Destructive command: '{verb}' — requires confirmation")

    # Find resource type
    resource_type = None
    for i, part in enumerate(parts[2:], start=2):
        if part.startswith("-"):
            continue
        # Could be resource/name or just resource
        if "/" in part:
            resource_type = part.split("/")[0]
        else:
            resource_type = part
        break

    # Validate resource type
    if resource_type and resource_type.lower() not in VALID_RESOURCE_TYPES:
        # Might be a flag or compound like deployment/name
        pass  # Don't reject, might be a valid custom resource

    # Check namespace flag for namespaced resources
    has_namespace = "-n " in command or "--namespace " in command or "--all-namespaces" in command or "-A" in parts
    if resource_type and resource_type.lower() in NAMESPACED_RESOURCES and not has_namespace:
        result.missing_namespace = True
        result.warnings.append(f"Command targets namespaced resource '{resource_type}' without -n flag")
        # Auto-fix: add namespace if provided
        if default_namespace:
            result.fixed_command = f"{command} -n {default_namespace}"

    # Specific checks
    if verb == "scale" and "--replicas=0" in command:
        result.warnings.append("Scaling to 0 replicas will terminate all pods")

    if verb == "delete" and ("--all" in parts or "-A" in parts):
        result.warnings.append("Deleting all resources — very destructive")

    return result


def add_dry_run(command: str) -> str:
    """Add --dry-run=client flag to a command for safe preview."""
    if "--dry-run" in command:
        return command
    return f"{command} --dry-run=client"


def generate_rollback(command: str) -> Optional[str]:
    """Generate a rollback command if possible."""
    parts = command.split()
    if len(parts) < 3:
        return None

    verb = parts[1]

    if verb == "scale":
        # Can't auto-generate rollback without knowing current state
        return "# Check current replicas first: kubectl get <resource> -o jsonpath='{.spec.replicas}'"

    if verb == "cordon":
        return command.replace("cordon", "uncordon")

    if verb == "drain":
        return command.replace("drain", "uncordon")

    if verb == "taint":
        # Add "-" to remove taint
        return f"{command}-"

    if verb == "rollout" and "undo" not in command:
        # Add undo
        return command.replace("rollout restart", "rollout undo").replace("rollout pause", "rollout resume")

    return None


# ---------------------------------------------------------------------------
# Forbidden commands & safety checks
# ---------------------------------------------------------------------------

FORBIDDEN_COMMANDS = [
    "kubectl delete namespace",
    "kubectl delete node",
    "kubectl delete pvc",
    "kubectl delete pv",
    "kubectl delete clusterrole",
    "kubectl delete clusterrolebinding",
    "kubectl delete crd",
    "kubectl delete storageclass",
    "kubectl replace --force",
]

OWNER_BEHAVIOR = {
    "ReplicaSet": "safe_recreated",
    "DaemonSet": "safe_recreated",
    "StatefulSet": "safe_recreated_with_identity",
    "Job": "may_not_restart",
    "None": "permanent_delete",
}


def check_forbidden(command: str) -> tuple[bool, str]:
    """Return (blocked, reason) if command is forbidden."""
    cmd_lower = command.lower().strip()
    for forbidden in FORBIDDEN_COMMANDS:
        pattern = r'\b' + re.escape(forbidden) + r'\b'
        if re.search(pattern, cmd_lower):
            return True, f"Blocked: '{forbidden}' requires manual execution"
    return False, ""


def simulate_command(command: str, topology: dict, domain_reports: list) -> dict:
    """Simulate cluster impact of a remediation command."""
    parts = command.split()
    verb = parts[1] if len(parts) > 1 else ""
    target = ""
    for p in parts[2:]:
        if not p.startswith("-"):
            target = p
            break

    # Determine action description
    action = verb
    impact = "safe"
    side_effects: list[str] = []
    recovery = ""

    if verb == "delete":
        impact = "destructive"
        # Check if target has an owner controller
        owner = _find_owner(target, topology)
        behavior = OWNER_BEHAVIOR.get(owner, "unknown")
        if behavior == "safe_recreated":
            impact = "safe — controller will recreate"
            recovery = f"{owner} will recreate the resource"
        elif behavior == "safe_recreated_with_identity":
            impact = "caution — StatefulSet will recreate with same identity"
            recovery = "StatefulSet recreates pod with same PVC"
        elif behavior == "may_not_restart":
            impact = "dangerous — Job may not restart"
            side_effects.append("Job pod will not be recreated automatically")
            recovery = "Manual re-run required"
        elif behavior == "permanent_delete":
            impact = "dangerous — no owner controller, permanent delete"
            recovery = "Manual recreation required"
    elif verb in ("drain", "cordon"):
        impact = "caution — node workloads affected"
        side_effects.append("Pods on node will be evicted (drain) or no new pods scheduled (cordon)")
        recovery = f"kubectl uncordon {target}"
    elif verb == "scale":
        if "--replicas=0" in command:
            impact = "dangerous — scaling to zero"
            side_effects.append("All pods terminated")
        else:
            impact = "safe — replica count change"
        recovery = "kubectl scale to previous replica count"
    elif verb == "rollout":
        impact = "safe — rolling update"
        recovery = "kubectl rollout undo"
    elif verb in ("get", "describe", "logs", "top", "explain"):
        impact = "safe — read-only"
    elif verb in ("apply", "patch"):
        impact = "caution — resource mutation"
        recovery = "Revert manifest and re-apply"

    return {
        "action": action,
        "target": target,
        "impact": impact,
        "side_effects": side_effects,
        "recovery": recovery,
    }


def _find_owner(target: str, topology: dict) -> str:
    """Find the owner kind for a resource from topology data."""
    nodes = topology.get("nodes", {})
    # Try direct lookup
    node_data = nodes.get(target, {})
    if isinstance(node_data, dict):
        owner = node_data.get("owner_kind", "")
        if owner:
            return owner
    # Search by partial match
    for key, val in nodes.items():
        if isinstance(val, dict) and target in key:
            owner = val.get("owner_kind", "")
            if owner:
                return owner
    return "None"


def check_replica_safety(command: str, domain_reports: list) -> str:
    """Check if deleting a pod when deployment has replicas=1."""
    if "delete pod" not in command.lower() and "delete po " not in command.lower():
        return "safe"
    # Search domain reports for related deployment with replicas=1
    for report in domain_reports:
        if not isinstance(report, dict):
            continue
        for anomaly in report.get("anomalies", []):
            desc = str(anomaly.get("description", "")).lower()
            if "replicas" in desc and ("1/" in desc or "replicas=1" in desc or "single replica" in desc):
                return "dangerous"
        # Also check raw data if present
        raw = report.get("raw_data", {})
        if isinstance(raw, dict):
            for key, val in raw.items():
                if isinstance(val, dict) and val.get("replicas") == 1:
                    return "dangerous"
    return "caution"


def check_drain_capacity(command: str, topology: dict) -> str:
    """Check if draining node leaves enough capacity."""
    if "drain" not in command.lower() and "cordon" not in command.lower():
        return "safe"
    nodes = topology.get("nodes", {})
    total_nodes = sum(
        1 for k, v in nodes.items()
        if isinstance(v, dict) and v.get("kind", "").lower() == "node"
    )
    if total_nodes <= 2:
        return "dangerous"
    return "caution"


def check_fixes_root_cause(step: dict, hypothesis_selection: dict) -> str:
    """Verify remediation targets root cause, not symptom."""
    root_causes = hypothesis_selection.get("root_causes", [])
    root_resources: set[str] = set()
    for h in root_causes:
        if isinstance(h, dict):
            root_resources.add(h.get("root_resource", ""))

    command = step.get("command", "")
    # Extract target resource from command
    parts = command.split()
    target = ""
    for p in parts[2:]:
        if not p.startswith("-") and "/" in p:
            target = p
            break

    if target and root_resources and target not in root_resources:
        destructive = any(v in command for v in ["delete", "restart", "scale"])
        if destructive:
            return "caution"
    return "safe"


def compute_remediation_confidence(step: dict, hypothesis: dict, simulation: dict, risk: str) -> float:
    """Score how likely this remediation fixes the problem."""
    if not hypothesis or not hypothesis.get("hypothesis_id"):
        return 0.3  # Speculative without hypothesis context
    score = 0.0
    score += hypothesis.get("confidence", 0) * 0.4
    if step.get("source") == "pattern":
        score += 0.3
    if "safe" in simulation.get("impact", ""):
        score += 0.2
    if simulation.get("side_effects"):
        score -= 0.1
    if risk == "safe":
        score += 0.1
    elif risk == "dangerous":
        score -= 0.2
    return max(0.0, min(1.0, score))
