"""Task 3.6 — K8s continue-token pagination."""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.agents.k8s_pagination import list_all


# ── Fakes that mimic the kubernetes-client shape ─────────────────────────


@dataclass
class FakeMeta:
    _continue: str | None = None
    remaining_item_count: int | None = None


@dataclass
class FakePodList:
    items: list
    metadata: FakeMeta


class FakeK8s:
    def __init__(self, pods: list[str], page_size: int = 500):
        self._pods = pods
        self._default_page_size = page_size
        self.calls: list[dict] = []

    def list_namespaced_pod(self, *, namespace: str, limit: int, _continue: str | None = None, **_):
        self.calls.append({"namespace": namespace, "limit": limit, "_continue": _continue})
        start = int(_continue) if _continue else 0
        end = start + limit
        page = self._pods[start:end]
        next_token = str(end) if end < len(self._pods) else None
        return FakePodList(items=page, metadata=FakeMeta(_continue=next_token))


class FakeK8sAsync(FakeK8s):
    async def list_namespaced_pod(self, *, namespace: str, limit: int, _continue: str | None = None, **_):
        return super().list_namespaced_pod(
            namespace=namespace, limit=limit, _continue=_continue
        )


# ── Tests ────────────────────────────────────────────────────────────────


class TestContinueTokenLoop:
    @pytest.mark.asyncio
    async def test_list_pods_follows_continue_tokens(self):
        fake = FakeK8s([f"pod-{i}" for i in range(2300)])
        pods = await list_all(fake.list_namespaced_pod, limit=500, namespace="default")
        assert len(pods) == 2300
        # 2300 / 500 = 5 pages
        assert len(fake.calls) == 5

    @pytest.mark.asyncio
    async def test_single_page_short_circuits(self):
        fake = FakeK8s([f"pod-{i}" for i in range(42)])
        pods = await list_all(fake.list_namespaced_pod, limit=500, namespace="default")
        assert len(pods) == 42
        assert len(fake.calls) == 1

    @pytest.mark.asyncio
    async def test_empty_cluster_returns_empty(self):
        fake = FakeK8s([])
        pods = await list_all(fake.list_namespaced_pod, namespace="default")
        assert pods == []
        assert len(fake.calls) == 1

    @pytest.mark.asyncio
    async def test_kwargs_propagate_to_every_call(self):
        fake = FakeK8s([f"pod-{i}" for i in range(2000)])
        await list_all(
            fake.list_namespaced_pod,
            limit=500,
            namespace="payments",
        )
        for c in fake.calls:
            assert c["namespace"] == "payments"
            assert c["limit"] == 500


class TestAsyncSupport:
    @pytest.mark.asyncio
    async def test_async_list_fn_also_paginates(self):
        fake = FakeK8sAsync([f"pod-{i}" for i in range(1500)])
        pods = await list_all(fake.list_namespaced_pod, limit=500, namespace="default")
        assert len(pods) == 1500


class TestDictShape:
    @pytest.mark.asyncio
    async def test_dict_response_shape_also_paginates(self):
        """REST-style dicts (metadata.continue) should also work."""

        pages = [
            {"items": [1, 2, 3], "metadata": {"continue": "tok1"}},
            {"items": [4, 5, 6], "metadata": {"continue": "tok2"}},
            {"items": [7], "metadata": {"continue": None}},
        ]

        def fake_list(**kw):
            return pages.pop(0)

        items = await list_all(fake_list, limit=3)
        assert items == [1, 2, 3, 4, 5, 6, 7]
