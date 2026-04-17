"""Task 4.7 - 4.9 — design stubs raise NotImplementedError cleanly."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.learning import LearningPipeline, LearningReport, PriorUpdate, SignatureFloorUpdate
from src.remediation.counterfactual import (
    FORBIDDEN_ACTIONS,
    ProposedRemediation,
    estimate_blast_radius,
    is_eligible,
    replay_in_staging,
)


class TestLearningStub:
    @pytest.mark.asyncio
    async def test_consume_feedback_batch_raises(self):
        p = LearningPipeline()
        with pytest.raises(NotImplementedError):
            await p.consume_feedback_batch(since=datetime.now() - timedelta(days=7))

    def test_dataclasses_importable(self):
        PriorUpdate(agent_name="log", before=0.5, after=0.55, sample_count_delta=1)
        SignatureFloorUpdate(pattern_name="oom", before=0.7, after=0.72)
        LearningReport(since=datetime.now(), until=datetime.now())


class TestCounterfactualStub:
    @pytest.mark.asyncio
    async def test_replay_raises(self):
        with pytest.raises(NotImplementedError):
            await replay_in_staging(ProposedRemediation(action_kind="restart_pod", target="p-0"))

    def test_estimate_blast_radius_raises(self):
        with pytest.raises(NotImplementedError):
            estimate_blast_radius(ProposedRemediation(action_kind="restart_pod", target="p-0"))


class TestSafetyInvariants:
    def test_forbidden_actions_never_eligible(self):
        for kind in FORBIDDEN_ACTIONS:
            assert not is_eligible(ProposedRemediation(action_kind=kind, target="x"))

    def test_non_forbidden_action_is_eligible(self):
        assert is_eligible(ProposedRemediation(action_kind="restart_pod", target="p-0"))
