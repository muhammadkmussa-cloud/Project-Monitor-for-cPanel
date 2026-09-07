from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from uuid import uuid4, UUID
from fastapi import HTTPException
import asyncio
import hmac
import hashlib
import json
import secrets

from app.config import get_settings
from app.db import fetch_one, fetch_all, execute, execute_returning

settings = get_settings()


class Role:
    def __init__(self, name: str, description: str, permissions: List[str], is_system: bool = False):
        self.name = name
        self.description = description
        self.permissions = set(permissions)
        self.is_system = is_system

    def has_permission(self, permission: str) -> bool:
        if "*:*" in self.permissions:
            return True
        resource = permission.split(":")[0]
        if f"{resource}:*" in self.permissions:
            return True
        return permission in self.permissions


DEFAULT_ROLES = {
    "owner": Role("owner", "Full system access", ["*:*"], True),
    "admin": Role("admin", "Administrative access", [
        "projects:*", "incidents:*", "remediation:*", "settings:*",
        "users:*", "billing:*", "reports:*",
    ], True),
    "manager": Role("manager", "Management access", [
        "projects:read", "projects:update", "incidents:read", "incidents:update",
        "remediation:approve", "reports:read", "users:read",
    ], True),
    "developer": Role("developer", "Developer access", [
        "projects:read", "incidents:read", "incidents:create", "logs:read", "diagnostics:read",
    ], True),
    "viewer": Role("viewer", "Read-only access", [
        "projects:read", "incidents:read", "reports:read",
    ], True),
    "api_readonly": Role("api_readonly", "API read-only access", [
        "projects:read", "incidents:read", "health:read", "stats:read",
    ], True),
}


