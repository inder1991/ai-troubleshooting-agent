from __future__ import annotations

import pytest


def test_assistant_tools_capability_enum_includes_troubleshoot_pipeline():
    """troubleshoot_pipeline must be advertised by start_investigation JSON schema."""
    from src.agents.assistant.tools import ASSISTANT_TOOLS

    start_tool = next(
        (t for t in ASSISTANT_TOOLS if t["name"] == "start_investigation"),
        None,
    )
    assert start_tool is not None, "start_investigation tool not registered"
    enum = start_tool["input_schema"]["properties"]["capability"]["enum"]
    assert "troubleshoot_pipeline" in enum


def test_routes_v4_has_pipeline_capability_branch():
    """Source-level guard: routes_v4.py must contain the capability branch."""
    from pathlib import Path
    src = Path(__file__).parent.parent / "src" / "api" / "routes_v4.py"
    text = src.read_text()
    assert 'capability == "troubleshoot_pipeline"' in text
    assert '"capability": "troubleshoot_pipeline"' in text


def test_pipeline_agent_importable_via_capability_name():
    """PipelineAgent is reachable (imported from src path) so the session can dispatch later."""
    from src.agents.pipeline_agent import PipelineAgent, PipelineCapabilityInput
    assert PipelineAgent is not None
    inp = PipelineCapabilityInput(cluster_id="c1")
    assert inp.cluster_id == "c1"
    assert inp.time_window_minutes == 60
