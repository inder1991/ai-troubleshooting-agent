"""Tests for the Agent Registry: structure validation, status logic, and health cache."""

import pytest

from src.api.agent_registry import (
    AGENT_REGISTRY,
    AGENT_REGISTRY_MAP,
    HEALTH_PROBES,
    get_agent_status,
    clear_health_cache,
    _CACHE_TTL,
    _health_cache,
)


# =========================================================================
# Registry Structure Tests
# =========================================================================


class TestRegistryStructure:
    """Validate the static AGENT_REGISTRY has correct shape and data."""

    def test_registry_has_25_agents(self):
        assert len(AGENT_REGISTRY) == 25

    def test_registry_map_has_25_agents(self):
        assert len(AGENT_REGISTRY_MAP) == 25

    def test_all_ids_unique(self):
        ids = [a["id"] for a in AGENT_REGISTRY]
        assert len(ids) == len(set(ids)), f"Duplicate IDs found: {[x for x in ids if ids.count(x) > 1]}"

    def test_all_names_uppercase(self):
        for agent in AGENT_REGISTRY:
            assert agent["name"] == agent["name"].upper(), (
                f"Agent {agent['id']} name '{agent['name']}' is not uppercase"
            )

    def test_required_fields_present(self):
        required = {
            "id", "name", "workflow", "role", "description", "icon",
            "level", "llm_config", "timeout_s", "tools",
            "tool_health_checks", "architecture_stages",
        }
        for agent in AGENT_REGISTRY:
            missing = required - set(agent.keys())
            assert not missing, f"Agent {agent['id']} missing fields: {missing}"

    def test_valid_workflows(self):
        valid = {"app_diagnostics", "cluster_diagnostics"}
        for agent in AGENT_REGISTRY:
            assert agent["workflow"] in valid, (
                f"Agent {agent['id']} has invalid workflow '{agent['workflow']}'"
            )

    def test_valid_roles(self):
        valid = {"orchestrator", "analysis", "validation", "fix_generation", "domain_expert"}
        for agent in AGENT_REGISTRY:
            assert agent["role"] in valid, (
                f"Agent {agent['id']} has invalid role '{agent['role']}'"
            )

    def test_valid_levels(self):
        for agent in AGENT_REGISTRY:
            assert 1 <= agent["level"] <= 5, (
                f"Agent {agent['id']} has invalid level {agent['level']}"
            )

    def test_llm_config_fields(self):
        required_llm = {"model", "temperature", "context_window", "mode"}
        for agent in AGENT_REGISTRY:
            missing = required_llm - set(agent["llm_config"].keys())
            assert not missing, f"Agent {agent['id']} llm_config missing: {missing}"

    def test_architecture_stages_non_empty(self):
        for agent in AGENT_REGISTRY:
            assert len(agent["architecture_stages"]) >= 2, (
                f"Agent {agent['id']} needs at least 2 architecture stages"
            )

    def test_tools_is_list(self):
        for agent in AGENT_REGISTRY:
            assert isinstance(agent["tools"], list), (
                f"Agent {agent['id']} tools should be a list"
            )

    def test_tool_health_checks_is_dict(self):
        for agent in AGENT_REGISTRY:
            assert isinstance(agent["tool_health_checks"], dict), (
                f"Agent {agent['id']} tool_health_checks should be a dict"
            )

    def test_15_app_diagnostic_agents(self):
        app_agents = [a for a in AGENT_REGISTRY if a["workflow"] == "app_diagnostics"]
        assert len(app_agents) == 15

    def test_10_cluster_diagnostic_agents(self):
        cluster_agents = [a for a in AGENT_REGISTRY if a["workflow"] == "cluster_diagnostics"]
        assert len(cluster_agents) == 10

    def test_timeout_positive(self):
        for agent in AGENT_REGISTRY:
            assert agent["timeout_s"] > 0, (
                f"Agent {agent['id']} has non-positive timeout"
            )

    def test_description_non_empty(self):
        for agent in AGENT_REGISTRY:
            assert len(agent["description"]) > 10, (
                f"Agent {agent['id']} description is too short"
            )

    def test_registry_map_matches_registry(self):
        for agent in AGENT_REGISTRY:
            assert AGENT_REGISTRY_MAP[agent["id"]] is agent

    def test_health_probes_defined(self):
        assert "k8s_api" in HEALTH_PROBES
        assert "prometheus" in HEALTH_PROBES
        assert "elasticsearch" in HEALTH_PROBES
        assert "github" in HEALTH_PROBES

    def test_all_tool_health_check_keys_have_probes(self):
        """Every tool_health_checks key used by agents must exist in HEALTH_PROBES."""
        for agent in AGENT_REGISTRY:
            for key in agent["tool_health_checks"]:
                assert key in HEALTH_PROBES, (
                    f"Agent {agent['id']} references health check '{key}' not in HEALTH_PROBES"
                )


