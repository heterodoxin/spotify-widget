from lyrics_overlay.motion import approach, pick_corner, rubber, spring


def test_band_gives_about_half_then_less():
    assert 50 < rubber(100, 1920) < 60
    assert rubber(1000, 1920) < 500
    assert rubber(-100, 1920) == -rubber(100, 1920)
    assert rubber(10**6, 1920) < 1920


def test_slow_short_pull_keeps_the_corner():
    assert pick_corner(False, False, (40, 30), (0, 0), 1920, 1080) == (False, False)


def test_long_pull_switches_both_ways():
    assert pick_corner(False, False, (300, 300), (0, 0), 1920, 1080) == (True, True)


def test_sideways_flick_keeps_the_row():
    assert pick_corner(True, True, (-110, 0), (-2200, 0), 1920, 1080) == (False, True)


def test_upward_flick_keeps_the_column():
    assert pick_corner(False, True, (0, -110), (0, -2200), 1920, 1080) == (False, False)


def test_approach_closes_the_gap_without_passing_it():
    value = 0.0
    for _ in range(200):
        nearer = approach(value, 10.0, 0.01, 9.0)
        assert value <= nearer <= 10.0
        value = nearer
    assert abs(value-10.0) < 0.01


def test_released_spring_overshoots_then_settles_on_target():
    position, velocity, lowest = [0.0, 300.0], [0.0, -900.0], 300.0
    for _ in range(600):
        position, velocity, settled = spring(position, velocity, (0.0, 0.0), 0.007, held=False)
        lowest = min(lowest, position[1])
        if settled:
            break
    assert settled and lowest < 0


def test_held_spring_never_reports_settled():
    assert spring([5.0, 5.0], [0.0, 0.0], (5.0, 5.0), 0.007, held=True)[2] is False
