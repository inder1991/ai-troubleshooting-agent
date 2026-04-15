from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.contracts.registry import ContractRegistry
from src.workflows.compiler import CompiledWorkflow, _extract_ref_paths, _path_exists_in_schema


@dataclass
class DriftError:
    step_id: str
    reason: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"step_id": self.step_id, "reason": self.reason, "detail": self.detail}


def check_drift(
    compiled: CompiledWorkflow, contracts: ContractRegistry
) -> list[DriftError]:
    """Re-validate a compiled workflow against the live ContractRegistry.

    Flags any of: contract missing, version deprecated, ref paths that no
    longer resolve against current output schemas, or step overrides that
    would now violate contract bounds (timeout, retry_on subset).
    """
    drifts: list[DriftError] = []

    for sid, cs in compiled.steps.items():
        try:
            current = contracts.get(cs.agent, version=cs.agent_version)
        except KeyError:
            drifts.append(
                DriftError(
                    step_id=sid,
                    reason="contract_missing",
                    detail=f"{cs.agent} v{cs.agent_version} not in registry",
                )
            )
            continue

        if cs.agent_version in (current.deprecated_versions or []):
            drifts.append(
                DriftError(
                    step_id=sid,
                    reason="version_deprecated",
                    detail=f"{cs.agent} v{cs.agent_version} is deprecated",
                )
            )

        # Timeout override must still fit within current contract timeout.
        if cs.timeout_seconds > current.timeout_seconds:
            drifts.append(
                DriftError(
                    step_id=sid,
                    reason="timeout_exceeds_contract",
                    detail=(
                        f"compiled timeout {cs.timeout_seconds}s exceeds "
                        f"current contract timeout {current.timeout_seconds}s"
                    ),
                )
            )

        # retry_on must still be subset of current contract retry_on.
        if not set(cs.retry_on).issubset(set(current.retry_on)):
            drifts.append(
                DriftError(
                    step_id=sid,
                    reason="retry_on_not_subset",
                    detail=(
                        f"compiled retry_on {sorted(cs.retry_on)} not subset of "
                        f"current contract retry_on {sorted(current.retry_on)}"
                    ),
                )
            )

    # Ref-path drift: each node ref must still resolve against the referenced
    # upstream's CURRENT output schema.
    for sid, cs in compiled.steps.items():
        refs: list[tuple[str, Any]] = []
        _extract_ref_paths(cs.inputs, refs)
        if cs.when is not None:
            _extract_ref_paths(cs.when, refs)
        for kind, r in refs:
            if kind != "ref" or r.get("from") != "node":
                continue
            up_id = r["node_id"]
            if up_id not in compiled.steps:
                drifts.append(
                    DriftError(
                        step_id=sid,
                        reason="ref_target_missing",
                        detail=f"ref to unknown node {up_id!r}",
                    )
                )
                continue
            up = compiled.steps[up_id]
            try:
                up_contract = contracts.get(up.agent, version=up.agent_version)
            except KeyError:
                # Already reported above as contract_missing on up_id.
                continue
            path = r["path"]
            if not path.startswith("output"):
                continue
            sub = path[len("output"):].lstrip(".")
            if sub and not _path_exists_in_schema(up_contract.output_schema, sub):
                drifts.append(
                    DriftError(
                        step_id=sid,
                        reason="ref_path_missing",
                        detail=(
                            f"path {path!r} not in current "
                            f"{up.agent} v{up.agent_version} output schema"
                        ),
                    )
                )

    return drifts
