"""Shared DTOs used across routers."""

from typing import Any, Literal

from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | list[Any] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    environment: str


class DbHealthResponse(HealthResponse):
    database: Literal["up"]
    latency_ms: int
