#!/usr/bin/env python3
"""Run before deploy – env safety + import smoke test."""

from __future__ import annotations
import os
import sys


def main() -> int:
    errors = []
    # Env
    try:
        from molido_security import check_env_safety
        report = check_env_safety()
        for f in report.findings:
            errors.append(f"[security] {f}")
        for w in report.warnings:
            print(f"WARNING: {w}")
    except ImportError:
        print("WARNING: molido_security not installed in this environment")

    mode = os.getenv("TRADING_ACCOUNT_MODE", "DEMO")
    if mode == "REAL":
        errors.append("Refusing preflight success while TRADING_ACCOUNT_MODE=REAL without explicit override")

    # Core imports
    for mod in [
        "molido_shared",
        "molido_broker",
        "molido_indicators",
        "molido_strategies",
        "molido_signals",
        "molido_risk",
        "molido_execution",
        "molido_portfolio",
    ]:
        try:
            __import__(mod)
        except ImportError as e:
            errors.append(f"import {mod}: {e}")

    if errors:
        print("PREFLIGHT FAILED:")
        for e in errors:
            print(" -", e)
        return 1
    print("PREFLIGHT OK – safe to start DEMO/Paper services")
    return 0


if __name__ == "__main__":
    sys.exit(main())
