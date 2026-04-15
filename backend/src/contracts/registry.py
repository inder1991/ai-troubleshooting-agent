"""Manifest registry — loads YAML files from a directory and exposes
``AgentContract`` objects keyed by ``(name, version)``.

Phase 1 Task 3. Loader is all-or-nothing: any validation, parse, or
duplicate-key error aborts the load with a single ``ManifestLoadError``
carrying the aggregated messages. This keeps startup failures loud and
prevents a partially-populated registry.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import yaml
from pydantic import ValidationError

from .models import AgentContract


class ManifestLoadError(Exception):
    """Raised when one or more manifests in a directory fail to load."""


class ContractRegistry:
    def __init__(self) -> None:
        self._by_key: dict[tuple[str, int], AgentContract] = {}

    def load_all(self, manifests_dir: Path) -> None:
        errors: list[str] = []
        new_index: dict[tuple[str, int], AgentContract] = {}

        for path in sorted(Path(manifests_dir).glob("*.yaml")):
            try:
                raw = yaml.safe_load(path.read_text())
            except yaml.YAMLError as e:
                errors.append(f"{path.name}: YAML parse error: {e}")
                continue

            if not isinstance(raw, dict):
                errors.append(f"{path.name}: YAML root must be a mapping")
                continue

            try:
                contract = AgentContract.model_validate(raw)
            except ValidationError as e:
                errors.append(f"{path.name}: {e}")
                continue

            key = (contract.name, contract.version)
            if key in new_index:
                errors.append(
                    f"duplicate manifest for {contract.name} v{contract.version} in {path.name}"
                )
                continue
            new_index[key] = contract

        if errors:
            raise ManifestLoadError(" | ".join(errors))

        self._by_key = new_index

    def get(self, name: str, *, version: int) -> AgentContract:
        return self._by_key[(name, version)]

    def list(self) -> list[AgentContract]:
        """Latest version per agent name, sorted by name."""
        by_name: dict[str, AgentContract] = {}
        for (name, version), contract in self._by_key.items():
            current = by_name.get(name)
            if current is None or version > current.version:
                by_name[name] = contract
        return sorted(by_name.values(), key=lambda c: c.name)

    def list_all_versions(self) -> Iterable[AgentContract]:
        return list(self._by_key.values())
