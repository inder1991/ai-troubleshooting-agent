"""Utility functions for code agent — extracted for testability."""

import fnmatch
import re


def detect_repo_type(file_tree: list[str]) -> str:
    infra_markers = {"Chart.yaml", "kustomization.yaml", "Dockerfile", "docker-compose.yml"}
    has_infra = any(f.split("/")[-1] in infra_markers for f in file_tree)
    has_tf = any(f.endswith(".tf") for f in file_tree)
    has_k8s_manifests = sum(1 for f in file_tree
        if f.endswith(('.yaml', '.yml'))
        and any(d in f for d in ['deploy', 'k8s', 'manifests', 'charts'])) > 2
    has_app_code = any(f.endswith(('.py', '.js', '.ts', '.java', '.go')) for f in file_tree)

    is_infra = has_infra or has_tf or has_k8s_manifests
    if is_infra and has_app_code:
        return "monorepo"
    if is_infra:
        return "infrastructure"
    return "application"


# ---------------------------------------------------------------------------
# Infra file type detection
# ---------------------------------------------------------------------------

# Maps infra type -> (list of filename glob patterns, list of content patterns)
# Content patterns are checked against the first 512 bytes of the file when
# the filename alone is not conclusive (e.g. generic *.yaml files).
INFRA_FILE_PATTERNS: dict[str, dict] = {
    "helm_chart_metadata": {
        "filename_globs": ["Chart.yaml", "Chart.yml"],
        "content_patterns": [],
        "analysis_hints": [
            "Check 'apiVersion' (v1 vs v2) and 'type' (application vs library)",
            "Review 'appVersion' vs 'version' — mismatches indicate stale chart packaging",
            "Verify 'dependencies' entries have pinned 'version' and correct 'repository' URLs",
            "Look for missing or overly broad 'keywords' and 'maintainers' fields",
        ],
    },
    "helm_values": {
        "filename_globs": ["values.yaml", "values.yml", "values-*.yaml", "values-*.yml"],
        "content_patterns": [],
        "analysis_hints": [
            "Check image 'repository' and 'tag' — avoid 'latest'; prefer digest-pinned or semver tags",
            "Verify resource 'requests' and 'limits' (cpu/memory) are set and reasonable",
            "Look for 'replicaCount' — ensure >= 2 for HA; check 'autoscaling.enabled'",
            "Review 'livenessProbe' and 'readinessProbe' — missing probes cause silent failures",
            "Check 'securityContext' — 'runAsNonRoot: true', 'readOnlyRootFilesystem: true'",
            "Confirm 'ingress.enabled' and TLS settings match environment expectations",
            "Look for hardcoded secrets/passwords — should reference Secrets, not plain values",
        ],
    },
    "helm_template": {
        "filename_globs": ["templates/*.yaml", "templates/*.yml", "templates/*.tpl"],
        "content_patterns": [r"\{\{[\s-]*\.Values\.", r"\{\{[\s-]*include\s+", r"\{\{[\s-]*template\s+"],
        "analysis_hints": [
            "Check all '.Values.*' references have 'default' fallbacks to prevent nil panics",
            "Verify 'resources:' block is templated from values, not hardcoded",
            "Look for missing 'namespace:' on ClusterRole bindings",
            "Review '{{- if .Values.*}}' guards — ensure optional sections degrade gracefully",
            "Check 'imagePullPolicy' — 'Always' causes rate-limit issues; prefer 'IfNotPresent'",
            "Ensure 'securityContext' is propagated from values, not omitted in templates",
        ],
    },
    "terraform": {
        "filename_globs": ["*.tf"],
        "content_patterns": [],
        "analysis_hints": [
            "Check 'resource' blocks for missing 'lifecycle { prevent_destroy = true }' on stateful resources",
            "Review IAM policies — look for overly permissive '*' actions or resources",
            "Verify 'count' and 'for_each' usages — changing from one to the other destroys resources",
            "Check provider version constraints — unpinned providers cause drift",
            "Look for hardcoded region/account IDs — should use variables or data sources",
            "Verify VPC/subnet CIDR ranges don't overlap with existing infrastructure",
            "Check 'depends_on' for missing explicit dependencies that could cause race conditions",
        ],
    },
    "terraform_vars": {
        "filename_globs": ["*.tfvars", "*.tfvars.json"],
        "content_patterns": [],
        "analysis_hints": [
            "Verify sensitive variables (passwords, tokens) are not committed — should use TF_VAR_ env vars or secrets manager",
            "Check that variable values match expected types and constraints defined in variables.tf",
            "Look for environment-specific values that differ from defaults in unexpected ways",
        ],
    },
    "kubernetes_manifest": {
        # Generic *.yaml — only classified if content signals match
        "filename_globs": ["*.yaml", "*.yml"],
        "content_patterns": [r"^apiVersion:", r"^kind:"],
        "analysis_hints": [
            "Check 'resources.requests' and 'resources.limits' — missing limits cause node OOM kills",
            "Verify 'securityContext.runAsNonRoot: true' and 'allowPrivilegeEscalation: false'",
            "Review 'imagePullPolicy' — avoid 'Always' on production; use digest-pinned images",
            "Check 'livenessProbe' and 'readinessProbe' thresholds — too aggressive causes restart loops",
            "Look for 'hostNetwork: true' or 'hostPID: true' — security red flags",
            "Verify 'PodDisruptionBudget' exists for critical workloads",
            "Check 'nodeSelector' and 'tolerations' match actual cluster node labels",
            "Review RBAC 'ClusterRole'/'Role' rules — least-privilege principle",
            "For 'PersistentVolumeClaim': check storageClass, accessMode, and capacity",
            "For 'HorizontalPodAutoscaler': verify minReplicas >= 2 and targetCPU is realistic",
        ],
    },
    "dockerfile": {
        "filename_globs": ["Dockerfile", "Dockerfile.*", "*.dockerfile", "*.Dockerfile"],
        "content_patterns": [r"^FROM\s+", r"^RUN\s+", r"^ENTRYPOINT\s+"],
        "analysis_hints": [
            "Check base image — avoid 'latest' tag; use specific digest or semver",
            "Look for 'USER' instruction — running as root is a security risk",
            "Verify multi-stage build separates build and runtime layers to minimize image size",
            "Check 'COPY'/'ADD' patterns — avoid 'COPY . .' which includes secrets/.git",
            "Review 'RUN apt-get' — pin package versions, combine into single layer, clean cache",
            "Look for hardcoded secrets in ENV or ARG instructions",
            "Verify 'HEALTHCHECK' instruction is present for container health signaling",
            "Check 'EXPOSE' matches actual application port",
            "Look for 'ADD' with URLs — prefer 'RUN curl' for explicit checksum verification",
        ],
    },
}

