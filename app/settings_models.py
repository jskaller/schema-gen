
from __future__ import annotations
from typing import Optional
from sqlmodel import SQLModel, Field, Column, JSON

class Settings(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    provider: str = "dummy"
    provider_model: Optional[str] = None
    page_type: str = "Hospital"  # display label or key
    # Map of display page types to {"primary": "<SchemaType>", "secondary": ["TypeA","TypeB",...]}
    page_type_map: dict = Field(sa_column=Column(JSON), default_factory=lambda: {
        "Hospital": {"primary": "Hospital", "secondary": []},
        "MedicalClinic": {"primary": "MedicalClinic", "secondary": []},
        "Physician": {"primary": "Physician", "secondary": []},
    })
    required_fields: list = Field(sa_column=Column(JSON), default_factory=lambda: ["@context","@type","name","url"])
    recommended_fields: list = Field(sa_column=Column(JSON), default_factory=lambda: ["description","telephone","address","audience","dateModified","sameAs","medicalSpecialty"])
