"""
Broker factory – creates the correct adapter based on configuration.
"""

from __future__ import annotations
from enum import Enum

from molido_broker.base import BrokerAdapter
from molido_broker.mock import MockBrokerAdapter
from molido_broker.mt5 import MT5BrokerAdapter


class BrokerType(str, Enum):
    MOCK = "mock"
    MT5 = "mt5"


def create_broker(
    broker_type: BrokerType | str = BrokerType.MOCK,
    *,
    login: int | None = None,
    password: str | None = None,
    server: str | None = None,
    path: str | None = None,
    initial_balance: float = 10_000.0,
    account_type: str = "DEMO",
    rpc_host: str | None = None,
    rpc_port: int | None = None,
) -> BrokerAdapter:
    """
    Factory function.
    Default is MOCK so the system can run without a real MT5 terminal.
    """
    if isinstance(broker_type, str):
        broker_type = BrokerType(broker_type.lower())

    if broker_type == BrokerType.MOCK:
        return MockBrokerAdapter(
            initial_balance=initial_balance,
            account_type=account_type,
        )

    if broker_type == BrokerType.MT5:
        return MT5BrokerAdapter(
            login=login,
            password=password,
            server=server,
            path=path,
            # Which MT5 terminal bridge this account uses; None falls back to
            # the MT5_RPC_HOST/PORT env vars for single-account setups.
            rpc_host=rpc_host,
            rpc_port=rpc_port,
        )

    raise ValueError(f"Unknown broker type: {broker_type}")
