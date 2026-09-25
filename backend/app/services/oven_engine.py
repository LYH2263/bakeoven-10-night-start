"""Oven scheduling with half-open ferment+bake intervals and next free window.

Minutes are measured from the current day origin (00:00). A batch that started
fermenting the previous night carries a negative ``start_min`` and its
ferment/bake intervals may cross minute 0. Overlap and free-window checks run on
these full intervals, never only on the slice visible within the current day.
"""

from __future__ import annotations

from dataclasses import dataclass

# Current-day boundaries, in minutes from 00:00.
DAY_ORIGIN = 0
DAY_OPEN = 8 * 60
DAY_CLOSE = 22 * 60
DAY_END = 24 * 60
# Earliest a previous-night start may be (00:00 the previous day).
NIGHT_EARLIEST = -24 * 60


@dataclass(frozen=True)
class Interval:
    start: int  # minutes from day origin; negative = previous day
    end: int  # exclusive

    def overlaps(self, other: "Interval") -> bool:
        return self.start < other.end and other.start < self.end


@dataclass(frozen=True)
class RecipeDurations:
    ferment_min: int
    bake_min: int

    @property
    def total(self) -> int:
        return self.ferment_min + self.bake_min


@dataclass(frozen=True)
class Occupancy:
    oven_id: int
    interval: Interval
    phase: str  # ferment | bake
    batch_id: int


def build_occupancies(
    oven_id: int,
    batch_id: int,
    start_min: int,
    recipe: RecipeDurations,
) -> list[Occupancy]:
    ferment = Interval(start_min, start_min + recipe.ferment_min)
    bake = Interval(ferment.end, ferment.end + recipe.bake_min)
    return [
        Occupancy(oven_id, ferment, "ferment", batch_id),
        Occupancy(oven_id, bake, "bake", batch_id),
    ]


def clip_to_day(interval: Interval) -> Interval | None:
    """Return the half-open slice of ``interval`` still occupying the current day.

    Only minutes in [0, 24h) are drawn on the gantt. A batch that finished before
    the day origin (bake end <= 0) returns ``None``; one merely touching the
    origin at its end (ferment end == 0) also has no visible slice.
    """
    start = max(interval.start, DAY_ORIGIN)
    end = min(interval.end, DAY_END)
    if start < end:
        return Interval(start, end)
    return None


def find_conflicts(existing: list[Occupancy], candidates: list[Occupancy]) -> list[tuple[Occupancy, Occupancy]]:
    hits: list[tuple[Occupancy, Occupancy]] = []
    for cand in candidates:
        for ex in existing:
            if ex.oven_id != cand.oven_id:
                continue
            if ex.interval.overlaps(cand.interval):
                hits.append((ex, cand))
    return hits


def next_free_window(
    existing: list[Occupancy],
    oven_id: int,
    duration: int,
    search_from: int = 0,
    search_to: int = 24 * 60,
) -> Interval | None:
    """Find earliest half-open [start, start+duration) free on oven."""
    if duration <= 0:
        return None
    busy = sorted(
        [o.interval for o in existing if o.oven_id == oven_id],
        key=lambda i: i.start,
    )
    cursor = search_from
    for iv in busy:
        if iv.end <= cursor:
            continue
        if iv.start >= cursor + duration:
            end = cursor + duration
            if end <= search_to:
                return Interval(cursor, end)
            return None
        cursor = max(cursor, iv.end)
    if cursor + duration <= search_to:
        return Interval(cursor, cursor + duration)
    return None
