"""Utility functions for code agent — extracted for testability."""


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
