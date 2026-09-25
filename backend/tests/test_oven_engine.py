from app.services.oven_engine import (
    DAY_OPEN,
    Interval,
    Occupancy,
    RecipeDurations,
    build_occupancies,
    clip_to_day,
    find_conflicts,
    next_free_window,
)


def test_half_open_no_touch_conflict():
    a = Occupancy(1, Interval(0, 30), "bake", 1)
    b = Occupancy(1, Interval(30, 60), "bake", 2)
    assert find_conflicts([a], [b]) == []


def test_overlap_detected():
    recipe = RecipeDurations(20, 30)
    cand = build_occupancies(1, 9, 10, recipe)
    existing = [Occupancy(1, Interval(25, 40), "bake", 1)]
    assert find_conflicts(existing, cand)


def test_next_free_window_after_busy():
    existing = [
        Occupancy(1, Interval(0, 40), "ferment", 1),
        Occupancy(1, Interval(40, 70), "bake", 1),
    ]
    w = next_free_window(existing, 1, duration=30, search_from=0)
    assert w == Interval(70, 100)


def test_next_free_in_gap():
    existing = [
        Occupancy(1, Interval(0, 20), "bake", 1),
        Occupancy(1, Interval(80, 100), "bake", 2),
    ]
    w = next_free_window(existing, 1, duration=30, search_from=0)
    assert w == Interval(20, 50)


# --- previous-night (overnight) fermentation ---


def test_night_builds_cross_midnight_intervals():
    # Start 23:30 the previous day (-30), ferment 60, bake 40.
    recipe = RecipeDurations(60, 40)
    occs = build_occupancies(1, 7, -30, recipe)
    ferment, bake = occs
    assert ferment.interval == Interval(-30, 30)
    assert bake.interval == Interval(30, 70)


def test_night_ferment_overlaps_today_batch_on_full_interval():
    # Night batch ferments [-20, 20); a same-day batch bakes [10, 40).
    recipe = RecipeDurations(40, 20)
    night = build_occupancies(1, 7, -20, recipe)
    today = [Occupancy(1, Interval(10, 40), "bake", 3)]
    # The overlap [10, 20) exists only on the today-visible slice; the engine
    # still catches it because it works on full intervals.
    assert find_conflicts(today, night)


def test_night_ferment_overlaps_before_midnight_too():
    # Night batch ferments [-60, 0); another night/today interval reaches into
    # the pre-midnight portion [-30, 10).
    recipe = RecipeDurations(60, 30)
    night = build_occupancies(1, 7, -60, recipe)  # ferment [-60,0)
    other = [Occupancy(1, Interval(-30, 10), "bake", 8)]
    assert find_conflicts(other, night)


def test_half_open_touch_at_midnight_no_conflict():
    # Existing interval ends exactly at 0; night ferment starts at/before 0 but
    # only touches at the boundary. [..,0) vs [0,..) must not overlap.
    a = Occupancy(1, Interval(-60, 0), "bake", 1)
    b = Occupancy(1, Interval(0, 40), "ferment", 2)
    assert find_conflicts([a], [b]) == []


def test_night_no_conflict_when_clear_after_open():
    # Night batch ferments [-60,0), bakes [0,40); today batch starts at 40.
    recipe = RecipeDurations(60, 40)
    night = build_occupancies(1, 7, -60, recipe)
    today = build_occupancies(1, 9, 40, RecipeDurations(10, 10))
    assert find_conflicts(night, today) == []


def test_next_free_window_respects_negative_busy():
    # Oven busy [-30, 30); first free 30-minute slot from open search start.
    existing = [Occupancy(1, Interval(-30, 30), "bake", 1)]
    w = next_free_window(existing, 1, duration=30, search_from=0)
    assert w == Interval(30, 60)


def test_clip_drops_pre_midnight_only_slice():
    # Entirely before the day origin -> nothing to draw.
    assert clip_to_day(Interval(-60, 0)) is None
    assert clip_to_day(Interval(-60, -10)) is None


def test_clip_keeps_only_post_origin_slice():
    # Cross-midnight interval keeps only its [0, ...) part.
    assert clip_to_day(Interval(-30, 30)) == Interval(0, 30)
    # Fully inside the day is unchanged.
    assert clip_to_day(Interval(10, 50)) == Interval(10, 50)
    # Extending past the day end is capped at 24h.
    assert clip_to_day(Interval(23 * 60, 25 * 60)) == Interval(23 * 60, 24 * 60)


def test_day_open_constant():
    assert DAY_OPEN == 8 * 60
