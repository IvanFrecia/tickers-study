"""Local session helpers for the study dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
from typing import Any

from fastapi import Request as FastAPIRequest


def _canonical(path: Path) -> Path:
    """Return canonical absolute path without requiring existence."""
    return path.expanduser().resolve(strict=False)


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _b64url_decode(raw: str) -> bytes:
    padding = "=" * ((4 - len(raw) % 4) % 4)
    return base64.urlsafe_b64decode(raw + padding)


def _sign(raw: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest()
    return _b64url_encode(digest)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


@dataclass(frozen=True)
class AuthUser:
    email: str
    role: str
    name: str | None

    @property
    def is_owner(self) -> bool:
        return self.role == "owner"

    @property
    def is_admin(self) -> bool:
        return self.role in {"owner", "admin"}

    @property
    def is_test(self) -> bool:
        return self.role == "test"


class AuthManager:
    """Optional local signed-cookie sessions."""

    SESSION_COOKIE = "tickers_session"
    STATE_COOKIE = "tickers_oauth_state"
    SESSION_DURATION = timedelta(hours=8)
    STATE_DURATION = timedelta(minutes=10)
    OAUTH_SCOPE = "openid email profile"
    VALID_ROLES = frozenset({"owner", "admin", "user", "test"})

    def __init__(self) -> None:
        self.session_secret = os.getenv("TICKERS_SESSION_SECRET", "").strip()
        self.auth_enforced = os.getenv("TICKERS_AUTH_ENFORCED", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if self.auth_enforced and not self.session_secret:
            raise RuntimeError("TICKERS_AUTH_ENFORCED requires TICKERS_SESSION_SECRET. Refusing to sign sessions with a built-in key.")
        self.test_user_enabled = os.getenv("TICKERS_TEST_USER_ENABLED", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.test_user_email = _normalize_email(os.getenv("TICKERS_TEST_USER_EMAIL", ""))
        self.test_user_password = os.getenv("TICKERS_TEST_USER_PASSWORD", "").strip()
        self.test_user_role = self._normalize_role(os.getenv("TICKERS_TEST_USER_ROLE", "test"), default="test")
        self.password_login_users: dict[str, str] = {}

        role_map_override = os.getenv("TICKERS_ALLOWED_USERS_JSON", "").strip()
        if role_map_override:
            try:
                parsed = json.loads(role_map_override)
                if isinstance(parsed, dict):
                    self.allowed_users, self.password_login_users = self._coerce_allowed_users(parsed)
                else:
                    self.allowed_users = self._default_allowed_users()
            except json.JSONDecodeError:
                self.allowed_users = self._default_allowed_users()
        else:
            self.allowed_users = self._default_allowed_users()

        if not self.test_user_password and not self.password_login_users:
            self.test_user_enabled = False
        if self.test_user_enabled and self.test_user_email:
            self.allowed_users.setdefault(self.test_user_email, self.test_user_role)

    @staticmethod
    def _default_allowed_users() -> dict[str, str]:
        return {}

    @classmethod
    def _normalize_role(cls, role: str, *, default: str = "user") -> str:
        normalized = str(role).strip().lower()
        if normalized in cls.VALID_ROLES:
            return normalized
        return default

    @classmethod
    def _coerce_allowed_users(cls, source: dict[Any, Any]) -> tuple[dict[str, str], dict[str, str]]:
        role_map: dict[str, str] = {}
        password_map: dict[str, str] = {}
        for raw_email, raw_role in source.items():
            email = _normalize_email(str(raw_email))
            if not email:
                continue
            if isinstance(raw_role, dict):
                role_map[email] = cls._normalize_role(str(raw_role.get("role", "")), default="user")
                password = str(raw_role.get("password", "")).strip()
                if password:
                    password_map[email] = password
                continue
            role_map[email] = cls._normalize_role(str(raw_role), default="user")
        return role_map, password_map

    def dev_user(self) -> AuthUser:
        if not self.allowed_users:
            fallback_email = self.test_user_email or "local.dev@tickers.invalid"
            fallback_role = self._normalize_role(self.test_user_role, default="owner")
            return AuthUser(email=fallback_email, role=fallback_role, name="Local Dev User")
        owner_email = next((email for email, role in self.allowed_users.items() if role == "owner"), None)
        if owner_email is None:
            owner_email = sorted(self.allowed_users)[0]
        return AuthUser(email=owner_email, role=self.allowed_users[owner_email], name="Local Dev User")

    def _base_url(self, request: FastAPIRequest) -> str:
        proto = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
        host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc)).split(",")[0].strip()
        return f"{proto}://{host}"

    def redirect_uri(self, request: FastAPIRequest) -> str:
        if self.redirect_uri_env:
            return self.redirect_uri_env
        return f"{self._base_url(request)}/auth/callback"

    def _cookie_secure(self, request: FastAPIRequest) -> bool:
        forced = os.getenv("TICKERS_COOKIE_SECURE", "").strip().lower()
        if forced in {"1", "true", "yes", "on"}:
            return True
        if forced in {"0", "false", "no", "off"}:
            return False
        proto = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip().lower()
        return proto == "https"

    def _encode_token(self, payload: dict[str, Any]) -> str:
        if not self.session_secret:
            raise RuntimeError("TICKERS_SESSION_SECRET is required to sign a session.")
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        body = _b64url_encode(raw)
        sig = _sign(body.encode("utf-8"), self.session_secret)
        return f"{body}.{sig}"

    def _decode_token(self, token: str) -> dict[str, Any] | None:
        if not token or "." not in token or not self.session_secret:
            return None
        body, sig = token.split(".", 1)
        expected = _sign(body.encode("utf-8"), self.session_secret)
        if not hmac.compare_digest(sig, expected):
            return None
        try:
            payload = json.loads(_b64url_decode(body).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            return None
        if not isinstance(payload, dict):
            return None
        exp = payload.get("exp")
        if not isinstance(exp, (int, float)):
            return None
        if _now_utc().timestamp() > float(exp):
            return None
        return payload

    def user_from_test_credentials(self, email: str, password: str) -> AuthUser | None:
        normalized = _normalize_email(email)
        if not self.test_user_enabled and normalized not in self.password_login_users:
            return None
        role = self.allowed_users.get(normalized)
        if not role:
            return None
        expected_password = self.password_login_users.get(normalized, self.test_user_password)
        if not expected_password:
            return None
        if not hmac.compare_digest(password, expected_password):
            return None
        return AuthUser(email=normalized, role=role, name="Password Login User")

    def issue_session_token(self, user: AuthUser) -> str:
        payload = {
            "email": user.email,
            "role": user.role,
            "name": user.name,
            "exp": int((_now_utc() + self.SESSION_DURATION).timestamp()),
        }
        return self._encode_token(payload)

    def user_from_session_cookie(self, token: str | None) -> AuthUser | None:
        if not self.auth_enforced:
            return self.dev_user()
        if not token:
            return None
        payload = self._decode_token(token)
        if not payload:
            return None
        email = _normalize_email(str(payload.get("email", "")))
        role = self._normalize_role(str(payload.get("role", "")), default="")
        if not email or self.allowed_users.get(email) != role:
            return None
        name = payload.get("name")
        return AuthUser(email=email, role=role, name=name if isinstance(name, str) else None)

    def session_cookie_args(self, request: FastAPIRequest) -> dict[str, Any]:
        return {
            "httponly": True,
            "secure": self._cookie_secure(request),
            "samesite": "lax",
            "path": "/",
        }

    def public_config(self) -> dict[str, Any]:
        return {
            "auth_enforced": self.auth_enforced,
            "password_login_enabled": bool(self.password_login_users) or self.test_user_enabled,
            "roles": sorted(self.VALID_ROLES),
        }
