"""
Fee models for simulated execution.
"""
from __future__ import annotations

from dataclasses import dataclass


def calculate_fee(notional: float, fee_bps: float = 10) -> float:
    if notional < 0:
        raise ValueError("notional cannot be negative")
    return notional * fee_bps / 10_000


@dataclass(frozen=True)
class FeeModel:
    rate_bps: float = 10.0

    def calculate(self, notional: float) -> float:
        return calculate_fee(notional, self.rate_bps)
