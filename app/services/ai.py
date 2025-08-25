
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Optional, Dict, Any
import datetime as dt

PageType = Literal["Hospital"]

@dataclass
class GenerationInputs:
    url: str
    cleaned_text: str
    topic: Optional[str] = None
    subject: Optional[str] = None
    audience: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    page_type: PageType = "Hospital"
    sameAs: Optional[list[str]] = None

class LLMProvider:
    name: str = "base"
    def generate_jsonld(self, inputs: GenerationInputs) -> Dict[str, Any]:
        raise NotImplementedError

class DummyLLM(LLMProvider):
    name = "dummy"
    def generate_jsonld(self, inputs: GenerationInputs) -> Dict[str, Any]:
        title = (inputs.subject or inputs.topic or "Hospital").strip()
        description = inputs.cleaned_text.split("\n", 1)[0][:280] if inputs.cleaned_text else f"{title} page."
        data: Dict[str, Any] = {
            "@context": "https://schema.org",
            "@type": "Hospital",
            "name": title,
            "description": description,
            "url": inputs.url,
        }
        if inputs.phone:
            data["telephone"] = inputs.phone
        if inputs.address:
            data["address"] = {"@type": "PostalAddress", "streetAddress": inputs.address}
        if inputs.audience:
            data["audience"] = {"@type": "Audience", "audienceType": inputs.audience}
        if inputs.sameAs:
            data["sameAs"] = inputs.sameAs
        if inputs.topic:
            data["medicalSpecialty"] = inputs.topic
        data["dateModified"] = dt.datetime.utcnow().isoformat() + "Z"
        return data

def get_provider(provider_name: str = "dummy") -> LLMProvider:
    return DummyLLM()
