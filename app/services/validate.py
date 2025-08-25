
from __future__ import annotations
from typing import Dict, Any, Tuple, List
import json
from jsonschema import Draft202012Validator

def validate_against_schema(data: Dict[str, Any], schema_str: str) -> Tuple[bool, List[str]]:
    schema = json.loads(schema_str)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: e.path)
    msgs = []
    for e in errors:
        loc = ".".join([str(p) for p in e.path]) or "(root)"
        msgs.append(f"{loc}: {e.message}")
    return (len(msgs) == 0, msgs)
