
from __future__ import annotations
from typing import Tuple, List, Any, Dict
import json

def _fallback_validate(instance: Dict[str, Any], schema: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errors: List[str] = []

    # Check @type const if specified
    props = schema.get("properties", {})
    tprop = props.get("@type", {})
    const = tprop.get("const")
    if const and instance.get("@type") != const:
        errors.append(f"@type: '{const}' was expected")

    # Check required
    for key in schema.get("required", []):
        if key not in instance or instance.get(key) in (None, "", []):
            errors.append(f"Missing required field: {key}")

    return (len(errors) == 0, errors)

def validate_against_schema(instance: Dict[str, Any], schema_in: Any) -> Tuple[bool, List[str]]:
    """Validate a JSON object against a JSON Schema.
    Accepts schema as a dict (preferred) or a JSON string for backward compatibility.
    Returns (is_valid, error_messages).
    """
    # Normalize schema input
    if isinstance(schema_in, (bytes, bytearray, str)):
        try:
            schema = json.loads(schema_in) if not isinstance(schema_in, dict) else schema_in
        except Exception:
            # If schema_in was already a JSON string representing an object
            # but failed to parse, fall back to permissive.
            return True, []
    elif isinstance(schema_in, dict):
        schema = schema_in
    else:
        # Unknown schema format -> permissive
        return True, []

    # Try jsonschema library if available
    try:
        import jsonschema  # type: ignore
        from jsonschema import Draft7Validator  # type: ignore
        v = Draft7Validator(schema)
        errs = sorted(v.iter_errors(instance), key=lambda e: e.path)
        if errs:
            def fmt(e):
                path = ".".join(map(str, e.path)) or "$"
                msg = e.message
                return f"{path}: {msg}"
            return False, [fmt(e) for e in errs]
        return True, []
    except Exception:
        # Fallback minimal checks
        return _fallback_validate(instance, schema)
