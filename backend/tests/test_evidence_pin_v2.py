"""Tests for EvidencePin v2 schema extensions (live investigation steering fields).

Validates backward compatibility, new field defaults, manual pin creation,
and Literal validation for domain/validation_status/evidence_type.
"""

import pytest
from datetime import datetime
from pydantic import ValidationError
from src.models.schemas import EvidencePin, TimeWindow


class TestEvidencePinV2:
    """Tests for the extended EvidencePin schema."""

    # -- helpers --
    @staticmethod
    def _make_minimal_pin(**overrides) -> EvidencePin:
        """Create an EvidencePin with only the original required fields."""
        defaults = dict(
            claim="Pod crash-looping in namespace prod",
            supporting_evidence=["OOMKilled exit code 137"],
            source_agent="log_agent",
            source_tool="elasticsearch",
            confidence=0.85,
            timestamp=datetime(2026, 2, 28, 12, 0, 0),
            evidence_type="log",
        )
        defaults.update(overrides)
        return EvidencePin(**defaults)

    # -----------------------------------------------------------------------
    # 1. Backward compatibility: new fields all have sensible defaults
    # -----------------------------------------------------------------------
    def test_new_fields_have_defaults(self):
        """Creating a pin with only the original V5 fields should succeed
        and populate all new fields with their defaults."""
        pin = self._make_minimal_pin()

        # Original fields unchanged
        assert pin.claim == "Pod crash-looping in namespace prod"
        assert pin.source_agent == "log_agent"
        assert pin.confidence == 0.85
        assert pin.evidence_type == "log"

        # New fields should have defaults
        assert pin.id is not None and len(pin.id) > 0  # auto UUID
        assert pin.source == "auto"
        assert pin.triggered_by == "automated_pipeline"
        assert pin.raw_output is None
        assert pin.severity is None
        assert pin.causal_role is None
        assert pin.domain == "unknown"
        assert pin.validation_status == "pending_critic"
        assert pin.namespace is None
        assert pin.service is None
        assert pin.resource_name is None
        assert pin.time_window is None

    # -----------------------------------------------------------------------
    # 2. Manual pin creation with all new fields explicitly set
    # -----------------------------------------------------------------------
    def test_manual_pin_creation(self):
        """A manual pin (submitted via user chat) should accept all new fields."""
        tw = TimeWindow(start="2026-02-28T11:00:00Z", end="2026-02-28T12:00:00Z")
        pin = EvidencePin(
            id="custom-id-123",
            claim="Liveness probe failing on payment-svc",
            supporting_evidence=["kubectl describe pod output"],
            source_agent=None,  # manual pins have no agent
            source_tool="kubectl",
            confidence=0.70,
            timestamp=datetime(2026, 2, 28, 12, 0, 0),
            evidence_type="k8s_resource",
            source="manual",
            triggered_by="user_chat",
            raw_output="NAME   READY   STATUS\npayment-svc-abc   0/1   CrashLoopBackOff",
            severity="critical",
            causal_role="root_cause",
            domain="compute",
            validation_status="pending_critic",
            namespace="prod",
            service="payment-svc",
            resource_name="payment-svc-abc",
            time_window=tw,
        )
        assert pin.id == "custom-id-123"
        assert pin.source_agent is None
        assert pin.source == "manual"
        assert pin.triggered_by == "user_chat"
        assert pin.evidence_type == "k8s_resource"
        assert pin.severity == "critical"
        assert pin.causal_role == "root_cause"
        assert pin.domain == "compute"
        assert pin.namespace == "prod"
        assert pin.service == "payment-svc"
        assert pin.resource_name == "payment-svc-abc"
        assert pin.time_window is not None
        assert pin.time_window.start == "2026-02-28T11:00:00Z"

    # -----------------------------------------------------------------------
    # 3. Domain Literal validation — invalid value rejected
    # -----------------------------------------------------------------------
    def test_domain_literal_validation(self):
        """An invalid domain value should raise a ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            self._make_minimal_pin(domain="database")  # not in the Literal
        assert "domain" in str(exc_info.value).lower()

    # -----------------------------------------------------------------------
    # 4. validation_status Literal — all three valid values accepted
    # -----------------------------------------------------------------------
    def test_validation_status_literal(self):
        """All three validation_status values should be accepted."""
        for status in ("pending_critic", "validated", "rejected"):
            pin = self._make_minimal_pin(validation_status=status)
            assert pin.validation_status == status

    def test_validation_status_invalid_rejected(self):
        """An invalid validation_status should raise a ValidationError."""
        with pytest.raises(ValidationError):
            self._make_minimal_pin(validation_status="approved")

    # -----------------------------------------------------------------------
    # 5. source_agent is nullable for manual pins
    # -----------------------------------------------------------------------
    def test_source_agent_nullable_for_manual(self):
        """source_agent=None should be accepted (for manual / user-submitted pins)."""
        pin = self._make_minimal_pin(source_agent=None, source="manual")
        assert pin.source_agent is None
        assert pin.source == "manual"

    # -----------------------------------------------------------------------
    # 6. evidence_type includes k8s_resource
    # -----------------------------------------------------------------------
    def test_evidence_type_includes_k8s_resource(self):
        """'k8s_resource' should be a valid evidence_type value."""
        pin = self._make_minimal_pin(evidence_type="k8s_resource")
        assert pin.evidence_type == "k8s_resource"

    def test_evidence_type_invalid_rejected(self):
        """An invalid evidence_type should still raise a ValidationError."""
        with pytest.raises(ValidationError):
            self._make_minimal_pin(evidence_type="database_query")

    # -----------------------------------------------------------------------
    # Bonus: auto-generated id is a valid UUID string
    # -----------------------------------------------------------------------
    def test_auto_id_is_uuid(self):
        """The default id should be a valid UUID4 string."""
        import uuid
        pin = self._make_minimal_pin()
        parsed = uuid.UUID(pin.id)  # will raise if not a valid UUID
        assert parsed.version == 4

    def test_two_pins_get_different_ids(self):
        """Each pin should get a unique auto-generated id."""
        pin_a = self._make_minimal_pin()
        pin_b = self._make_minimal_pin()
        assert pin_a.id != pin_b.id
