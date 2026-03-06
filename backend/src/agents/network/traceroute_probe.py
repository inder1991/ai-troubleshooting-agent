"""Traceroute probe node — runs traceroute and detects routing loops."""
import socket
import threading
import time as time_mod
import uuid
from datetime import datetime, timezone
from typing import Optional

# Graceful import of icmplib
try:
    from icmplib import traceroute as icmp_traceroute
    HAS_ICMPLIB = True
except ImportError:
    icmp_traceroute = None  # type: ignore[assignment]
    HAS_ICMPLIB = False


# Rate limiting: max concurrent traceroutes
_MAX_CONCURRENT = 3
_semaphore = threading.Semaphore(_MAX_CONCURRENT)


def _tcp_traceroute(dst_ip: str, port: int = 443, max_hops: int = 30, timeout: float = 2.0) -> list[dict]:
    """TCP SYN traceroute — works through ICMP-blocking firewalls."""
    hops = []
    for ttl in range(1, max_hops + 1):
        recv_sock = None
        send_sock = None
        try:
            recv_sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
            recv_sock.settimeout(timeout)
            send_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            send_sock.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, ttl)
            send_sock.settimeout(timeout)

            start = time_mod.monotonic()
            try:
                send_sock.connect_ex((dst_ip, port))
                data, addr = recv_sock.recvfrom(512)
                rtt = (time_mod.monotonic() - start) * 1000
                hops.append({"hop": ttl, "ip": addr[0], "rtt_ms": round(rtt, 2), "status": "responded"})
                if addr[0] == dst_ip:
                    break
            except socket.timeout:
                hops.append({"hop": ttl, "ip": None, "rtt_ms": 0, "status": "timeout"})
        except OSError:
            hops.append({"hop": ttl, "ip": None, "rtt_ms": 0, "status": "timeout"})
        finally:
            if send_sock:
                send_sock.close()
            if recv_sock:
                recv_sock.close()
    return hops


def _udp_traceroute(dst_ip: str, port: int = 33434, max_hops: int = 30, timeout: float = 2.0) -> list[dict]:
    """UDP traceroute — fallback when both ICMP and TCP fail."""
    hops = []
    for ttl in range(1, max_hops + 1):
        recv_sock = None
        send_sock = None
        try:
            recv_sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
            recv_sock.settimeout(timeout)
            send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            send_sock.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, ttl)

            start = time_mod.monotonic()
            send_sock.sendto(b"", (dst_ip, port + ttl))
            try:
                data, addr = recv_sock.recvfrom(512)
                rtt = (time_mod.monotonic() - start) * 1000
                hops.append({"hop": ttl, "ip": addr[0], "rtt_ms": round(rtt, 2), "status": "responded"})
                if addr[0] == dst_ip:
                    break
            except socket.timeout:
                hops.append({"hop": ttl, "ip": None, "rtt_ms": 0, "status": "timeout"})
        except OSError:
            hops.append({"hop": ttl, "ip": None, "rtt_ms": 0, "status": "timeout"})
        finally:
            if send_sock:
                send_sock.close()
            if recv_sock:
                recv_sock.close()
    return hops


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

        # Check if ICMP got any real responses
        responded_hops = [h for h in hops if h.get("ip") and h["ip"] != ""]
        trace_method = "ICMP"

        if not responded_hops:
            # ICMP failed — try TCP
            tcp_hops = _tcp_traceroute(dst_ip)
            tcp_responded = [h for h in tcp_hops if h.get("ip")]
            if tcp_responded:
                hops = []
                for h in tcp_hops:
                    hops.append({
                        "id": f"{trace_id}-{h['hop']}",
                        "trace_id": trace_id,
                        "hop_number": h["hop"],
                        "ip": h["ip"] or "",
                        "rtt_ms": h["rtt_ms"],
                        "status": h["status"],
                    })
                trace_method = "TCP"
            else:
                # TCP also failed — try UDP
                udp_hops = _udp_traceroute(dst_ip)
                udp_responded = [h for h in udp_hops if h.get("ip")]
                if udp_responded:
                    hops = []
                    for h in udp_hops:
                        hops.append({
                            "id": f"{trace_id}-{h['hop']}",
                            "trace_id": trace_id,
                            "hop_number": h["hop"],
                            "ip": h["ip"] or "",
                            "rtt_ms": h["rtt_ms"],
                            "status": h["status"],
                        })
                    trace_method = "UDP"

        return {
            "trace_id": trace_id,
            "trace_method": trace_method,
            "trace_hops": hops,
            "routing_loop_detected": loop_detected,
            "traced_path": {
                "hops": [h["ip"] for h in hops if h["ip"]],
                "method": trace_method,
                "hop_count": len(hops),
            },
            "evidence": [{"type": "traceroute", "detail": f"{trace_method} traceroute: {len(hops)} hops, loop={'yes' if loop_detected else 'no'}"}],
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
