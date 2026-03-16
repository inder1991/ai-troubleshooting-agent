import pytest
from src.network.repository.radial_layout import compute_radial_layout


class TestRadialLayout:
    def test_devices_get_positions(self):
        devices = [
            {"id": "fw-01", "group": "onprem", "role": "core", "deviceType": "FIREWALL"},
            {"id": "rtr-01", "group": "onprem", "role": "core", "deviceType": "ROUTER"},
        ]
        result = compute_radial_layout(devices)
        assert "fw-01" in result["device_positions"]
        assert "rtr-01" in result["device_positions"]
        assert "x" in result["device_positions"]["fw-01"]
        assert "y" in result["device_positions"]["fw-01"]

    def test_multi_group_devices(self):
        devices = [
            {"id": "fw-01", "group": "onprem", "role": "core", "deviceType": "FIREWALL"},
            {"id": "csr-01", "group": "aws", "role": "cloud_gateway", "deviceType": "CLOUD_GATEWAY"},
            {"id": "er-01", "group": "azure", "role": "core", "deviceType": "ROUTER"},
        ]
        result = compute_radial_layout(devices)
        assert len(result["device_positions"]) == 3
        # Env labels for each group
        label_ids = {l["id"] for l in result["env_labels"]}
        assert "env-label-onprem" in label_ids
        assert "env-label-aws" in label_ids
        assert "env-label-azure" in label_ids

    def test_env_labels_created(self):
        devices = [
            {"id": "fw-01", "group": "onprem", "role": "core", "deviceType": "FIREWALL"},
        ]
        result = compute_radial_layout(devices)
        assert len(result["env_labels"]) >= 1
        label = result["env_labels"][0]
        assert label["type"] == "envLabel"
        assert label["data"]["label"] == "ON-PREMISES DC"

    def test_devices_have_no_parent_id(self):
        devices = [
            {"id": "fw-01", "group": "onprem", "role": "core", "deviceType": "FIREWALL"},
        ]
        result = compute_radial_layout(devices)
        pos = result["device_positions"]["fw-01"]
        assert "x" in pos
        assert "y" in pos
        assert "parentId" not in pos

    def test_35_devices_all_positioned(self):
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
        result = compute_radial_layout(devices)
        assert len(result["device_positions"]) == 31
        assert len(result["group_nodes"]) == 5
        assert len(result["env_labels"]) == 5

    def test_no_overlap(self):
        """No two devices should occupy the same pixel area."""
        devices = [
            {"id": f"dev-{i}", "group": "onprem", "role": "core", "deviceType": "ROUTER"}
            for i in range(10)
        ]
        result = compute_radial_layout(devices)
        positions = list(result["device_positions"].values())
        for i in range(len(positions)):
            for j in range(i + 1, len(positions)):
                dx = abs(positions[i]["x"] - positions[j]["x"])
                dy = abs(positions[i]["y"] - positions[j]["y"])
                # At least one dimension must have enough gap
                assert dx >= 170 or dy >= 80, f"Devices {i} and {j} overlap: dx={dx}, dy={dy}"

    def test_empty_input(self):
        result = compute_radial_layout([])
        assert result["device_positions"] == {}
        assert result["group_nodes"] == []
