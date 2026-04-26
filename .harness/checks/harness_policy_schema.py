#!/usr/bin/env python3
"""H-21 self-test — every .harness/<topic>_policy.yaml has and validates against
its JSON schema.

Two rules:
  H21.policy-schema-missing   — yaml exists in .harness/ but no matching
                                 schema file at .harness/schemas/<topic>.schema.json.
  H21.policy-schema-violation — yaml fails JSON Schema validation.

H-25:
  Missing input    — exit 2 if --target needs --schema and one is absent.
  Malformed input  — WARN harness.unparseable on yaml/json read errors.
  Upstream failed  — jsonschema lib missing → WARN; rule degrades.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / ".harness/checks"))

from _common import emit  # noqa: E402

DEFAULT_POLICIES_DIR = REPO_ROOT / ".harness"
DEFAULT_SCHEMAS_DIR = REPO_ROOT / ".harness" / "schemas"

POLICY_YAML_NAMES = {
    # Each entry maps yaml filename → schema basename (without .schema.json).
    # Lets us cover yaml files that don't follow the *_policy.yaml suffix.
    "dependencies.yaml": "dependencies",
    "performance_budgets.yaml": "performance_budgets",
    "security_policy.yaml": "security_policy",
    "accessibility_policy.yaml": "accessibility_policy",
    "documentation_policy.yaml": "documentation_policy",
    "logging_policy.yaml": "logging_policy",
    "error_handling_policy.yaml": "error_handling_policy",
    "rule_coverage_exemptions.yaml": "rule_coverage_exemptions",
    "typecheck_policy.yaml": "typecheck_policy",
}


def _validate_one(yaml_path: Path, schema_path: Path) -> int:
    """Validate yaml_path against schema_path. Returns count of ERROR findings."""
    try:
        import jsonschema
    except ImportError:
        emit("WARN", yaml_path, "H21.policy-schema-violation",
             "jsonschema library not installed; schema check skipped",
             "pip install jsonschema (and add to .harness/dependencies.yaml)",
             line=0)
        return 0
    try:
        with yaml_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError) as exc:
        emit("WARN", yaml_path, "harness.unparseable",
             f"could not parse {yaml_path.name}: {exc}",
             "fix YAML syntax", line=0)
        return 0
    try:
        with schema_path.open("r", encoding="utf-8") as fh:
            schema = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        emit("WARN", schema_path, "harness.unparseable",
             f"could not parse {schema_path.name}: {exc}",
             "fix schema JSON", line=0)
        return 0
    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as exc:
        path_str = ".".join(str(p) for p in exc.absolute_path) or "<root>"
        emit("ERROR", yaml_path, "H21.policy-schema-violation",
             f"{yaml_path.name} fails schema at {path_str}: {exc.message}",
             "fix the policy yaml or update the schema (with ADR)",
             line=0)
        return 1
    return 0


def scan(
    policies_dir: Path,
    schemas_dir: Path,
    single_target: Path | None,
    single_schema: Path | None,
) -> int:
    """Validate single_target (with single_schema) OR walk policies_dir."""
    if single_target is not None:
        if single_schema is None:
            emit("ERROR", single_target, "harness.target-missing",
                 "--target requires --schema when invoked directly",
                 "pass --schema <schema.json>", line=0)
            return 2
        return 1 if _validate_one(single_target, single_schema) else 0

    if not policies_dir.exists():
        emit("ERROR", policies_dir, "harness.target-missing",
             f"policies dir does not exist: {policies_dir}",
             "check --policies-dir", line=0)
        return 2

    total_errors = 0
    for yaml_name, schema_basename in POLICY_YAML_NAMES.items():
        yaml_path = policies_dir / yaml_name
        if not yaml_path.exists():
            continue
        schema_path = schemas_dir / f"{schema_basename}.schema.json"
        if not schema_path.exists():
            emit("ERROR", yaml_path, "H21.policy-schema-missing",
                 f"{yaml_path.name} has no matching schema in {schemas_dir}",
                 f"add {schema_path.name}", line=0)
            total_errors += 1
            continue
        total_errors += _validate_one(yaml_path, schema_path)

    # Also validate every .harness/generated/*.json against
    # .harness/schemas/generated/<name>.schema.json (warn-only when missing).
    generated_dir = REPO_ROOT / ".harness" / "generated"
    generated_schemas_dir = schemas_dir / "generated"
    if generated_dir.exists():
        for json_path in sorted(generated_dir.glob("*.json")):
            schema_path = generated_schemas_dir / f"{json_path.stem}.schema.json"
            if not schema_path.exists():
                emit("WARN", json_path, "H21.policy-schema-missing",
                     f"{json_path.name} has no matching generated schema",
                     f"add .harness/schemas/generated/{json_path.stem}.schema.json",
                     line=0)
                continue
            total_errors += _validate_json_one(json_path, schema_path)
    return 1 if total_errors else 0


def _validate_json_one(json_path: Path, schema_path: Path) -> int:
    """Validate generated JSON file against its schema. Returns count of ERRORs."""
    try:
        import jsonschema
    except ImportError:
        return 0
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        emit("WARN", json_path, "harness.unparseable",
             f"could not parse {json_path.name}: {exc}",
             "regenerate via `make harness`", line=0)
        return 0
    try:
        with schema_path.open("r", encoding="utf-8") as fh:
            schema = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        emit("WARN", schema_path, "harness.unparseable",
             f"could not parse {schema_path.name}: {exc}",
             "fix schema JSON", line=0)
        return 0
    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as exc:
        path_str = ".".join(str(p) for p in exc.absolute_path) or "<root>"
        emit("ERROR", json_path, "H21.policy-schema-violation",
             f"{json_path.name} fails schema at {path_str}: {exc.message}",
             "fix the generator or update the schema (with ADR)",
             line=0)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint: per-target schema validation OR whole-policies-dir scan."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path)
    parser.add_argument("--schema", type=Path)
    parser.add_argument("--policies-dir", type=Path, default=DEFAULT_POLICIES_DIR)
    parser.add_argument("--schemas-dir", type=Path, default=DEFAULT_SCHEMAS_DIR)
    parser.add_argument("--pretend-path", type=str)
    args = parser.parse_args(argv)
    return scan(args.policies_dir, args.schemas_dir, args.target, args.schema)


if __name__ == "__main__":
    sys.exit(main())
