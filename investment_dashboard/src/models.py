from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    market: Mapped[str] = mapped_column(String(20), default="KR")
    sector: Mapped[str] = mapped_column(String(80), default="")
    memo: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class PriceBar(Base):
    __tablename__ = "price_bars"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    date: Mapped[str] = mapped_column(String(20), index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    trading_value: Mapped[float] = mapped_column(Float, default=0.0)
    change_rate: Mapped[float] = mapped_column(Float, default=0.0)


class VirtualOrder(Base):
    __tablename__ = "virtual_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    market: Mapped[str] = mapped_column(String(20), default="KR")
    side: Mapped[str] = mapped_column(String(10))
    quantity: Mapped[int] = mapped_column(Integer)
    price: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="filled")
    reason: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class VirtualPosition(Base):
    __tablename__ = "virtual_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    market: Mapped[str] = mapped_column(String(20), default="KR", index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    avg_price: Mapped[float] = mapped_column(Float)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )


class RealizedPnlLog(Base):
    __tablename__ = "realized_pnl_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    market: Mapped[str] = mapped_column(String(20), default="KR", index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    entry_price: Mapped[float] = mapped_column(Float)
    exit_price: Mapped[float] = mapped_column(Float)
    realized_pnl: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
