import os
import time

import pytest

os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from lyrics_overlay import card as card_module
from lyrics_overlay import lyrics
from lyrics_overlay.placement.base import Monitor, Placement
from lyrics_overlay.players.base import Player, State


class FakePlacement(Placement):
    """Two screens, one above the other, with a 30px bar along the top of each."""
    flags = Qt.FramelessWindowHint

    def __init__(self):
        self.screens = {'A': Monitor(0, 0, 1920, 1080, 0, 30, 0, 0), 'B': Monitor(0, -1440, 2560, 1440, 0, 30, 0, 0)}
        self.pointer = (0.0, 0.0)
        self.window = None
        self.moves = []
        self.handed_back = 0

    def monitors(self):
        return self.screens

    def focused(self):
        return 'A'

    def cursor(self):
        return self.pointer

    def attach(self, widget):
        return True

    def move(self, x, y):
        self.window = (x, y)
        self.moves.append((x, y))

    def released(self):
        self.handed_back += 1


class FakePlayer(Player):
    def __init__(self):
        self.state = None
        self.commands = []
        self.levels = []

    def poll(self):
        return self.state

    def command(self, action):
        self.commands.append(action)

    def set_volume(self, level):
        self.levels.append(level)


SONG = State(track_id='t1', title='Song', artist='Artist', album='Album', length=200.0, position=0.5,
             playing=False, volume=0.8, art=None)


@pytest.fixture(scope='session')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def pump(app):
    def run(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.002)
    return run


@pytest.fixture
def rig(app, pump, tmp_path, monkeypatch):
    """A card on fake screens with a fake player, already faded in and showing a song."""
    monkeypatch.setattr(card_module, 'config_dir', lambda: tmp_path)
    monkeypatch.setattr(lyrics, 'fetch', lambda *song: ([(i*2.0, f'line {i}') for i in range(30)], ''))
    monkeypatch.setattr(lyrics, 'cover', lambda source: None)
    placement, player = FakePlacement(), FakePlayer()
    player.state = SONG
    card = card_module.Card(player, placement)
    pump(1.4)
    yield card, placement, player
    card.timer.stop()
    card.close()


def mouse(kind, at=(60, 60)):
    held = Qt.NoButton if kind == QEvent.MouseButtonRelease else Qt.LeftButton
    return QMouseEvent(kind, QPointF(*at), QPointF(*at), Qt.LeftButton, held, Qt.NoModifier)


@pytest.fixture
def drag(pump):
    def run(card, placement, dx, dy, seconds, hold=0.0, steps=8):
        """Pull the card by (dx, dy) and return how far it had given before release, and its path after."""
        start = placement.window
        x, y = start[0]+60, start[1]+60
        placement.pointer = (x, y)
        card.mousePressEvent(mouse(QEvent.MouseButtonPress))
        for i in range(1, steps+1):
            placement.pointer = (x+dx*i/steps, y+dy*i/steps)
            pump(seconds/steps)
        pump(hold)
        given = (placement.window[0]-start[0], placement.window[1]-start[1])
        placement.moves.clear()
        card.mouseReleaseEvent(mouse(QEvent.MouseButtonRelease))
        pump(1.6)
        return given, list(placement.moves)
    return run
