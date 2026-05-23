from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class OrderRequest:
    symbol: str
    side: str
    quantity: int
    price: float
    reason: str = ""


@dataclass
class OrderResult:
    order_id: int | None
    symbol: str
    side: str
    quantity: int
    price: float
    status: str
    message: str
    created_at: datetime


class Broker(ABC):
    @abstractmethod
    def place_order(self, request: OrderRequest) -> OrderResult:
        """Place an order through the broker adapter."""

    @abstractmethod
    def get_positions(self) -> list[dict[str, float | int | str]]:
        """Return open positions."""
