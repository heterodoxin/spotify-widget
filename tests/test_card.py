import dataclasses
import json

from PySide6.QtCore import QEvent

from spotify_widget import card as card_module
from spotify_widget.card import BUTTONS, HEIGHT, SLIDER_BOTTOM, SLIDER_TOP, SLIDER_X, SPEAKER_Y, WIDTH

from conftest import SONG, mouse


def corner(card):
    return card.home['screen'], card.home['right'], card.home['bottom']


def click(card, at):
    card.mousePressEvent(mouse(QEvent.MouseButtonPress, at))
    card.mouseReleaseEvent(mouse(QEvent.MouseButtonRelease, at))


def test_starts_in_the_top_left_below_the_bar_and_fades_in(rig):
    card, placement, _ = rig
    assert placement.window == (12, 42) and card.fade == 1.0


def test_shows_the_song_and_its_lyrics(rig):
    card, _, _ = rig
    assert (card.title, card.artist, card.length) == ('Song', 'Artist', 200.0)
    assert len(card.lines) == 30 and len(card.rows) == 30


def test_held_card_gives_way_but_resists(rig, drag):
    card, placement, _ = rig
    given, _ = drag(card, placement, 160, 100, 0.5, hold=0.4)
    assert 40 < given[0] < 160 and 25 < given[1] < 100


def test_long_pull_glides_to_the_far_corner_and_is_remembered(rig, drag):
    card, placement, _ = rig
    drag(card, placement, 420, 300, 0.5, hold=0.4)
    assert corner(card) == ('A', True, True)
    assert placement.window == card.anchor() == (1920-12-WIDTH, 1080-12-HEIGHT) and card.target is None
    assert json.loads(card.home_file.read_text()) == card.home
    assert placement.handed_back == 1


def test_flicks_pick_the_corner_in_their_direction(rig, drag):
    card, placement, _ = rig
    drag(card, placement, 420, 300, 0.5, hold=0.4)
    drag(card, placement, -110, 0, 0.05)
    assert corner(card) == ('A', False, True) and placement.window == card.anchor()
    _, path = drag(card, placement, 0, -110, 0.05)
    assert corner(card) == ('A', False, False) and placement.window == card.anchor()
    assert min(y for _, y in path) < card.anchor()[1]


def test_far_pull_snaps_to_the_next_corner_while_still_held(rig, pump):
    card, placement, _ = rig
    x, y = placement.window[0]+60, placement.window[1]+60
    placement.pointer = (x, y)
    card.mousePressEvent(mouse(QEvent.MouseButtonPress))
    for i in range(1, 9):
        placement.pointer = (x+150*i/8, y)
        pump(0.06)
    pump(0.3)
    assert corner(card) == ('A', False, False) and placement.window[0] < 150
    placement.moves.clear()
    for i in range(1, 9):
        placement.pointer = (x+150+250*i/8, y)
        pump(0.06)
    pump(1.2)
    assert card.grab is not None and corner(card) == ('A', True, False)
    assert abs(placement.window[0]-card.anchor()[0]) < 60 and len(set(placement.moves)) > 12
    card.mouseReleaseEvent(mouse(QEvent.MouseButtonRelease))
    pump(1.2)
    assert corner(card) == ('A', True, False) and placement.window == card.anchor() and card.target is None


def test_held_card_can_cross_two_corners_in_one_drag(rig, pump):
    card, placement, _ = rig
    x, y = placement.window[0]+60, placement.window[1]+60
    placement.pointer = (x, y)
    card.mousePressEvent(mouse(QEvent.MouseButtonPress))
    for dx, dy in ((400, 0), (400, 260)):
        placement.pointer = (x+dx, y+dy)
        pump(0.5)
    assert card.grab is not None and corner(card) == ('A', True, True)
    card.mouseReleaseEvent(mouse(QEvent.MouseButtonRelease))
    pump(1.6)
    assert placement.window == card.anchor() == (1920-12-WIDTH, 1080-12-HEIGHT)


def test_small_nudge_springs_back(rig, drag):
    card, placement, _ = rig
    drag(card, placement, 40, 30, 0.5, hold=0.2)
    assert corner(card) == ('A', False, False) and placement.window == (12, 42)


def test_dropping_on_another_screen_takes_its_nearest_corner(rig, drag):
    card, placement, _ = rig
    drag(card, placement, 1900, -200, 0.6, hold=0.1)
    assert corner(card) == ('B', True, True)
    assert placement.window == card.anchor() == (2560-12-WIDTH, 0-12-HEIGHT)


def test_pushing_on_into_another_screen_reaches_its_far_corner(rig, drag):
    card, placement, _ = rig
    drag(card, placement, 1900, -600, 0.6, hold=0.1)
    assert corner(card) == ('B', True, False)
    assert placement.window == card.anchor() == (2560-12-WIDTH, -1440+30+12)


