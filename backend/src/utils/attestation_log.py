import logging
from datetime import datetime

import redis.asyncio as redis

logger = logging.getLogger(__name__)

STREAM_KEY = "audit:attestations"
LIFECYCLE_STREAM_KEY = "audit:attestation_lifecycle"
MAX_STREAM_LEN = 10_000


class AttestationLogger:
    def __init__(self, redis_client: redis.Redis):
        self._redis = redis_client

    async def log_decision(self, session_id: str, finding_id: str, decision: str,
                           decided_by: str, confidence: float, finding_summary: str) -> str:
        entry = {
            "session_id": session_id,
            "finding_id": finding_id,
            "decision": decision,
            "decided_by": decided_by,
            "decided_at": datetime.utcnow().isoformat(),
            "confidence": str(confidence),
            "finding_summary": finding_summary,
        }
        entry_id = await self._redis.xadd(STREAM_KEY, entry, maxlen=MAX_STREAM_LEN, approximate=True)
        return entry_id

    async def query(self, session_id: str | None = None, decided_by: str | None = None,
                    since: str | None = None, count: int = 500) -> list[dict]:
        start = "-"
        if since:
            try:
                dt = datetime.fromisoformat(since)
                start = str(int(dt.timestamp() * 1000))
            except (ValueError, TypeError):
                start = "-"

        raw = await self._redis.xrange(STREAM_KEY, min=start, max="+", count=count)
        results = []
        for entry_id, fields in raw:
            record = {
                (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
                for k, v in fields.items()
            }
            record["stream_id"] = entry_id.decode() if isinstance(entry_id, bytes) else entry_id
            if session_id and record.get("session_id") != session_id:
                continue
            if decided_by and record.get("decided_by") != decided_by:
                continue
            if "confidence" in record:
                try:
                    record["confidence"] = float(record["confidence"])
                except (ValueError, TypeError):
                    pass
            results.append(record)
        return results

    async def log_lifecycle(self, session_id: str, event: str, details: dict) -> str:
        entry = {
            "session_id": session_id,
            "event": event,
            "timestamp": datetime.utcnow().isoformat(),
            **{k: str(v) for k, v in details.items()},
        }
        return await self._redis.xadd(
            LIFECYCLE_STREAM_KEY, entry,
            maxlen=MAX_STREAM_LEN, approximate=True,
        )

    async def query_lifecycle(self, session_id: str | None = None, count: int = 500) -> list[dict]:
        raw = await self._redis.xrange(LIFECYCLE_STREAM_KEY, min="-", max="+", count=count)
        results = []
        for entry_id, fields in raw:
            record = {
                (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
                for k, v in fields.items()
            }
            record["stream_id"] = entry_id.decode() if isinstance(entry_id, bytes) else entry_id
            if session_id and record.get("session_id") != session_id:
                continue
            results.append(record)
        return results
