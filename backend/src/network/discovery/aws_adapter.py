"""AWS cloud discovery adapter — discovers VPCs, subnets, ENIs, and security groups."""

from __future__ import annotations

import logging
from typing import AsyncIterator, Optional

from .adapter import DiscoveryAdapter
from .observation import DiscoveryObservation, ObservationType

logger = logging.getLogger(__name__)


class AWSDiscoveryAdapter(DiscoveryAdapter):
    """Discovery adapter for AWS cloud accounts.

    Supports a *mock_data* mode for testing and development.  In production
    mode the adapter imports ``boto3`` at call time so that the dependency
    remains optional.
    """

    def __init__(self, mock_data: Optional[dict] = None) -> None:
        self._mock_data = mock_data

    # ------------------------------------------------------------------
    # DiscoveryAdapter interface
    # ------------------------------------------------------------------

    def supports(self, target: dict) -> bool:
        return target.get("type") == "cloud_account" and target.get("provider") == "aws"

    async def discover(self, target: dict) -> AsyncIterator[DiscoveryObservation]:
        if self._mock_data is not None:
            async for obs in self._discover_mock(target):
                yield obs
        else:
            async for obs in self._discover_live(target):
                yield obs

    # ------------------------------------------------------------------
    # Mock discovery
    # ------------------------------------------------------------------

    async def _discover_mock(self, target: dict) -> AsyncIterator[DiscoveryObservation]:
        for vpc in self._mock_data.get("vpcs", []):
            yield DiscoveryObservation(
                observation_type=ObservationType.VPC,
                source="aws_api",
                device_id=vpc["VpcId"],
                confidence=0.95,
                data={
                    "cidr": vpc.get("CidrBlock", ""),
                    "name": self._get_tag(vpc, "Name"),
                },
            )

        for subnet in self._mock_data.get("subnets", []):
            yield DiscoveryObservation(
                observation_type=ObservationType.SUBNET,
                source="aws_api",
                device_id=subnet["SubnetId"],
                confidence=0.95,
                data={
                    "cidr": subnet.get("CidrBlock", ""),
                    "vpc_id": subnet.get("VpcId", ""),
                    "availability_zone": subnet.get("AvailabilityZone", ""),
                    "name": self._get_tag(subnet, "Name"),
                },
            )

        for eni in self._mock_data.get("enis", []):
            yield DiscoveryObservation(
                observation_type=ObservationType.CLOUD_INTERFACE,
                source="aws_api",
                device_id=eni["NetworkInterfaceId"],
                confidence=0.95,
                data={
                    "subnet_id": eni.get("SubnetId", ""),
                    "vpc_id": eni.get("VpcId", ""),
                    "private_ip": eni.get("PrivateIpAddress", ""),
                    "name": self._get_tag(eni, "Name"),
                },
            )

        for sg in self._mock_data.get("security_groups", []):
            yield DiscoveryObservation(
                observation_type=ObservationType.SECURITY_GROUP,
                source="aws_api",
                device_id=sg["GroupId"],
                confidence=0.95,
                data={
                    "group_name": sg.get("GroupName", ""),
                    "vpc_id": sg.get("VpcId", ""),
                    "description": sg.get("Description", ""),
                    "name": self._get_tag(sg, "Name"),
                },
            )

    # ------------------------------------------------------------------
    # Live / boto3 discovery
    # ------------------------------------------------------------------

    async def _discover_live(self, target: dict) -> AsyncIterator[DiscoveryObservation]:
        try:
            import boto3  # noqa: F401
        except ImportError:
            logger.warning("boto3 is not installed — cannot perform live AWS discovery")
            return

        region = target.get("region", "us-east-1")
        ec2 = boto3.client("ec2", region_name=region)

        for vpc in ec2.describe_vpcs().get("Vpcs", []):
            yield DiscoveryObservation(
                observation_type=ObservationType.VPC,
                source="aws_api",
                device_id=vpc["VpcId"],
                confidence=0.95,
                data={
                    "cidr": vpc.get("CidrBlock", ""),
                    "name": self._get_tag(vpc, "Name"),
                },
            )

        for subnet in ec2.describe_subnets().get("Subnets", []):
            yield DiscoveryObservation(
                observation_type=ObservationType.SUBNET,
                source="aws_api",
                device_id=subnet["SubnetId"],
                confidence=0.95,
                data={
                    "cidr": subnet.get("CidrBlock", ""),
                    "vpc_id": subnet.get("VpcId", ""),
                    "availability_zone": subnet.get("AvailabilityZone", ""),
                    "name": self._get_tag(subnet, "Name"),
                },
            )

        for eni in ec2.describe_network_interfaces().get("NetworkInterfaces", []):
            yield DiscoveryObservation(
                observation_type=ObservationType.CLOUD_INTERFACE,
                source="aws_api",
                device_id=eni["NetworkInterfaceId"],
                confidence=0.95,
                data={
                    "subnet_id": eni.get("SubnetId", ""),
                    "vpc_id": eni.get("VpcId", ""),
                    "private_ip": eni.get("PrivateIpAddress", ""),
                    "name": self._get_tag(eni, "Name"),
                },
            )

        for sg in ec2.describe_security_groups().get("SecurityGroups", []):
            yield DiscoveryObservation(
                observation_type=ObservationType.SECURITY_GROUP,
                source="aws_api",
                device_id=sg["GroupId"],
                confidence=0.95,
                data={
                    "group_name": sg.get("GroupName", ""),
                    "vpc_id": sg.get("VpcId", ""),
                    "description": sg.get("Description", ""),
                    "name": self._get_tag(sg, "Name"),
                },
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_tag(resource: dict, key: str) -> str:
        """Extract a tag value from an AWS-style Tags list."""
        for tag in resource.get("Tags", []):
            if tag.get("Key") == key:
                return tag.get("Value", "")
        return ""
