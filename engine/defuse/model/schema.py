"""The IOC JSON Schema that the advisory-intake flow's output is validated against."""

from __future__ import annotations

import json
from pathlib import Path

from defuse.model.ioc import IOCSet

SCHEMA_PATH = Path(__file__).with_name("ioc.schema.json")


def ioc_schema_json() -> str:
    schema = IOCSet.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = (
        "https://gitlab.com/defuse/defuse/-/raw/main/engine/defuse/model/ioc.schema.json"
    )
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def write_schema() -> Path:
    SCHEMA_PATH.write_text(ioc_schema_json(), encoding="utf-8")
    return SCHEMA_PATH
