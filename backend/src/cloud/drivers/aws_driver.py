"""AWS cloud provider driver using boto3."""
from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator

from src.cloud.drivers.base import CloudProviderDriver
from src.cloud.models import (
    CloudAccount,
    DiscoveredItem,
    DiscoveredRelation,
    DiscoveryBatch,
    DriverHealth,
    RateLimitInfo,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _extract_name(tags: list[dict] | None) -> str | None:
    """Extract the 'Name' tag value from an AWS Tags list."""
    if not tags:
        return None
    for t in tags:
        if t.get("Key") == "Name":
            return t.get("Value")
    return None


def _extract_tags(tags: list[dict] | None) -> dict[str, str]:
    """Convert AWS Tags list to a flat dict."""
    if not tags:
        return {}
    return {t["Key"]: t["Value"] for t in tags if "Key" in t and "Value" in t}


class AWSDriver(CloudProviderDriver):
    """AWS resource discovery via boto3."""

    _RESOURCE_TYPES: dict[str, int] = {
        # Tier 1 — core topology (10 min cadence)
        "vpc": 1,
        "subnet": 1,
        "security_group": 1,
        "nacl": 1,
        "route_table": 1,
        # Tier 2 — attached resources (30 min cadence)
        "eni": 2,
        "instance": 2,
        "elb": 2,
        "target_group": 2,
        "tgw": 2,
        "tgw_attachment": 2,
        "vpn_connection": 2,
        "nat_gateway": 2,
        "vpc_peering": 2,
        # Tier 3 — IAM, flow logs (6 hr cadence)
        "iam_policy": 3,
        "direct_connect": 3,
        "flow_log_config": 3,
    }

    def supported_resource_types(self) -> dict[str, int]:
        """Return {resource_type: sync_tier} mapping for all AWS types."""
        return dict(self._RESOURCE_TYPES)

    @staticmethod
    def _extract_creds(creds: dict) -> tuple[str, str]:
        """Extract access key with fallback for legacy field names."""
        ak = creds.get("access_key_id") or creds.get("aws_access_key_id", "")
        sk = creds.get("secret_access_key") or creds.get("aws_secret_access_key", "")
        return ak, sk

    def _get_boto_client(
        self, service: str, account: CloudAccount, region: str = "us-east-1"
    ):
        """Create a boto3 client with the account's credentials.

        Supports two auth flows:
        - role_arn present: assumes a cross-account role via STS (with user creds)
        - otherwise: uses static access key / secret key directly
        """
        import boto3

        creds = (
            json.loads(account.credential_handle)
            if isinstance(account.credential_handle, str)
            else {}
        )
        access_key, secret_key = self._extract_creds(creds)
        session_token = creds.get("session_token")
        role_arn = creds.get("role_arn", "")

        if role_arn:
            # Build STS client WITH user credentials
            sts_kwargs: dict[str, Any] = {}
            if access_key:
                sts_kwargs["aws_access_key_id"] = access_key
                sts_kwargs["aws_secret_access_key"] = secret_key
            if session_token:
                sts_kwargs["aws_session_token"] = session_token
            sts = boto3.client("sts", **sts_kwargs)
            assumed = sts.assume_role(
                RoleArn=role_arn,
                ExternalId=creds.get("external_id", "debugduck"),
                RoleSessionName="debugduck-cloud-sync",
            )
            temp = assumed["Credentials"]
            return boto3.client(
                service,
                region_name=region,
                aws_access_key_id=temp["AccessKeyId"],
                aws_secret_access_key=temp["SecretAccessKey"],
                aws_session_token=temp["SessionToken"],
            )
        else:
            kwargs: dict[str, Any] = {}
            if access_key:
                kwargs["aws_access_key_id"] = access_key
                kwargs["aws_secret_access_key"] = secret_key
            if session_token:
                kwargs["aws_session_token"] = session_token
            return boto3.client(service, region_name=region, **kwargs)

    # ── ABC implementations ──

    async def health_check(self, account: CloudAccount) -> DriverHealth:
        """Validate credentials via STS get-caller-identity."""
        start = time.monotonic()
        try:
            sts = self._get_boto_client("sts", account)
            identity = sts.get_caller_identity()
            latency = (time.monotonic() - start) * 1000
            return DriverHealth(
                connected=True,
                latency_ms=latency,
                identity=identity.get("Arn", ""),
                permissions_ok=True,
                missing_permissions=[],
                message="Connected successfully",
            )
        except Exception as e:
            return DriverHealth(
                connected=False,
                latency_ms=(time.monotonic() - start) * 1000,
                identity="",
                permissions_ok=False,
                missing_permissions=[],
                message=str(e),
            )

    async def discover(
        self,
        account: CloudAccount,
        region: str,
        resource_types: list[str],
    ) -> AsyncIterator[DiscoveryBatch]:
        """Yield batches of discovered AWS resources by type."""
        ec2 = self._get_boto_client("ec2", account, region)

        dispatchers = {
            "vpc": self._discover_vpcs,
            "subnet": self._discover_subnets,
            "security_group": self._discover_security_groups,
            "nacl": self._discover_nacls,
            "route_table": self._discover_route_tables,
            "eni": self._discover_enis,
            "instance": self._discover_instances,
            "nat_gateway": self._discover_nat_gateways,
            "vpc_peering": self._discover_vpc_peerings,
        }

        for rt in resource_types:
            handler = dispatchers.get(rt)
            if handler:
                try:
                    batch = handler(ec2, account.account_id, region)
                    yield batch
                except Exception as e:
                    logger.warning(
                        "Failed to discover %s in %s: %s", rt, region, e
                    )

    # ── Tier 1 Discoverers ──

    def _discover_vpcs(
        self, ec2, account_id: str, region: str
    ) -> DiscoveryBatch:
        resp = ec2.describe_vpcs()
        items = []
        for vpc in resp.get("Vpcs", []):
            items.append(
                DiscoveredItem(
                    native_id=vpc["VpcId"],
                    name=_extract_name(vpc.get("Tags")),
                    raw=vpc,
                    tags=_extract_tags(vpc.get("Tags")),
                )
            )
        return DiscoveryBatch(
            account_id=account_id,
            region=region,
            resource_type="vpc",
            source="aws-describe-vpcs",
            items=items,
            relations=[],
        )

    def _discover_subnets(
        self, ec2, account_id: str, region: str
    ) -> DiscoveryBatch:
        resp = ec2.describe_subnets()
        items, relations = [], []
        for s in resp.get("Subnets", []):
            items.append(
                DiscoveredItem(
                    native_id=s["SubnetId"],
                    name=_extract_name(s.get("Tags")),
                    raw=s,
                    tags=_extract_tags(s.get("Tags")),
                )
            )
            relations.append(
                DiscoveredRelation(
                    source_native_id=s["SubnetId"],
                    target_native_id=s["VpcId"],
                    relation_type="member_of",
                )
            )
        return DiscoveryBatch(
            account_id=account_id,
            region=region,
            resource_type="subnet",
            source="aws-describe-subnets",
            items=items,
            relations=relations,
        )

    def _discover_security_groups(
        self, ec2, account_id: str, region: str
    ) -> DiscoveryBatch:
        resp = ec2.describe_security_groups()
        items, relations = [], []
        for sg in resp.get("SecurityGroups", []):
            items.append(
                DiscoveredItem(
                    native_id=sg["GroupId"],
                    name=sg.get("GroupName") or _extract_name(sg.get("Tags")),
                    raw=sg,
                    tags=_extract_tags(sg.get("Tags")),
                )
            )
            if sg.get("VpcId"):
                relations.append(
                    DiscoveredRelation(
                        source_native_id=sg["GroupId"],
                        target_native_id=sg["VpcId"],
                        relation_type="member_of",
                    )
                )
        return DiscoveryBatch(
            account_id=account_id,
            region=region,
            resource_type="security_group",
            source="aws-describe-security-groups",
            items=items,
            relations=relations,
        )

    def _discover_nacls(
        self, ec2, account_id: str, region: str
    ) -> DiscoveryBatch:
        resp = ec2.describe_network_acls()
        items, relations = [], []
        for nacl in resp.get("NetworkAcls", []):
            items.append(
                DiscoveredItem(
                    native_id=nacl["NetworkAclId"],
                    name=_extract_name(nacl.get("Tags")),
                    raw=nacl,
                    tags=_extract_tags(nacl.get("Tags")),
                )
            )
            if nacl.get("VpcId"):
                relations.append(
                    DiscoveredRelation(
                        source_native_id=nacl["NetworkAclId"],
                        target_native_id=nacl["VpcId"],
                        relation_type="member_of",
                    )
                )
        return DiscoveryBatch(
            account_id=account_id,
            region=region,
            resource_type="nacl",
            source="aws-describe-nacls",
            items=items,
            relations=relations,
        )

    def _discover_route_tables(
        self, ec2, account_id: str, region: str
    ) -> DiscoveryBatch:
        resp = ec2.describe_route_tables()
        items, relations = [], []
        for rt in resp.get("RouteTables", []):
            items.append(
                DiscoveredItem(
                    native_id=rt["RouteTableId"],
                    name=_extract_name(rt.get("Tags")),
                    raw=rt,
                    tags=_extract_tags(rt.get("Tags")),
                )
            )
            if rt.get("VpcId"):
                relations.append(
                    DiscoveredRelation(
                        source_native_id=rt["RouteTableId"],
                        target_native_id=rt["VpcId"],
                        relation_type="member_of",
                    )
                )
            for assoc in rt.get("Associations", []):
                if assoc.get("SubnetId"):
                    relations.append(
                        DiscoveredRelation(
                            source_native_id=rt["RouteTableId"],
                            target_native_id=assoc["SubnetId"],
                            relation_type="associated_with",
                        )
                    )
        return DiscoveryBatch(
            account_id=account_id,
            region=region,
            resource_type="route_table",
            source="aws-describe-route-tables",
            items=items,
            relations=relations,
        )

    # ── Tier 2 Discoverers ──

    def _discover_enis(
        self, ec2, account_id: str, region: str
    ) -> DiscoveryBatch:
        resp = ec2.describe_network_interfaces()
        items, relations = [], []
        for eni in resp.get("NetworkInterfaces", []):
            items.append(
                DiscoveredItem(
                    native_id=eni["NetworkInterfaceId"],
                    name=eni.get("Description")
                    or _extract_name(eni.get("TagSet")),
                    raw=eni,
                    tags=_extract_tags(eni.get("TagSet")),
                )
            )
            if eni.get("SubnetId"):
                relations.append(
                    DiscoveredRelation(
                        source_native_id=eni["NetworkInterfaceId"],
                        target_native_id=eni["SubnetId"],
                        relation_type="attached_to",
                    )
                )
            for sg in eni.get("Groups", []):
                relations.append(
                    DiscoveredRelation(
                        source_native_id=sg["GroupId"],
                        target_native_id=eni["NetworkInterfaceId"],
                        relation_type="applied_to",
                    )
                )
        return DiscoveryBatch(
            account_id=account_id,
            region=region,
            resource_type="eni",
            source="aws-describe-enis",
            items=items,
            relations=relations,
        )

    def _discover_instances(
        self, ec2, account_id: str, region: str
    ) -> DiscoveryBatch:
        resp = ec2.describe_instances()
        items, relations = [], []
        for reservation in resp.get("Reservations", []):
            for inst in reservation.get("Instances", []):
                items.append(
                    DiscoveredItem(
                        native_id=inst["InstanceId"],
                        name=_extract_name(inst.get("Tags")),
                        raw=inst,
                        tags=_extract_tags(inst.get("Tags")),
                    )
                )
                for ni in inst.get("NetworkInterfaces", []):
                    relations.append(
                        DiscoveredRelation(
                            source_native_id=inst["InstanceId"],
                            target_native_id=ni["NetworkInterfaceId"],
                            relation_type="has_interface",
                        )
                    )
        return DiscoveryBatch(
            account_id=account_id,
            region=region,
            resource_type="instance",
            source="aws-describe-instances",
            items=items,
            relations=relations,
        )

    def _discover_nat_gateways(
        self, ec2, account_id: str, region: str
    ) -> DiscoveryBatch:
        resp = ec2.describe_nat_gateways()
        items, relations = [], []
        for nat in resp.get("NatGateways", []):
            items.append(
                DiscoveredItem(
                    native_id=nat["NatGatewayId"],
                    name=_extract_name(nat.get("Tags")),
                    raw=nat,
                    tags=_extract_tags(nat.get("Tags")),
                )
            )
            if nat.get("SubnetId"):
                relations.append(
                    DiscoveredRelation(
                        source_native_id=nat["NatGatewayId"],
                        target_native_id=nat["SubnetId"],
                        relation_type="deployed_in",
                    )
                )
        return DiscoveryBatch(
            account_id=account_id,
            region=region,
            resource_type="nat_gateway",
            source="aws-describe-nat-gateways",
            items=items,
            relations=relations,
        )

    def _discover_vpc_peerings(
        self, ec2, account_id: str, region: str
    ) -> DiscoveryBatch:
        resp = ec2.describe_vpc_peering_connections()
        items, relations = [], []
        for pcx in resp.get("VpcPeeringConnections", []):
            items.append(
                DiscoveredItem(
                    native_id=pcx["VpcPeeringConnectionId"],
                    name=_extract_name(pcx.get("Tags")),
                    raw=pcx,
                    tags=_extract_tags(pcx.get("Tags")),
                )
            )
            if pcx.get("RequesterVpcInfo", {}).get("VpcId"):
                relations.append(
                    DiscoveredRelation(
                        source_native_id=pcx["VpcPeeringConnectionId"],
                        target_native_id=pcx["RequesterVpcInfo"]["VpcId"],
                        relation_type="peered_with",
                    )
                )
            if pcx.get("AccepterVpcInfo", {}).get("VpcId"):
                relations.append(
                    DiscoveredRelation(
                        source_native_id=pcx["VpcPeeringConnectionId"],
                        target_native_id=pcx["AccepterVpcInfo"]["VpcId"],
                        relation_type="peered_with",
                    )
                )
        return DiscoveryBatch(
            account_id=account_id,
            region=region,
            resource_type="vpc_peering",
            source="aws-describe-vpc-peerings",
            items=items,
            relations=relations,
        )