# Ordered list of types to try when content-sniffing is needed.
# Types with filename_globs that are conclusive (no content_patterns) are
# matched first to avoid unnecessary content reads.
_CONCLUSIVE_TYPES = {
    "helm_chart_metadata",
    "helm_values",
    "helm_template",
    "terraform",
    "terraform_vars",
}


def classify_infra_file(file_path: str, content_snippet: str = "") -> str | None:
    """Classify a file as an infra type, or return None if not infra.

    Args:
        file_path: Relative path of the file (e.g. 'helm/templates/deployment.yaml').
        content_snippet: First ~512 bytes of the file content (optional). Needed to
                         distinguish generic YAML files (K8s manifests vs other YAML).

    Returns:
        One of the keys in INFRA_FILE_PATTERNS, or None if not an infra file.
    """
    filename = file_path.split("/")[-1]

    # Pass 1: types with conclusive filename patterns (no content sniffing needed)
    for infra_type, spec in INFRA_FILE_PATTERNS.items():
        if infra_type not in _CONCLUSIVE_TYPES:
            continue
        for glob_pattern in spec["filename_globs"]:
            if fnmatch.fnmatch(filename, glob_pattern):
                return infra_type

    # Pass 2: Dockerfile — check filename before content because no apiVersion present
    for glob_pattern in INFRA_FILE_PATTERNS["dockerfile"]["filename_globs"]:
        if fnmatch.fnmatch(filename, glob_pattern):
            if not content_snippet or any(
                re.search(p, content_snippet, re.MULTILINE)
                for p in INFRA_FILE_PATTERNS["dockerfile"]["content_patterns"]
            ):
                return "dockerfile"

    # Pass 3: kubernetes_manifest — generic YAML, need content to confirm
    if filename.endswith((".yaml", ".yml")) and content_snippet:
        k8s_spec = INFRA_FILE_PATTERNS["kubernetes_manifest"]
        if all(
            re.search(p, content_snippet, re.MULTILINE)
            for p in k8s_spec["content_patterns"]
        ):
            return "kubernetes_manifest"

    return None


def get_infra_hints_for_files(
    file_paths: list[str],
    file_contents: dict[str, str] | None = None,
) -> dict[str, list[str]]:
    """Return {file_path: [hint, ...]} for every file that classifies as infra.

    Args:
        file_paths: List of relative file paths.
        file_contents: Optional dict mapping file_path -> content string. When
                       provided, the first 512 chars are used for content-sniffing.
    """
    result: dict[str, list[str]] = {}
    contents = file_contents or {}
    for fp in file_paths:
        snippet = contents.get(fp, "")[:512]
        infra_type = classify_infra_file(fp, snippet)
        if infra_type:
            result[fp] = INFRA_FILE_PATTERNS[infra_type]["analysis_hints"]
    return result
