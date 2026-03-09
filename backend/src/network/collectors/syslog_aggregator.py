"""Template-based syslog message aggregation.

Groups similar syslog messages by extracting a template (replacing variable
parts like IPs, numbers, and interface names with placeholders) and then
aggregating by (device_ip, severity, template).
"""
from __future__ import annotations

import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field


_IP_RE = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
_NUM_RE = re.compile(r"\b\d{2,}\b")  # 2+ digit numbers
_HEX_RE = re.compile(r"\b0x[0-9a-fA-F]+\b")
_IFACE_RE = re.compile(
    r"\b(GigabitEthernet|FastEthernet|TenGigE|Ethernet|eth|ens|enp|ge-|xe-|et-)"
    r"[\w/.:]+\b"
)


@dataclass
class _AggGroup:
    device_ip: str
    severity: str
    facility: str
    template: str
    count: int = 0
    first_seen: float = 0.0
    last_seen: float = 0.0
    samples: list[str] = field(default_factory=list)
    MAX_SAMPLES: int = 5


class SyslogAggregator:
    """Groups syslog messages by extracted template."""

    def __init__(self, max_groups: int = 2000) -> None:
        self.max_groups = max_groups
        self._groups: OrderedDict[str, _AggGroup] = OrderedDict()

    def _extract_template(self, message: str) -> str:
        """Replace variable portions of the message with placeholders."""
        tpl = _IP_RE.sub("<IP>", message)
        tpl = _HEX_RE.sub("<HEX>", tpl)
        tpl = _IFACE_RE.sub("<IFACE>", tpl)
        tpl = _NUM_RE.sub("<NUM>", tpl)
        return tpl

    def _make_key(self, device_ip: str, severity: str, template: str) -> str:
        return f"{device_ip}|{severity}|{template}"

    def add(self, device_ip: str, message: str, severity: str, facility: str) -> None:
        """Add a syslog message to the aggregator."""
        template = self._extract_template(message)
        key = self._make_key(device_ip, severity, template)
        now = time.monotonic()

        if key in self._groups:
            grp = self._groups[key]
            grp.count += 1
            grp.last_seen = now
            if len(grp.samples) < grp.MAX_SAMPLES:
                grp.samples.append(message)
            # Move to end (most recently seen)
            self._groups.move_to_end(key)
        else:
            # Evict oldest if at capacity
            if len(self._groups) >= self.max_groups:
                self._groups.popitem(last=False)
            self._groups[key] = _AggGroup(
                device_ip=device_ip,
                severity=severity,
                facility=facility,
                template=template,
                count=1,
                first_seen=now,
                last_seen=now,
                samples=[message],
            )

    def get_groups(self) -> list[dict]:
        """Return all aggregation groups sorted by count descending."""
        result = []
        for grp in self._groups.values():
            result.append({
                "device_ip": grp.device_ip,
                "severity": grp.severity,
                "facility": grp.facility,
                "template": grp.template,
                "count": grp.count,
                "first_seen": grp.first_seen,
                "last_seen": grp.last_seen,
                "samples": list(grp.samples),
            })
        result.sort(key=lambda x: x["count"], reverse=True)
        return result

    def clear(self) -> None:
        """Remove all aggregated groups."""
        self._groups.clear()
