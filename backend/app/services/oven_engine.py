"""Oven scheduling with half-open ferment+bake intervals and next free window.

All times are absolute minutes from the current day's 00:00 and may be
negative: a negative start means the batch began on the previous day
(overnight fermentation) and its occupancy is allowed to cross midnight.
Conflict and free-window math always uses the full interval, never the
part merely visible on the current day.
"""

from __future__ import annotations

from dataclasses import dataclass

DAY_MINUTES = 24 * 60
DAY_OPEN = 8 * 60  # 当日开门 08:00


@dataclass(frozen=True)
class Interval:
    start: int  # minutes from day origin, negative = previous day
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


def absolute_start(start_min: int, prev_day: bool) -> int:
    """Normalize a registration to absolute minutes from today 00:00.

    Two ways to register a previous-day (overnight) start:
    - negative minutes: start_min is already absolute (e.g. -60 = 23:00 yesterday);
    - explicit marker: prev_day=True reads start_min as a clock time on the
      previous day (0..1439, e.g. 1380 = 23:00 yesterday).
    Without the marker, non-negative start_min keeps counting from today 00:00.
    """
    if prev_day and start_min >= 0:
        return start_min - DAY_MINUTES
    return start_min


def is_overnight(start_min_absolute: int) -> bool:
    """True when the absolute start falls on the previous day."""
    return start_min_absolute < 0


def overnight_rejection(
    absolute_start: int,
    recipe: RecipeDurations,
    day_open: int = DAY_OPEN,
) -> str | None:
    """Reason an overnight batch must be rejected, else None.

    Same-day batches are never affected. An overnight batch whose bake
    ends before the shop opens is refused.
    """
    if not is_overnight(absolute_start):
        return None
    if absolute_start + recipe.total < day_open:
        return "bake_end_before_open"
    return None


def clip_to_day(interval: Interval, day_start: int = 0) -> Interval | None:
    """The part of the interval at/after day_start (today 00:00), or None.

    Used for drawing: only what still occupies the oven after midnight is
    shown. The upper end is left unclipped so same-day batches keep their
    full span. Never use this for conflict or window math.
    """
    start = max(interval.start, day_start)
    if interval.end <= start:
        return None
    return Interval(start, interval.end)


def build_occupancies(
    oven_id: int,
    batch_id: int,
    start_min: int,
    recipe: RecipeDurations,
) -> list[Occupancy]:
    """Ferment+bake occupancies; start_min is absolute and may be negative."""
    ferment = Interval(start_min, start_min + recipe.ferment_min)
    bake = Interval(ferment.end, ferment.end + recipe.bake_min)
    return [
        Occupancy(oven_id, ferment, "ferment", batch_id),
        Occupancy(oven_id, bake, "bake", batch_id),
    ]


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
