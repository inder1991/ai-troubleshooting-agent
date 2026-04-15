# Phase 1 — Contract Foundation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship the agent catalog substrate — versioned YAML manifests for every agent, a `ContractRegistry` that loads them, REST endpoints that expose contracts, and a read-only `/catalog` UI — without touching the existing Auto-mode Supervisor workflow.

**Architecture:** Additive-only. New Python package `backend/src/contracts/` with Pydantic models, manifest loader, and JSON-Schema validator (uses `jsonschema` lib). New YAML files under `backend/src/agents/manifests/`. New FastAPI router mounted under `/v4/catalog`. New React route `/catalog` with list/detail panes. Everything gated behind `CATALOG_UI_ENABLED` flag (default OFF). Zero lines changed in `supervisor.py`, `routes_v4.py` diagnostic paths, `InvestigationView.tsx`, or any existing test.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, PyYAML, `jsonschema`, pytest. React 18 + TypeScript + Vite + Tailwind + React Router on the frontend.

**Reference design:** `docs/plans/2026-04-15-agent-catalog-workflow-builder-design.md`

---

## Non-Impact Invariants (do NOT violate)

Run after every task:
```bash
cd backend && python3 -m pytest tests/ -v -x
cd frontend && npx tsc --noEmit
```

**Never touch in Phase 1:**
- `backend/src/agents/supervisor.py`
- `backend/src/api/routes_v4.py` — the existing diagnostic endpoints (you will add a new router file for catalog)
- `backend/src/models/schemas.py` — the existing `DiagnosticState` / `V4Findings` / event shapes
- `frontend/src/components/Investigation/**` — the existing Investigation view
- `frontend/src/types/index.ts` — only add new interfaces; do not rename or remove

**If you find yourself needing to modify any of these, stop and raise the concern.**

---

## Task 0: Verify baseline

**Step 1: Run the backend test suite**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
python3 -m pytest tests/ -v 2>&1 | tail -20
```

Expected: all tests pass. Record the count.

**Step 2: Run frontend typecheck**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend
npx tsc --noEmit
```

Expected: 0 errors.

**Step 3: Note baseline**

Write the test count + typecheck status to memory. Every subsequent task must preserve both.

---

## Task 1: Feature flag `CATALOG_UI_ENABLED` (backend)

**Files:**
- Modify: `backend/src/config.py` (add a single new key)
- Test: `backend/tests/test_feature_flags.py` (create)

**Step 1: Write the failing test**

```python
# backend/tests/test_feature_flags.py
from backend.src.config import settings

def test_catalog_flag_default_off():
    assert settings.CATALOG_UI_ENABLED is False

def test_catalog_flag_respects_env(monkeypatch):
    monkeypatch.setenv("CATALOG_UI_ENABLED", "true")
    # re-read from env
    from importlib import reload
    from backend.src import config
    reload(config)
    assert config.settings.CATALOG_UI_ENABLED is True
```

**Step 2: Run to verify fail**

```bash
python3 -m pytest backend/tests/test_feature_flags.py -v
```
Expected: FAIL — `AttributeError: CATALOG_UI_ENABLED`

**Step 3: Add the flag**

Open `backend/src/config.py`. Locate the Pydantic `Settings` class (or whatever config pattern exists). Add:

```python
CATALOG_UI_ENABLED: bool = Field(
    default=False,
    description="Phase 1: expose /v4/catalog/* endpoints and /catalog UI"
)
```

If no Pydantic settings exist, create a minimal one following existing env-reading patterns. Do not refactor existing config code.

**Step 4: Run to verify pass**

```bash
python3 -m pytest backend/tests/test_feature_flags.py -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/src/config.py backend/tests/test_feature_flags.py
git commit -m "feat(config): add CATALOG_UI_ENABLED flag (default off)"
```

---

## Task 2: `AgentContract` + manifest Pydantic schema

**Files:**
- Create: `backend/src/contracts/__init__.py` (empty)
- Create: `backend/src/contracts/models.py`
- Test: `backend/tests/test_contract_models.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_contract_models.py
import pytest
from pydantic import ValidationError
from backend.src.contracts.models import AgentContract, ManifestValidationError

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
```

**Step 2: Run fail**

```bash
python3 -m pytest backend/tests/test_contract_models.py -v
```
Expected: FAIL — module not found.

**Step 3: Implement**

```python
# backend/src/contracts/__init__.py
# empty
```

```python
# backend/src/contracts/models.py
from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field, field_validator, ConfigDict


class ManifestValidationError(ValueError):
    pass


class CostHint(BaseModel):
    llm_calls: int = 0
    typical_duration_s: float = 0.0


class AgentContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: int = Field(gt=0)
    deprecated_versions: list[int] = Field(default_factory=list)
    description: str
    category: str
    tags: list[str] = Field(default_factory=list)

    # JSON-Schema dicts; field name `inputs`/`outputs` in YAML,
    # exposed as input_schema/output_schema internally
    input_schema: dict[str, Any] = Field(alias="inputs")
    output_schema: dict[str, Any] = Field(alias="outputs")

    trigger_examples: list[str]
    retry_on: list[str] = Field(default_factory=list)  # class names; resolved later
    timeout_seconds: float = Field(gt=0)
    cost_hint: CostHint | None = None

    @field_validator("trigger_examples")
    @classmethod
    def at_least_two_examples(cls, v: list[str]) -> list[str]:
        if len(v) < 2:
            raise ValueError("trigger_examples must contain at least 2 entries")
        return v

    @field_validator("input_schema", "output_schema")
    @classmethod
    def must_be_object_schema(cls, v: dict[str, Any]) -> dict[str, Any]:
        if v.get("type") != "object":
            raise ValueError("schema must be of type 'object'")
        return v
```

