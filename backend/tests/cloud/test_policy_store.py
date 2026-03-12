"""Tests for PolicyStore."""
import os
import tempfile
import pytest

from src.cloud.policy_store import PolicyStore


@pytest.fixture
def tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    for ext in ("", "-wal", "-shm"):
        try:
            os.unlink(path + ext)
        except FileNotFoundError:
            pass


@pytest.fixture
def store(tmp_db):
    return PolicyStore(db_path=tmp_db)


class TestPolicyGroupCRUD:
    @pytest.mark.asyncio
    async def test_upsert_and_get(self, store):
        await store.upsert_policy_group(
            policy_group_id="pg-001",
            name="web-sg",
            provider="aws",
            source_type="security_group",
            cloud_resource_id="res-001",
        )
        group = await store.get_policy_group("pg-001")
        assert group is not None
        assert group["name"] == "web-sg"
        assert group["source_type"] == "security_group"

    @pytest.mark.asyncio
    async def test_get_by_cloud_resource(self, store):
        await store.upsert_policy_group(
            policy_group_id="pg-001",
            name="web-sg",
            provider="aws",
            source_type="security_group",
            cloud_resource_id="res-001",
        )
        group = await store.get_by_cloud_resource("res-001")
        assert group is not None
        assert group["policy_group_id"] == "pg-001"

    @pytest.mark.asyncio
    async def test_list_groups(self, store):
        for i in range(3):
            await store.upsert_policy_group(
                policy_group_id=f"pg-{i}",
                name=f"sg-{i}",
                provider="aws",
                source_type="security_group",
            )
        groups = await store.list_policy_groups()
        assert len(groups) == 3


class TestPolicyRuleCRUD:
    @pytest.mark.asyncio
    async def test_add_and_list_rules(self, store):
        await store.upsert_policy_group(
            policy_group_id="pg-001", name="web-sg",
            provider="aws", source_type="security_group",
        )
        await store.add_rule(
            rule_id="r-001", policy_group_id="pg-001",
            direction="inbound", action="allow",
            protocol="tcp", port_range_start=443,
            port_range_end=443, source_cidr="0.0.0.0/0",
        )
        await store.add_rule(
            rule_id="r-002", policy_group_id="pg-001",
            direction="outbound", action="allow",
            protocol="all",
        )
        rules = await store.list_rules("pg-001")
        assert len(rules) == 2

    @pytest.mark.asyncio
    async def test_replace_rules(self, store):
        await store.upsert_policy_group(
            policy_group_id="pg-001", name="web-sg",
            provider="aws", source_type="security_group",
        )
        await store.add_rule(
            rule_id="r-001", policy_group_id="pg-001",
            direction="inbound", action="allow", protocol="tcp",
        )
        # Replace all rules
        await store.replace_rules("pg-001", [
            {"rule_id": "r-new", "direction": "inbound",
             "action": "deny", "protocol": "udp"},
        ])
        rules = await store.list_rules("pg-001")
        assert len(rules) == 1
        assert rules[0]["action"] == "deny"


class TestPolicyAttachments:
    @pytest.mark.asyncio
    async def test_attach_and_list(self, store):
        await store.upsert_policy_group(
            policy_group_id="pg-001", name="web-sg",
            provider="aws", source_type="security_group",
        )
        await store.attach(
            attachment_id="att-001",
            policy_group_id="pg-001",
            target_resource_id="res-eni-001",
            target_type="eni",
        )
        attachments = await store.list_attachments("pg-001")
        assert len(attachments) == 1
        assert attachments[0]["target_type"] == "eni"
