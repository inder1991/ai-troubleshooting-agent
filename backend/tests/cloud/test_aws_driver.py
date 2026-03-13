"""Tests for AWS cloud provider driver."""
import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock, call
from src.cloud.drivers.aws_driver import AWSDriver
from src.cloud.models import CloudAccount, DiscoveryBatch, DriverHealth


@pytest.fixture
def aws_account():
    return CloudAccount(
        account_id="acc-001",
        provider="aws",
        display_name="Test AWS",
        credential_handle='{"access_key_id":"AKID","secret_access_key":"SECRET"}',
        auth_method="access_key",
        regions=["us-east-1"],
    )


@pytest.fixture
def aws_role_account():
    return CloudAccount(
        account_id="acc-002",
        provider="aws",
        display_name="Test AWS Cross-Account",
        credential_handle=json.dumps({
            "access_key_id": "AKID",
            "secret_access_key": "SECRET",
            "role_arn": "arn:aws:iam::999999999:role/DebugDuck",
            "external_id": "debugduck-test",
        }),
        auth_method="access_key",
        regions=["us-east-1"],
    )


@pytest.fixture
def driver():
    return AWSDriver()


class TestAWSDriverResourceTypes:
    def test_supported_types(self, driver):
        types = driver.supported_resource_types()
        assert "vpc" in types
        assert "subnet" in types
        assert "security_group" in types
        assert types["vpc"] == 1  # Tier 1
        assert types["instance"] == 2  # Tier 2
        assert types["iam_policy"] == 3  # Tier 3

    def test_tier_1_types(self, driver):
        tier1 = driver.resource_types_for_tier(1)
        assert "vpc" in tier1
        assert "subnet" in tier1
        assert "security_group" in tier1
        assert "nacl" in tier1
        assert "route_table" in tier1
        assert "instance" not in tier1

    def test_tier_2_types(self, driver):
        tier2 = driver.resource_types_for_tier(2)
        assert "eni" in tier2
        assert "instance" in tier2
        assert "elb" in tier2
        assert "vpc" not in tier2


class TestAWSDriverHealthCheck:
    @pytest.mark.asyncio
    async def test_healthy_check(self, driver, aws_account):
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:iam::123456:role/TestRole",
            "Account": "123456",
        }
        with patch.object(driver, "_get_boto_client", return_value=mock_sts):
            health = await driver.health_check(aws_account)
        assert health.connected is True
        assert "123456" in health.identity

    @pytest.mark.asyncio
    async def test_failed_check(self, driver, aws_account):
        with patch.object(
            driver, "_get_boto_client",
            side_effect=Exception("Invalid credentials"),
        ):
            health = await driver.health_check(aws_account)
        assert health.connected is False
        assert "Invalid credentials" in health.message


