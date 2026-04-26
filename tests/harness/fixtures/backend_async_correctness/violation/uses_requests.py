"""Q7 violation — bans the sync `requests` library."""
import requests

def fetch(url: str) -> str:
    return requests.get(url).text
