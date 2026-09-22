"""Pydantic schemas for the official stand contract.

POST /process
    request:  {"payload": string, "payload_id": string}
    response: {"result": string}
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProcessRequest(BaseModel):
    payload: str = Field(..., description="Input text to process")
    payload_id: str = Field(..., description="Correlation id for the pair")


class ProcessResponse(BaseModel):
    result: str = Field(..., description="Processed text")


class HealthResponse(BaseModel):
    status: str
    profile: str
    engine_stub: bool