from __future__ import annotations

import pytest

from src.workflows.evaluator import (
    evaluate,
    SkippedRefError,
    MissingRefError,
)


def test_literal():
    assert evaluate({"literal": 7}, {}) == 7


def test_ref_input_path():
    state = {"input": {"x": {"y": 42}}}
    assert evaluate({"ref": {"from": "input", "path": "x.y"}}, state) == 42


def test_ref_node_output_path():
    state = {
        "nodes": {
            "a": {"status": "SUCCESS", "output": {"svc": "billing"}},
        }
    }
    expr = {"ref": {"from": "node", "node_id": "a", "path": "output.svc"}}
    assert evaluate(expr, state) == "billing"


def test_ref_skipped_raises():
    state = {"nodes": {"a": {"status": "SKIPPED", "output": None}}}
    with pytest.raises(SkippedRefError):
        evaluate({"ref": {"from": "node", "node_id": "a", "path": "output.x"}}, state)


def test_ref_missing_node_raises():
    with pytest.raises(MissingRefError):
        evaluate({"ref": {"from": "node", "node_id": "a", "path": "output.x"}}, {"nodes": {}})


def test_ref_missing_path_raises():
    state = {"nodes": {"a": {"status": "SUCCESS", "output": {"svc": "b"}}}}
    with pytest.raises(MissingRefError):
        evaluate({"ref": {"from": "node", "node_id": "a", "path": "output.missing"}}, state)


def test_coalesce_with_null_then_literal():
    # first ref missing, second literal chosen
    state = {"nodes": {}}
    expr = {
        "op": "coalesce",
        "args": [
            {"ref": {"from": "node", "node_id": "ghost", "path": "output.x"}},
            {"literal": "def"},
        ],
    }
    assert evaluate(expr, state) == "def"


def test_eq_literals():
    assert evaluate({"op": "eq", "args": [{"literal": 1}, {"literal": 1}]}, {}) is True
    assert evaluate({"op": "eq", "args": [{"literal": 1}, {"literal": 2}]}, {}) is False


def test_and_with_eq_and_not():
    expr = {
        "op": "and",
        "args": [
            {"op": "eq", "args": [{"literal": 1}, {"literal": 1}]},
            {"op": "not", "args": [{"literal": False}]},
        ],
    }
    assert evaluate(expr, {}) is True


def test_concat_strings():
    assert evaluate({"op": "concat", "args": [{"literal": "a"}, {"literal": 1}]}, {}) == "a1"


def test_in_operator():
    state = {"input": {"list": [1, 2, 3]}}
    assert evaluate(
        {"op": "in", "args": [{"literal": 2}, {"ref": {"from": "input", "path": "list"}}]},
        state,
    ) is True


def test_exists_operator():
    state = {"input": {"x": 1}}
    assert (
        evaluate(
            {"op": "exists", "args": [{"ref": {"from": "input", "path": "x"}}]}, state
        )
        is True
    )
    assert (
        evaluate(
            {"op": "exists", "args": [{"ref": {"from": "input", "path": "missing"}}]},
            state,
        )
        is False
    )


def test_ref_env():
    assert evaluate({"ref": {"from": "env", "path": "FOO"}}, {"env": {"FOO": "bar"}}) == "bar"
