from __future__ import annotations

from datetime import date, datetime
from typing import Any

from bson import ObjectId
from pydantic import BaseModel


def serialize_for_json(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, ObjectId):
        return str(value)

    if isinstance(value, BaseModel):
        return serialize_for_json(value.model_dump(mode="json"))

    if isinstance(value, dict):
        return {str(key): serialize_for_json(item) for key, item in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [serialize_for_json(item) for item in list(value)]

    return value
