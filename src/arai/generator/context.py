"""Shared state for one world: settings, catalog, calendar and identifiers."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from arai.catalog import Catalog
from arai.settings import Settings

DAY = np.timedelta64(1, "D")


@dataclass
class Context:
    s: Settings
    seed: int
    n: int
    world_id: str
    catalog: Catalog
    abuse_enabled: bool = True
    customer_ids: np.ndarray = field(default=None, repr=False)

    def __post_init__(self):
        self.snapshot = np.datetime64(self.s.snapshot_date, "D")
        self.history_start = np.datetime64(self.s.history_start, "D")
        # the evidence cutoff is the last second of the snapshot date, local time
        self.cutoff_ts = self.snapshot.astype("datetime64[s]") + np.timedelta64(86399, "s")
        self.history = np.arange(self.history_start, self.snapshot + DAY, dtype="datetime64[D]")
        self.festive_multiplier = _festive_multipliers(self.history, self.s.festive_windows)
        self.customer_ids = np.array([f"{self.world_id}-C{i:05d}" for i in range(self.n)], dtype=object)


def _festive_multipliers(dates: np.ndarray, windows: list) -> np.ndarray:
    """Multiplier of the festive window covering each date (0 outside every window). Windows may cross New Year."""
    month_day = np.array([(d.month, d.day) for d in dates.astype(object)])
    key = month_day[:, 0] * 100 + month_day[:, 1]
    multiplier = np.zeros(len(dates))
    for window in windows:
        start = int(window["start"].replace("-", ""))
        end = int(window["end"].replace("-", ""))
        inside = (key >= start) & (key <= end) if start <= end else (key >= start) | (key <= end)
        multiplier = np.where(inside, np.maximum(multiplier, float(window["multiplier"])), multiplier)
    return multiplier