# =========================================================================
# Agent Status Logic Tests
# =========================================================================


class TestAgentStatus:
    """Test get_agent_status() for active/degraded/offline determination."""

    def test_no_health_checks_always_active(self):
        agent = {"tool_health_checks": {}}
        status, degraded = get_agent_status(agent, {})
        assert status == "active"
        assert degraded == []

    def test_all_checks_pass_active(self):
        agent = {
            "tool_health_checks": {
                "k8s_api": "check_k8s_connectivity",
                "prometheus": "check_prometheus_connectivity",
            }
        }
        health = {"k8s_api": True, "prometheus": True}
        status, degraded = get_agent_status(agent, health)
        assert status == "active"
        assert degraded == []

    def test_one_check_fails_degraded(self):
        agent = {
            "tool_health_checks": {
                "k8s_api": "check_k8s_connectivity",
                "prometheus": "check_prometheus_connectivity",
            }
        }
        health = {"k8s_api": True, "prometheus": False}
        status, degraded = get_agent_status(agent, health)
        assert status == "degraded"
        assert "prometheus" in degraded
        assert "k8s_api" not in degraded

    def test_all_checks_fail_offline(self):
        agent = {
            "tool_health_checks": {
                "k8s_api": "check_k8s_connectivity",
                "prometheus": "check_prometheus_connectivity",
            }
        }
        health = {"k8s_api": False, "prometheus": False}
        status, degraded = get_agent_status(agent, health)
        assert status == "offline"
        assert set(degraded) == {"k8s_api", "prometheus"}

    def test_single_check_fails_offline(self):
        """Agent with only one health check that fails should be offline, not degraded."""
        agent = {
            "tool_health_checks": {
                "k8s_api": "check_k8s_connectivity",
            }
        }
        health = {"k8s_api": False}
        status, degraded = get_agent_status(agent, health)
        assert status == "offline"
        assert degraded == ["k8s_api"]

    def test_single_check_passes_active(self):
        agent = {
            "tool_health_checks": {
                "k8s_api": "check_k8s_connectivity",
            }
        }
        health = {"k8s_api": True}
        status, degraded = get_agent_status(agent, health)
        assert status == "active"
        assert degraded == []

    def test_missing_health_key_treated_as_failing(self):
        """If a tool key is not in health_results at all, treat it as failing."""
        agent = {
            "tool_health_checks": {
                "k8s_api": "check_k8s_connectivity",
                "elasticsearch": "check_elasticsearch_connectivity",
            }
        }
        health = {"k8s_api": True}  # elasticsearch missing
        status, degraded = get_agent_status(agent, health)
        assert status == "degraded"
        assert "elasticsearch" in degraded

    def test_real_agent_supervisor_always_active(self):
        """SupervisorAgent has no health checks, should always be active."""
        agent = AGENT_REGISTRY_MAP["supervisor_agent"]
        status, degraded = get_agent_status(agent, {})
        assert status == "active"
        assert degraded == []

    def test_real_agent_node_agent_all_healthy(self):
        """NodeAgent with all probes healthy should be active."""
        agent = AGENT_REGISTRY_MAP["node_agent"]
        health = {"k8s_api": True, "prometheus": True, "elasticsearch": True, "github": True}
        status, degraded = get_agent_status(agent, health)
        assert status == "active"

    def test_real_agent_log_agent_partial_failure(self):
        """LogAnalysisAgent with elasticsearch down should be degraded."""
        agent = AGENT_REGISTRY_MAP["log_analysis_agent"]
        health = {"k8s_api": True, "prometheus": True, "elasticsearch": False, "github": True}
        status, degraded = get_agent_status(agent, health)
        assert status == "degraded"
        assert "elasticsearch" in degraded


# =========================================================================
# Health Cache Tests
# =========================================================================


class TestHealthCache:
    """Test cache clear and TTL value."""

    def test_cache_ttl_is_30_seconds(self):
        assert _CACHE_TTL == 30.0

    def test_clear_health_cache(self):
        # Manually insert a value
        _health_cache["test_key"] = (True, 0.0)
        assert "test_key" in _health_cache

        clear_health_cache()
        assert len(_health_cache) == 0

    def test_cache_starts_empty(self):
        clear_health_cache()
        assert len(_health_cache) == 0

    def test_health_probes_are_callable(self):
        for key, probe_fn in HEALTH_PROBES.items():
            assert callable(probe_fn), f"HEALTH_PROBES['{key}'] is not callable"
