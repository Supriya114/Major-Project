from datetime import datetime, date
from bson import ObjectId

from app.utils.serialization import serialize_for_json
from app.services.ai_service import extract_json_object


def test_serialize_for_json_handles_nested_mongo_values():
    value = {
        "created_at": datetime(2024, 1, 2, 3, 4, 5),
        "updated_on": date(2024, 1, 3),
        "_id": ObjectId("507f1f77bcf86cd799439011"),
        "items": ["ok", {"when": datetime(2024, 1, 2, 3, 4, 5)}],
    }

    assert serialize_for_json(value) == {
        "created_at": "2024-01-02T03:04:05",
        "updated_on": "2024-01-03",
        "_id": "507f1f77bcf86cd799439011",
        "items": ["ok", {"when": "2024-01-02T03:04:05"}],
    }


def test_extract_json_object_handles_markdown_and_noise():
    payload = "\nHere is the result:\n```json\n{\"project_summary\": \"demo\", \"functional_requirements\": []}\n```\n"

    obj = extract_json_object(payload)
    assert isinstance(obj, dict)
    assert obj["project_summary"] == "demo"
    assert obj["functional_requirements"] == []
