"""The floating card: what it draws, how it moves and what its controls do."""
import bisect
import json
import time
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
                           QPolygonF)
from PySide6.QtWidgets import QWidget

from spotify_widget import lyrics
from spotify_widget.colors import NEUTRAL, mix, tint
from spotify_widget.motion import approach, pick_corner, rubber, spring
from spotify_widget.paths import config_dir

WIDTH, HEIGHT, PAD, ART, GAP, RADIUS, MARGIN, LINE_GAP = 680, 326, 24, 150, 28, 12, 12, 10
FONTS = ['Inter', 'SF Pro Display', 'Segoe UI', 'Noto Sans', 'Helvetica Neue', 'Arial']
GREEN = '#1ed760'
BUTTONS = {'Previous': (PAD+ART/2-46, 287), 'PlayPause': (PAD+ART/2, 287), 'Next': (PAD+ART/2+46, 287)}
SLIDER_X, SLIDER_TOP, SLIDER_BOTTOM, SPEAKER_Y = WIDTH-20, PAD+8, HEIGHT-PAD-30, HEIGHT-PAD-7
IDLE, HINT, WAITING = 'Nothing playing', 'Play a song in Spotify to see its lyrics here', 'Loading lyrics…'


def font(size, weight=QFont.Normal):
    face = QFont()
    face.setFamilies(FONTS)
    face.setPointSizeF(size)
    face.setWeight(weight)
    return face


