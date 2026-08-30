"""
Security helpers and runtime checks (Master Prompt §32).
"""

from __future__ import annotations
import os
import re
from dataclasses import dataclass, field


SECRET_PATTERNS = [
    re.compile(r"(?i)(password|secret|api[_-]?key|token)\s*=\s*['\"]?[^'\s\"]{8,}"),
]


@dataclass
class SecurityReport:
    ok: bool
    findings: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def check_env_safety() -> SecurityReport:
    findings: list[str] = []
    warnings: list[str] = []

    secret = os.getenv("SECRET_KEY", "")
    if not secret or secret in ("change-me-to-a-long-random-string", "changeme") or secret.startswith("replace-me"):
        findings.append("SECRET_KEY is missing or still the example value")
    elif len(secret) < 32:
        findings.append("SECRET_KEY should be at least 32 characters")

    mode = os.getenv("TRADING_ACCOUNT_MODE", "DEMO").upper()
    if mode == "REAL":
        warnings.append("TRADING_ACCOUNT_MODE=REAL — live capital is in use")
        if not os.getenv("MT5_REAL_LOGIN") or not os.getenv("MT5_REAL_PASSWORD") or not os.getenv("MT5_REAL_SERVER"):
            findings.append("LIVE mode is on but MT5_REAL_LOGIN/PASSWORD/SERVER are empty")
    if mode not in ("DEMO", "PROP", "REAL"):
        findings.append(f"Invalid TRADING_ACCOUNT_MODE: {mode}")

    if os.getenv("MASTER_BOT_ENABLED", "false").lower() in ("1", "true", "yes"):
        warnings.append("MASTER_BOT_ENABLED is true at process start")

    engine_token = os.getenv("ENGINE_INTERNAL_TOKEN", "")
    if not engine_token or len(engine_token) < 16:
        findings.append("ENGINE_INTERNAL_TOKEN is missing or too short (needed to authenticate POST /ops/heartbeat)")

    pw = os.getenv("POSTGRES_PASSWORD", "")
    if not pw or pw in ("changeme", "change-me-strong-password") or pw.startswith("replace-me"):
        findings.append("POSTGRES_PASSWORD is missing or still the example value")

    if not os.getenv("REDIS_PASSWORD"):
        findings.append("REDIS_PASSWORD is empty")

    return SecurityReport(ok=len(findings) == 0, findings=findings, warnings=warnings)


def redact_url(url: str) -> str:
    """Strip credentials from URLs before logging."""
    return re.sub(r":([^:@/]+)@", ":***@", url)
