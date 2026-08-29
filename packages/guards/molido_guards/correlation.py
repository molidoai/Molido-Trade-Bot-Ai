"""Block stacking correlated FX majors. Second pair in a cluster is denied."""

from __future__ import annotations

CLUSTERS: tuple[frozenset[str], ...] = (
    frozenset({"EURUSD", "GBPUSD", "EURGBP", "EURJPY", "GBPJPY"}),
    frozenset({"USDJPY", "EURJPY", "GBPJPY", "AUDJPY"}),
    frozenset({"AUDUSD", "NZDUSD", "AUDNZD"}),
    frozenset({"XAUUSD", "XAGUSD"}),
)


def _norm(symbol: str) -> str:
    return (symbol or "").replace("/", "").upper()


def correlated_block(symbol: str, open_symbols: list[str] | None) -> tuple[bool, str]:
    """Return (allowed, reason)."""
    want = _norm(symbol)
    open_n = {_norm(s) for s in (open_symbols or []) if _norm(s) != want}
    if not open_n:
        return True, "no other positions"
    for cluster in CLUSTERS:
        if want in cluster and open_n & cluster:
            hit = ", ".join(sorted(open_n & cluster))
            return False, f"correlated with open {hit}"
    return True, "uncorrelated"
