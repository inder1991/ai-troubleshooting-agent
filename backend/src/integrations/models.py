from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
import uuid


class IntegrationConfig(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    cluster_type: Literal["openshift", "kubernetes"]
    cluster_url: str
    auth_method: Literal["kubeconfig", "token", "service_account"]
    auth_data: str  # Token string or kubeconfig content
    prometheus_url: Optional[str] = None
    elasticsearch_url: Optional[str] = None
    jaeger_url: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    last_verified: Optional[datetime] = None
    status: Literal["active", "unreachable", "expired"] = "active"
    auto_discovered: dict = Field(default_factory=dict)