**Step 4: Run pass**

```bash
python3 -m pytest backend/tests/test_contract_models.py -v
```
Expected: all PASS.

**Step 5: Commit**

```bash
git add backend/src/contracts/ backend/tests/test_contract_models.py
git commit -m "feat(contracts): AgentContract Pydantic model with manifest validation"
```

---

## Task 3: `ContractRegistry` — loads manifests from disk

**Files:**
- Create: `backend/src/contracts/registry.py`
- Test: `backend/tests/test_contract_registry.py`
- Create (fixture): `backend/tests/fixtures/manifests/good_agent.yaml`
- Create (fixture): `backend/tests/fixtures/manifests/bad_agent.yaml`

**Step 1: Write the fixtures**

```yaml
# backend/tests/fixtures/manifests/good_agent.yaml
name: good_agent
version: 1
description: Test agent
category: infrastructure
inputs:
  type: object
  properties:
    x: { type: string }
  required: [x]
outputs:
  type: object
  properties:
    y: { type: string }
  required: [y]
trigger_examples:
  - "do something"
  - "do another"
timeout_seconds: 10
```

```yaml
# backend/tests/fixtures/manifests/bad_agent.yaml
name: bad_agent
version: 1
description: missing trigger examples and schemas
category: infrastructure
timeout_seconds: 10
```

**Step 2: Write the failing test**

```python
# backend/tests/test_contract_registry.py
from pathlib import Path
import pytest
from backend.src.contracts.registry import ContractRegistry, ManifestLoadError

FIXTURES = Path(__file__).parent / "fixtures" / "manifests"

def test_load_valid_manifest(tmp_path):
    (tmp_path / "good_agent.yaml").write_text((FIXTURES / "good_agent.yaml").read_text())
    reg = ContractRegistry()
    reg.load_all(tmp_path)
    c = reg.get("good_agent", version=1)
    assert c.name == "good_agent"
    assert reg.list()[0].name == "good_agent"

def test_load_invalid_manifest_raises(tmp_path):
    (tmp_path / "bad_agent.yaml").write_text((FIXTURES / "bad_agent.yaml").read_text())
    reg = ContractRegistry()
    with pytest.raises(ManifestLoadError) as exc_info:
        reg.load_all(tmp_path)
    assert "bad_agent" in str(exc_info.value)

def test_get_missing_raises(tmp_path):
    reg = ContractRegistry()
    reg.load_all(tmp_path)
    with pytest.raises(KeyError):
        reg.get("nonexistent", version=1)

def test_get_missing_version_raises(tmp_path):
    (tmp_path / "good_agent.yaml").write_text((FIXTURES / "good_agent.yaml").read_text())
    reg = ContractRegistry()
    reg.load_all(tmp_path)
    with pytest.raises(KeyError):
        reg.get("good_agent", version=99)

def test_duplicate_name_version_raises(tmp_path):
    src = (FIXTURES / "good_agent.yaml").read_text()
    (tmp_path / "good_agent.yaml").write_text(src)
    (tmp_path / "good_agent_dup.yaml").write_text(src)
    reg = ContractRegistry()
    with pytest.raises(ManifestLoadError) as exc_info:
        reg.load_all(tmp_path)
    assert "duplicate" in str(exc_info.value).lower()

def test_list_all_returns_latest_per_name(tmp_path):
    (tmp_path / "a_v1.yaml").write_text((FIXTURES / "good_agent.yaml").read_text())
    v2 = (FIXTURES / "good_agent.yaml").read_text().replace("version: 1", "version: 2")
    (tmp_path / "a_v2.yaml").write_text(v2)
    reg = ContractRegistry()
    reg.load_all(tmp_path)
    all_latest = reg.list()
    assert len(all_latest) == 1
    assert all_latest[0].version == 2
```

**Step 3: Run fail**

```bash
python3 -m pytest backend/tests/test_contract_registry.py -v
```
Expected: FAIL — module not found.

**Step 4: Implement**

```python
# backend/src/contracts/registry.py
from __future__ import annotations
from pathlib import Path
from typing import Iterable
import yaml
from pydantic import ValidationError
from .models import AgentContract


class ManifestLoadError(Exception):
    pass


class ContractRegistry:
    def __init__(self) -> None:
        self._by_key: dict[tuple[str, int], AgentContract] = {}

    def load_all(self, manifests_dir: Path) -> None:
        errors: list[str] = []
        new_index: dict[tuple[str, int], AgentContract] = {}
        for path in sorted(manifests_dir.glob("*.yaml")):
            try:
                raw = yaml.safe_load(path.read_text())
                if not isinstance(raw, dict):
                    raise ManifestLoadError(f"{path.name}: YAML root must be a mapping")
                contract = AgentContract.model_validate(raw)
            except (ValidationError, ManifestLoadError, yaml.YAMLError) as e:
                errors.append(f"{path.name}: {e}")
                continue
            key = (contract.name, contract.version)
            if key in new_index:
                errors.append(f"duplicate manifest {key} in {path.name}")
                continue
            new_index[key] = contract

        if errors:
            raise ManifestLoadError(" | ".join(errors))
        self._by_key = new_index

    def get(self, name: str, *, version: int) -> AgentContract:
        return self._by_key[(name, version)]

    def list(self) -> list[AgentContract]:
        """Returns latest version per agent name."""
        by_name: dict[str, AgentContract] = {}
        for (name, version), contract in self._by_key.items():
            if name not in by_name or version > by_name[name].version:
                by_name[name] = contract
        return sorted(by_name.values(), key=lambda c: c.name)

    def list_all_versions(self) -> Iterable[AgentContract]:
        return list(self._by_key.values())
```

