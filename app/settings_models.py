from __future__ import annotations
from typing import Optional, Dict, List
from sqlmodel import SQLModel, Field, Column, JSON

class Settings(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    # Generation provider defaults
    provider: str = Field(default="dummy")
    provider_model: Optional[str] = Field(default=None)

    # UI / run-time defaults
    page_type: str = Field(default="WebPage")

    # Admin-managed page-type mapping, e.g. { "MEAC HomePage": {"primary": "MedicalOrganization", "secondary": ["WebSite","WebPage","MedicalOrganization","BreadcrumbList","Logo"]} }
    page_type_map: Dict[str, dict] = Field(sa_column=Column(JSON), default_factory=dict)

    # Field expectations used by validator & UI
    required_fields: List[str] = Field(sa_column=Column(JSON), default_factory=lambda: ["@context","@type","name","url"])
    recommended_fields: List[str] = Field(sa_column=Column(JSON), default_factory=lambda: ["description","telephone","address","audience","dateModified","sameAs","medicalSpecialty"])