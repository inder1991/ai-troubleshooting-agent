"""Phase 2 Task 6: every shipped contract has a registered runner, and
every registered runner is constructible and exposes ``run``."""

from __future__ import annotations

from src.contracts.service import init_registry as init_contracts
from src.workflows.runners import get_runner_registry, init_runners


def test_every_contract_has_runner() -> None:
    contracts = init_contracts()
    init_runners()
    runners = get_runner_registry()
    missing = runners.verify_covers(contracts)
    assert missing == [], f"missing runners: {missing}"


def test_every_registered_runner_is_constructible() -> None:
    contracts = init_contracts()
    init_runners()
    runners = get_runner_registry()
    for c in contracts.list_all_versions():
        runner = runners.get(c.name, c.version)
        assert hasattr(runner, "run"), (
            f"runner for {c.name} v{c.version} has no 'run' method"
        )