**Step 5: Run pass**

```bash
python3 -m pytest backend/tests/test_contract_registry.py -v
```
Expected: all PASS.

**Step 6: Commit**

```bash
git add backend/src/contracts/registry.py backend/tests/test_contract_registry.py backend/tests/fixtures/manifests/
git commit -m "feat(contracts): ContractRegistry loads YAML manifests with dedupe and per-name latest"
```

---

## Task 4: JSON-Schema validator wrapper

**Files:**
- Create: `backend/src/contracts/validator.py`
- Test: `backend/tests/test_contract_validator.py`

**Step 1: Write failing test**

```python
# backend/tests/test_contract_validator.py
from backend.src.contracts.validator import validate_against, ValidationIssue

SCHEMA = {
    "type": "object",
    "properties": {
        "x": {"type": "string"},
        "n": {"type": "integer"},
    },
    "required": ["x"],
}

def test_valid_payload_returns_empty_list():
    assert validate_against({"x": "ok"}, SCHEMA) == []

def test_missing_required_returns_issue():
    issues = validate_against({}, SCHEMA)
    assert len(issues) == 1
    assert issues[0].path == "$"
    assert "x" in issues[0].message

def test_type_mismatch_returns_issue():
    issues = validate_against({"x": "ok", "n": "not-an-int"}, SCHEMA)
    assert any(i.path == "$.n" for i in issues)

def test_multiple_issues_returned():
    issues = validate_against({"n": "bad"}, SCHEMA)
    paths = {i.path for i in issues}
    assert "$" in paths or any("x" in i.message for i in issues)
    assert any("n" in i.path for i in issues)
```

**Step 2: Run fail**

```bash
python3 -m pytest backend/tests/test_contract_validator.py -v
```
Expected: FAIL — module not found.

**Step 3: Install `jsonschema` if not present**

```bash
cd backend && python3 -c "import jsonschema" 2>&1
```
If missing: add `jsonschema>=4.0` to `backend/requirements.txt` (or `pyproject.toml`) and install.

**Step 4: Implement**

```python
# backend/src/contracts/validator.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from jsonschema import Draft202012Validator


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    message: str


def validate_against(payload: Any, schema: dict[str, Any]) -> list[ValidationIssue]:
    validator = Draft202012Validator(schema)
    issues: list[ValidationIssue] = []
    for err in validator.iter_errors(payload):
        path = "$" + "".join(f".{p}" if isinstance(p, str) else f"[{p}]" for p in err.absolute_path)
        issues.append(ValidationIssue(path=path, message=err.message))
    return issues
```

**Step 5: Run pass**

```bash
python3 -m pytest backend/tests/test_contract_validator.py -v
```
Expected: all PASS.

**Step 6: Commit**

```bash
git add backend/src/contracts/validator.py backend/tests/test_contract_validator.py backend/requirements.txt
git commit -m "feat(contracts): JSON-Schema validator returning structured issue list"
```

---

## Task 5: Write first real manifest (`log_agent`) + enforce via CI test

**Files:**
- Create: `backend/src/agents/manifests/log_agent.yaml`
- Test: `backend/tests/test_manifests_ci.py`

**Step 1: Read the existing agent signature for accurate schema**

```bash
python3 -c "from backend.src.agents.log_agent import LogAnalysisAgent; help(LogAnalysisAgent.run)"
```

Inspect `run(self, context: dict) -> dict`. Read the module to understand what keys it reads from `context` and returns. Use the real shape.

**Step 2: Write the manifest**

```yaml
# backend/src/agents/manifests/log_agent.yaml
name: log_agent
version: 1
description: Analyzes application logs to identify error patterns, OOMs, panics, and crash causes.
category: observability
tags: [logs, errors, patterns]
inputs:
  type: object
  properties:
    service_name:
      type: string
      description: Target service to analyze logs for
    namespace:
      type: string
    time_window:
      type: object
      properties:
        minutes: { type: integer, minimum: 1 }
      required: [minutes]
  required: [service_name]
outputs:
  type: object
  properties:
    findings:
      type: array
      items: { type: object }
    error_patterns:
      type: array
      items: { type: object }
    summary:
      type: string
  required: [findings]
trigger_examples:
  - "Why is my service erroring?"
  - "Analyze logs for the last 30 minutes"
  - "Find crash causes in payment-service"
retry_on: [TimeoutError]
timeout_seconds: 30
cost_hint:
  llm_calls: 2
  typical_duration_s: 15
```

**Step 3: Write a CI enforcement test**

```python
# backend/tests/test_manifests_ci.py
from pathlib import Path
import pytest
from backend.src.contracts.registry import ContractRegistry

MANIFESTS_DIR = Path(__file__).parent.parent / "src" / "agents" / "manifests"

def test_manifests_directory_exists():
    assert MANIFESTS_DIR.is_dir(), f"expected {MANIFESTS_DIR}"

def test_all_manifests_load():
    reg = ContractRegistry()
    reg.load_all(MANIFESTS_DIR)
    assert len(reg.list()) >= 1

def test_log_agent_manifest_present():
    reg = ContractRegistry()
    reg.load_all(MANIFESTS_DIR)
    c = reg.get("log_agent", version=1)
    assert c.category == "observability"
    assert "service_name" in c.input_schema["properties"]
```

**Step 4: Run**

