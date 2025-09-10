from __future__ import annotations
from typing import Optional, Dict, List, Any
from sqlmodel import SQLModel, Field, Column, JSON

class Settings(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    # Generation provider defaults
    provider: str = Field(default="dummy")
    provider_model: Optional[str] = Field(default=None)

    # UI / run-time defaults
    page_type: str = Field(default="WebPage")

    # Admin-managed page-type mapping
    page_type_map: Dict[str, dict] = Field(sa_column=Column(JSON), default_factory=dict)

    # Field expectations used by validator & UI
    required_fields: List[str] = Field(sa_column=Column(JSON), default_factory=lambda: ["@context","@type","name","url"])
    recommended_fields: List[str] = Field(sa_column=Column(JSON), default_factory=lambda: ["description","telephone","address","audience","dateModified","sameAs","medicalSpecialty"])

    # Phase-1 enrichment flags (DB-backed, editable via Admin)
    # shadow: when True, compute enrichments but do NOT write them into output (diff-only mode)
    extract_config: Dict[str, Any] = Field(sa_column=Column(JSON), default_factory=lambda: {
        "shadow": True,
        "inLanguage": True,
        "canonical": True,
        "dateModified": True,
        # Future Phase-2 flags (inactive by default)
        "telephone": False,
        "logo": False,
        "sameAs": False,
        "address": False,
    })