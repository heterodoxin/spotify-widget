"""How the card learns about screens and gets moved around them."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Monitor:
    x: float
    y: float
    w: float
    h: float
    left: float
    top: float
    right: float
    bottom: float

    def contains(self, x, y):
        return self.x <= x < self.x+self.w and self.y <= y < self.y+self.h


class Placement:
    """Screen geometry, pointer position and window movement for one windowing system."""

    def monitors(self):
        """Return {name: Monitor}, with the edges of each screen that bars and docks take."""
        raise NotImplementedError

    def focused(self):
        """Return the name of the screen in use right now."""
        raise NotImplementedError

    def cursor(self):
        """Return the pointer position in the same coordinates as the monitors."""
        raise NotImplementedError

    def attach(self, widget):
        """Take hold of the shown window and return True once it can be moved."""
        raise NotImplementedError

    def detach(self):
        """Forget the window after it is hidden."""

    def move(self, x, y):
        raise NotImplementedError

    def tick(self):
        """Run once a second for bookkeeping."""

    def released(self):
        """Run after a click or drag on the card ends."""
