import json
from app.db import fetch_one


async def read_setting(key, default=None):
    row = await fetch_one("SELECT setting_value FROM platform_settings WHERE setting_key=$1", key)
    if not row:
        return default
    value = row["setting_value"]
    return json.loads(value) if isinstance(value, str) else value