class RBACService:
    def __init__(self):
        self.roles = DEFAULT_ROLES

    def _hash_password(self, password: str) -> str:
        salt = secrets.token_hex(16)
        digest = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
        return f"scrypt:{salt}:{digest}"

    def _verify_password(self, password: str, password_hash: str) -> bool:
        try:
            if password_hash.startswith("scrypt:"):
                _, salt, expected = password_hash.split(":")
                actual = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
            else:
                salt, expected = password_hash.split(":")
                actual = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
            return hmac.compare_digest(actual, expected)
        except (ValueError, TypeError):
            return False

    @staticmethod
    def public_user(row):
        if not row:
            return None
        fields = {"user_id", "client_id", "email", "name", "role", "status", "preferences", "last_login", "created_at", "updated_at"}
        return {k: str(v) if isinstance(v, UUID) else v for k, v in dict(row).items() if k in fields}

    def _hash_api_key(self, api_key: str) -> str:
        return hashlib.sha256(api_key.encode()).hexdigest()

    async def create_user(
        self, client_id: str, email: str, name: str, role: str = "viewer", password: Optional[str] = None
    ) -> Dict[str, Any]:
        user_id = str(uuid4())
        if role not in {*DEFAULT_ROLES, "user"}:
            raise HTTPException(422, "Invalid role")
        if not password or len(password) < 10:
            raise HTTPException(422, "Password must contain at least 10 characters")
        password_hash = await asyncio.to_thread(self._hash_password, password)
        now = datetime.utcnow().isoformat()

        row = await execute_returning(
            """INSERT INTO users (user_id, client_id, email, name, password_hash, role, status, preferences)
               VALUES ($1, $2, $3, $4, $5, $6, 'active', $7)
               RETURNING *""",
            uuid4() if len(user_id) != 36 else user_id,
            uuid4() if len(client_id) != 36 else client_id,
            email, name, password_hash, role,
            '{"timezone": "UTC", "notifications": {"email": true, "slack": false}}',
        )
        return self.public_user(row) or {}

    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        try:
            row = await fetch_one("SELECT * FROM users WHERE user_id = $1", user_id)
            if not row:
                return None
            return self.public_user(row)
        except Exception:
            return None

    async def list_users(self, client_id: Optional[str] = None, role: Optional[str] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
        conditions = []
        params = []
        idx = 1
        if client_id:
            conditions.append(f"client_id = ${idx}")
            params.append(uuid4() if len(client_id) != 36 else client_id)
            idx += 1
        if role:
            conditions.append(f"role = ${idx}")
            params.append(role)
            idx += 1
        if status:
            conditions.append(f"status = ${idx}")
            params.append(status)
            idx += 1

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = await fetch_all(f"SELECT * FROM users {where} ORDER BY created_at DESC", *params)
        return [self.public_user(r) for r in rows]

    async def update_user(self, user_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        if "role" in kwargs and kwargs["role"] not in {*DEFAULT_ROLES, "user"}:
            raise HTTPException(422, "Invalid role")
        if "status" in kwargs and kwargs["status"] not in {"active", "inactive", "deleted"}:
            raise HTTPException(422, "Invalid user status")
        allowed = ["name", "role", "status", "preferences"]
        sets = []
        params = []
        idx = 1
        for field, value in kwargs.items():
            if field in allowed:
                sets.append(f"{field} = ${idx}")
                params.append(value)
                idx += 1
        if not sets:
            return await self.get_user(user_id)
        params.append(uuid4() if len(user_id) != 36 else user_id)
        row = await execute_returning(
            f"UPDATE users SET {', '.join(sets)} WHERE user_id = ${idx} RETURNING *", *params
        )
        return self.public_user(row)

    async def delete_user(self, user_id: str) -> bool:
        result = await execute("UPDATE users SET status = 'deleted' WHERE user_id = $1", uuid4() if len(user_id) != 36 else user_id)
        return result == "UPDATE 1"

    async def authenticate_user(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        row = await fetch_one("SELECT * FROM users WHERE email = $1 AND status = 'active'", email)
        if not row:
            return None
        user = dict(row)
        if user.get("password_hash") and await asyncio.to_thread(self._verify_password, password, user["password_hash"]):
            if not user["password_hash"].startswith("scrypt:"):
                upgraded = await asyncio.to_thread(self._hash_password, password)
                await execute("UPDATE users SET password_hash=$2 WHERE user_id=$1", str(user["user_id"]), upgraded)
            await execute("UPDATE users SET last_login = NOW() WHERE user_id = $1", str(user["user_id"]))
            return self.public_user(user)
        return None


    async def create_api_key(self, user_id: str, name: str, permissions: Optional[List[str]] = None, expires_in_days: int = 90) -> Dict[str, Any]:
        user = await self.get_user(user_id)
        if not user:
            return {"success": False, "error": "User not found"}

        if not 1 <= expires_in_days <= 365:
            raise HTTPException(422, "API keys must expire within 1 to 365 days")
        api_key = f"pm_{secrets.token_urlsafe(32)}"
        key_id = str(uuid4())
        key_hash = self._hash_api_key(api_key)

        await execute(
            """INSERT INTO api_keys (key_id, user_id, client_id, name, key_hash, permissions, role, expires_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
            uuid4() if len(key_id) != 36 else key_id,
            uuid4() if len(user_id) != 36 else user_id,
            user.get("client_id"), name, key_hash,
            json.dumps(permissions if permissions else ["projects:read", "incidents:read", "analytics:read", "billing:read"]), user.get("role"),
            datetime.utcnow() + timedelta(days=expires_in_days),
        )

        return {"success": True, "api_key": api_key, "key_id": key_id}

    async def validate_api_key(self, key_hash: str) -> Optional[Dict[str, Any]]:
        row = await fetch_one(
            "SELECT ak.*, u.role FROM api_keys ak JOIN users u ON ak.user_id = u.user_id WHERE ak.key_hash = $1 AND ak.status = 'active'",
            key_hash,
        )
        if row:
            return dict(row)
        return None

    async def revoke_api_key(self, key_id: str) -> bool:
        result = await execute("UPDATE api_keys SET status = 'revoked' WHERE key_id = $1", uuid4() if len(key_id) != 36 else key_id)
        return result == "UPDATE 1"

    async def check_permission(self, user_id: str, permission: str) -> Dict[str, Any]:
        user = await self.get_user(user_id)
        if not user:
            return {"allowed": False, "error": "User not found"}
        role = self.roles.get(user.get("role"))
        if not role:
            return {"allowed": False, "error": "Invalid role"}
        if role.has_permission(permission):
            return {"allowed": True}
        return {"allowed": False, "error": "Permission denied"}

    async def get_user_permissions(self, user_id: str) -> List[str]:
        user = await self.get_user(user_id)
        if not user:
            return []
        role = self.roles.get(user.get("role"))
        return list(role.permissions) if role else []

    async def list_roles(self) -> List[Dict[str, Any]]:
        return [
            {"name": r.name, "description": r.description, "permissions": list(r.permissions), "is_system": r.is_system}
            for r in self.roles.values()
        ]


rbac_service = RBACService()
