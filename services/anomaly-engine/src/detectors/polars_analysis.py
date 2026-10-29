"""
Optional Polars-based batch analysis helpers.

The online path uses the pure-Python CUSUM (constant memory, true streaming).
These functions are useful for:
  - post-incident forensic analysis of a Redis stream dump
  - tuning CUSUM parameters offline
  - generating summary statistics for dashboards
"""

from __future__ import annotations

from typing import Optional
import polars as pl


def load_stream_dump(path: str) -> pl.DataFrame:
    """Load a JSON-lines or CSV dump of telemetry into a Polars DataFrame."""
    if path.endswith(".csv"):
        return pl.read_csv(path)
    return pl.read_ndjson(path)


def compute_rolling_stats(
    df: pl.DataFrame,
    value_col: str = "value",
    window: int = 30,
) -> pl.DataFrame:
    """Add rolling mean and std for quick visual inspection."""
    return df.with_columns(
        [
            pl.col(value_col).rolling_mean(window_size=window).alias("roll_mean"),
            pl.col(value_col).rolling_std(window_size=window).alias("roll_std"),
        ]
    )


def simple_cusum_series(
    values: list[float],
    k: float = 0.5,
    h: float = 5.0,
    mu0: Optional[float] = None,
) -> pl.DataFrame:
    """
    Compute CUSUM statistics over a complete series (offline).
    Returns a DataFrame with S+, S- and a boolean trigger column.
    """
    if not values:
        return pl.DataFrame()

    if mu0 is None:
        mu0 = sum(values[: min(30, len(values))]) / min(30, len(values))

    s_pos = 0.0
    s_neg = 0.0
    rows = []
    for i, x in enumerate(values):
        z = x - mu0
        s_pos = max(0.0, s_pos + (z - k))
        s_neg = max(0.0, s_neg + (-z - k))
        triggered = s_pos > h or s_neg > h
        rows.append(
            {
                "idx": i,
                "value": x,
                "s_pos": s_pos,
                "s_neg": s_neg,
                "triggered": triggered,
            }
        )
        if triggered:
            s_pos = s_neg = 0.0

    return pl.DataFrame(rows)
