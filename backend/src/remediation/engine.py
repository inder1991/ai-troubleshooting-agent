from .models import RunbookMatch, RemediationDecision, RemediationResult
from datetime import datetime


class RemediationEngine:
    def __init__(self):
        self._runbooks: list[RunbookMatch] = []
        self._results: list[RemediationResult] = []

    def register_runbook(self, runbook: RunbookMatch) -> None:
        self._runbooks.append(runbook)

    def match_runbooks(self, symptoms: list[str], threshold: float = 0.5) -> list[RunbookMatch]:
        matches = []
        for rb in self._runbooks:
            rb_symptoms = set(rb.matched_symptoms)
            current = set(symptoms)
            if not rb_symptoms and not current:
                continue
            intersection = rb_symptoms & current
            union = rb_symptoms | current
            score = len(intersection) / len(union) if union else 0.0
            if score >= threshold:
                # Create a copy with updated score
                matched = rb.model_copy(update={"match_score": score})
                matches.append(matched)
        return sorted(matches, key=lambda x: x.match_score, reverse=True)

    def create_decision(self, action: str, action_type: str,
                        is_destructive: bool = False,
                        rollback_plan: str = "",
                        pre_checks: list[str] = None,
                        post_checks: list[str] = None) -> RemediationDecision:
        return RemediationDecision(
            proposed_action=action,
            action_type=action_type,
            is_destructive=is_destructive,
            requires_double_confirmation=is_destructive,
            rollback_plan=rollback_plan,
            pre_checks=pre_checks or [],
            post_checks=post_checks or [],
        )

    async def dry_run(self, decision: RemediationDecision) -> RemediationResult:
        result = RemediationResult(
            decision=decision,
            status="dry_run_complete",
            dry_run_output=f"Dry run of '{decision.proposed_action}': would affect {decision.action_type}",
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )
        self._results.append(result)
        return result

    async def execute(self, decision: RemediationDecision) -> RemediationResult:
        # Safety checks
        if decision.is_destructive and not decision.requires_double_confirmation:
            return RemediationResult(
                decision=decision, status="failed",
                execution_output="Destructive action requires double confirmation",
            )
        result = RemediationResult(
            decision=decision,
            status="success",
            execution_output=f"Executed: {decision.proposed_action}",
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )
        self._results.append(result)
        return result

    async def rollback(self, result: RemediationResult) -> RemediationResult:
        rolled_back = result.model_copy(update={
            "status": "rolled_back",
            "rollback_output": f"Rolled back: {result.decision.rollback_plan}",
            "completed_at": datetime.now(),
        })
        return rolled_back