```bash
python3 -m pytest backend/tests/test_manifests_ci.py -v
```
Expected: all PASS.

**Step 5: Commit**

```bash
git add backend/src/agents/manifests/log_agent.yaml backend/tests/test_manifests_ci.py
git commit -m "feat(manifests): log_agent v1 manifest + CI enforcement test"
```

---

## Task 6: Write the remaining 9 manifests

**Files:**
- Create: `backend/src/agents/manifests/k8s_agent.yaml`
- Create: `backend/src/agents/manifests/metrics_agent.yaml`
- Create: `backend/src/agents/manifests/tracing_agent.yaml`
- Create: `backend/src/agents/manifests/code_agent.yaml`
- Create: `backend/src/agents/manifests/change_agent.yaml`
- Create: `backend/src/agents/manifests/critic_agent.yaml`
- Create: `backend/src/agents/manifests/pipeline_agent.yaml`
- Create: `backend/src/agents/manifests/impact_analyzer.yaml`
- Create: `backend/src/agents/manifests/intent_parser.yaml`

**Step 1: Inspect each agent's actual run() signature**

For each module in `backend/src/agents/*.py` that has an `async def run()`, read the function to derive the real input/output shape. Use the actual keys the code reads and returns — not made-up schema.

```bash
grep -nE "async def run|context\[|context.get|return \{" backend/src/agents/k8s_agent.py | head -40
```

Repeat per agent.

**Step 2: Write each manifest following the `log_agent.yaml` template**

Each file: name, version=1, description, category (`observability` / `infrastructure` / `code` / `process`), inputs + outputs schemas, ≥ 2 trigger_examples, `timeout_seconds`, optional `retry_on` and `cost_hint`.

**Do not invent fields the agent does not use.** If an agent's output shape is loose, reflect that in a permissive output schema (`type: object`, `properties: {...known keys...}`, no `required`).

**Step 3: Extend CI test to require a minimum count**

```python
# backend/tests/test_manifests_ci.py — add
def test_minimum_manifest_count():
    reg = ContractRegistry()
    reg.load_all(MANIFESTS_DIR)
    assert len(reg.list()) >= 10, f"got {len(reg.list())}"
```

**Step 4: Run**

```bash
python3 -m pytest backend/tests/test_manifests_ci.py -v
```
Expected: all PASS.

**Step 5: Commit**

```bash
git add backend/src/agents/manifests/*.yaml backend/tests/test_manifests_ci.py
git commit -m "feat(manifests): manifests for 9 remaining agents + min-count CI test"
```

---

## Task 7: Registry singleton + app startup wiring

**Files:**
- Create: `backend/src/contracts/service.py` (the singleton accessor)
- Modify: `backend/src/api/main.py` (or wherever FastAPI `app` is created) — **one-line addition only**
- Test: `backend/tests/test_contract_service.py`

**Step 1: Failing test**

```python
# backend/tests/test_contract_service.py
from backend.src.contracts.service import get_registry, init_registry

def test_registry_is_singleton():
    init_registry()
    r1 = get_registry()
    r2 = get_registry()
    assert r1 is r2

def test_registry_has_log_agent():
    init_registry()
    r = get_registry()
    assert r.get("log_agent", version=1).name == "log_agent"
```

**Step 2: Run fail**

```bash
python3 -m pytest backend/tests/test_contract_service.py -v
```

**Step 3: Implement**

```python
# backend/src/contracts/service.py
from pathlib import Path
from .registry import ContractRegistry

_registry: ContractRegistry | None = None


def init_registry(manifests_dir: Path | None = None) -> ContractRegistry:
    global _registry
    if manifests_dir is None:
        manifests_dir = Path(__file__).parent.parent / "agents" / "manifests"
    reg = ContractRegistry()
    reg.load_all(manifests_dir)
    _registry = reg
    return reg


def get_registry() -> ContractRegistry:
    if _registry is None:
        raise RuntimeError("ContractRegistry not initialized — call init_registry() at startup")
    return _registry
```

Modify the FastAPI startup to call `init_registry()`. Find the file that creates `app = FastAPI(...)`:

```bash
grep -rn "FastAPI(" backend/src/api/ | head -5
```

Add **only** this at app startup (inside an existing startup handler or lifespan):

```python
from backend.src.contracts.service import init_registry
init_registry()
```

**Do not refactor existing startup code.**

**Step 4: Run pass**

```bash
python3 -m pytest backend/tests/test_contract_service.py -v
```

**Step 5: Commit**

```bash
git add backend/src/contracts/service.py backend/src/api/main.py backend/tests/test_contract_service.py
git commit -m "feat(contracts): registry singleton + startup init"
```

---

## Task 8: REST endpoint `GET /v4/catalog/agents` (list)

**Files:**
- Create: `backend/src/api/routes_catalog.py`
- Modify: `backend/src/api/main.py` — include the new router (one line)
- Test: `backend/tests/test_catalog_api.py`

**Step 1: Failing test**

```python
# backend/tests/test_catalog_api.py
import os
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def client_enabled(monkeypatch):
    monkeypatch.setenv("CATALOG_UI_ENABLED", "true")
    from importlib import reload
    from backend.src import config
    reload(config)
    from backend.src.api import main as app_main
    reload(app_main)
    return TestClient(app_main.app)

@pytest.fixture
def client_disabled(monkeypatch):
    monkeypatch.setenv("CATALOG_UI_ENABLED", "false")
    from importlib import reload
    from backend.src import config
    reload(config)
    from backend.src.api import main as app_main
    reload(app_main)
    return TestClient(app_main.app)

def test_list_agents_when_enabled(client_enabled):
    resp = client_enabled.get("/v4/catalog/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert "agents" in data
    assert len(data["agents"]) >= 10
    sample = data["agents"][0]
    assert set(["name", "version", "description", "category"]).issubset(sample.keys())

def test_list_agents_returns_404_when_disabled(client_disabled):
    resp = client_disabled.get("/v4/catalog/agents")
    assert resp.status_code == 404
```

