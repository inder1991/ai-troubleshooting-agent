"""Process-wide ``ContractRegistry`` accessor. Initialized once at app
startup; looked up synchronously everywhere else.

Phase 1 Task 7.
"""

from __future__ import annotations

from pathlib import Path

from .registry import ContractRegistry

_DEFAULT_MANIFESTS_DIR = Path(__file__).parent.parent / "agents" / "manifests"

_registry: ContractRegistry | None = None


def init_registry(manifests_dir: Path | None = None) -> ContractRegistry:
    """Load manifests from ``manifests_dir`` (default: shipped directory)
    and install the result as the process singleton."""
    global _registry
    target = manifests_dir if manifests_dir is not None else _DEFAULT_MANIFESTS_DIR
    reg = ContractRegistry()
    reg.load_all(target)
    _registry = reg
    return reg


def get_registry() -> ContractRegistry:
    if _registry is None:
        raise RuntimeError(
            "ContractRegistry not initialized — call init_registry() at startup"
        )
    return _registry
