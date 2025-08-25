from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Optional, Dict, Any
import datetime as dt

PageType = Literal["Hospital"]  # extend later: "Article", "Department", etc.

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

class LLMProvider:
    """Pluggable provider interface."""
    name: str = "base"

    def generate_jsonld(self, inputs: GenerationInputs) -> Dict[str, Any]:
        raise NotImplementedError

class DummyLLM(LLMProvider):
    """Heuristic generator so the flow works without external APIs."""
    name = "dummy"

    def generate_jsonld(self, inputs: GenerationInputs) -> Dict[str, Any]:
        # naive derivations from helpers + page text
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
            data["address"] = {
                "@type": "PostalAddress",
                "streetAddress": inputs.address,
            }
        if inputs.audience:
            data["audience"] = {"@type": "Audience", "audienceType": inputs.audience}
        # Very light structured data we can derive
        data["dateModified"] = dt.datetime.utcnow().isoformat() + "Z"
        return data

def get_provider(provider_name: str = "dummy") -> LLMProvider:
    # later: "openai", "ollama", etc.
    return DummyLLM()
