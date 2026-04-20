"""In-process state for the demo-controller.

Intentionally NOT persistent — the demo-controller is the
single-operator tool running on a laptop during a CXO demo. Reset
on pod / process restart is fine (and desirable — state should
always start clean for a fresh demo run).
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class DemoState:
    traffic_on: bool = False
    fault_on: bool = False
    current_incident_id: Optional[str] = None
    last_trigger_ts: Optional[str] = None
    last_verdict_ts: Optional[str] = None
    history_seeded: bool = False

    # Last POST-time record so the operator page can show "verdict
    # landed in 01:31 (expected ~01:30)" without needing to poll the
    # workflow backend itself.
    triggered_txn_ids: list[str] = field(default_factory=list)

    def mark_triggered(self, incident_id: str, txn_ids: list[str]) -> None:
        self.current_incident_id = incident_id
        self.triggered_txn_ids = list(txn_ids)
        self.last_trigger_ts = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "traffic_on": self.traffic_on,
            "fault_on": self.fault_on,
            "current_incident_id": self.current_incident_id,
            "last_trigger_ts": self.last_trigger_ts,
            "last_verdict_ts": self.last_verdict_ts,
            "history_seeded": self.history_seeded,
            "triggered_count": len(self.triggered_txn_ids),
        }


STATE = DemoState()
