"""Tests for store write error handling."""
import inspect


AGENT_MODULES = [
    "src.agents.cluster.ctrl_plane_agent",
    "src.agents.cluster.node_agent",
    "src.agents.cluster.network_agent",
    "src.agents.cluster.storage_agent",
    "src.agents.cluster.rbac_agent",
    "src.agents.cluster.synthesizer",
]

BARE_PATTERN = "ensure_future(store.log_llm_call"


def test_ensure_future_has_error_callback():
    """No call-site should use bare ensure_future(store.log_llm_call(...)) -- must use _safe_store_write."""
    import importlib
    import re

    violations = []
    for mod_name in AGENT_MODULES:
        mod = importlib.import_module(mod_name)
        source = inspect.getsource(mod)
        # Remove the _safe_store_write helper definition so we only check call sites
        source_without_helper = re.sub(
            r"def _safe_store_write\b.*?(?=\ndef |\nclass |\n[A-Z_]+ =|\Z)",
            "",
            source,
            flags=re.DOTALL,
        )
        if BARE_PATTERN in source_without_helper:
            violations.append(mod_name)

    assert not violations, (
        f"These modules have bare ensure_future without error handling: {violations}"
    )


def test_safe_store_write_exists():
    """Each agent module must define or import _safe_store_write."""
    import importlib

    missing = []
    for mod_name in AGENT_MODULES:
        mod = importlib.import_module(mod_name)
        if not hasattr(mod, "_safe_store_write"):
            missing.append(mod_name)

    assert not missing, (
        f"These modules are missing _safe_store_write: {missing}"
    )
