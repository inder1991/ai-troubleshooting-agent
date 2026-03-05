"""Traceroute probe node — runs traceroute and detects routing loops."""
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

# Graceful import of icmplib
try:
    from icmplib import traceroute as icmp_traceroute
    HAS_ICMPLIB = True
except ImportError:
    HAS_ICMPLIB = False


# Rate limiting: max concurrent traceroutes
_MAX_CONCURRENT = 3
_semaphore = threading.Semaphore(_MAX_CONCURRENT)


def traceroute_probe(state: dict) -> dict:
    """Run traceroute from current host to destination.

    Features:
    - Rate limiting (max 3 concurrent)
    - Loop detection (repeated IPs)
    - Graceful fallback when icmplib unavailable
    """
    dst_ip = state.get("dst_ip", "")

    if not dst_ip:
        return {
            "trace_method": "unavailable",
            "trace_hops": [],
            "evidence": [{"type": "traceroute", "detail": "No destination IP"}],
        }

    if not _semaphore.acquire(blocking=False):
        return {
            "trace_method": "unavailable",
            "trace_hops": [],
            "evidence": [{"type": "traceroute", "detail": "Rate limit: too many concurrent traceroutes"}],
        }

    # Everything from here is inside try/finally to guarantee release
    try:
        if not HAS_ICMPLIB:
            return {
                "trace_method": "unavailable",
                "trace_hops": [],
                "evidence": [{"type": "traceroute", "detail": "icmplib not available"}],
            }

        trace_id = str(uuid.uuid4())[:8]

        result = icmp_traceroute(dst_ip, max_hops=30, timeout=2)

        hops = []
        seen_ips = set()
        loop_detected = False

        for i, hop in enumerate(result):
            hop_ip = hop.address if hop.address != "*" else ""
            rtt = hop.avg_rtt if hasattr(hop, 'avg_rtt') else 0.0
            status = "responded" if hop_ip else "timeout"

            # Loop detection
            if hop_ip and hop_ip in seen_ips:
                loop_detected = True
            if hop_ip:
                seen_ips.add(hop_ip)

            hops.append({
                "id": f"hop-{trace_id}-{i+1}",
                "trace_id": trace_id,
                "hop_number": i + 1,
                "ip": hop_ip,
                "rtt_ms": rtt,
                "status": status,
            })

        return {
            "trace_id": trace_id,
            "trace_method": "icmp",
            "trace_hops": hops,
            "routing_loop_detected": loop_detected,
            "traced_path": {
                "hops": [h["ip"] for h in hops if h["ip"]],
                "method": "icmp",
                "hop_count": len(hops),
            },
            "evidence": [{"type": "traceroute", "detail": f"ICMP traceroute: {len(hops)} hops, loop={'yes' if loop_detected else 'no'}"}],
        }
    except Exception as e:
        return {
            "trace_method": "unavailable",
            "trace_hops": [],
            "error": str(e),
            "evidence": [{"type": "traceroute", "detail": f"Traceroute failed: {e}"}],
        }
    finally:
        _semaphore.release()


def make_manual_trace(hops: list[dict]) -> dict:
    """Create a trace from manually-provided hop data (for testing/demo)."""
    trace_id = str(uuid.uuid4())[:8]
    seen_ips = set()
    loop_detected = False

    formatted_hops = []
    for i, h in enumerate(hops):
        hop_ip = h.get("ip", "")
        if hop_ip and hop_ip in seen_ips:
            loop_detected = True
        if hop_ip:
            seen_ips.add(hop_ip)
        formatted_hops.append({
            "id": f"hop-{trace_id}-{i+1}",
            "trace_id": trace_id,
            "hop_number": i + 1,
            "ip": hop_ip,
            "rtt_ms": h.get("rtt_ms", 0.0),
            "status": h.get("status", "responded"),
        })

    return {
        "trace_id": trace_id,
        "trace_method": "manual",
        "trace_hops": formatted_hops,
        "routing_loop_detected": loop_detected,
        "traced_path": {
            "hops": [h["ip"] for h in formatted_hops if h["ip"]],
            "method": "manual",
            "hop_count": len(formatted_hops),
        },
        "evidence": [{"type": "traceroute", "detail": f"Manual trace: {len(formatted_hops)} hops"}],
    }
