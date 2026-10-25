"""Pydantic DTOs for cases (Phase 06)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CaseStatus = Literal["OPEN", "IN_PROGRESS", "ESCALATED", "CLOSED_TRUE", "CLOSED_FALSE"]


class CaseCreate(BaseModel):
    alert_id: int
    title: str | None = Field(default=None, max_length=200)
    assignee: str | None = Field(default=None, max_length=80)


class CasePatch(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    assignee: str | None = Field(default=None, max_length=80)  # "" clears the assignee
    status: CaseStatus | None = None
    actor: str | None = Field(default=None, max_length=80)  # shown in audit notes


class NoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    author: str | None = Field(default=None, max_length=80)


class AnalystOut(BaseModel):
    emp_id: int
    name: str
    role: str
    branch: str
