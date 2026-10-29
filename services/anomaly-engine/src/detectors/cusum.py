"""CUSUM (Cumulative Sum) change-point detector."""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import deque
from typing import Deque, Optional, Tuple
import math
import time


@dataclass
class CusumConfig:
    k: float = 0.5
    h: float = 5.0
    baseline_window: int = 30
    min_samples: int = 15
    cooldown_seconds: float = 300.0


@dataclass
class CusumState:
    samples: Deque[float] = field(default_factory=lambda: deque(maxlen=500))
    s_pos: float = 0.0
    s_neg: float = 0.0
    mu0: Optional[float] = None
    sigma: Optional[float] = None
    last_alert_ts: float = 0.0
    warmed: bool = False

    def reset_sums(self) -> None:
        self.s_pos = 0.0
        self.s_neg = 0.0


class CusumDetector:
    def __init__(self, config: Optional[CusumConfig] = None):
        self.config = config or CusumConfig()
        self.state = CusumState()

    def _estimate_baseline(self) -> None:
        n = len(self.state.samples)
        if n < self.config.min_samples:
            return
        vals = list(self.state.samples)
        mean = sum(vals) / n
        var = sum((x - mean) ** 2 for x in vals) / max(n - 1, 1)
        sigma = math.sqrt(var) if var > 0 else 1e-6
        self.state.mu0 = mean
        self.state.sigma = max(sigma, 1e-6)
        self.state.warmed = True

    def update(self, value: float) -> Tuple[bool, Optional[str], float]:
        self.state.samples.append(value)
        if not self.state.warmed:
            if len(self.state.samples) >= self.config.baseline_window:
                self._estimate_baseline()
            return False, None, 0.0

        assert self.state.mu0 is not None and self.state.sigma is not None
        z = (value - self.state.mu0) / self.state.sigma
        k = self.config.k
        h = self.config.h
        self.state.s_pos = max(0.0, self.state.s_pos + (z - k))
        self.state.s_neg = max(0.0, self.state.s_neg + (-z - k))
        score = max(self.state.s_pos, self.state.s_neg)
        now = time.time()
        if now - self.state.last_alert_ts < self.config.cooldown_seconds:
            return False, None, score
        if self.state.s_pos > h:
            self.state.last_alert_ts = now
            self.state.reset_sums()
            return True, "up", score
        if self.state.s_neg > h:
            self.state.last_alert_ts = now
            self.state.reset_sums()
            return True, "down", score
        return False, None, score

    def force_reset(self) -> None:
        self.state = CusumState()
