"""
Latency models for execution simulation.
"""

from __future__ import annotations

import random
from dataclasses import dataclass


class LatencyModel:
    def sample_ms(self) -> int:
        raise NotImplementedError


@dataclass(frozen=True)
class FixedLatencyModel(LatencyModel):
    latency_ms: int = 0

    def sample_ms(self) -> int:
        if self.latency_ms < 0:
            raise ValueError("latency_ms cannot be negative")
        return self.latency_ms


@dataclass
class UniformLatencyModel(LatencyModel):
    min_ms: int = 0
    max_ms: int = 250
    seed: int | None = None

    def __post_init__(self) -> None:
        if self.min_ms < 0 or self.max_ms < 0:
            raise ValueError("latency bounds cannot be negative")
        if self.min_ms > self.max_ms:
            raise ValueError("min_ms cannot exceed max_ms")
        self._random = random.Random(self.seed)

    def sample_ms(self) -> int:
        return self._random.randint(self.min_ms, self.max_ms)
