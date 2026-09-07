import base64
import hashlib
import json
from uuid import uuid4

from cryptography.fernet import Fernet

from app.config import get_settings
from app.db import execute, execute_returning, fetch_all, fetch_one

settings = get_settings()


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.api_secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_value(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_value(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


async def store_credential(
    project_id: str,
    credential_type: str,
    payload: dict,
    name: str = "default",
) -> dict:
    """Store an encrypted credential for a project (type: ssh|sftp)."""
    secrets = {k: v for k, v in payload.items() if k in ("password", "private_key") and v is not None}
    plain = {k: v for k, v in payload.items() if k not in secrets and v is not None}
    plain["secrets"] = {k: encrypt_value(v) for k, v in secrets.items()}
    credential_id = str(uuid4())
    row = await execute_returning(
        """INSERT INTO project_credentials
           (credential_id, project_id, credential_name, credential_type, encrypted_data)
           VALUES ($1, $2, $3, $4, $5) RETURNING *""",
        credential_id,
        str(project_id),
        name,
        credential_type,
        json.dumps(plain),
    )
    return {
        "credential_id": str(row["credential_id"]),
        "project_id": str(row["project_id"]),
        "name": row["credential_name"],
        "type": row["credential_type"],
        "host": payload.get("host"),
        "port": payload.get("port"),
        "username": payload.get("username"),
    }


async def list_credentials(project_id: str) -> list:
    rows = await fetch_all(
        "SELECT credential_id, credential_name, credential_type, encrypted_data, created_at FROM project_credentials WHERE project_id = $1 ORDER BY created_at",
        str(project_id),
    )
    result = []
    for r in rows:
        data = json.loads(r["encrypted_data"])
        secrets = data.pop("secrets", {})
        result.append({
            "credential_id": str(r["credential_id"]),
            "project_id": str(project_id),
            "name": r["credential_name"],
            "type": r["credential_type"],
            "host": data.get("host"),
            "port": data.get("port") or 22,
            "username": data.get("username"),
            "key_path": data.get("key_path"),
            "has_password": "password" in secrets,
            "has_private_key": "private_key" in secrets,
        })
    return result


async def delete_credential(project_id: str, credential_id: str) -> bool:
    result = await execute(
        "DELETE FROM project_credentials WHERE project_id = $1 AND credential_id = $2",
        str(project_id),
        str(credential_id),
    )
    return result == "DELETE 1"


async def get_decrypted_credential(project_id: str, credential_type: str = "ssh", connection=None):
    """Fetch a decrypted credential for connecting, preferring latest created."""
    reader = connection.fetchrow if connection is not None else fetch_one
    row = await reader(
        """SELECT credential_id, credential_name, credential_type, encrypted_data
           FROM project_credentials
           WHERE project_id = $1 AND credential_type = $2
           ORDER BY created_at DESC LIMIT 1""",
        str(project_id),
        credential_type,
    )
    if not row:
        return None
    data = json.loads(row["encrypted_data"])
    secrets = data.pop("secrets", {})
    for k, v in secrets.items():
        try:
            data[k] = decrypt_value(v)
        except Exception as exc:
            raise ValueError("Stored credential cannot be decrypted; check the encryption key") from exc
    return {
        "credential_id": str(row["credential_id"]),
        "type": row["credential_type"],
        "name": row["credential_name"],
        **data,
    }
