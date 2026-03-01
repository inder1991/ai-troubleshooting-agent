"""Parse @[kind:namespace/name] inline resource references from LLM-generated text."""
import re
from src.models.schemas import ResourceRef

# Matches @[kind:namespace/name] or @[kind:name]
_RESOURCE_REF_PATTERN = re.compile(
    r'@\[([a-z_]+):(?:([a-z0-9][a-z0-9._-]*)/)?'
    r'([a-z0-9][a-z0-9._-]*)\]',
    re.IGNORECASE,
)

_VALID_KINDS = frozenset({
    "pod", "deployment", "service", "configmap", "pvc", "node", "ingress",
    "replicaset", "namespace", "secret", "statefulset", "daemonset", "job", "cronjob",
    # OpenShift
    "deploymentconfig", "route", "buildconfig", "imagestream",
})


def extract_resource_refs(text: str, default_namespace: str | None = None) -> list[ResourceRef]:
    """Extract all @[kind:namespace/name] references from text.

    Args:
        text: LLM-generated text containing inline references.
        default_namespace: Fallback namespace when short format @[kind:name] is used.

    Returns:
        Deduplicated list of ResourceRef objects.
    """
    seen: set[tuple[str, str, str | None]] = set()
    refs: list[ResourceRef] = []

    for match in _RESOURCE_REF_PATTERN.finditer(text):
        kind = match.group(1).lower()
        namespace = match.group(2) or default_namespace
        name = match.group(3)

        if kind not in _VALID_KINDS:
            continue

        key = (kind, name, namespace)
        if key in seen:
            continue
        seen.add(key)

        refs.append(ResourceRef(type=kind, name=name, namespace=namespace))

    return refs


def strip_resource_ref_syntax(text: str) -> str:
    """Remove @[kind:ns/name] syntax, leaving just the resource name.

    Example: 'Pod @[pod:default/auth-5b6q] crashed' -> 'Pod auth-5b6q crashed'
    """
    def _replace(match: re.Match) -> str:
        return match.group(3)  # Just the name

    return _RESOURCE_REF_PATTERN.sub(_replace, text)
