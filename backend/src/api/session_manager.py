"""
Session Manager for Agent 3 PR Data

Stores Agent 3 instances and PR data for Phase 2 PR creation
"""

from typing import Dict, Any, Optional
import threading

# Thread-safe session storage
_session_lock = threading.Lock()
_session_storage: Dict[str, Dict[str, Any]] = {}


def store_session_data(session_id: str, key: str, value: Any) -> None:
    """
    Store data for a session
    
    Args:
        session_id: Session identifier
        key: Data key (e.g., 'agent3_instance', 'pr_data', 'repo_path')
        value: Data to store
    """
    with _session_lock:
        if session_id not in _session_storage:
            _session_storage[session_id] = {}
        
        _session_storage[session_id][key] = value
        print(f"📦 Session storage: {session_id}/{key} stored")


def get_session_data(session_id: str, key: str) -> Optional[Any]:
    """
    Retrieve data for a session
    
    Args:
        session_id: Session identifier
        key: Data key
    
    Returns:
        Stored value or None
    """
    with _session_lock:
        if session_id in _session_storage:
            value = _session_storage[session_id].get(key)
            if value is not None:
                print(f"📦 Session storage: {session_id}/{key} retrieved")
            return value
        return None


def clear_session_data(session_id: str) -> None:
    """
    Clear all data for a session
    
    Args:
        session_id: Session identifier
    """
    with _session_lock:
        if session_id in _session_storage:
            del _session_storage[session_id]
            print(f"📦 Session storage: {session_id} cleared")


def list_sessions() -> list:
    """
    Get list of active session IDs
    
    Returns:
        List of session IDs
    """
    with _session_lock:
        return list(_session_storage.keys())