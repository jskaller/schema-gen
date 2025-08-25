
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Optional, Dict, Any, List
from app.services.providers import DummyLLM, OllamaLLM, LLMProvider

PageType = Literal["Hospital","MedicalClinic","Physician","MedicalWebPage"]

@dataclass
class GenerationInputs:
    url: str
    cleaned_text: str
    topic: Optional[str] = None
    subject: Optional[str] = None
    audience: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    page_type: str = "Hospital"
    sameAs: Optional[list[str]] = None
    secondary_types: Optional[List[str]] = None

def get_provider(provider_name: str = "dummy", model: str | None = None) -> LLMProvider:
    name = (provider_name or "dummy").lower()
    if name == "ollama":
        return OllamaLLM(model=model or "llama3")
    return DummyLLM()
