import pytest
from src.models.pending_action import PendingAction


def test_campaign_confirm_pending_action_shape():
    pa = PendingAction(
        type="campaign_execute_confirm",
        blocking=True,
        actions=["confirm", "cancel"],
        expires_at=None,
        context={"repo_count": 5, "repos": ["repo1", "repo2"]},
        version=1,
    )
    d = pa.to_dict()
    assert d["type"] == "campaign_execute_confirm"
    assert d["actions"] == ["confirm", "cancel"]
    assert d["context"]["repo_count"] == 5