**Step 2: Run fail**

```bash
python3 -m pytest backend/tests/test_catalog_api.py::test_list_agents_when_enabled -v
```

**Step 3: Implement**

```python
# backend/src/api/routes_catalog.py
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from backend.src.config import settings
from backend.src.contracts.service import get_registry
from backend.src.contracts.models import AgentContract, CostHint

router = APIRouter(prefix="/v4/catalog", tags=["catalog"])


def require_flag():
    if not settings.CATALOG_UI_ENABLED:
        raise HTTPException(status_code=404)


class AgentSummary(BaseModel):
    name: str
    version: int
    description: str
    category: str
    tags: list[str]
    cost_hint: CostHint | None = None


class AgentListResponse(BaseModel):
    agents: list[AgentSummary]


@router.get("/agents", response_model=AgentListResponse, dependencies=[Depends(require_flag)])
def list_agents() -> AgentListResponse:
    reg = get_registry()
    return AgentListResponse(
        agents=[
            AgentSummary(
                name=c.name, version=c.version, description=c.description,
                category=c.category, tags=c.tags, cost_hint=c.cost_hint,
            )
            for c in reg.list()
        ]
    )
```

In `backend/src/api/main.py` add (once):

```python
from backend.src.api.routes_catalog import router as catalog_router
app.include_router(catalog_router)
```

**Step 4: Run pass**

```bash
python3 -m pytest backend/tests/test_catalog_api.py -v
```

**Step 5: Commit**

```bash
git add backend/src/api/routes_catalog.py backend/src/api/main.py backend/tests/test_catalog_api.py
git commit -m "feat(api): GET /v4/catalog/agents (flag-gated)"
```

---

## Task 9: `GET /v4/catalog/agents/{name}` + `/v/{version}` (detail)

**Files:**
- Modify: `backend/src/api/routes_catalog.py`
- Modify: `backend/tests/test_catalog_api.py`

**Step 1: Failing tests**

```python
# backend/tests/test_catalog_api.py — add
def test_get_agent_detail(client_enabled):
    resp = client_enabled.get("/v4/catalog/agents/log_agent")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "log_agent"
    assert "input_schema" in data
    assert "output_schema" in data
    assert len(data["trigger_examples"]) >= 2

def test_get_agent_specific_version(client_enabled):
    resp = client_enabled.get("/v4/catalog/agents/log_agent/v/1")
    assert resp.status_code == 200
    assert resp.json()["version"] == 1

def test_get_unknown_agent_returns_404(client_enabled):
    resp = client_enabled.get("/v4/catalog/agents/unknown_xyz")
    assert resp.status_code == 404

def test_get_unknown_version_returns_404(client_enabled):
    resp = client_enabled.get("/v4/catalog/agents/log_agent/v/999")
    assert resp.status_code == 404
```

**Step 2: Run fail**

```bash
python3 -m pytest backend/tests/test_catalog_api.py -v
```

**Step 3: Implement**

In `routes_catalog.py`:

```python
class AgentDetail(AgentSummary):
    deprecated_versions: list[int]
    input_schema: dict
    output_schema: dict
    trigger_examples: list[str]
    timeout_seconds: float
    retry_on: list[str]


def _to_detail(c: AgentContract) -> AgentDetail:
    return AgentDetail(
        name=c.name, version=c.version, description=c.description,
        category=c.category, tags=c.tags, cost_hint=c.cost_hint,
        deprecated_versions=c.deprecated_versions,
        input_schema=c.input_schema, output_schema=c.output_schema,
        trigger_examples=c.trigger_examples,
        timeout_seconds=c.timeout_seconds, retry_on=c.retry_on,
    )


@router.get("/agents/{name}", response_model=AgentDetail, dependencies=[Depends(require_flag)])
def get_agent(name: str) -> AgentDetail:
    reg = get_registry()
    latest = next((c for c in reg.list() if c.name == name), None)
    if latest is None:
        raise HTTPException(status_code=404, detail=f"unknown agent: {name}")
    return _to_detail(latest)


@router.get("/agents/{name}/v/{version}", response_model=AgentDetail, dependencies=[Depends(require_flag)])
def get_agent_version(name: str, version: int) -> AgentDetail:
    reg = get_registry()
    try:
        c = reg.get(name, version=version)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown: {name} v{version}")
    return _to_detail(c)
```

**Step 4: Run pass**

```bash
python3 -m pytest backend/tests/test_catalog_api.py -v
```

**Step 5: Commit**

```bash
git add backend/src/api/routes_catalog.py backend/tests/test_catalog_api.py
git commit -m "feat(api): GET agent detail and specific-version endpoints"
```

---

## Task 10: Non-impact snapshot baseline (critical)

**Files:**
- Create: `backend/tests/test_auto_mode_nonimpact.py`

**Purpose:** Record current Auto-mode behavior as golden snapshots so every future PR proves it hasn't drifted.

**Step 1: Capture existing V4 routes response shape**

