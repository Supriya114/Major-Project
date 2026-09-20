import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

_client = None
_db = None


def get_database():
    global _client, _db

    if _db is not None:
        return _db

    uri = os.getenv("MONGODB_URI")
    database_name = os.getenv("DATABASE_NAME", "ai_software_team")

    if not uri:
        raise RuntimeError(
            "MONGODB_URI is not configured. Add it to backend/.env."
        )

    _client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    _client.admin.command("ping")
    _db = _client[database_name]
    return _db


def close_database():
    global _client, _db

    if _client is not None:
        _client.close()

    _client = None
    _db = None
