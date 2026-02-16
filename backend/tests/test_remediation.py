import pytest
from datetime import datetime
from src.remediation.models import RunbookMatch, RemediationDecision, RemediationResult
from src.remediation.engine import RemediationEngine


class TestRunbookMatch:
    def test_creation(self):
        rb = RunbookMatch(
            runbook_id="rb-001",
            title="Restart crashed pods",
            match_score=0.8,
            matched_symptoms=["CrashLoopBackOff", "OOMKilled"],
            steps=["kubectl rollout restart", "verify pods"],
            success_rate=0.95,
            source="internal",
        )
        assert rb.runbook_id == "rb-001"
        assert rb.match_score == 0.8
        assert len(rb.matched_symptoms) == 2
        assert rb.source == "internal"

    def test_defaults(self):
        rb = RunbookMatch(runbook_id="rb-002", title="Scale up", match_score=0.5)
        assert rb.matched_symptoms == []
        assert rb.steps == []
        assert rb.success_rate == 0.0
        assert rb.last_used is None
        assert rb.source == "internal"


class TestRemediationDecision:
    def test_destructive_sets_double_confirmation(self):
        decision = RemediationDecision(
            proposed_action="Delete deployment",
            action_type="rollback",
            is_destructive=True,
            requires_double_confirmation=True,
        )
        assert decision.is_destructive is True
        assert decision.requires_double_confirmation is True

    def test_non_destructive_defaults(self):
        decision = RemediationDecision(
            proposed_action="Scale replicas to 3",
            action_type="scale",
        )
        assert decision.is_destructive is False
        assert decision.requires_double_confirmation is False
        assert decision.dry_run_available is True

    def test_pre_post_checks(self):
        decision = RemediationDecision(
            proposed_action="Rollback to v2.3.0",
            action_type="rollback",
            pre_checks=["verify current version", "check health"],
            post_checks=["verify rollback", "run smoke tests"],
        )
        assert len(decision.pre_checks) == 2
        assert len(decision.post_checks) == 2


class TestRemediationEngine:
    def setup_method(self):
        self.engine = RemediationEngine()

    def test_register_runbook(self):
        rb = RunbookMatch(
            runbook_id="rb-001", title="Fix OOM", match_score=0.0,
            matched_symptoms=["OOMKilled", "high_memory"],
        )
        self.engine.register_runbook(rb)
        assert len(self.engine._runbooks) == 1

    def test_match_runbooks_match(self):
        rb = RunbookMatch(
            runbook_id="rb-001", title="Fix OOM", match_score=0.0,
            matched_symptoms=["OOMKilled", "high_memory"],
        )
        self.engine.register_runbook(rb)
        matches = self.engine.match_runbooks(["OOMKilled", "high_memory"], threshold=0.5)
        assert len(matches) == 1
        assert matches[0].match_score == 1.0

    def test_match_runbooks_partial(self):
        rb = RunbookMatch(
            runbook_id="rb-001", title="Fix OOM", match_score=0.0,
            matched_symptoms=["OOMKilled", "high_memory"],
        )
        self.engine.register_runbook(rb)
        matches = self.engine.match_runbooks(["OOMKilled", "high_cpu"], threshold=0.3)
        assert len(matches) == 1
        # Jaccard: 1 intersection / 3 union = 0.333
        assert abs(matches[0].match_score - 1 / 3) < 0.01

    def test_match_runbooks_no_match(self):
        rb = RunbookMatch(
            runbook_id="rb-001", title="Fix OOM", match_score=0.0,
            matched_symptoms=["OOMKilled", "high_memory"],
        )
        self.engine.register_runbook(rb)
        matches = self.engine.match_runbooks(["network_timeout"], threshold=0.5)
        assert len(matches) == 0

    def test_match_runbooks_sorted_by_score(self):
        rb1 = RunbookMatch(
            runbook_id="rb-001", title="Fix OOM", match_score=0.0,
            matched_symptoms=["OOMKilled", "high_memory"],
        )
        rb2 = RunbookMatch(
            runbook_id="rb-002", title="Fix crash", match_score=0.0,
            matched_symptoms=["OOMKilled", "CrashLoopBackOff"],
        )
        self.engine.register_runbook(rb1)
        self.engine.register_runbook(rb2)
        matches = self.engine.match_runbooks(["OOMKilled", "high_memory"], threshold=0.3)
        assert len(matches) == 2
        assert matches[0].match_score >= matches[1].match_score

    def test_create_decision(self):
        decision = self.engine.create_decision(
            action="Restart pods",
            action_type="restart",
            is_destructive=False,
            rollback_plan="Scale back down",
            pre_checks=["check health"],
            post_checks=["verify restart"],
        )
        assert decision.proposed_action == "Restart pods"
        assert decision.action_type == "restart"
        assert decision.requires_double_confirmation is False

    def test_create_decision_destructive(self):
        decision = self.engine.create_decision(
            action="Delete namespace",
            action_type="rollback",
            is_destructive=True,
        )
        assert decision.is_destructive is True
        assert decision.requires_double_confirmation is True

    @pytest.mark.asyncio
    async def test_dry_run(self):
        decision = self.engine.create_decision(
            action="Scale replicas", action_type="scale",
        )
        result = await self.engine.dry_run(decision)
        assert result.status == "dry_run_complete"
        assert "Dry run" in result.dry_run_output
        assert result.started_at is not None
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_execute_success(self):
        decision = self.engine.create_decision(
            action="Restart deployment", action_type="restart",
        )
        result = await self.engine.execute(decision)
        assert result.status == "success"
        assert "Executed" in result.execution_output

    @pytest.mark.asyncio
    async def test_execute_destructive_without_confirmation_fails(self):
        decision = RemediationDecision(
            proposed_action="Delete all",
            action_type="rollback",
            is_destructive=True,
            requires_double_confirmation=False,
        )
        result = await self.engine.execute(decision)
        assert result.status == "failed"
        assert "double confirmation" in result.execution_output

    @pytest.mark.asyncio
    async def test_execute_destructive_with_confirmation_succeeds(self):
        decision = self.engine.create_decision(
            action="Delete deployment",
            action_type="rollback",
            is_destructive=True,
        )
        # create_decision sets requires_double_confirmation=True when is_destructive=True
        result = await self.engine.execute(decision)
        assert result.status == "success"

    @pytest.mark.asyncio
    async def test_rollback(self):
        decision = self.engine.create_decision(
            action="Deploy v2.3.0", action_type="rollback",
            rollback_plan="Redeploy v2.2.0",
        )
        exec_result = await self.engine.execute(decision)
        rolled_back = await self.engine.rollback(exec_result)
        assert rolled_back.status == "rolled_back"
        assert "Redeploy v2.2.0" in rolled_back.rollback_output
