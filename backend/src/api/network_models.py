"""Request/response Pydantic models for the network troubleshooting API."""
from pydantic import BaseModel, Field
from typing import Optional


class DiagnoseRequest(BaseModel):
    src_ip: str
    dst_ip: str
    port: int = 80
    protocol: str = "tcp"
    session_id: Optional[str] = None  # reuse existing session


class DiagnoseResponse(BaseModel):
    session_id: str
    flow_id: str
    status: str
    message: str


class TopologySaveRequest(BaseModel):
    diagram_json: str
    description: str = ""


class AdapterConfigureRequest(BaseModel):
    api_endpoint: str
    api_key: str = ""
    extra_config: dict = Field(default_factory=dict)
