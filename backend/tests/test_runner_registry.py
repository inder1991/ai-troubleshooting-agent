"""Tests for ``AgentRunnerRegistry`` — Phase 2 Task 5."""

from __future__ import annotations

from typing import Any

import pytest

from src.contracts.registry import ContractRegistry
from src.contracts.service import init_registry as init_contracts
from src.workflows.runners.registry import AgentRunnerRegistry


class _StubRunner:
    async def run(
        self, inputs: dict[str, Any], *, context: dict[str, Any]
    ) -> dict[str, Any]:
        return {"ok": True}


def test_register_and_get_roundtrip() -> None:
    reg = AgentRunnerRegistry()
    runner = _StubRunner()
    reg.register("log_agent", 1, runner)
    assert reg.get("log_agent", 1) is runner
    assert reg.covers("log_agent", 1) is True


def test_get_missing_raises_keyerror() -> None:
    reg = AgentRunnerRegistry()
    with pytest.raises(KeyError):
        reg.get("does_not_exist", 1)


def test_verify_covers_reports_missing() -> None:
    contracts: ContractRegistry = init_contracts()
    reg = AgentRunnerRegistry()
    # Empty registry — every contract is missing.
    missing_all = reg.verify_covers(contracts)
    expected = [(c.name, c.version) for c in contracts.list_all_versions()]
    assert sorted(missing_all) == sorted(expected)

    # Register all → empty list.
    for name, version in expected:
        reg.register(name, version, _StubRunner())
    assert reg.verify_covers(contracts) == []
