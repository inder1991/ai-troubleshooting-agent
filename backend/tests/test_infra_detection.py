import pytest
from src.agents.code_agent_utils import detect_repo_type


class TestInfraDetection:
    def test_helm_chart(self):
        files = ["Chart.yaml", "values.yaml", "templates/deployment.yaml"]
        assert detect_repo_type(files) == "infrastructure"

    def test_terraform(self):
        files = ["main.tf", "variables.tf", "outputs.tf"]
        assert detect_repo_type(files) == "infrastructure"

    def test_kustomize(self):
        files = ["kustomization.yaml", "base/deployment.yaml"]
        assert detect_repo_type(files) == "infrastructure"

    def test_application_repo(self):
        files = ["src/main.py", "tests/test_main.py", "requirements.txt"]
        assert detect_repo_type(files) == "application"

    def test_monorepo(self):
        files = ["src/main.py", "charts/Chart.yaml", "deploy/k8s/deployment.yaml"]
        assert detect_repo_type(files) == "monorepo"