def test_buttons_reach_the_player_without_moving_the_card(rig, pump):
    card, placement, player = rig
    spot = placement.window
    for action in ('PlayPause', 'Next', 'Previous'):
        click(card, BUTTONS[action])
        pump(0.1)
    assert player.commands == ['PlayPause', 'Next', 'Previous']
    assert placement.window == spot and card.grab is None


def test_play_pause_flips_at_once(rig):
    card, _, _ = rig
    was = card.playing
    click(card, BUTTONS['PlayPause'])
    assert card.playing != was


def test_press_that_slides_off_a_button_does_nothing(rig, pump):
    card, _, player = rig
    card.mousePressEvent(mouse(QEvent.MouseButtonPress, BUTTONS['Next']))
    card.mouseReleaseEvent(mouse(QEvent.MouseButtonRelease, (400, 100)))
    pump(0.1)
    assert player.commands == []


def test_slider_sets_volume_and_stops_at_full(rig, pump):
    card, placement, player = rig
    spot = placement.window
    card.mousePressEvent(mouse(QEvent.MouseButtonPress, (SLIDER_X, (SLIDER_TOP+SLIDER_BOTTOM)/2)))
    pump(0.15)
    assert abs(card.volume-0.5) < 0.01 and abs(player.levels[-1]-0.5) < 0.01
    card.mouseMoveEvent(mouse(QEvent.MouseMove, (SLIDER_X-60, SLIDER_TOP-40)))
    card.mouseReleaseEvent(mouse(QEvent.MouseButtonRelease, (SLIDER_X-60, SLIDER_TOP-40)))
    pump(0.15)
    assert card.volume == 1.0 and player.levels[-1] == 1.0 and placement.window == spot and not card.sliding


class Wheel:
    def __init__(self, notches):
        self.notches = notches

    def angleDelta(self):
        notches = self.notches
        return type('Delta', (), {'y': lambda self: notches*120})()


def test_wheel_turns_volume_and_a_burst_is_sent_sparingly(rig, pump):
    card, _, player = rig
    card.wheelEvent(Wheel(-2))
    pump(0.15)
    assert abs(card.volume-0.7) < 0.001 and abs(player.levels[-1]-0.7) < 0.001
    sent = len(player.levels)
    for _ in range(40):
        card.wheelEvent(Wheel(-1))
    pump(0.3)
    assert card.volume == 0.0 and player.levels[-1] == 0.0 and len(player.levels)-sent <= 6


def test_speaker_mutes_and_restores(rig, pump):
    card, _, player = rig
    click(card, (SLIDER_X, SPEAKER_Y))
    pump(0.15)
    assert card.volume == 0.0
    click(card, (SLIDER_X, SPEAKER_Y))
    pump(0.15)
    assert abs(card.volume-0.8) < 0.001 and abs(player.levels[-1]-0.8) < 0.001


def test_player_without_volume_hides_the_slider_and_ignores_the_wheel(rig, pump):
    card, _, player = rig
    player.state = dataclasses.replace(SONG, volume=None)
    pump(2.2)
    assert card.volume is None and card.control_at(mouse(QEvent.MouseMove, (SLIDER_X, SPEAKER_Y)).position()) is None
    card.wheelEvent(Wheel(3))
    assert card.volume is None and player.levels == []


def test_lyrics_ease_to_the_current_line(rig, pump):
    card, _, player = rig
    assert abs(card.focus) < 0.05
    player.state = dataclasses.replace(SONG, position=2.5)
    for _ in range(200):
        if card.position == 2.5:
            break
        pump(0.01)
    pump(0.08)
    assert 0.05 < card.focus < 0.95
    pump(0.8)
    assert abs(card.focus-1) < 0.05


def test_song_change_resets_and_player_going_away_clears(rig, pump):
    card, _, player = rig
    player.state = dataclasses.replace(SONG, track_id='t2', title='Other')
    pump(2.2)
    assert card.title == 'Other' and card.old_title == 'Song' and card.blend == 1.0
    player.state = None
    pump(2.2)
    assert card.track is None and card.status == card_module.HINT and (card.title or card_module.IDLE) == 'Nothing playing' and not card.playing and card.lines == []


def test_hide_fades_out_and_show_returns_to_the_corner(rig, pump):
    card, placement, _ = rig
    card.set_shown(False)
    pump(0.06)
    assert 0 < card.fade < 1
    pump(0.4)
    assert not card.isVisible()
    placement.window = None
    card.set_shown(True)
    pump(0.5)
    assert card.isVisible() and card.fade == 1.0 and placement.window == card.anchor()
