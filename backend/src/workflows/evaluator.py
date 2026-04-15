from __future__ import annotations

from typing import Any


class SkippedRefError(Exception):
    """Raised when a ref targets a node whose status is SKIPPED."""


class MissingRefError(Exception):
    """Raised when a ref targets a node that hasn't run or a missing path."""


def _get_path(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict):
            if part not in cur:
                raise MissingRefError(f"missing path segment {part!r}")
            cur = cur[part]
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError) as e:
                raise MissingRefError(f"bad list index {part!r}: {e}")
        else:
            raise MissingRefError(
                f"cannot descend into {type(cur).__name__} at {part!r}"
            )
    return cur


def evaluate(expr: Any, state: dict) -> Any:
    if isinstance(expr, dict) and "literal" in expr:
        return expr["literal"]
    if isinstance(expr, dict) and "ref" in expr:
        r = expr["ref"]
        src = r["from"]
        if src == "input":
            return _get_path(state.get("input", {}), r["path"])
        if src == "env":
            return _get_path(state.get("env", {}), r["path"])
        if src == "node":
            node_id = r["node_id"]
            nodes = state.get("nodes", {})
            if node_id not in nodes:
                raise MissingRefError(f"node {node_id!r} has not run")
            node = nodes[node_id]
            if node.get("status") == "SKIPPED":
                raise SkippedRefError(f"node {node_id!r} was skipped")
            if node.get("status") != "SUCCESS":
                raise MissingRefError(
                    f"node {node_id!r} status={node.get('status')}"
                )
            return _get_path({"output": node.get("output")}, r["path"])
        raise ValueError(f"unknown ref source {src!r}")
    if isinstance(expr, dict) and "op" in expr:
        op = expr["op"]
        args = expr["args"]
        if op == "coalesce":
            for a in args:
                try:
                    v = evaluate(a, state)
                    if v is not None:
                        return v
                except (MissingRefError, SkippedRefError):
                    continue
            return None
        if op == "concat":
            return "".join(str(evaluate(a, state)) for a in args)
        if op == "eq":
            return evaluate(args[0], state) == evaluate(args[1], state)
        if op == "in":
            return evaluate(args[0], state) in evaluate(args[1], state)
        if op == "exists":
            try:
                evaluate(args[0], state)
                return True
            except (MissingRefError, SkippedRefError):
                return False
        if op == "and":
            return all(evaluate(a, state) for a in args)
        if op == "or":
            return any(evaluate(a, state) for a in args)
        if op == "not":
            return not evaluate(args[0], state)
        raise ValueError(f"unknown op {op}")
    if isinstance(expr, dict):
        return {k: evaluate(v, state) for k, v in expr.items()}
    if isinstance(expr, list):
        return [evaluate(x, state) for x in expr]
    return expr
