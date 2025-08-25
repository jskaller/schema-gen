
from __future__ import annotations
from typing import Dict, Any

# Simple, pragmatic JSON Schemas for our primary types.
# Each schema enforces the @type constant and a minimal required set.

MEDICAL_ORGANIZATION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "@context": {"type": "string"},
        "@type": {"const": "MedicalOrganization"},
        "name": {"type": "string"},
        "url": {"type": "string"},
        "description": {"type": "string"},
        "telephone": {"type": ["string", "null"]},
        "address": {
            "type": ["object", "null"],
            "properties": {
                "@type": {"const": "PostalAddress"},
                "streetAddress": {"type": ["string", "null"]},
                "addressLocality": {"type": ["string", "null"]},
                "addressRegion": {"type": ["string", "null"]},
                "postalCode": {"type": ["string", "null"]},
                "addressCountry": {"type": ["string", "null"]}
            }
        },
        "sameAs": {"type": ["array", "null"], "items": {"type": "string"}},
        "medicalSpecialty": {"type": ["string", "object", "null"]},
        "audience": {
            "type": ["object", "null"],
            "properties": {
                "@type": {"const": "Audience"},
                "audienceType": {"type": "string"}
            }
        },
        "dateModified": {"type": "string"}
    },
    "required": ["@type", "name", "url"]
}

HOSPITAL_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "@context": {"type": "string"},
        "@type": {"const": "Hospital"},
        "name": {"type": "string"},
        "url": {"type": "string"},
        "telephone": {"type": ["string", "null"]},
        "address": {"type": ["object", "null"]},
        "sameAs": {"type": ["array", "null"], "items": {"type": "string"}},
        "medicalSpecialty": {"type": ["string", "object", "null"]},
        "dateModified": {"type": "string"}
    },
    "required": ["@type", "name", "url"]
}

MEDICAL_WEBPAGE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "@type": {"const": "MedicalWebPage"},
        "url": {"type": "string"},
        "name": {"type": ["string", "null"]},
        "about": {"type": ["string", "null"]}
    },
    "required": ["@type", "url"]
}

PHYSICIAN_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "@type": {"const": "Physician"},
        "name": {"type": "string"},
        "url": {"type": "string"},
        "medicalSpecialty": {"type": ["string", "object", "null"]},
        "telephone": {"type": ["string", "null"]}
    },
    "required": ["@type", "name", "url"]
}

MEDICAL_CLINIC_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "@type": {"const": "MedicalClinic"},
        "name": {"type": "string"},
        "url": {"type": "string"}
    },
    "required": ["@type", "name", "url"]
}

# Defaults for required / recommended fields by primary type
_DEFAULTS = {
    "MedicalOrganization": {
        "required": ["@type", "name", "url"],
        "recommended": ["description", "telephone", "address", "medicalSpecialty", "sameAs", "audience", "dateModified"]
    },
    "Hospital": {
        "required": ["@type", "name", "url"],
        "recommended": ["telephone", "address", "sameAs", "medicalSpecialty", "dateModified"]
    },
    "MedicalWebPage": {
        "required": ["@type", "url"],
        "recommended": ["name", "about"]
    },
    "Physician": {
        "required": ["@type", "name", "url"],
        "recommended": ["medicalSpecialty", "telephone"]
    },
    "MedicalClinic": {
        "required": ["@type", "name", "url"],
        "recommended": []
    }
}

_SCHEMAS = {
    "MedicalOrganization": MEDICAL_ORGANIZATION_SCHEMA,
    "Hospital": HOSPITAL_SCHEMA,
    "MedicalWebPage": MEDICAL_WEBPAGE_SCHEMA,
    "Physician": PHYSICIAN_SCHEMA,
    "MedicalClinic": MEDICAL_CLINIC_SCHEMA,
}

AVAILABLE_PAGE_TYPES = list(_SCHEMAS.keys())

def load_schema(primary_type: str) -> Dict[str, Any]:
    # Fallback: if unknown, use MedicalOrganization (safer than Hospital for our content)
    return _SCHEMAS.get(primary_type, MEDICAL_ORGANIZATION_SCHEMA)

def defaults_for(primary_type: str) -> Dict[str, Any]:
    return _DEFAULTS.get(primary_type, _DEFAULTS["MedicalOrganization"])
