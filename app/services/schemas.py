
from __future__ import annotations
from pathlib import Path
import json

AVAILABLE_PAGE_TYPES = ["Hospital", "MedicalClinic", "Physician"]

SCHEMA_PATHS = {
    "Hospital": "app/schemas/hospital.schema.json",
    "MedicalClinic": "app/schemas/medical_clinic.schema.json",
    "Physician": "app/schemas/physician.schema.json",
    "MedicalWebPage": "app/schemas/medical_web_page.schema.json",
}

DEFAULTS = {
    "Hospital": {
        "required": ["@context","@type","name","url"],
        "recommended": ["description","telephone","address","audience","dateModified","sameAs","medicalSpecialty"],
    },
    "MedicalClinic": {
        "required": ["@context","@type","name","url"],
        "recommended": ["description","telephone","address","openingHours","sameAs"],
    },
    "Physician": {
        "required": ["@context","@type","name","url"],
        "recommended": ["description","telephone","address","medicalSpecialty","sameAs"],
    },
    "MedicalWebPage": {
        "required": ["@context","@type","name","url"],
        "recommended": ["description","breadcrumb","about","dateModified","primaryImageOfPage"],
    },
}

# Common pickers for UI
COMMON_PRIMARY_TYPES = [
    "Hospital","MedicalClinic","Physician","MedicalWebPage","Organization","LocalBusiness","WebPage","Article"
]
COMMON_SECONDARY_TYPES = [
    "BreadcrumbList","Organization","LocalBusiness","Person","ImageObject","PostalAddress","FAQPage","VideoObject","CommunityHealth"
]

def load_schema(page_type: str) -> str:
    path = SCHEMA_PATHS.get(page_type) or SCHEMA_PATHS.get("Hospital")
    if not path:
        raise FileNotFoundError(f"No schema path for {page_type}")
    return Path(path).read_text()

def defaults_for(page_type: str):
    return DEFAULTS.get(page_type, DEFAULTS["Hospital"])