class TestAWSDriverDiscoverVPCs:
    @pytest.mark.asyncio
    async def test_discover_vpcs(self, driver, aws_account):
        mock_ec2 = MagicMock()
        mock_ec2.describe_vpcs.return_value = {
            "Vpcs": [
                {
                    "VpcId": "vpc-abc",
                    "CidrBlock": "10.0.0.0/16",
                    "Tags": [{"Key": "Name", "Value": "prod-vpc"}],
                    "State": "available",
                },
            ],
        }
        mock_ec2.get_paginator.return_value.paginate.return_value = []
        with patch.object(driver, "_get_boto_client", return_value=mock_ec2):
            batches = []
            async for batch in driver.discover(aws_account, "us-east-1", ["vpc"]):
                batches.append(batch)
        assert len(batches) >= 1
        vpc_batch = next(b for b in batches if b.resource_type == "vpc")
        assert len(vpc_batch.items) == 1
        assert vpc_batch.items[0].native_id == "vpc-abc"
        assert vpc_batch.items[0].name == "prod-vpc"
        assert vpc_batch.source == "aws-describe-vpcs"

    @pytest.mark.asyncio
    async def test_discover_subnets_with_relations(self, driver, aws_account):
        mock_ec2 = MagicMock()
        mock_ec2.describe_subnets.return_value = {
            "Subnets": [
                {
                    "SubnetId": "subnet-123",
                    "VpcId": "vpc-abc",
                    "CidrBlock": "10.0.1.0/24",
                    "AvailabilityZone": "us-east-1a",
                    "Tags": [{"Key": "Name", "Value": "web-subnet"}],
                },
            ],
        }
        with patch.object(driver, "_get_boto_client", return_value=mock_ec2):
            batches = []
            async for batch in driver.discover(aws_account, "us-east-1", ["subnet"]):
                batches.append(batch)
        subnet_batch = next(b for b in batches if b.resource_type == "subnet")
        assert len(subnet_batch.items) == 1
        assert len(subnet_batch.relations) == 1
        rel = subnet_batch.relations[0]
        assert rel.source_native_id == "subnet-123"
        assert rel.target_native_id == "vpc-abc"
        assert rel.relation_type == "member_of"

    @pytest.mark.asyncio
    async def test_discover_security_groups(self, driver, aws_account):
        mock_ec2 = MagicMock()
        mock_ec2.describe_security_groups.return_value = {
            "SecurityGroups": [
                {
                    "GroupId": "sg-001",
                    "GroupName": "web-sg",
                    "VpcId": "vpc-abc",
                    "IpPermissions": [
                        {
                            "IpProtocol": "tcp",
                            "FromPort": 443,
                            "ToPort": 443,
                            "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                        },
                    ],
                    "IpPermissionsEgress": [],
                    "Tags": [],
                },
            ],
        }
        with patch.object(driver, "_get_boto_client", return_value=mock_ec2):
            batches = []
            async for batch in driver.discover(aws_account, "us-east-1", ["security_group"]):
                batches.append(batch)
        sg_batch = next(b for b in batches if b.resource_type == "security_group")
        assert len(sg_batch.items) == 1
        assert sg_batch.items[0].native_id == "sg-001"


class TestExtractCreds:
    def test_primary_field_names(self, driver):
        creds = {"access_key_id": "AK1", "secret_access_key": "SK1"}
        ak, sk = driver._extract_creds(creds)
        assert ak == "AK1"
        assert sk == "SK1"

    def test_legacy_field_names(self, driver):
        creds = {"aws_access_key_id": "AK2", "aws_secret_access_key": "SK2"}
        ak, sk = driver._extract_creds(creds)
        assert ak == "AK2"
        assert sk == "SK2"

    def test_primary_takes_precedence(self, driver):
        creds = {
            "access_key_id": "PRIMARY",
            "aws_access_key_id": "LEGACY",
            "secret_access_key": "SPRIMARY",
            "aws_secret_access_key": "SLEGACY",
        }
        ak, sk = driver._extract_creds(creds)
        assert ak == "PRIMARY"
        assert sk == "SPRIMARY"


class TestAWSDriverRoleAssumption:
    @pytest.mark.asyncio
    async def test_sts_receives_user_creds_for_role(self, driver, aws_role_account):
        """STS client must be created with user's access key when assuming a role."""
        mock_sts = MagicMock()
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "TEMP_AK",
                "SecretAccessKey": "TEMP_SK",
                "SessionToken": "TEMP_TOK",
            }
        }
        mock_service_client = MagicMock()

        with patch("boto3.client") as mock_client:
            # First call = STS client, second call = target service client
            mock_client.side_effect = [mock_sts, mock_service_client]
            result = driver._get_boto_client("ec2", aws_role_account, "us-east-1")

        # Verify STS client was created with user credentials
        sts_call = mock_client.call_args_list[0]
        assert sts_call == call(
            "sts",
            aws_access_key_id="AKID",
            aws_secret_access_key="SECRET",
        )

        # Verify assume_role was called with correct params
        mock_sts.assume_role.assert_called_once_with(
            RoleArn="arn:aws:iam::999999999:role/DebugDuck",
            ExternalId="debugduck-test",
            RoleSessionName="debugduck-cloud-sync",
        )

        # Verify final client uses temp credentials
        service_call = mock_client.call_args_list[1]
        assert service_call == call(
            "ec2",
            region_name="us-east-1",
            aws_access_key_id="TEMP_AK",
            aws_secret_access_key="TEMP_SK",
            aws_session_token="TEMP_TOK",
        )
        assert result is mock_service_client