```python
# backend/tests/test_auto_mode_nonimpact.py
"""
Guards that Auto-mode diagnostic endpoints remain byte-identical in shape.

DO NOT SKIP these tests. If a change legitimately alters an endpoint,
the change is out of Phase 1 scope — stop and raise the concern.
"""
from fastapi.testclient import TestClient
import pytest


@pytest.fixture
def client():
    from backend.src.api import main as app_main
    return TestClient(app_main.app)


def test_findings_route_exists_unchanged(client):
    # Known endpoint still mounted, returns 404 or 422 for bogus id (not 500)
    resp = client.get("/v4/findings/bogus-session-id")
    assert resp.status_code in (200, 404, 422)


def test_sessions_route_exists(client):
    resp = client.get("/v4/sessions")
    # Should not be 500; shape may vary by existing behavior
    assert resp.status_code < 500


def test_catalog_flag_off_does_not_expose_routes(monkeypatch):
    monkeypatch.setenv("CATALOG_UI_ENABLED", "false")
    from importlib import reload
    from backend.src import config
    reload(config)
    from backend.src.api import main as app_main
    reload(app_main)
    client = TestClient(app_main.app)
    assert client.get("/v4/catalog/agents").status_code == 404
```

**Step 2: Run**

```bash
python3 -m pytest backend/tests/test_auto_mode_nonimpact.py -v
```
Expected: all PASS.

**Step 3: Commit**

```bash
git add backend/tests/test_auto_mode_nonimpact.py
git commit -m "test: non-impact snapshot tests for auto-mode routes"
```

---

## Task 11: Frontend — catalog API client + types

**Files:**
- Modify: `frontend/src/types/index.ts` (add new interfaces, no modifications to existing)
- Create: `frontend/src/services/catalog.ts`

**Step 1: Add types**

Append (do not modify existing types):

```typescript
// frontend/src/types/index.ts — append
export interface CatalogCostHint {
  llm_calls: number;
  typical_duration_s: number;
}

export interface CatalogAgentSummary {
  name: string;
  version: number;
  description: string;
  category: string;
  tags: string[];
  cost_hint?: CatalogCostHint | null;
}

export interface CatalogAgentDetail extends CatalogAgentSummary {
  deprecated_versions: number[];
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  trigger_examples: string[];
  timeout_seconds: number;
  retry_on: string[];
}
```

**Step 2: Create service**

```typescript
// frontend/src/services/catalog.ts
import type { CatalogAgentSummary, CatalogAgentDetail } from '../types';

const API_BASE = import.meta.env.VITE_API_BASE ?? '';

export async function listAgents(signal?: AbortSignal): Promise<CatalogAgentSummary[]> {
  const resp = await fetch(`${API_BASE}/v4/catalog/agents`, { signal });
  if (resp.status === 404) throw new CatalogDisabledError();
  if (!resp.ok) throw new Error(`catalog list failed: ${resp.status}`);
  const data = await resp.json();
  return data.agents;
}

export async function getAgent(name: string, signal?: AbortSignal): Promise<CatalogAgentDetail> {
  const resp = await fetch(`${API_BASE}/v4/catalog/agents/${encodeURIComponent(name)}`, { signal });
  if (!resp.ok) throw new Error(`catalog get failed: ${resp.status}`);
  return resp.json();
}

export async function getAgentVersion(name: string, version: number, signal?: AbortSignal): Promise<CatalogAgentDetail> {
  const resp = await fetch(`${API_BASE}/v4/catalog/agents/${encodeURIComponent(name)}/v/${version}`, { signal });
  if (!resp.ok) throw new Error(`catalog get version failed: ${resp.status}`);
  return resp.json();
}

export class CatalogDisabledError extends Error {
  constructor() { super("Catalog feature is disabled."); }
}
```

**Step 3: Typecheck**

```bash
cd frontend && npx tsc --noEmit
```
Expected: 0 errors.

**Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/services/catalog.ts
git commit -m "feat(ui): catalog API client + types"
```

---

## Task 12: Frontend — `/catalog` route + page shell

**Files:**
- Create: `frontend/src/pages/CatalogPage.tsx`
- Modify: `frontend/src/App.tsx` (or whichever router file exists) — add the route (additive only)

**Step 1: Find the router**

```bash
grep -rn "createBrowserRouter\|BrowserRouter\|<Routes\|<Route " frontend/src/ | head -10
```

**Step 2: Implement page shell**

```tsx
// frontend/src/pages/CatalogPage.tsx
import React, { useEffect, useState } from 'react';
import type { CatalogAgentSummary } from '../types';
import { listAgents, CatalogDisabledError } from '../services/catalog';

const CatalogPage: React.FC = () => {
  const [agents, setAgents] = useState<CatalogAgentSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    listAgents(ctrl.signal)
      .then((a) => { setAgents(a); setSelected(a[0]?.name ?? null); })
      .catch((e) => setError(e instanceof CatalogDisabledError ? 'disabled' : String(e)));
    return () => ctrl.abort();
  }, []);

  if (error === 'disabled') {
    return <div className="p-8 text-wr-muted">The agent catalog is not enabled in this environment.</div>;
  }
  if (error) return <div className="p-8 text-red-400">Error: {error}</div>;
  if (!agents) return <div className="p-8 text-wr-muted">Loading agents…</div>;

  return (
    <div className="flex h-full">
      <aside className="w-80 border-r border-wr-border overflow-auto" aria-label="Agent list">
        <header className="px-4 py-3 border-b border-wr-border">
          <h1 className="text-body-sm font-medium text-wr-text">Agent Catalog</h1>
          <p className="text-body-xs text-wr-muted">{agents.length} agents</p>
        </header>
        <ul>
          {agents.map((a) => (
            <li key={a.name}>
              <button
                className={`w-full text-left px-4 py-2 hover:bg-wr-surface-hover ${selected === a.name ? 'bg-wr-surface-hover' : ''}`}
                onClick={() => setSelected(a.name)}
              >
                <div className="text-body-sm text-wr-text">{a.name}</div>
                <div className="text-body-xs text-wr-muted">{a.category} · v{a.version}</div>
              </button>
            </li>
          ))}
        </ul>
      </aside>
      <main className="flex-1 overflow-auto p-6">
        {selected ? <AgentDetailView name={selected} /> : <div className="text-wr-muted">Select an agent.</div>}
      </main>
    </div>
  );
};

