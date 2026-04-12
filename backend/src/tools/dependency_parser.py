import os
import re
import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

MANIFEST_PATTERNS = [
    "requirements.txt", "pyproject.toml", "setup.py", "Pipfile",
    "package.json",
    "go.mod",
    "pom.xml", "build.gradle", "build.gradle.kts",
    "Cargo.toml",
    "*.csproj", "packages.config",
]


@dataclass
class Dependency:
    name: str
    version_spec: str
    source: str
    manifest_file: str
    repo_url: str | None = None
    is_internal: bool = False


class DependencyParser:
    def __init__(self, repo_map: dict[str, str] | None = None):
        self._repo_map = repo_map or {}
        self._internal_names = set(self._repo_map.keys())

    def detect_manifest_files(self, repo_path: str) -> list[str]:
        found = []
        root = Path(repo_path)
        for pattern in MANIFEST_PATTERNS:
            if "*" in pattern:
                found.extend(str(p) for p in root.rglob(pattern))
            else:
                candidate = root / pattern
                if candidate.exists():
                    found.append(str(candidate))
        return found

    def parse(self, repo_path: str) -> list[Dependency]:
        deps = []
        for manifest in self.detect_manifest_files(repo_path):
            name = os.path.basename(manifest)
            try:
                if name == "requirements.txt":
                    deps.extend(self._parse_requirements(manifest))
                elif name == "package.json":
                    deps.extend(self._parse_package_json(manifest))
                elif name == "go.mod":
                    deps.extend(self._parse_go_mod(manifest))
                elif name == "Cargo.toml":
                    deps.extend(self._parse_cargo_toml(manifest))
                elif name in ("pom.xml", "build.gradle", "build.gradle.kts"):
                    deps.extend(self._parse_jvm(manifest))
            except Exception as e:
                logger.warning(f"Failed to parse {manifest}: {e}")
        for dep in deps:
            dep.is_internal = self._is_internal(dep.name)
            if dep.is_internal:
                dep.repo_url = self._repo_map.get(dep.name)
        return deps

    def _is_internal(self, name: str) -> bool:
        clean = name.split("/")[-1].lower().replace("-", "_").replace(".", "_")
        for internal in self._internal_names:
            if clean == internal.lower().replace("-", "_"):
                return True
        return False

    def _parse_requirements(self, path: str) -> list[Dependency]:
        deps = []
        for line in Path(path).read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            match = re.match(r"^([a-zA-Z0-9_.-]+)\s*([>=<!\[\]~,.*\d]*)", line)
            if match:
                deps.append(Dependency(name=match.group(1), version_spec=match.group(2).strip(),
                                       source="pypi", manifest_file=path))
        return deps

    def _parse_package_json(self, path: str) -> list[Dependency]:
        deps = []
        data = json.loads(Path(path).read_text())
        for section in ("dependencies", "devDependencies"):
            for name, version in data.get(section, {}).items():
                deps.append(Dependency(name=name, version_spec=version,
                                       source="npm", manifest_file=path))
        return deps

    def _parse_go_mod(self, path: str) -> list[Dependency]:
        deps = []
        for line in Path(path).read_text().splitlines():
            match = re.match(r"^\s*require\s+(\S+)\s+(\S+)", line)
            if match:
                deps.append(Dependency(name=match.group(1), version_spec=match.group(2),
                                       source="go", manifest_file=path))
            match2 = re.match(r"^\s+(\S+)\s+(v\S+)", line)
            if match2:
                deps.append(Dependency(name=match2.group(1), version_spec=match2.group(2),
                                       source="go", manifest_file=path))
        return deps

    def _parse_cargo_toml(self, path: str) -> list[Dependency]:
        deps = []
        in_deps = False
        for line in Path(path).read_text().splitlines():
            if line.strip() == "[dependencies]":
                in_deps = True
                continue
            if line.strip().startswith("[") and in_deps:
                break
            if in_deps:
                match = re.match(r'^(\S+)\s*=\s*"([^"]*)"', line.strip())
                if match:
                    deps.append(Dependency(name=match.group(1), version_spec=match.group(2),
                                           source="crates", manifest_file=path))
        return deps

    def _parse_jvm(self, path: str) -> list[Dependency]:
        deps = []
        content = Path(path).read_text()
        if path.endswith(".xml"):
            for match in re.finditer(r"<groupId>([^<]+)</groupId>\s*<artifactId>([^<]+)</artifactId>\s*<version>([^<]+)</version>", content):
                deps.append(Dependency(name=f"{match.group(1)}:{match.group(2)}", version_spec=match.group(3),
                                       source="maven", manifest_file=path))
        else:
            for match in re.finditer(r"implementation\s+['\"]([^'\"]+)['\"]", content):
                parts = match.group(1).split(":")
                name = ":".join(parts[:2]) if len(parts) >= 2 else parts[0]
                version = parts[2] if len(parts) >= 3 else ""
                deps.append(Dependency(name=name, version_spec=version,
                                       source="maven", manifest_file=path))
        return deps
