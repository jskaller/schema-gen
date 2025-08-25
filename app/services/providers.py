
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
import datetime as dt
import json
import httpx

class LLMProvider:
    name: str = "base"
    async def generate_jsonld(self, inputs) -> Dict[str, Any]:
        raise NotImplementedError

class DummyLLM(LLMProvider):
    name = "dummy"
    async def generate_jsonld(self, inputs) -> Dict[str, Any]:
        title = (inputs.subject or inputs.topic or inputs.page_type or "Entity").strip()
        description = inputs.cleaned_text.split("\n", 1)[0][:280] if inputs.cleaned_text else f"{title} page."
        main: Dict[str, Any] = {
            "@context": "https://schema.org",
            "@type": inputs.page_type or "Thing",
            "name": title,
            "description": description,
            "url": inputs.url,
        }
        if inputs.phone:
            main["telephone"] = inputs.phone
        if inputs.address:
            main["address"] = {"@type": "PostalAddress", "streetAddress": inputs.address}
        if inputs.audience:
            main["audience"] = {"@type": "Audience", "audienceType": inputs.audience}
        if inputs.sameAs:
            main["sameAs"] = inputs.sameAs
        if inputs.topic and inputs.page_type in ("Hospital","Physician","MedicalClinic"):
            main["medicalSpecialty"] = inputs.topic
        main["dateModified"] = dt.datetime.utcnow().isoformat() + "Z"

        # Secondary schemas -> add minimal nodes in @graph
        graph: List[Dict[str, Any]] = [main]
        if inputs.secondary_types:
            for i, t in enumerate(inputs.secondary_types):
                node = {"@type": t}
                if t == "BreadcrumbList":
                    node["@id"] = inputs.url + "#breadcrumbs"
                    node["itemListElement"] = []
                elif t.endswith("WebPage") or t == "MedicalWebPage":
                    node["@id"] = inputs.url
                    node["name"] = title
                    node["url"] = inputs.url
                graph.append(node)
            return {"@context": "https://schema.org", "@graph": graph}
        return main

class OllamaLLM(LLMProvider):
    name = "ollama"
    def __init__(self, model: str = "llama3"):
        self.model = model or "llama3"

    async def generate_jsonld(self, inputs) -> Dict[str, Any]:
        prompt = f"""You are a schema.org assistant. Produce ONLY valid JSON for a single {inputs.page_type} main entity in JSON-LD.
If secondary schema types are provided, include them as additional nodes in an "@graph".
Secondary types: {', '.join(inputs.secondary_types or [])}
Fields to prioritize on the main entity: @context, @type, name, url, description, telephone, address, audience, sameAs, dateModified.
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
        payload = {"model": self.model, "prompt": prompt, "stream": False, "options": {"temperature": 0.2}}
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post("http://localhost:11434/api/generate", json=payload); r.raise_for_status()
            data = r.json()
        text = (data.get("response") or "").strip()
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start:end+1]
        try:
            return json.loads(text)
        except Exception:
            return {"@context":"https://schema.org","@type":inputs.page_type,"name":inputs.subject or inputs.topic or inputs.page_type,"url":inputs.url}

async def list_ollama_models() -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get("http://localhost:11434/api/tags"); r.raise_for_status()
            data = r.json()
        return [m.get("name") for m in data.get("models", []) if m.get("name")]
    except Exception:
        return []