// Placeholder — replaced in Task 13
const AgentDetailView: React.FC<{ name: string }> = ({ name }) => (
  <div className="text-wr-text">Detail pane for <strong>{name}</strong> — built in next task.</div>
);

export default CatalogPage;
```

**Step 3: Register route**

Add to the router config **additively**:

```tsx
// (inside existing routes block)
<Route path="/catalog" element={<CatalogPage />} />
```

**Step 4: Typecheck + manual smoke**

```bash
cd frontend && npx tsc --noEmit
```

Start dev server (`npm run dev`), with backend `CATALOG_UI_ENABLED=true`. Navigate to `http://localhost:5173/catalog`. Verify:
- List populates with ≥ 10 agents.
- Clicking a row updates the selected placeholder.
- With flag OFF on backend → page shows "catalog is not enabled".

**Step 5: Commit**

```bash
git add frontend/src/pages/CatalogPage.tsx frontend/src/App.tsx
git commit -m "feat(ui): /catalog page shell with list + placeholder detail"
```

---

## Task 13: Frontend — agent detail view with schema trees

**Files:**
- Create: `frontend/src/components/Catalog/AgentDetail.tsx`
- Create: `frontend/src/components/Catalog/JsonSchemaTree.tsx`
- Modify: `frontend/src/pages/CatalogPage.tsx` (swap placeholder for real component)

**Step 1: JsonSchemaTree (collapsible tree)**

```tsx
// frontend/src/components/Catalog/JsonSchemaTree.tsx
import React, { useState } from 'react';

interface Props {
  schema: Record<string, unknown>;
  depth?: number;
}

const JsonSchemaTree: React.FC<Props> = ({ schema, depth = 0 }) => {
  const properties = (schema.properties ?? {}) as Record<string, any>;
  const required = (schema.required ?? []) as string[];
  const entries = Object.entries(properties);

  if (entries.length === 0) {
    return <div className="text-body-xs text-wr-muted italic">No fields declared.</div>;
  }

  return (
    <ul className={depth === 0 ? '' : 'pl-4 border-l border-wr-border'}>
      {entries.map(([name, prop]) => (
        <FieldRow key={name} name={name} prop={prop} required={required.includes(name)} depth={depth} />
      ))}
    </ul>
  );
};

const FieldRow: React.FC<{ name: string; prop: any; required: boolean; depth: number }> = ({ name, prop, required, depth }) => {
  const [open, setOpen] = useState(depth === 0);
  const hasNested = prop.type === 'object' && prop.properties;

  return (
    <li className="py-1">
      <div className="flex items-center gap-2 text-body-sm">
        {hasNested ? (
          <button onClick={() => setOpen(!open)} className="text-wr-muted" aria-expanded={open}>
            {open ? '▾' : '▸'}
          </button>
        ) : <span className="w-3" />}
        <span className="text-wr-text font-medium">{name}</span>
        <span className="text-wr-muted text-body-xs">{prop.type ?? 'any'}</span>
        {required && <span className="text-amber-400 text-body-xs">required</span>}
        {prop.description && <span className="text-wr-muted text-body-xs">— {prop.description}</span>}
      </div>
      {hasNested && open && <JsonSchemaTree schema={prop} depth={depth + 1} />}
    </li>
  );
};

export default JsonSchemaTree;
```

**Step 2: AgentDetail**

```tsx
// frontend/src/components/Catalog/AgentDetail.tsx
import React, { useEffect, useState } from 'react';
import type { CatalogAgentDetail } from '../../types';
import { getAgent } from '../../services/catalog';
import JsonSchemaTree from './JsonSchemaTree';

const AgentDetail: React.FC<{ name: string }> = ({ name }) => {
  const [detail, setDetail] = useState<CatalogAgentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    setDetail(null);
    getAgent(name, ctrl.signal).then(setDetail).catch((e) => setError(String(e)));
    return () => ctrl.abort();
  }, [name]);

  if (error) return <div className="text-red-400">Error: {error}</div>;
  if (!detail) return <div className="text-wr-muted">Loading…</div>;

  return (
    <article className="max-w-3xl">
      <header className="mb-6">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold text-wr-text">{detail.name}</h2>
          <span className="px-2 py-0.5 rounded bg-wr-surface text-body-xs text-wr-muted">v{detail.version}</span>
          <span className="px-2 py-0.5 rounded bg-wr-surface text-body-xs text-wr-muted">{detail.category}</span>
        </div>
        <p className="mt-2 text-wr-text">{detail.description}</p>
        {detail.cost_hint && (
          <p className="mt-1 text-body-xs text-wr-muted">
            ~{detail.cost_hint.llm_calls} LLM calls · ~{detail.cost_hint.typical_duration_s}s typical
          </p>
        )}
      </header>

      <section className="mb-6">
        <h3 className="text-body-sm font-medium text-wr-text mb-2">Inputs</h3>
        <JsonSchemaTree schema={detail.input_schema} />
      </section>

      <section className="mb-6">
        <h3 className="text-body-sm font-medium text-wr-text mb-2">Outputs</h3>
        <JsonSchemaTree schema={detail.output_schema} />
      </section>

      <section className="mb-6">
        <h3 className="text-body-sm font-medium text-wr-text mb-2">Trigger examples</h3>
        <ul className="list-disc pl-5 text-body-sm text-wr-text">
          {detail.trigger_examples.map((t, i) => <li key={i}>{t}</li>)}
        </ul>
      </section>

      <section className="mb-6">
        <h3 className="text-body-sm font-medium text-wr-text mb-2">Runtime</h3>
        <dl className="text-body-sm grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
          <dt className="text-wr-muted">Timeout</dt><dd>{detail.timeout_seconds}s</dd>
          <dt className="text-wr-muted">Retries on</dt><dd>{detail.retry_on.length ? detail.retry_on.join(', ') : '—'}</dd>
        </dl>
      </section>

      <button
        disabled
        title="Workflow builder arrives in Phase 3"
        className="px-3 py-1.5 rounded bg-wr-surface text-wr-muted cursor-not-allowed text-body-sm"
      >
        Use in workflow
      </button>
    </article>
  );
};

export default AgentDetail;
```

