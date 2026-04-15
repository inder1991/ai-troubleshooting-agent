"""ContractRegistry singleton accessor."""

import pytest

from src.contracts import service as contract_service
from src.contracts.service import get_registry, init_registry


def test_get_registry_before_init_raises():
    # Fresh module state — clear any prior init.
    contract_service._registry = None
    with pytest.raises(RuntimeError):
        get_registry()


def test_registry_is_singleton():
    init_registry()
    r1 = get_registry()
    r2 = get_registry()
    assert r1 is r2


def test_registry_has_log_agent():
    init_registry()
    r = get_registry()
    assert r.get("log_agent", version=1).name == "log_agent"
