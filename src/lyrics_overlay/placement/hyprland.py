"""Hyprland: a native Wayland window that the compositor moves over its socket."""
import json
import os
import socket

from PySide6.QtCore import Qt

from lyrics_overlay.placement.base import Monitor, Placement


def request(command):
    """Send one command to Hyprland and return its reply."""
    path = f"{os.environ['XDG_RUNTIME_DIR']}/hypr/{os.environ['HYPRLAND_INSTANCE_SIGNATURE']}/.socket.sock"
    with socket.socket(socket.AF_UNIX) as sock:
        sock.connect(path)
        sock.sendall(command.encode())
        reply = b''
        while chunk := sock.recv(65536):
            reply += chunk
    return reply.decode()


class HyprlandPlacement(Placement):
    flags = Qt.FramelessWindowHint

    def __init__(self):
        self.address = None
        self.lua = True
        self.last_active = ''

    def monitors(self):
        result = {}
        for m in json.loads(request('j/monitors')):
            left, top, right, bottom = m['reserved']
            result[m['name']] = Monitor(m['x'], m['y'], m['width']/m['scale'], m['height']/m['scale'], left, top, right, bottom)
        return result

    def focused(self):
        return next((m['name'] for m in json.loads(request('j/monitors')) if m['focused']), '')

    def cursor(self):
        point = json.loads(request('j/cursorpos'))
        return float(point['x']), float(point['y'])

    def attach(self, widget):
        mine = [c for c in json.loads(request('j/clients')) if c['pid'] == os.getpid() and c['mapped']]
        if not mine:
            return False
        self.address = mine[0]['address']
        # Hyprland with a Lua config takes Lua dispatchers, older ones take the classic syntax.
        x, y = mine[0]['at']
        self.lua = request(self.lua_move(x, y)).strip() == 'ok'
        return True

    def detach(self):
        self.address = None

    def lua_move(self, x, y):
        return f"/dispatch hl.dsp.window.move({{ x = {x}, y = {y}, window = 'address:{self.address}' }})"

    def move(self, x, y):
        if self.address is None:
            return
        if self.lua:
            request(self.lua_move(x, y))
        else:
            request(f'/dispatch movewindowpixel exact {x} {y},address:{self.address}')

    def tick(self):
        active = json.loads(request('j/activewindow')).get('address', '')
        if active and active != self.address:
            self.last_active = active

    def released(self):
        # Clicking the card focused it, so the keyboard goes back to the window that had it.
        if not self.last_active:
            return
        if self.lua:
            request(f"/dispatch hl.dsp.focus({{ window = 'address:{self.last_active}' }})")
        else:
            request(f'/dispatch focuswindow address:{self.last_active}')
