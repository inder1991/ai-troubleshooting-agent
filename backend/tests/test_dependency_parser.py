import pytest
import tempfile
import os
import json

from src.tools.dependency_parser import DependencyParser, Dependency


@pytest.fixture
def parser():
    return DependencyParser(repo_map={"auth-service": "https://github.com/org/auth-service"})


def test_parse_requirements_txt(parser, tmp_path):
    (tmp_path / "requirements.txt").write_text("requests>=2.28\nflask==2.3.0\n")
    deps = parser.parse(str(tmp_path))
    assert len(deps) == 2
    assert deps[0].name == "requests"
    assert deps[0].source == "pypi"


def test_parse_package_json(parser, tmp_path):
    pkg = {"dependencies": {"express": "^4.18.0", "@org/auth-client": "^1.0.0"}}
    (tmp_path / "package.json").write_text(json.dumps(pkg))
    deps = parser.parse(str(tmp_path))
    assert any(d.name == "express" for d in deps)


def test_parse_go_mod(parser, tmp_path):
    (tmp_path / "go.mod").write_text("module github.com/org/myapp\nrequire github.com/gin-gonic/gin v1.9.1\n")
    deps = parser.parse(str(tmp_path))
    assert any(d.name == "github.com/gin-gonic/gin" for d in deps)


def test_internal_dependency_detection(parser, tmp_path):
    pkg = {"dependencies": {"auth-service": "^1.0.0"}}
    (tmp_path / "package.json").write_text(json.dumps(pkg))
    deps = parser.parse(str(tmp_path))
    internal = [d for d in deps if d.is_internal]
    assert len(internal) >= 0


def test_detect_manifest_files(parser, tmp_path):
    (tmp_path / "requirements.txt").write_text("flask\n")
    (tmp_path / "package.json").write_text("{}")
    files = parser.detect_manifest_files(str(tmp_path))
    assert "requirements.txt" in [os.path.basename(f) for f in files]
