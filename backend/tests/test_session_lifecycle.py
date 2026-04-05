"""Tests for session lifecycle management."""
import inspect


def test_delete_session_cancels_diagnosis_task():
    """delete_session must cancel any running diagnosis task."""
    from src.api.routes_v4 import delete_session
    source = inspect.getsource(delete_session)
    assert "_diagnosis_tasks" in source, "delete_session does not reference _diagnosis_tasks"
    assert "cancel" in source.lower(), "delete_session does not cancel the diagnosis task"
