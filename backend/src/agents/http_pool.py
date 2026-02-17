"""
Connection pooling for agent HTTP requests.
"""

import threading
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
import requests

_lock = threading.Lock()
_sessions: dict[str, requests.Session] = {}


def get_session(base_url: str) -> requests.Session:
    """Get or create a pooled requests.Session for a base URL.

    Sessions are keyed by base URL so connections to the same host are reused.
    Each session has:
    - Connection pooling (max 10 connections per host)
    - Default timeout of 30s
    - Retry adapter for 502/503/504
    """
    with _lock:
        if base_url in _sessions:
            return _sessions[base_url]

        session = requests.Session()

        # Configure retry adapter
        retry_strategy = Retry(
            total=2,
            backoff_factor=0.5,
            status_forcelist=[502, 503, 504],
            allowed_methods=["GET", "POST"],
        )
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=10,
        )
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        _sessions[base_url] = session
        return session


def close_all():
    """Close all pooled sessions."""
    with _lock:
        for session in _sessions.values():
            session.close()
        _sessions.clear()
