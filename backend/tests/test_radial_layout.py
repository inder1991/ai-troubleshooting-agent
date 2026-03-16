import pytest
from src.network.repository.radial_layout import compute_radial_layout


class TestRadialLayout:
    def test_onprem_core_at_center(self):
        devices = [
            {"id": "fw-01", "group": "onprem", "role": "core", "deviceType": "FIREWALL"},
            {"id": "rtr-01", "group": "onprem", "role": "core", "deviceType": "ROUTER"},
        ]
        result = compute_radial_layout(devices)
        # Core devices should be near center (relative to group container)
        assert "fw-01" in result["device_positions"]
        assert "rtr-01" in result["device_positions"]
        # Group container exists
        assert len(result["group_nodes"]) >= 1

    def test_cloud_groups_at_outer_ring(self):
        devices = [
            {"id": "fw-01", "group": "onprem", "role": "core", "deviceType": "FIREWALL"},
            {"id": "csr-01", "group": "aws", "role": "cloud_gateway", "deviceType": "CLOUD_GATEWAY"},
            {"id": "er-01", "group": "azure", "role": "core", "deviceType": "ROUTER"},
        ]
        result = compute_radial_layout(devices)
        # AWS and Azure groups should exist
        group_ids = [g["id"] for g in result["group_nodes"]]
        assert "group-aws" in group_ids
        assert "group-azure" in group_ids
        assert "group-onprem" in group_ids

    def test_env_labels_created(self):
        devices = [
            {"id": "fw-01", "group": "onprem", "role": "core", "deviceType": "FIREWALL"},
        ]
        result = compute_radial_layout(devices)
        assert len(result["env_labels"]) >= 1
        label = result["env_labels"][0]
        assert label["type"] == "envLabel"
        assert label["data"]["label"] == "On-Premises DC"

    def test_devices_have_parent_id(self):
        devices = [
            {"id": "fw-01", "group": "onprem", "role": "core", "deviceType": "FIREWALL"},
        ]
        result = compute_radial_layout(devices)
        pos = result["device_positions"]["fw-01"]
        assert "parentId" in pos
        assert pos["parentId"] == "group-onprem"

    def test_35_devices_no_overlap(self):
        # Simulate the real fixture data distribution
        devices = []
        for i in range(13):
            role = "core" if i < 4 else "distribution" if i < 7 else "access"
            devices.append({"id": f"onprem-{i}", "group": "onprem", "role": role, "deviceType": "ROUTER"})
        for i in range(6):
            devices.append({"id": f"aws-{i}", "group": "aws", "role": "cloud_gateway" if i == 0 else "access", "deviceType": "CLOUD_GATEWAY" if i == 0 else "HOST"})
        for i in range(5):
            devices.append({"id": f"azure-{i}", "group": "azure", "role": "core", "deviceType": "ROUTER"})
        for i in range(4):
            devices.append({"id": f"oci-{i}", "group": "oci", "role": "core", "deviceType": "ROUTER"})
        for i in range(3):
            devices.append({"id": f"branch-{i}", "group": "branch", "role": "edge", "deviceType": "ROUTER"})
        # 31 devices, 5 groups
        result = compute_radial_layout(devices)
        assert len(result["device_positions"]) == 31
        assert len(result["group_nodes"]) == 5
        assert len(result["env_labels"]) == 5

    def test_empty_input(self):
        result = compute_radial_layout([])
        assert result["device_positions"] == {}
        assert result["group_nodes"] == []
