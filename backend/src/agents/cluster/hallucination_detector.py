"""Anti-hallucination controls for cluster diagnostic findings."""

from __future__ import annotations
import re
from typing import Optional
from src.utils.logger import get_logger

logger = get_logger(__name__)


def extract_resource_refs(text: str) -> list[str]:
    """Extract K8s resource references from finding text."""
    refs = []
    # Match patterns like: pod/name, deployment/name, node/name, namespace/name
    pattern = r'\b(pod|deployment|service|node|namespace|pvc|statefulset|daemonset|job|cronjob|hpa|configmap|secret|ingress)/([a-z0-9][-a-z0-9.]*[a-z0-9])'
    for match in re.finditer(pattern, text, re.IGNORECASE):
        refs.append(f"{match.group(1)}/{match.group(2)}")
    return refs


class HallucinationDetector:
    """Validates LLM findings against known cluster resources."""

    def __init__(self, known_resources: set[str] | None = None):
        self.known_resources = known_resources or set()

    def add_known_resources(self, resources: set[str]) -> None:
        """Add resources discovered from topology or API queries."""
        self.known_resources.update(resources)

    def build_known_set_from_topology(self, topology: dict) -> None:
        """Build known resource set from topology snapshot."""
        nodes = topology.get("nodes", {})
        for key, node_data in nodes.items():
            self.known_resources.add(key)
            if isinstance(node_data, dict):
                kind = node_data.get("kind", "")
                name = node_data.get("name", "")
                ns = node_data.get("namespace", "")
                if kind and name:
                    self.known_resources.add(f"{kind}/{name}")
                    if ns:
                        self.known_resources.add(f"{kind}/{ns}/{name}")

    def validate_finding(self, finding: dict) -> tuple[bool, str]:
        """Check if finding references real K8s resources.

        Returns (is_valid, reason).
        """
        if not self.known_resources:
            return True, "no_known_resources_to_validate_against"

        description = finding.get("description", "")
        evidence_ref = finding.get("evidence_ref", "")

        # Extract references from description
        referenced = extract_resource_refs(description)
        if evidence_ref:
            referenced.extend(extract_resource_refs(evidence_ref))

        for ref in referenced:
            # Check if this resource (or a close match) exists
            if ref not in self.known_resources:
                # Try partial matching (kind/name without namespace)
                parts = ref.split("/")
                partial_match = any(
                    ref in known or known.endswith(f"/{parts[-1]}")
                    for known in self.known_resources
                )
                if not partial_match:
                    logger.warning(
                        "Hallucination detected: finding references non-existent resource %s",
                        ref, extra={"action": "hallucination_detected"}
                    )
                    return False, f"references non-existent resource: {ref}"

        return True, "valid"

    def validate_kubectl_command(self, command: str) -> tuple[bool, str]:
        """Check if kubectl command references real resources."""
        # Extract resource references from command
        # Pattern: kubectl <verb> <type>/<name> or kubectl <verb> <type> <name>
        parts = command.split()
        if len(parts) < 3:
            return True, "too_short_to_validate"

        # Look for type/name patterns
        for part in parts[2:]:
            if "/" in part and not part.startswith("-"):
                resource_type, name = part.split("/", 1)
                ref = f"{resource_type}/{name}"
                if self.known_resources and ref not in self.known_resources:
                    partial = any(
                        known.endswith(f"/{name}") for known in self.known_resources
                    )
                    if not partial:
                        return False, f"command references unknown resource: {ref}"

        return True, "valid"
