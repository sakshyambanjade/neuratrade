"""
Order-book based execution simulator.
"""
from __future__ import annotations

import json
import math
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from services.fees import calculate_fee
from services.fees import FeeModel
from services.latency import FixedLatencyModel, LatencyModel
from services.order_book import OrderBookSnapshot, OrderType, Side
from services.slippage import calculate_slippage_bps, estimate_slippage_bps


OrderStatus = Literal["FILLED", "PARTIAL", "REJECTED"]
MarketOrderStatus = Literal["FILLED", "REJECTED"]


class OrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    side: Side
    quantity: float
    price: float = Field(gt=0)
    cash_balance: float = Field(ge=0)
    btc_balance: float = Field(ge=0)
    avg_entry_price: float | None = Field(default=None, ge=0)
    spread_bps: float = Field(default=10.0, ge=0)
    minute_volume: float = Field(default=1.0)
    volatility: float = Field(default=0.0, ge=0)
    fee_bps: float = Field(default=10.0, ge=0)
    latency_ms: int = Field(default=0, ge=0)

    @field_validator("side", mode="before")
    @classmethod
    def normalize_side(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("side must be BUY or SELL")
        side = value.upper()
        if side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        return side


class FillReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: MarketOrderStatus
    side: Side
    requested_quantity: float
    filled_quantity: float
    average_fill_price: float | None
    gross_notional: float
    fee: float
    slippage_bps: float
    cash_before: float
    cash_after: float
    btc_before: float
    btc_after: float
    realized_pnl: float
    latency_ms: int
    error_reason: str | None = None


@dataclass(frozen=True)
class SimulatedOrder:
    side: Side
    order_type: OrderType
    quantity: float
    limit_price: float | None = None
    client_order_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    submitted_ts_ms: int | None = None

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.order_type == "LIMIT" and self.limit_price is None:
            raise ValueError("limit orders require limit_price")
        if self.limit_price is not None and self.limit_price <= 0:
            raise ValueError("limit_price must be positive")


@dataclass(frozen=True)
class Fill:
    price: float
    quantity: float
    notional: float
    fee: float


@dataclass(frozen=True)
class ExecutionReport:
    order_id: str
    symbol: str
    side: Side
    order_type: OrderType
    status: OrderStatus
    requested_quantity: float
    filled_quantity: float
    remaining_quantity: float
    average_price: float | None
    reference_price: float
    slippage_bps: float
    fee_total: float
    latency_ms: int
    fills: tuple[Fill, ...]
    submitted_ts_ms: int | None
    executed_ts_ms: int

    def to_dict(self) -> dict:
        return asdict(self)


class FillReportLogger:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def __call__(self, report: ExecutionReport) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(report.to_dict(), separators=(",", ":")) + "\n")


