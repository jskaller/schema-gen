
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, Any
import datetime as dt
import json
import httpx

# Shared inputs dataclass is defined in app.services.ai (GenerationInputs)

class LLMProvider:
    name: str = "base"
    async def generate_jsonld(self, inputs) -> Dict[str, Any]:
        raise NotImplementedError

class DummyLLM(LLMProvider):
    name = "dummy"
    async def generate_jsonld(self, inputs) -> Dict[str, Any]:
        title = (inputs.subject or inputs.topic or "Hospital").strip()
        description = inputs.cleaned_text.split("\n", 1)[0][:280] if inputs.cleaned_text else f"{title} page."
        data: Dict[str, Any] = {
            "@context": "https://schema.org",
            "@type": inputs.page_type or "Hospital",
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

class OllamaLLM(LLMProvider):
    name = "ollama"
    def __init__(self, model: str = "llama3"):
        self.model = model or "llama3"

    async def generate_jsonld(self, inputs) -> Dict[str, Any]:
        # Construct a prompt that asks for strict JSON only.
        prompt = f"""You are a schema.org assistant. Produce ONLY valid JSON (no prose) for a single {inputs.page_type or 'Hospital'} entity in JSON-LD.
Fields to prioritize: @context, @type, name, url, description, telephone, address (PostalAddress.streetAddress), audience (Audience.audienceType), sameAs, medicalSpecialty, dateModified (UTC ISO8601 with Z).
Use this page context:
URL: {inputs.url}
Topic: {inputs.topic or ''}
Subject: {inputs.subject or ''}
Audience: {inputs.audience or ''}
Address: {inputs.address or ''}
Phone: {inputs.phone or ''}
Cleaned text (may be truncated):
{inputs.cleaned_text[:1200]}
Return ONLY the JSON object, nothing else.
"""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2},
        }
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post("http://localhost:11434/api/generate", json=payload)
            r.raise_for_status()
            data = r.json()
        # Ollama returns {'response': '...'} text; try to parse JSON body inside.
        text = data.get("response", "").strip()
        # Best effort: find first '{' to last '}' to strip stray text.
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start:end+1]
        try:
            obj = json.loads(text)
            return obj
        except Exception:
            # Fallback minimal object to avoid crashes
            return {
                "@context": "https://schema.org",
                "@type": inputs.page_type or "Hospital",
                "name": inputs.subject or inputs.topic or "Hospital",
                "url": inputs.url,
                "description": (inputs.cleaned_text or "")[:200],
            }

async def list_ollama_models() -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get("http://localhost:11434/api/tags")
            r.raise_for_status()
            data = r.json()
        models = [m.get("name") for m in data.get("models", []) if m.get("name")]
        return models
    except Exception:
        return []
