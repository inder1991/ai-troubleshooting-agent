"""Adapter factory -- creates the right adapter based on vendor and SDK availability."""
from __future__ import annotations

import logging
from typing import Optional

from ..models import FirewallVendor
from .base import FirewallAdapter
from .mock_adapter import MockFirewallAdapter

logger = logging.getLogger(__name__)


def create_adapter(
    vendor: FirewallVendor,
    api_endpoint: str = "",
    api_key: str = "",
    extra_config: Optional[dict] = None,
) -> FirewallAdapter:
    """Create the appropriate adapter for the given vendor.

    Falls back to MockFirewallAdapter if the vendor SDK is not installed.
    """
    extra = extra_config or {}

    if vendor == FirewallVendor.PALO_ALTO:
        try:
            from .panorama_adapter import PanoramaAdapter, HAS_PANOS
            if HAS_PANOS and api_endpoint:
                device_group = extra.get("device_group", "")
                vsys = extra.get("vsys", "vsys1")
                return PanoramaAdapter(
                    hostname=api_endpoint,
                    api_key=api_key,
                    device_group=device_group,
                    vsys=vsys,
                )
        except Exception as e:
            logger.warning("Failed to create PanoramaAdapter: %s, falling back to mock", e)

    elif vendor == FirewallVendor.AWS_SG:
        try:
            from .aws_sg_adapter import AWSSGAdapter, BOTO3_AVAILABLE
            if BOTO3_AVAILABLE and extra.get("security_group_id"):
                return AWSSGAdapter(
                    region=extra.get("region", "us-east-1"),
                    security_group_id=extra["security_group_id"],
                    aws_access_key=extra.get("aws_access_key"),
                    aws_secret_key=extra.get("aws_secret_key"),
                    api_endpoint=api_endpoint,
                    api_key=api_key,
                )
        except Exception as e:
            logger.warning("Failed to create AWSSGAdapter: %s, falling back to mock", e)

    elif vendor == FirewallVendor.AZURE_NSG:
        try:
            from .azure_nsg_adapter import AzureNSGAdapter, AZURE_AVAILABLE
            if AZURE_AVAILABLE and extra.get("nsg_name"):
                return AzureNSGAdapter(
                    subscription_id=extra.get("subscription_id", ""),
                    resource_group=extra.get("resource_group", ""),
                    nsg_name=extra["nsg_name"],
                    api_endpoint=api_endpoint,
                    api_key=api_key,
                )
        except Exception as e:
            logger.warning("Failed to create AzureNSGAdapter: %s, falling back to mock", e)

    elif vendor == FirewallVendor.ORACLE_NSG:
        try:
            from .oracle_nsg_adapter import OracleNSGAdapter, OCI_AVAILABLE
            if OCI_AVAILABLE and extra.get("nsg_id"):
                return OracleNSGAdapter(
                    compartment_id=extra.get("compartment_id", ""),
                    nsg_id=extra["nsg_id"],
                    api_endpoint=api_endpoint,
                    api_key=api_key,
                )
        except Exception as e:
            logger.warning("Failed to create OracleNSGAdapter: %s, falling back to mock", e)

    elif vendor == FirewallVendor.ZSCALER:
        try:
            from .zscaler_adapter import ZscalerAdapter, _HTTPX_AVAILABLE
            cloud_name = extra.get("cloud_name", "")
            username = extra.get("username", "")
            password = extra.get("password", "")
            if _HTTPX_AVAILABLE and cloud_name and username and password:
                return ZscalerAdapter(
                    cloud_name=cloud_name,
                    api_key=api_key,
                    username=username,
                    password=password,
                )
        except Exception as e:
            logger.warning("Failed to create ZscalerAdapter: %s, falling back to mock", e)

    # Fallback: mock adapter
    logger.info(
        "Using MockFirewallAdapter for vendor=%s (SDK not available or not configured)",
        vendor.value,
    )
    return MockFirewallAdapter(
        vendor=vendor,
        api_endpoint=api_endpoint,
        api_key=api_key,
        extra_config=extra,
    )
