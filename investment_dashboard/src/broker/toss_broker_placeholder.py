from __future__ import annotations

from src.broker.base import Broker, OrderRequest, OrderResult


class TossBrokerPlaceholder(Broker):
    """Placeholder for a future Toss Securities adapter.

    Actual order submission is intentionally not implemented in this MVP.
    """

    def place_order(self, request: OrderRequest) -> OrderResult:
        raise NotImplementedError("토스증권 API 승인 전까지 실제 주문 기능은 구현하지 않습니다.")

    def get_positions(self) -> list[dict[str, float | int | str]]:
        raise NotImplementedError("토스증권 API 승인 후 포지션 조회 어댑터를 구현하세요.")
