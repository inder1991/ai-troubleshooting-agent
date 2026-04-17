"""Task 2.10 — SupervisorAgent is single-use and has no shared state."""
import pytest

from src.agents.supervisor import SupervisorAgent, SupervisorAlreadyConsumed


@pytest.mark.asyncio
async def test_two_supervisors_do_not_share_state():
    s1 = SupervisorAgent()
    s2 = SupervisorAgent()
    s1._seen_feedback_ids.add("inv-1")
    assert "inv-1" not in s2._seen_feedback_ids


@pytest.mark.asyncio
async def test_supervisor_rejects_reuse_via_run_v5():
    s = SupervisorAgent()
    s._claim_single_use()
    with pytest.raises(SupervisorAlreadyConsumed):
        s._claim_single_use()


def test_consumed_flag_starts_false():
    s = SupervisorAgent()
    assert s._consumed is False


def test_claim_sets_consumed_flag():
    s = SupervisorAgent()
    s._claim_single_use()
    assert s._consumed is True


def test_attributes_are_instance_level_not_class_level():
    """A mutation to one instance must not leak to another."""
    s1 = SupervisorAgent()
    s2 = SupervisorAgent()
    assert s1._all_signals is not s2._all_signals
    assert s1._candidate_repos is not s2._candidate_repos
    assert s1._confirmed_repo_map is not s2._confirmed_repo_map
    assert s1._seen_feedback_ids is not s2._seen_feedback_ids