class Card(QWidget):
    def __init__(self, player, placement):
        super().__init__()
        self.player, self.placement = player, placement
        self.pool = ThreadPoolExecutor(max_workers=4)
        self.setWindowTitle('Spotify Widget')
        self.setWindowFlags(placement.flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.OpenHandCursor)
        self.setMouseTracking(True)
        self.resize(WIDTH, HEIGHT)

        self.track = None
        self.lines, self.times, self.rows = [], [], []
        self.status = HINT
        self.title = self.old_title = ''
        self.artist = self.old_artist = ''
        self.length = 0.0
        self.art = self.old_art = None
        self.tint = self.old_tint = QColor(NEUTRAL)
        self.blend = 1.0
        self.position, self.observed, self.playing = 0.0, time.monotonic(), False
        self.poll = self.fetch = self.art_job = None
        self.polled = 0.0
        self.focus, self.scroll = -1.0, 0.0

        self.volume = None
        self.unmuted = 1.0
        self.sliding = False
        self.volume_unsent, self.volume_sent, self.volume_hold = False, 0.0, 0.0
        self.seeking, self.seek_hold = None, 0.0
        self.hover = self.pressed = None

        self.enabled, self.fade, self.attached = True, 0.0, False
        self.monitors = {}
        self.home_file = config_dir() / 'home.json'
        self.home = {'screen': '', 'right': False, 'bottom': False}
        try:
            self.home.update(json.loads(self.home_file.read_text(encoding='utf-8')))
        except (OSError, ValueError):
            pass
        self.grab, self.origin, self.trail, self.flying = None, (0.0, 0.0), [], False
        self.at, self.velocity, self.target, self.sent = [0.0, 0.0], [0.0, 0.0], None, None

        self.read_monitors()
        self.show()
        self.last_frame, self.last_paint = time.monotonic(), 0.0
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self.frame)
        self.timer.start(7)

    # Placement.

    def read_monitors(self):
        try:
            self.monitors = self.placement.monitors()
            if self.home['screen'] not in self.monitors:
                self.home['screen'] = self.placement.focused()
        except (OSError, ValueError, KeyError):
            pass

    def home_monitor(self):
        return self.monitors.get(self.home['screen']) or next(iter(self.monitors.values()), None)

    def anchor(self):
        """The home corner, a margin inside the screen and clear of its bars."""
        m = self.home_monitor()
        if m is None:
            return None
        x = m.x+m.w-m.right-MARGIN-self.width() if self.home['right'] else m.x+m.left+MARGIN
        y = m.y+m.h-m.bottom-MARGIN-self.height() if self.home['bottom'] else m.y+m.top+MARGIN
        return round(x), round(y)

    def place(self, x, y):
        if not self.attached or (x, y) == self.sent:
            return
        try:
            self.placement.move(x, y)
            self.sent = (x, y)
        except OSError:
            pass

    def rest(self):
        anchor = self.anchor()
        if anchor is not None and self.grab is None and self.target is None:
            self.at = [float(anchor[0]), float(anchor[1])]
            self.place(*anchor)

    def toggle(self):
        self.set_shown(not self.enabled)

    def set_shown(self, shown):
        self.enabled = shown
        self.last_frame = time.monotonic()
        self.timer.setInterval(7)
        if shown:
            self.show()

    # Pointer.

    def control_at(self, point):
        for action, (x, y) in BUTTONS.items():
            if abs(point.x()-x) <= 18 and abs(point.y()-y) <= 18:
                return action
        if self.length > 0 and PAD-6 <= point.x() <= PAD+ART+6 and abs(point.y()-self.bar_top()-2) <= 9:
            return 'Seek'
        if self.volume is not None and abs(point.x()-SLIDER_X) <= 13:
            if abs(point.y()-SPEAKER_Y) <= 11:
                return 'Mute'
            if SLIDER_TOP-8 <= point.y() <= SLIDER_BOTTOM+6:
                return 'Volume'
        return None

    def change_volume(self, level):
        self.volume = max(0.0, min(1.0, level))
        self.volume_unsent, self.volume_hold = True, time.monotonic() + 1.5
        self.timer.setInterval(7)
        self.update()

    def seek_to(self, x):
        """Show the song as if it were at the point under the pointer, until release sends it."""
        self.seeking = max(0.0, min(self.length-1, (x-PAD)/ART*self.length))
        self.timer.setInterval(7)
        self.update()

    def control(self, action):
        if action == 'Mute':
            if self.volume > 0:
                self.unmuted = self.volume
            self.change_volume(0.0 if self.volume > 0 else self.unmuted or 0.5)
            return
        if action == 'PlayPause':
            # The icon flips at once and the next poll confirms it.
            self.position, self.observed, self.playing = self.now(), time.monotonic(), not self.playing
        self.pool.submit(self.player.command, action)
        self.polled = time.monotonic() - 0.7

    def released(self):
        try:
            self.placement.released()
        except (OSError, ValueError):
            pass

    def wheelEvent(self, event):
        if self.volume is not None:
            self.change_volume(self.volume + event.angleDelta().y()/120*0.05)

    def mouseMoveEvent(self, event):
        if self.sliding:
            self.change_volume((SLIDER_BOTTOM-event.position().y())/(SLIDER_BOTTOM-SLIDER_TOP))
            return
        if self.seeking is not None:
            self.seek_to(event.position().x())
            return
        hover = self.control_at(event.position()) if self.grab is None else None
        if hover != self.hover:
            self.hover = hover
            self.setCursor(Qt.PointingHandCursor if hover else Qt.ClosedHandCursor if self.grab else Qt.OpenHandCursor)
            self.update()

    def leaveEvent(self, event):
        if self.hover is not None:
            self.hover = None
            self.update()

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or not self.attached:
            return
        self.pressed = self.control_at(event.position())
        if self.pressed == 'Volume':
            self.pressed, self.sliding = None, True
            self.mouseMoveEvent(event)
            return
        if self.pressed == 'Seek':
            self.pressed = None
            self.seek_to(event.position().x())
            return
        if self.pressed:
            self.update()
            return
        try:
            self.grab = self.placement.cursor()
        except (OSError, ValueError, KeyError):
            return
        self.origin, self.flying = tuple(self.at), False
        self.trail = [(time.monotonic(), *self.grab)]
        self.setCursor(Qt.ClosedHandCursor)
        self.last_frame = time.monotonic()
        self.timer.setInterval(7)

    def pull(self):
        """Aim the card at where the hand is, less the give of the band tying it to its corner."""
        try:
            point = self.placement.cursor()
        except (OSError, ValueError, KeyError):
            return
        now = time.monotonic()
        self.trail = [sample for sample in self.trail if now-sample[0] <= 0.1] + [(now, *point)]
        home = self.aim(0.0)
        if home != self.home:
            # Pulled past its reach, the band lets go and takes hold again from the new corner on the side that gave.
            moved = [home['screen'] != self.home['screen'] or home[side] != self.home[side] for side in ('right', 'bottom')]
            self.home, self.flying = home, True
            self.grab = tuple(point[a] if moved[a] else self.grab[a] for a in (0, 1))
            self.origin = tuple(float(self.anchor()[a]) if moved[a] else self.origin[a] for a in (0, 1))
        m = self.home_monitor()
        self.target = (self.origin[0] + rubber(point[0]-self.grab[0], m.w), self.origin[1] + rubber(point[1]-self.grab[1], m.h))

    def throw(self):
        """The hand's speed over the last tenth of a second."""
        (t0, x0, y0), (t1, x1, y1) = self.trail[0], self.trail[-1]
        return ((x1-x0)/(t1-t0), (y1-y0)/(t1-t0)) if t1-t0 >= 0.02 else (0.0, 0.0)

    def aim(self, carry):
        """The screen and corner the hand is heading for, counting carry seconds of its speed."""
        _, x, y = self.trail[-1]
        name = next((key for key, m in self.monitors.items() if m.contains(x, y)), self.home['screen'])
        m = self.monitors.get(name) or self.home_monitor()
        if name == self.home['screen']:
            pulled = (x-self.grab[0], y-self.grab[1])
            right, bottom = pick_corner(self.home['right'], self.home['bottom'], pulled, self.throw(), m.w, m.h, carry)
        else:
            # On another screen the card takes the corner nearest the hand, nudged by the throw.
            right, bottom = pick_corner(x > m.x+m.w/2, y > m.y+m.h/2, (0, 0), self.throw(), m.w, m.h, carry)
        return {'screen': name, 'right': right, 'bottom': bottom}

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if self.seeking is not None:
            # The card jumps at once and polls are ignored until the player has caught up.
            self.position, self.observed, self.seeking = self.seeking, time.monotonic(), None
            self.seek_hold = time.monotonic() + 1.0
            self.pool.submit(self.player.seek, self.position)
            self.released()
            self.update()
            return
        if self.sliding or self.pressed:
            action, self.pressed, self.sliding = self.pressed, None, False
            if action and self.control_at(event.position()) == action:
                self.control(action)
            self.released()
            self.update()
            return
        if self.grab is None:
            return
        self.read_monitors()
        self.pull()
        throw, self.home = self.throw(), self.aim(0.05)
        self.grab, self.flying = None, False
        self.setCursor(Qt.OpenHandCursor)
        self.velocity = [self.velocity[a] + max(-2500.0, min(2500.0, throw[a]*0.35)) for a in (0, 1)]
        self.target = tuple(float(v) for v in self.anchor())
        try:
            self.home_file.write_text(json.dumps(self.home), encoding='utf-8')
        except OSError:
            pass
        self.released()

    # Frames.

    def frame(self):
        now = time.monotonic()
        dt = min(now-self.last_frame, 0.05)
        self.last_frame = now
        moving = gliding = False

        if self.isVisible() and not self.attached:
            try:
                self.attached = self.placement.attach(self)
            except (OSError, ValueError, KeyError):
                self.attached = False
            if self.attached:
                self.sent = None
                self.rest()
        if self.volume_unsent and now-self.volume_sent >= 0.06:
            self.volume_unsent, self.volume_sent = False, now
            self.pool.submit(self.player.set_volume, self.volume)
        moving |= self.volume_unsent or self.sliding or self.seeking is not None
        if self.grab is not None:
            self.pull()
        if self.target is not None:
            # A held card follows stiffly, a freed or just-snapped one glides.
            stiff = self.grab is not None and not self.flying
            self.at, self.velocity, settled = spring(self.at, self.velocity, self.target, dt, stiff)
            self.flying = self.flying and not settled
            if settled and self.grab is None:
                self.at, self.velocity, self.target = list(self.target), [0.0, 0.0], None
            self.place(round(self.at[0]), round(self.at[1]))
            gliding = True

        shown = self.enabled and self.attached
        if self.fade != (1.0 if shown else 0.0):
            self.fade = max(0.0, min(1.0, self.fade + (dt if shown else -dt)/0.16))
            moving = True
            if self.fade == 0.0 and not self.enabled:
                self.hide()
                self.placement.detach()
                self.attached = False
        if self.blend < 1.0:
            self.blend = min(1.0, self.blend + dt/0.45)
            moving = True

        self.update_playback(now)
        index = bisect.bisect_right(self.times, self.now())-1
        if abs(self.focus-index) > 0.002:
            self.focus = approach(self.focus, index, dt, 9.0) if abs(self.focus-index) < 3 else float(index)
            moving = True
        goal = self.scroll_goal(index)
        if abs(self.scroll-goal) > 0.2:
            self.scroll = approach(self.scroll, goal, dt, 8.0) if abs(self.scroll-goal) < 400 else goal
            moving = True

        # Full rate only while something moves, and a repaint only when what the card shows changed.
        self.timer.setInterval(7 if moving or gliding or self.grab is not None else 40)
        if self.isVisible() and (moving or now-self.last_paint >= 0.25):
            self.last_paint = now
            self.update()

    def update_playback(self, now):
        if self.poll is None and now-self.polled >= 1:
            self.polled = now
            self.poll = self.pool.submit(self.player.poll)
            self.read_monitors()
            try:
                self.placement.tick()
            except (OSError, ValueError):
                pass
            if self.target is None and self.grab is None:
                self.rest()
        elif self.poll is not None and self.poll.done():
            try:
                state = self.poll.result()
            except Exception:
                state = None
            self.poll = None
            if state is None:
                if self.track is not None:
                    self.change_track(None, '', '', 0.0)
                self.status, self.playing, self.volume = HINT, False, None
            else:
                self.playing = state.playing
                if time.monotonic() >= self.seek_hold and self.seeking is None:
                    self.position, self.observed = state.position, time.monotonic()
                if time.monotonic() >= self.volume_hold:
                    self.volume = state.volume
                if state.track_id != self.track:
                    self.change_track(state.track_id, state.title, state.artist, state.length)
                    self.status = WAITING
                    self.fetch = (state.track_id, self.pool.submit(lyrics.fetch, state.title, state.artist, state.album, state.length))
                    self.art_job = (state.track_id, self.pool.submit(lyrics.cover, state.art))
        if self.fetch and self.fetch[1].done():
            track, future = self.fetch
            self.fetch = None
            if track == self.track:
                try:
                    self.lines, self.status = future.result()
                except Exception:
                    self.lines, self.status = [], 'Lyrics are unavailable right now'
                self.lay_out()
        if self.art_job and self.art_job[1].done():
            track, future = self.art_job
            self.art_job = None
            if track == self.track:
                try:
                    pixmap = QPixmap(future.result() or '')
                except Exception:
                    pixmap = QPixmap()
                if not pixmap.isNull():
                    # The cover arrives after the song changes, so it cross-fades in with its colour.
                    self.old_art, self.old_tint = self.art, self.shown_tint()
                    self.old_title, self.old_artist = self.title, self.artist
                    self.art, self.tint, self.blend = pixmap, tint(pixmap), 0.0

    def change_track(self, track, title, artist, length):
        self.old_art, self.old_tint = self.art, self.shown_tint()
        self.old_title, self.old_artist = self.title, self.artist
        self.track, self.title, self.artist, self.length = track, title, artist, length
        self.art, self.tint, self.blend = None, QColor(NEUTRAL), 0.0
        self.lines = []
        self.lay_out()

    def shown_tint(self):
        return mix(self.old_tint, self.tint, self.blend)

    def now(self):
        if self.seeking is not None:
            return self.seeking
        return self.position + (time.monotonic()-self.observed if self.playing else 0)

    # Lyrics.

    def lyric_font(self):
        face = font(16, QFont.Bold)
        face.setLetterSpacing(QFont.AbsoluteSpacing, -0.3)
        return face

    def lyric_width(self):
        return self.width() - (PAD+ART+GAP) - PAD - 22

    def lay_out(self):
        """Wrap every line of the song once, so scrolling is only a matter of an offset."""
        metrics = QFontMetricsF(self.lyric_font())
        self.rows, top = [], 0.0
        self.times = [start for start, _ in self.lines]
        for _, words in self.lines:
            text = words or '· · ·'
            bounds = metrics.boundingRect(QRectF(0, 0, self.lyric_width(), 2000), Qt.TextWordWrap | Qt.AlignLeft, text)
            height = max(bounds.height(), metrics.lineSpacing())
            self.rows.append((top, height, text))
            top += height + LINE_GAP
        self.focus, self.scroll = -1.0, self.scroll_goal(-1)

    def scroll_goal(self, index):
        """The offset that puts the middle of the current line in the middle of the card."""
        if not self.rows:
            return 0.0
        top, height, _ = self.rows[max(0, min(index, len(self.rows)-1))]
        low, high = self.scroll_range()
        return max(low, min(high, top + height/2))

    def scroll_range(self):
        """The offsets that rest the first line at the top of the card and the last line at its bottom."""
        top, height, _ = self.rows[-1]
        low = self.height()/2 - PAD
        return low, max(low, top + height - self.height()/2 + PAD)

    def bar_top(self):
        """Where the progress bar sits, under the song's name and artist."""
        names = QFontMetricsF(font(12, QFont.Bold)).height() + 1 + QFontMetricsF(font(10, QFont.Medium)).height()
        return PAD + ART + 14 + names + 12

    # Painting.

    def paint_lyrics(self, painter, left, alpha):
        width, height = self.lyric_width(), self.height()
        if not self.rows:
            painter.setFont(font(13, QFont.DemiBold))
            painter.setPen(QColor(255, 255, 255, round(170*alpha)))
            painter.drawText(QRectF(left, 0, width, height), Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap, self.status)
            return
        # The lines get their own layer so the top and bottom can melt into the card.
        ratio = self.devicePixelRatioF()
        layer = QImage(round(width*ratio), round(height*ratio), QImage.Format_ARGB32_Premultiplied)
        layer.setDevicePixelRatio(ratio)
        layer.fill(Qt.transparent)
        ink = QPainter(layer)
        ink.setRenderHint(QPainter.Antialiasing)
        ink.setRenderHint(QPainter.TextAntialiasing)
        ink.setFont(self.lyric_font())
        sung, coming, current = QColor(255, 255, 255, 140), QColor(0, 0, 0, 135), QColor(255, 255, 255, 255)
        for i, (top, line_height, text) in enumerate(self.rows):
            y = top - self.scroll + height/2
            if y + line_height < 0 or y > height:
                continue
            nearness = max(0.0, 1.0-abs(i-self.focus))
            ink.setPen(mix(sung if i < self.focus else coming, current, nearness))
            ink.drawText(QRectF(0, y, width, line_height), Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop, text)
        ink.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        edge = QLinearGradient(0, 0, 0, height)
        soft = 46/height
        # An edge melts away only when there are lines beyond it.
        low, high = self.scroll_range()
        above, below = min(1.0, (self.scroll-low)/46), min(1.0, (high-self.scroll)/46)
        for stop, opacity in ((0, round(255*(1-max(0.0, above)))), (soft, 255), (1-soft, 255), (1, round(255*(1-max(0.0, below))))):
            edge.setColorAt(stop, QColor(0, 0, 0, opacity))
        ink.fillRect(QRectF(0, 0, width, height), edge)
        ink.end()
        painter.setOpacity(alpha)
        painter.drawImage(QPoint(int(left), 0), layer)

    def paint_buttons(self, painter):
        painter.setPen(Qt.NoPen)
        for action, (x, y) in BUTTONS.items():
            size = 0.92 if self.pressed == action else 1.07 if self.hover == action else 1.0
            painter.save()
            painter.translate(x, y)
            painter.scale(size, size)
            shape = QPainterPath()
            if action == 'PlayPause':
                painter.setBrush(QColor(255, 255, 255))
                painter.drawEllipse(QRectF(-16, -16, 32, 32))
                painter.setBrush(QColor(0, 0, 0))
                if self.playing:
                    shape.addRoundedRect(QRectF(-5.5, -6, 4, 12), 1, 1)
                    shape.addRoundedRect(QRectF(1.5, -6, 4, 12), 1, 1)
                else:
                    shape.addPolygon(QPolygonF([QPointF(-3.5, -6.5), QPointF(-3.5, 6.5), QPointF(6.5, 0)]))
            else:
                # One skip arrow, mirrored for going back.
                if action == 'Previous':
                    painter.scale(-1, 1)
                painter.setBrush(QColor(255, 255, 255, 255 if self.hover == action else 178))
                shape.addPolygon(QPolygonF([QPointF(-6.5, -6.5), QPointF(-6.5, 6.5), QPointF(3.5, 0)]))
                shape.addRoundedRect(QRectF(4, -6.5, 2.6, 13), 1, 1)
            painter.drawPath(shape)
            painter.restore()

    def paint_volume(self, painter):
        if self.volume is None:
            return
        active = self.sliding or self.hover in ('Volume', 'Mute')
        white = QColor(255, 255, 255, 255 if active else 120)
        x, y = SLIDER_X-1, SPEAKER_Y
        painter.setPen(Qt.NoPen)
        painter.setBrush(white)
        speaker = QPainterPath()
        speaker.addPolygon(QPolygonF([QPointF(x-7, y-2.5), QPointF(x-4, y-2.5), QPointF(x, y-6), QPointF(x, y+6),
                                      QPointF(x-4, y+2.5), QPointF(x-7, y+2.5)]))
        painter.drawPath(speaker)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(white, 1.6, Qt.SolidLine, Qt.RoundCap))
        if self.volume <= 0:
            painter.drawLine(QPointF(x+3, y-3), QPointF(x+8, y+3))
            painter.drawLine(QPointF(x+8, y-3), QPointF(x+3, y+3))
        else:
            painter.drawArc(QRectF(x-2.5, y-3.5, 7, 7), -55*16, 110*16)
            if self.volume > 0.5:
                painter.drawArc(QRectF(x-4.5, y-6.5, 13, 13), -55*16, 110*16)
        painter.setPen(Qt.NoPen)
        length = SLIDER_BOTTOM - SLIDER_TOP
        level = SLIDER_BOTTOM - length*self.volume
        painter.setBrush(QColor(255, 255, 255, 70 if active else 40))
        painter.drawRoundedRect(QRectF(SLIDER_X-2, SLIDER_TOP, 4, length), 2, 2)
        painter.setBrush(QColor(GREEN) if active else QColor(255, 255, 255, 150))
        painter.drawRoundedRect(QRectF(SLIDER_X-2, level, 4, SLIDER_BOTTOM-level), 2, 2)
        if active:
            painter.setBrush(QColor(255, 255, 255))
            painter.drawEllipse(QPointF(SLIDER_X, level), 5.5, 5.5)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        # Showing and hiding fades the card while it grows the last few percent.
        ease = 1 - (1-self.fade)**3
        scale = 0.96 + 0.04*ease
        painter.translate(self.width()/2, self.height()/2)
        painter.scale(scale, scale)
        painter.translate(-self.width()/2, -self.height()/2)
        painter.setOpacity(ease)
        white = lambda alpha=255: QColor(255, 255, 255, alpha)
        turn = self.blend*self.blend*(3-2*self.blend)

        card = QPainterPath()
        card.addRoundedRect(QRectF(0, 0, self.width(), self.height()), RADIUS, RADIUS)
        painter.fillPath(card, mix(self.old_tint, self.tint, turn))
        shade = QLinearGradient(0, 0, 0, self.height())
        shade.setColorAt(0, QColor(0, 0, 0, 0))
        shade.setColorAt(1, QColor(0, 0, 0, 70))
        painter.fillPath(card, shade)

        art = QRectF(PAD, PAD, ART, ART)
        for spread, alpha in ((8, 14), (5, 22), (2, 34)):
            shadow = QPainterPath()
            shadow.addRoundedRect(art.adjusted(-spread, -spread+4, spread, spread+4), 6+spread, 6+spread)
            painter.fillPath(shadow, QColor(0, 0, 0, alpha))
        clip = QPainterPath()
        clip.addRoundedRect(art, 6, 6)
        painter.save()
        painter.setClipPath(clip)
        for pixmap, alpha in ((self.old_art, 1.0), (self.art, turn)):
            if alpha <= 0:
                continue
            painter.setOpacity(ease*alpha)
            if pixmap is not None:
                side = min(pixmap.width(), pixmap.height())
                painter.drawPixmap(art, pixmap, QRectF((pixmap.width()-side)/2, (pixmap.height()-side)/2, side, side))
            else:
                painter.fillPath(clip, QColor('#282828'))
                painter.setPen(white(110))
                painter.setFont(font(34))
                painter.drawText(art, Qt.AlignCenter, '♪')
        painter.restore()

        y = PAD + ART + 14
        title_font, artist_font = font(12, QFont.Bold), font(10, QFont.Medium)
        title_metrics, artist_metrics = QFontMetricsF(title_font), QFontMetricsF(artist_font)
        names = [(self.old_title, self.old_artist, 1-turn), (self.title, self.artist, turn)]
        if (self.old_title, self.old_artist) == (self.title, self.artist):
            names = [(self.title, self.artist, 1.0)]
        for title, artist, alpha in names:
            if alpha <= 0:
                continue
            painter.setFont(title_font)
            painter.setPen(white(round(255*alpha)))
            painter.drawText(QRectF(PAD, y, ART, title_metrics.height()), Qt.AlignLeft | Qt.AlignVCenter,
                             title_metrics.elidedText(title or IDLE, Qt.ElideRight, ART))
            painter.setFont(artist_font)
            painter.setPen(white(round(178*alpha)))
            painter.drawText(QRectF(PAD, y+title_metrics.height()+1, ART, artist_metrics.height()),
                             Qt.AlignLeft | Qt.AlignVCenter, artist_metrics.elidedText(artist, Qt.ElideRight, ART))
        y = self.bar_top()
        seeking = self.seeking is not None or self.hover == 'Seek'

        painter.setPen(Qt.NoPen)
        painter.setBrush(white(70))
        painter.drawRoundedRect(QRectF(PAD, y, ART, 4), 2, 2)
        elapsed = max(0.0, min(self.length, self.now())) if self.length > 0 else 0.0
        if self.length > 0:
            painter.setBrush(QColor(GREEN) if seeking else white() if self.playing else white(150))
            painter.drawRoundedRect(QRectF(PAD, y, max(4.0, ART*elapsed/self.length), 4), 2, 2)
            if seeking:
                painter.setBrush(white())
                painter.drawEllipse(QPointF(PAD+ART*elapsed/self.length, y+2), 5.5, 5.5)
        clock = lambda seconds: f'{int(seconds)//60}:{int(seconds)%60:02d}'
        time_font = font(8, QFont.Medium)
        painter.setFont(time_font)
        painter.setPen(white(178))
        times = QRectF(PAD, y+9, ART, QFontMetricsF(time_font).height())
        painter.drawText(times, Qt.AlignLeft | Qt.AlignVCenter, clock(elapsed))
        painter.drawText(times, Qt.AlignRight | Qt.AlignVCenter, clock(self.length))

        self.paint_buttons(painter)
        self.paint_volume(painter)
        self.paint_lyrics(painter, PAD+ART+GAP, ease)
