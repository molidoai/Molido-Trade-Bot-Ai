#!/usr/bin/env python3
"""VPS-broker latency probe. No secrets. Warns if > 80ms."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/broker"))
sys.path.insert(0, str(ROOT / "packages/shared"))

from molido_broker.latency import probe_latency


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=None)
    ap.add_argument("--port", type=int, default=None)
    args = ap.parse_args()
    rec = probe_latency(host=args.host, port=args.port)
    print(f"{rec['host']}:{rec['port']} {rec['ms']}ms ok={rec['ok']} warn={rec['warn']}")
    return 0 if rec["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
