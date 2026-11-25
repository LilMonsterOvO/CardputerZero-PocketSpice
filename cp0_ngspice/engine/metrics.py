"""Waveform statistics and process memory telemetry helpers."""
from __future__ import annotations

from dataclasses import dataclass
import os
import numpy as np
import psutil


@dataclass
class SignalStats:
    name: str
    vmin: float
    vmax: float
    vavg: float
    vrms: float
    vpp_tail: float
    samples: int


def get_rss_mb() -> float:
    """Return current process resident set size (RSS) in MiB."""
    proc = psutil.Process(os.getpid())
    return proc.memory_info().rss / (1024.0 * 1024.0)


def compute_signal_stats(name: str, data: np.ndarray) -> SignalStats:
    if data.size == 0:
        return SignalStats(name=name, vmin=0.0, vmax=0.0, vavg=0.0, vrms=0.0, vpp_tail=0.0, samples=0)
    tail_start = max(0, int(data.size * 0.7))
    tail = data[tail_start:]
    return SignalStats(
        name=name,
        vmin=float(np.min(data)),
        vmax=float(np.max(data)),
        vavg=float(np.mean(tail)),
        vrms=float(np.sqrt(np.mean(np.square(tail)))),
        vpp_tail=float(np.max(tail) - np.min(tail)),
        samples=int(data.size),
    )


def format_eng(val: float, unit: str = "") -> str:
    """Compact engineering number formatter for 320x170 HUD."""
    av = abs(val)
    if av < 1e-9:
        return f"0{unit}"
    if av >= 1e3:
        return f"{val/1e3:.2f}k{unit}"
    if av >= 1.0:
        return f"{val:.2f}{unit}"
    if av >= 1e-3:
        return f"{val*1e3:.1f}m{unit}"
    if av >= 1e-6:
        return f"{val*1e6:.1f}u{unit}"
    return f"{val:.2e}{unit}"