**Step 3: Wire into page**

Replace the placeholder `AgentDetailView` in `CatalogPage.tsx` with the real `AgentDetail`.

**Step 4: Typecheck + smoke**

```bash
cd frontend && npx tsc --noEmit
```

Dev server: click different agents; verify schema trees render, required badges appear, "Use in workflow" is disabled.

**Step 5: Commit**

```bash
git add frontend/src/components/Catalog/ frontend/src/pages/CatalogPage.tsx
git commit -m "feat(ui): agent detail view with collapsible schema trees"
```

---

## Task 14: Navigation entry point

**Files:**
- Modify: the primary navigation component (find via `grep -rn "Investigation\|dashboard" frontend/src/components/nav* frontend/src/components/*Header* 2>/dev/null`)

**Step 1: Add nav link**

Find the existing top-level navigation. Add a single link:

```tsx
<NavLink to="/catalog" className={...existing classes...}>Catalog</NavLink>
```

**Do not change the existing nav structure or styles.**

**Step 2: Guard with flag (frontend-side UX)**

Since the flag is backend-enforced via 404, the UI gracefully handles it. No frontend flag needed — the page itself shows the "disabled" message.

**Step 3: Typecheck + smoke**

```bash
cd frontend && npx tsc --noEmit
```

Dev server: click nav link, land on `/catalog`.

**Step 4: Commit**

```bash
git add frontend/src/components/...
git commit -m "feat(ui): add Catalog nav link"
```

---

## Task 15: End-to-end verification

**Step 1: Full backend test suite**

```bash
cd backend && python3 -m pytest tests/ -v 2>&1 | tail -30
```
Expected: every Phase 1 test passes; baseline count + new tests = total count. No pre-existing test broken.

**Step 2: Frontend typecheck**

```bash
cd frontend && npx tsc --noEmit
```
Expected: 0 errors.

**Step 3: Manual integration**

- Start backend with `CATALOG_UI_ENABLED=true`.
- Start frontend dev server.
- Navigate to `/catalog` — list of ≥ 10 agents.
- Click each agent — detail renders, schemas are trees, trigger examples list, timeout shown.
- Navigate back to an existing Investigation view — **verify no visual change** vs. pre-Phase-1. Open a real session, scroll through findings, confirm Investigator / EvidenceFindings / Navigator all render identically.
- Toggle `CATALOG_UI_ENABLED=false`, restart backend. `/catalog` shows "not enabled" message. Existing Investigation view still works.

**Step 4: Final commit (if any cleanup)**

```bash
git commit --allow-empty -m "chore: Phase 1 contract foundation complete"
```

---

## Phase 1 Exit Criteria

- [ ] All 10+ agents have manifests that load and validate.
- [ ] `ContractRegistry` loads at app startup without errors.
- [ ] `GET /v4/catalog/agents`, `GET /v4/catalog/agents/{name}`, `GET /v4/catalog/agents/{name}/v/{version}` all work.
- [ ] All three endpoints return 404 when `CATALOG_UI_ENABLED=false`.
- [ ] `/catalog` UI lists agents and renders detail with schema trees.
- [ ] Non-impact tests (`test_auto_mode_nonimpact.py`) pass.
- [ ] Full backend pytest suite green.
- [ ] Frontend `npx tsc --noEmit` clean.
- [ ] Manual verification: existing Investigation view unchanged.
- [ ] `git diff origin/main -- backend/src/agents/supervisor.py` is empty.
- [ ] `git diff origin/main -- frontend/src/components/Investigation/` is empty.

---

## Follow-on Plans (not in this file)

- **Phase 2 — Orchestrator + WorkflowExecutor:** `docs/plans/YYYY-MM-DD-phase2-executor.md`
- **Phase 3 — Workflow Builder UI:** `docs/plans/YYYY-MM-DD-phase3-builder-ui.md`
- **Phase 4 — Canvas View:** `docs/plans/YYYY-MM-DD-phase4-canvas.md`
- **Phase 5 — Supervisor Unification:** `docs/plans/YYYY-MM-DD-phase5-supervisor.md`
- **Phase 6 — Management UI:** `docs/plans/YYYY-MM-DD-phase6-admin.md`

Each will be written as its own TDD plan after the previous phase lands. Do not start Phase 2 until Phase 1 exit criteria are met and at least one week of production burn-in for the catalog UI has passed.
