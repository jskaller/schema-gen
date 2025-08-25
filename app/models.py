
from __future__ import annotations
from typing import Optional
from sqlmodel import SQLModel, Field, Column, JSON
from datetime import datetime

class Run(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    url: str = Field(index=True)
    title: Optional[str] = None
    topic: Optional[str] = None
    subject: Optional[str] = None
    audience: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None

    score_overall: Optional[int] = None
    valid: Optional[bool] = None
    jsonld: dict = Field(sa_column=Column(JSON), default_factory=dict)
    details: dict = Field(sa_column=Column(JSON), default_factory=dict)
    validation_errors: list = Field(sa_column=Column(JSON), default_factory=list)
    comparisons: list = Field(sa_column=Column(JSON), default_factory=list)
    comparison_notes: list = Field(sa_column=Column(JSON), default_factory=list)
