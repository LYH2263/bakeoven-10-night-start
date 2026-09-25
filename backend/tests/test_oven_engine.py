from app.services.oven_engine import (
    Interval,
    Occupancy,
    RecipeDurations,
    absolute_start,
    build_occupancies,
    clip_to_day,
    find_conflicts,
    is_overnight,
    next_free_window,
    overnight_rejection,
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


# —— 夜间发酵（前一日开工）——


def test_absolute_start_prev_day_marker():
    assert absolute_start(23 * 60, True) == -60  # 前一日 23:00
    assert absolute_start(0, True) == -1440  # 前一日 0:00


def test_absolute_start_negative_minutes_passthrough():
    assert absolute_start(-90, False) == -90
    assert absolute_start(-90, True) == -90  # 负分钟已是绝对值，幂等


def test_absolute_start_same_day_unchanged():
    assert absolute_start(9 * 60, False) == 9 * 60
    assert not is_overnight(9 * 60)
    assert is_overnight(-1)


def test_overnight_interval_crosses_midnight():
    occ = build_occupancies(1, 7, -30, RecipeDurations(40, 35))
    assert occ[0].interval == Interval(-30, 10)
    assert occ[1].interval == Interval(10, 45)


def test_overnight_ferment_overlap_same_day_detected():
    # 发酵段跨 0 点，与当日批次重叠必须判冲突：按完整区间，不是当日可见段
    cand = build_occupancies(1, 9, -120, RecipeDurations(600, 60))
    existing = [Occupancy(1, Interval(400, 440), "ferment", 2)]
    hits = find_conflicts(existing, cand)
    assert hits
    assert hits[0][1].phase == "ferment"


def test_overnight_no_conflict_when_intervals_clear():
    cand = build_occupancies(1, 9, -120, RecipeDurations(300, 60))  # [-120,180) [180,240)
    existing = [Occupancy(1, Interval(240, 300), "bake", 2)]
    assert find_conflicts(existing, cand) == []


def test_next_free_window_respects_overnight_full_interval():
    # 夜间批次 0 点前已占炉，窗口仍要从完整区间的结束算起
    existing = [Occupancy(1, Interval(-120, 540), "ferment", 1)]
    w = next_free_window(existing, 1, duration=60, search_from=8 * 60)
    assert w == Interval(540, 600)


def test_overnight_rejection_bake_end_before_open():
    # 前一日 23:00 开工，0:15 就烤完，早于 08:00 开门 → 拒绝
    assert overnight_rejection(-60, RecipeDurations(40, 35)) == "bake_end_before_open"
    # 前一日 22:00 开工，烤到 09:00 → 允许
    assert overnight_rejection(-120, RecipeDurations(600, 60)) is None


def test_overnight_rejection_ignores_same_day():
    assert overnight_rejection(540, RecipeDurations(40, 35)) is None


def test_clip_to_day_keeps_only_after_midnight():
    assert clip_to_day(Interval(-120, 480)) == Interval(0, 480)
    assert clip_to_day(Interval(-120, -30)) is None  # 0 点前已结束，不画
    assert clip_to_day(Interval(60, 120)) == Interval(60, 120)  # 当日段原样保留