class ExecutionSimulator:
    def __init__(
        self,
        *,
        fee_model: FeeModel | None = None,
        latency_model: LatencyModel | None = None,
        report_logger: Callable[[ExecutionReport], None] | None = None,
        sleep_latency: bool = False,
    ) -> None:
        self.fee_model = fee_model or FeeModel()
        self.latency_model = latency_model or FixedLatencyModel(0)
        self.report_logger = report_logger
        self.sleep_latency = sleep_latency

    def execute_market_order(self, request: OrderRequest) -> FillReport:
        invalid_reason = self._invalid_market_order_reason(request)
        if invalid_reason:
            return self._rejected_report(request, invalid_reason)

        latency_ms = request.latency_ms or self.latency_model.sample_ms()
        if self.sleep_latency and latency_ms > 0:
            time.sleep(latency_ms / 1000)

        slippage_bps = estimate_slippage_bps(
            spread_bps=request.spread_bps,
            order_size=request.quantity,
            minute_volume=request.minute_volume,
            volatility=request.volatility,
        )
        average_fill_price = self._apply_slippage(request.side, request.price, slippage_bps)
        gross_notional = request.quantity * average_fill_price
        fee = calculate_fee(gross_notional, request.fee_bps)

        if request.side == "BUY":
            cash_required = gross_notional + fee
            if cash_required > request.cash_balance + 1e-12:
                return self._rejected_report(
                    request,
                    f"INSUFFICIENT_CASH: required {cash_required:.8f}, available {request.cash_balance:.8f}",
                    slippage_bps=slippage_bps,
                    average_fill_price=average_fill_price,
                    fee=fee,
                    gross_notional=gross_notional,
                    latency_ms=latency_ms,
                )
            cash_after = request.cash_balance - cash_required
            btc_after = request.btc_balance + request.quantity
            realized_pnl = 0.0
        else:
            if request.quantity > request.btc_balance + 1e-12:
                return self._rejected_report(
                    request,
                    f"INSUFFICIENT_BTC: required {request.quantity:.8f}, available {request.btc_balance:.8f}",
                    slippage_bps=slippage_bps,
                    average_fill_price=average_fill_price,
                    fee=fee,
                    gross_notional=gross_notional,
                    latency_ms=latency_ms,
                )
            cash_after = request.cash_balance + gross_notional - fee
            btc_after = request.btc_balance - request.quantity
            realized_pnl = self._realized_pnl(request, average_fill_price, fee)

        return self._filled_report(
            request=request,
            average_fill_price=average_fill_price,
            gross_notional=gross_notional,
            fee=fee,
            slippage_bps=slippage_bps,
            cash_after=cash_after,
            btc_after=btc_after,
            realized_pnl=realized_pnl,
            latency_ms=latency_ms,
        )

    def execute(self, order: SimulatedOrder, book: OrderBookSnapshot) -> ExecutionReport:
        latency_ms = self.latency_model.sample_ms()
        if self.sleep_latency and latency_ms > 0:
            time.sleep(latency_ms / 1000)

        fills = self._fill_order(order, book)
        filled_quantity = sum(fill.quantity for fill in fills)
        remaining_quantity = max(order.quantity - filled_quantity, 0.0)
        notional = sum(fill.notional for fill in fills)
        fee_total = sum(fill.fee for fill in fills)
        average_price = notional / filled_quantity if filled_quantity else None
        status = self._status(order.quantity, filled_quantity)
        slippage_bps = (
            calculate_slippage_bps(
                side=order.side,
                reference_price=book.mid_price,
                execution_price=average_price,
            )
            if average_price
            else 0.0
        )

        report = ExecutionReport(
            order_id=order.client_order_id,
            symbol=book.symbol,
            side=order.side,
            order_type=order.order_type,
            status=status,
            requested_quantity=order.quantity,
            filled_quantity=filled_quantity,
            remaining_quantity=remaining_quantity,
            average_price=average_price,
            reference_price=book.mid_price,
            slippage_bps=slippage_bps,
            fee_total=fee_total,
            latency_ms=latency_ms,
            fills=tuple(fills),
            submitted_ts_ms=order.submitted_ts_ms,
            executed_ts_ms=int(time.time() * 1000),
        )
        if self.report_logger:
            self.report_logger(report)
        return report

    def _fill_order(self, order: SimulatedOrder, book: OrderBookSnapshot) -> list[Fill]:
        fills: list[Fill] = []
        remaining = order.quantity
        for level in book.executable_levels(order.side):
            if not self._is_executable(order, level.price):
                break
            fill_qty = min(remaining, level.quantity)
            notional = fill_qty * level.price
            fills.append(
                Fill(
                    price=level.price,
                    quantity=fill_qty,
                    notional=notional,
                    fee=self.fee_model.calculate(notional),
                )
            )
            remaining -= fill_qty
            if remaining <= 1e-12:
                break
        return fills

    def _is_executable(self, order: SimulatedOrder, price: float) -> bool:
        if order.order_type == "MARKET":
            return True
        if order.side == "BUY":
            return price <= float(order.limit_price)
        return price >= float(order.limit_price)

    @staticmethod
    def _status(requested_quantity: float, filled_quantity: float) -> OrderStatus:
        if filled_quantity <= 0:
            return "REJECTED"
        if filled_quantity + 1e-12 < requested_quantity:
            return "PARTIAL"
        return "FILLED"

    @staticmethod
    def _invalid_market_order_reason(request: OrderRequest) -> str | None:
        numeric_fields = {
            "quantity": request.quantity,
            "price": request.price,
            "cash_balance": request.cash_balance,
            "btc_balance": request.btc_balance,
            "spread_bps": request.spread_bps,
            "minute_volume": request.minute_volume,
            "volatility": request.volatility,
            "fee_bps": request.fee_bps,
            "latency_ms": float(request.latency_ms),
        }
        for field_name, value in numeric_fields.items():
            if not math.isfinite(value):
                return f"INVALID_{field_name.upper()}: value must be finite"
        if request.quantity <= 0:
            return "INVALID_QUANTITY: quantity must be greater than zero"
        if request.minute_volume < 0:
            return "INVALID_MINUTE_VOLUME: minute_volume cannot be negative"
        return None

    @staticmethod
    def _apply_slippage(side: Side, price: float, slippage_bps: float) -> float:
        if side == "BUY":
            return price * (1 + slippage_bps / 10_000)
        return price * max(0.0, 1 - slippage_bps / 10_000)

    @staticmethod
    def _realized_pnl(request: OrderRequest, average_fill_price: float, fee: float) -> float:
        if request.avg_entry_price is None:
            return 0.0
        return (average_fill_price - request.avg_entry_price) * request.quantity - fee

    @staticmethod
    def _filled_report(
        *,
        request: OrderRequest,
        average_fill_price: float,
        gross_notional: float,
        fee: float,
        slippage_bps: float,
        cash_after: float,
        btc_after: float,
        realized_pnl: float,
        latency_ms: int,
    ) -> FillReport:
        return FillReport(
            status="FILLED",
            side=request.side,
            requested_quantity=request.quantity,
            filled_quantity=request.quantity,
            average_fill_price=average_fill_price,
            gross_notional=gross_notional,
            fee=fee,
            slippage_bps=slippage_bps,
            cash_before=request.cash_balance,
            cash_after=cash_after,
            btc_before=request.btc_balance,
            btc_after=btc_after,
            realized_pnl=realized_pnl,
            latency_ms=latency_ms,
        )

    @staticmethod
    def _rejected_report(
        request: OrderRequest,
        reason: str,
        *,
        slippage_bps: float = 0.0,
        average_fill_price: float | None = None,
        fee: float = 0.0,
        gross_notional: float = 0.0,
        latency_ms: int | None = None,
    ) -> FillReport:
        return FillReport(
            status="REJECTED",
            side=request.side,
            requested_quantity=request.quantity,
            filled_quantity=0.0,
            average_fill_price=average_fill_price,
            gross_notional=gross_notional,
            fee=fee,
            slippage_bps=slippage_bps,
            cash_before=request.cash_balance,
            cash_after=request.cash_balance,
            btc_before=request.btc_balance,
            btc_after=request.btc_balance,
            realized_pnl=0.0,
            latency_ms=request.latency_ms if latency_ms is None else latency_ms,
            error_reason=reason,
        )
