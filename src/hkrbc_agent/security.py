"""Server-side demonstration identities, permissions, and conservative text controls."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from dataclasses import dataclass
from enum import Enum


class AccessDenied(PermissionError):
    pass


class PrivacyError(ValueError):
    pass


class Role(str, Enum):
    ANALYST = "Actuarial Analyst"
    REVIEWER = "Actuarial Reviewer"
    ADMIN = "Administrator"


PERMISSIONS = {
    Role.ANALYST: frozenset({"query", "calculate", "report", "audit_own"}),
    Role.REVIEWER: frozenset({"query", "calculate", "report", "audit_all", "external"}),
    Role.ADMIN: frozenset({"query", "calculate", "report", "audit_all", "external", "ingest"}),
}
CLASSIFICATIONS = {
    Role.ANALYST: ("public",),
    Role.REVIEWER: ("public", "internal"),
    Role.ADMIN: ("public", "internal", "restricted"),
}
DEMO_PASSWORDS = {
    "analyst": "Demo-Analyst-2026!",
    "reviewer": "Demo-Reviewer-2026!",
    "admin": "Demo-Admin-2026!",
}


@dataclass(frozen=True)
class Principal:
    actor_id: str
    role: Role


class AuthService:
    """Signed, expiring sessions; role strings supplied by clients are never trusted.

    Demonstration credentials are public. This is NOT an enterprise identity provider.
    Server restart invalidates sessions; deploy behind real identity before shared use.
    """

    def __init__(self) -> None:
        self._secret = secrets.token_bytes(32)
        self._salt = secrets.token_bytes(16)
        self._accounts: dict[str, tuple[bytes, Role]] = {}
        for username, role in zip(DEMO_PASSWORDS, Role):
            password = os.getenv(f"HKRBC_{username.upper()}_PASSWORD") or DEMO_PASSWORDS[username]
            self._accounts[username] = (self._derive(password), role)

    def _derive(self, password: str) -> bytes:
        return hashlib.pbkdf2_hmac("sha256", password.encode(), self._salt, 120_000)

    def authenticate(self, username: str, password: str) -> str:
        account = self._accounts.get(username)
        candidate = self._derive(password)
        if account is None or not hmac.compare_digest(account[0], candidate):
            raise AccessDenied("Invalid demonstration credentials")
        payload = json.dumps({"actor": username, "role": account[1].value,
                              "expires": int(time.time()) + 3600}, sort_keys=True).encode()
        body = base64.urlsafe_b64encode(payload).decode()
        signature = hmac.new(self._secret, body.encode(), hashlib.sha256).hexdigest()
        return f"{body}.{signature}"

    def resolve(self, token: str) -> Principal:
        try:
            body, signature = token.split(".", 1)
            expected = hmac.new(self._secret, body.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError("signature")
            data = json.loads(base64.urlsafe_b64decode(body))
            role = Role(data["role"])
            if data["expires"] <= time.time() or self._accounts[data["actor"]][1] != role:
                raise ValueError("expired or invalid")
            return Principal(data["actor"], role)
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise AccessDenied("Invalid or expired session; sign in again") from exc


def require(principal: Principal, permission: str) -> None:
    if permission not in PERMISSIONS[principal.role]:
        raise AccessDenied(f"Role does not permit {permission}")


# Deliberately conservative demonstration patterns; not complete enterprise DLP.
PII_PATTERNS = (
    ("EMAIL", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)),
    ("HKID", re.compile(r"\b[A-Z]{1,2}\d{6}(?:\([0-9A]\)|[0-9A])(?![A-Za-z0-9])", re.I)),
    ("PHONE", re.compile(r"(?<!\d)(?:\+?852[\s-]?)?[2-9]\d{3}[\s-]?\d{4}(?!\d)")),
    ("CARD", re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")),
    ("SECRET", re.compile(r"\b(?:sk-[a-zA-Z0-9_-]{8,}|(?:api[_ -]?key|password|secret)\s*[:=]\s*\S+)", re.I)),
)
SENSITIVE_MARKERS = re.compile(r"\b(confidential|restricted|client data|policyholder|employee data)\b|機密|保密|客戶資料|個人資料", re.I)
INJECTION = re.compile(
    r"ignore\s+(?:all\s+)?(?:previous|prior|system)|system\s*prompt|developer\s*message|"
    r"<\|(?:system|assistant)|(?:send|upload|exfiltrate).{0,60}(?:secret|password|api.key)|"
    r"(?:call|execute|run)\s+(?:a\s+)?(?:tool|shell|python)|忽略.{0,10}(?:指令|規則)", re.I | re.S)


def redact(text: str) -> tuple[str, tuple[str, ...]]:
    kinds: list[str] = []
    for kind, pattern in PII_PATTERNS:
        if pattern.search(text):
            kinds.append(kind)
            text = pattern.sub(f"[REDACTED_{kind}]", text)
    return text, tuple(kinds)


def validate_text(text: str, *, max_length: int = 8000) -> str:
    if not isinstance(text, str) or not text.strip() or len(text) > max_length:
        raise ValueError(f"Text must contain 1–{max_length} characters")
    if "\x00" in text:
        raise ValueError("NUL characters are not allowed")
    return text.strip()


def is_injection(text: str) -> bool:
    return bool(INJECTION.search(text))


def sensitive(text: str) -> bool:
    return bool(redact(text)[1] or SENSITIVE_MARKERS.search(text))
