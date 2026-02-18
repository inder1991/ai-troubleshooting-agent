import pytest
import tempfile
import os
from pathlib import Path
from src.agents.code_agent import CodeNavigatorAgent


def test_code_agent_init():
    agent = CodeNavigatorAgent()
    assert agent.agent_name == "code_agent"
    assert agent.max_iterations == 6


def test_find_callers(tmp_path):
    (tmp_path / "main.py").write_text("from service import process_order\n\ndef handler():\n    process_order(data)\n")
    (tmp_path / "service.py").write_text("def process_order(data):\n    db.get_connection()\n    return data\n")
    (tmp_path / "other.py").write_text("def unrelated():\n    pass\n")

    callers = CodeNavigatorAgent._find_callers(str(tmp_path), "process_order")
    assert len(callers) == 1
    assert "main.py" in callers[0]["file_path"]
    assert callers[0]["line_number"] == 4


def test_find_callers_excludes_definition(tmp_path):
    (tmp_path / "service.py").write_text("def process_order(data):\n    return data\n")
    callers = CodeNavigatorAgent._find_callers(str(tmp_path), "process_order")
    assert len(callers) == 0


def test_extract_callees():
    content = """def process_order(data):
    validate_input(data)
    result = db_query(data["id"])
    send_notification(result)
    return result

def other_func():
    pass
"""
    callees = CodeNavigatorAgent._extract_callees(content, "process_order")
    assert "validate_input" in callees
    assert "db_query" in callees
    assert "send_notification" in callees
    assert "other_func" not in callees


def test_classify_impact():
    assert CodeNavigatorAgent._classify_impact("direct error location") == "direct_error"
    assert CodeNavigatorAgent._classify_impact("calls the broken function") == "caller"
    assert CodeNavigatorAgent._classify_impact("configuration file") == "config"
    assert CodeNavigatorAgent._classify_impact("test file for service") == "test"
    assert CodeNavigatorAgent._classify_impact("shared utility module") == "shared_resource"


def test_find_callers_multiple_files(tmp_path):
    (tmp_path / "a.py").write_text("def f():\n    process(x)\n")
    (tmp_path / "b.py").write_text("def g():\n    process(y)\n")
    (tmp_path / "c.py").write_text("def h():\n    something_else()\n")

    callers = CodeNavigatorAgent._find_callers(str(tmp_path), "process")
    files = [c["file_path"] for c in callers]
    assert any("a.py" in f for f in files)
    assert any("b.py" in f for f in files)
    assert not any("c.py" in f for f in files)


def test_find_callers_empty_repo(tmp_path):
    callers = CodeNavigatorAgent._find_callers(str(tmp_path), "nonexistent")
    assert callers == []
