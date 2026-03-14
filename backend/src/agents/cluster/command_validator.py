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
