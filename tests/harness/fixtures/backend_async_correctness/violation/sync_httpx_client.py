"""Q7 violation — sync httpx.Client banned in backend/src/.

Only AsyncClient is permitted on the backend spine.
"""
import httpx

def fetch(url: str) -> str:
    with httpx.Client() as client:
        return client.get(url).text
