"""AgentContract Pydantic model validation."""

import pytest
from pydantic import ValidationError

from backend.src.contracts.models import AgentContract

MINIMAL = {
    "name": "test_agent",
    "version": 1,
    "description": "desc",
    "category": "infrastructure",
    "inputs": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
    "outputs": {"type": "object", "properties": {"y": {"type": "string"}}, "required": ["y"]},
    "trigger_examples": ["example one", "example two"],
    "retry_on": [],
    "timeout_seconds": 30,
}


def test_valid_manifest_loads():
    c = AgentContract(**MINIMAL)
    assert c.name == "test_agent"
    assert c.version == 1
    assert c.input_schema == MINIMAL["inputs"]
    assert c.output_schema == MINIMAL["outputs"]


def test_requires_two_trigger_examples():
    bad = {**MINIMAL, "trigger_examples": ["only one"]}
    with pytest.raises(ValidationError):
        AgentContract(**bad)


def test_requires_input_and_output_schema():
    for field in ("inputs", "outputs"):
        bad = {k: v for k, v in MINIMAL.items() if k != field}
        with pytest.raises(ValidationError):
            AgentContract(**bad)


def test_version_must_be_positive_int():
    bad = {**MINIMAL, "version": 0}
    with pytest.raises(ValidationError):
        AgentContract(**bad)


def test_timeout_positive():
    bad = {**MINIMAL, "timeout_seconds": 0}
    with pytest.raises(ValidationError):
        AgentContract(**bad)


def test_deprecated_versions_optional():
    c = AgentContract(**MINIMAL, deprecated_versions=[0])
    assert c.deprecated_versions == [0]


def test_schema_must_be_object_type():
    bad = {**MINIMAL, "inputs": {"type": "string"}}
    with pytest.raises(ValidationError):
        AgentContract(**bad)


def test_extra_fields_forbidden():
    bad = {**MINIMAL, "unknown_key": "x"}
    with pytest.raises(ValidationError):
        AgentContract(**bad)
