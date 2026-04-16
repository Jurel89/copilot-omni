"""
Focused stdlib JSON Schema validator for MCP tool input/output schemas.

Supported subset:
  type (object/string/integer/number/boolean/array/null)
  properties, required, enum, additionalProperties
  items, minItems, maxItems
  minLength, maxLength, pattern (compiled regex)
  minimum, maximum
  oneOf, anyOf (basic — first match wins for anyOf, exactly-one for oneOf)

Returns list of (json_pointer, error_message) tuples. Empty list = valid.
"""
from __future__ import annotations

import re
from typing import Any, List, Tuple

ValidationErrors = List[Tuple[str, str]]

# Cache compiled regex patterns to avoid recompilation per-call.
_PATTERN_CACHE: dict[str, re.Pattern] = {}


def _get_pattern(pat: str) -> re.Pattern:
    if pat not in _PATTERN_CACHE:
        _PATTERN_CACHE[pat] = re.compile(pat)
    return _PATTERN_CACHE[pat]


def validate(instance: Any, schema: dict, pointer: str = "") -> ValidationErrors:
    """Validate *instance* against *schema*. Return list of (pointer, message)."""
    errors: ValidationErrors = []

    if not isinstance(schema, dict):
        return errors

    # ------------------------------------------------------------------ oneOf
    if "oneOf" in schema:
        subschemas = schema["oneOf"]
        matching = [s for s in subschemas if not validate(instance, s, pointer)]
        if len(matching) != 1:
            errors.append((
                pointer,
                f"oneOf: exactly one schema must match, but {len(matching)} matched",
            ))
        return errors  # oneOf is a terminal combinator here

    # ------------------------------------------------------------------ anyOf
    if "anyOf" in schema:
        subschemas = schema["anyOf"]
        if not any(not validate(instance, s, pointer) for s in subschemas):
            errors.append((pointer, "anyOf: instance does not match any subschema"))
        return errors  # anyOf is a terminal combinator here

    # ------------------------------------------------------------------ type
    if "type" in schema:
        errors.extend(_check_type(instance, schema["type"], pointer))
        # If type check failed, stop further checks to avoid cascading noise.
        if errors:
            return errors

    schema_type = schema.get("type")

    # ------------------------------------------------------------------ enum
    if "enum" in schema:
        if instance not in schema["enum"]:
            errors.append((pointer, f"value {instance!r} not in enum {schema['enum']!r}"))

    # ------------------------------------------------------------------ object checks
    if schema_type == "object" or isinstance(instance, dict):
        errors.extend(_check_object(instance, schema, pointer))

    # ------------------------------------------------------------------ array checks
    if schema_type == "array" or isinstance(instance, list):
        errors.extend(_check_array(instance, schema, pointer))

    # ------------------------------------------------------------------ string checks
    if schema_type == "string" or isinstance(instance, str):
        errors.extend(_check_string(instance, schema, pointer))

    # ------------------------------------------------------------------ number/integer checks
    if schema_type in ("number", "integer") or isinstance(instance, (int, float)):
        errors.extend(_check_numeric(instance, schema, pointer))

    return errors


def _check_type(instance: Any, expected: Any, pointer: str) -> ValidationErrors:
    """Check JSON Schema 'type' constraint."""
    if isinstance(expected, list):
        for t in expected:
            if _type_matches(instance, t):
                return []
        return [(pointer, f"expected type in {expected!r}, got {_json_type(instance)!r}")]
    if _type_matches(instance, expected):
        return []
    return [(pointer, f"expected type {expected!r}, got {_json_type(instance)!r}")]


def _type_matches(instance: Any, type_name: str) -> bool:
    if type_name == "null":
        return instance is None
    if type_name == "boolean":
        return isinstance(instance, bool)
    if type_name == "integer":
        return isinstance(instance, int) and not isinstance(instance, bool)
    if type_name == "number":
        return isinstance(instance, (int, float)) and not isinstance(instance, bool)
    if type_name == "string":
        return isinstance(instance, str)
    if type_name == "array":
        return isinstance(instance, list)
    if type_name == "object":
        return isinstance(instance, dict)
    return False


def _json_type(instance: Any) -> str:
    if instance is None:
        return "null"
    if isinstance(instance, bool):
        return "boolean"
    if isinstance(instance, int):
        return "integer"
    if isinstance(instance, float):
        return "number"
    if isinstance(instance, str):
        return "string"
    if isinstance(instance, list):
        return "array"
    if isinstance(instance, dict):
        return "object"
    return type(instance).__name__


def _check_object(instance: Any, schema: dict, pointer: str) -> ValidationErrors:
    if not isinstance(instance, dict):
        return []
    errors: ValidationErrors = []

    properties = schema.get("properties", {})
    required = schema.get("required", [])
    additional = schema.get("additionalProperties")

    # required fields
    for field in required:
        if field not in instance:
            errors.append((
                f"{pointer}/{field}" if pointer else f"/{field}",
                f"required field '{field}' is missing",
            ))

    # validate each property value
    for key, value in instance.items():
        child_pointer = f"{pointer}/{key}" if pointer else f"/{key}"
        if key in properties:
            errors.extend(validate(value, properties[key], child_pointer))
        elif additional is False:
            errors.append((child_pointer, f"additional property '{key}' is not allowed"))
        elif isinstance(additional, dict):
            errors.extend(validate(value, additional, child_pointer))

    return errors


def _check_array(instance: Any, schema: dict, pointer: str) -> ValidationErrors:
    if not isinstance(instance, list):
        return []
    errors: ValidationErrors = []

    min_items = schema.get("minItems")
    max_items = schema.get("maxItems")
    items_schema = schema.get("items")

    if min_items is not None and len(instance) < min_items:
        errors.append((pointer, f"array length {len(instance)} < minItems {min_items}"))
    if max_items is not None and len(instance) > max_items:
        errors.append((pointer, f"array length {len(instance)} > maxItems {max_items}"))

    if items_schema is not None:
        for idx, item in enumerate(instance):
            child_pointer = f"{pointer}/{idx}"
            errors.extend(validate(item, items_schema, child_pointer))

    return errors


def _check_string(instance: Any, schema: dict, pointer: str) -> ValidationErrors:
    if not isinstance(instance, str):
        return []
    errors: ValidationErrors = []

    min_length = schema.get("minLength")
    max_length = schema.get("maxLength")
    pattern = schema.get("pattern")

    if min_length is not None and len(instance) < min_length:
        errors.append((pointer, f"string length {len(instance)} < minLength {min_length}"))
    if max_length is not None and len(instance) > max_length:
        errors.append((pointer, f"string length {len(instance)} > maxLength {max_length}"))
    if pattern is not None:
        try:
            compiled = _get_pattern(pattern)
            if not compiled.search(instance):
                errors.append((pointer, f"string does not match pattern {pattern!r}"))
        except re.error as exc:
            errors.append((pointer, f"invalid pattern in schema: {exc}"))

    return errors


def _check_numeric(instance: Any, schema: dict, pointer: str) -> ValidationErrors:
    if not isinstance(instance, (int, float)) or isinstance(instance, bool):
        return []
    errors: ValidationErrors = []

    minimum = schema.get("minimum")
    maximum = schema.get("maximum")

    if minimum is not None and instance < minimum:
        errors.append((pointer, f"value {instance} < minimum {minimum}"))
    if maximum is not None and instance > maximum:
        errors.append((pointer, f"value {instance} > maximum {maximum}"))

    return errors
