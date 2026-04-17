"""Task 4.24 — repo-wide linter: temperature=0 + 'inconclusive' IDK clause.

Runs as pytest so CI enforces it. Failure means:
  - a new agent was added without setting temperature=0 in its LLM call, OR
  - a prompt was introduced without an explicit inconclusive/IDK escape.

Both mistakes are easy to make in review; catching them deterministically
beats hoping somebody notices.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.prompts.registry import PromptRegistry


_REPO_ROOT = Path(__file__).resolve().parents[2]
_AGENTS_DIR = _REPO_ROOT / "src" / "agents"


# Files exempt from temperature=0 enforcement. Each exemption needs a why:
#  - __init__.py / _decorators.py / budget.py etc: no LLM call at all.
#  - pipeline.py-style scripts: reviewer decides per-file.
# Keeping the exempt list inline makes the exception audit one greppable place.
_TEMPERATURE_EXEMPT: set[str] = {
    "__init__.py",
    "_decorators.py",
    "budget.py",
    "confidence_calibrator.py",
    "critic_retriever.py",
    "stack_trace_validator.py",
    "causal_engine.py",
    "incident_graph.py",
    "k8s_pagination.py",
    "elk_pagination.py",
    "retry.py",
    "workflow_state_machine.py",
    "evidence_handoff.py",
    "evidence_mapper.py",
    "causal_linker.py",
    "signal_normalizer.py",
    "hypothesis_tracker.py",
    "promql_library.py",
    "service_dependency.py",
    "react_base.py",
}


_TEMP_PATTERN = re.compile(r"temperature\s*=\s*([0-9]*\.?[0-9]+)")


def _python_files_under(path: Path) -> list[Path]:
    return sorted(p for p in path.rglob("*.py") if p.is_file())


class TestTemperatureDiscipline:
    def test_every_llm_call_uses_temperature_zero(self):
        """Any `temperature=...` literal in src/agents/ must be 0 / 0.0."""
        offenders: list[str] = []
        for py in _python_files_under(_AGENTS_DIR):
            if py.name in _TEMPERATURE_EXEMPT:
                continue
            text = py.read_text()
            for m in _TEMP_PATTERN.finditer(text):
                val = m.group(1)
                if val not in ("0", "0.0"):
                    offenders.append(f"{py.relative_to(_REPO_ROOT)} uses temperature={val}")
        assert offenders == [], (
            "temperature must be 0/0.0 for deterministic agent behavior. "
            "If a non-zero value is truly needed, add a '# temperature-override:' "
            "comment and update the exempt list in this test. Offenders:\n"
            + "\n".join(offenders)
        )


class TestIDKClause:
    def test_every_registered_prompt_has_inconclusive_clause(self):
        offenders: list[str] = []
        for p in PromptRegistry().list_all():
            text = p.system_prompt.lower()
            if "inconclusive" not in text and "i don't know" not in text and "i do not know" not in text:
                offenders.append(p.agent)
        assert offenders == [], (
            "every agent prompt must include an explicit inconclusive / "
            "'I don't know' escape clause so agents don't hallucinate when "
            "evidence is thin. Missing on: " + ", ".join(offenders)
        )


class TestCriticEnsembleTemperatureZero:
    def test_critic_ensemble_is_temperature_zero(self):
        src = (_REPO_ROOT / "src" / "agents" / "critic_ensemble.py").read_text()
        # Any non-zero temperature in the critic ensemble is a regression.
        for m in _TEMP_PATTERN.finditer(src):
            assert m.group(1) in ("0", "0.0"), (
                f"critic_ensemble has temperature={m.group(1)}; advocate + "
                "challenger must both be temperature=0."
            )
