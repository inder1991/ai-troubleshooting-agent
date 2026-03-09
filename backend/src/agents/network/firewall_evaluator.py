"""Firewall evaluator node — simulates flows through firewalls in path."""
import asyncio
from typing import Optional
from src.network.adapters.base import FirewallAdapter
from src.network.models import VerdictMatchType


# Bounded concurrency for adapter calls
_MAX_CONCURRENCY = 5


async def firewall_evaluator(state: dict, *, adapters: dict[str, FirewallAdapter]) -> dict:
    """Evaluate flow against all firewalls identified in the path.

    Uses bounded concurrency (max 5 concurrent adapter calls).
    Normalizes verdict confidence based on match type.
    """
    firewalls = state.get("firewalls_in_path", [])
    src_ip = state.get("src_ip", "")
    dst_ip = state.get("dst_ip", "")
    port = state.get("port", 0)
    protocol = state.get("protocol", "tcp")

    if not firewalls:
        return {
            "firewall_verdicts": [],
            "evidence": [{"type": "firewall", "detail": "No firewalls in path"}],
        }

    semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)
    verdicts = []

    async def evaluate_one(fw: dict) -> Optional[dict]:
        device_id = fw.get("device_id", "")
        adapter = adapters.get(device_id)
        if not adapter:
            return {
                "device_id": device_id,
                "device_name": fw.get("device_name", ""),
                "action": "unknown",
                "confidence": 0.0,
                "match_type": VerdictMatchType.ADAPTER_UNAVAILABLE.value,
                "details": "No adapter configured for this firewall",
            }

        async with semaphore:
            try:
                verdict = await adapter.simulate_flow(src_ip, dst_ip, port, protocol)
                try:
                    return {
                        "device_id": device_id,
                        "device_name": fw.get("device_name", ""),
                        "action": verdict.action.value,
                        "rule_id": getattr(verdict, "rule_id", ""),
                        "rule_name": getattr(verdict, "rule_name", ""),
                        "confidence": getattr(verdict, "confidence", 0.0),
                        "match_type": verdict.match_type.value,
                        "details": getattr(verdict, "details", ""),
                        "matched_source": getattr(verdict, "matched_source", ""),
                        "matched_destination": getattr(verdict, "matched_destination", ""),
                        "matched_ports": getattr(verdict, "matched_ports", ""),
                    }
                except AttributeError as ae:
                    return {
                        "device_id": device_id,
                        "device_name": fw.get("device_name", ""),
                        "action": "error",
                        "confidence": 0.0,
                        "match_type": VerdictMatchType.ADAPTER_UNAVAILABLE.value,
                        "details": f"Malformed verdict: {ae}",
                    }
            except Exception as e:
                return {
                    "device_id": device_id,
                    "device_name": fw.get("device_name", ""),
                    "action": "error",
                    "confidence": 0.0,
                    "match_type": VerdictMatchType.ADAPTER_UNAVAILABLE.value,
                    "details": f"Adapter error: {e}",
                }

    tasks = [evaluate_one(fw) for fw in firewalls]
    results = await asyncio.gather(*tasks)
    verdicts = [r for r in results if r is not None]

    # Determine overall verdict
    any_deny = any(v["action"] in ("deny", "drop") for v in verdicts)
    summary = "BLOCKED" if any_deny else "ALLOWED"

    return {
        "firewall_verdicts": verdicts,
        "evidence": [{
            "type": "firewall",
            "detail": f"Flow {summary} — evaluated {len(verdicts)} firewalls",
        }],
    }
