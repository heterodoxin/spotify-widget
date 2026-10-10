"""The card's colour, taken from the album art."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

NEUTRAL = '#535353'


def mix(a, b, t):
    return QColor(round(a.red()+(b.red()-a.red())*t), round(a.green()+(b.green()-a.green())*t),
                  round(a.blue()+(b.blue()-a.blue())*t), round(a.alpha()+(b.alpha()-a.alpha())*t))


def tint(pixmap):
    """The cover's dominant hue, held dark enough for white text, or grey for a colourless cover."""
    image = pixmap.scaled(32, 32, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).toImage()
    buckets = {}
    for x in range(image.width()):
        for y in range(image.height()):
            color = image.pixelColor(x, y)
            hue, sat, val = color.hsvHueF(), color.hsvSaturationF(), color.valueF()
            if hue < 0 or sat < 0.18 or val < 0.15:
                continue
            bucket = buckets.setdefault(int(hue*18), [0.0, 0.0, 0.0, 0.0])
            weight = sat*val
            bucket[0] += weight
            bucket[1] += hue*weight
            bucket[2] += sat*weight
            bucket[3] += val*weight
    if not buckets:
        return QColor(NEUTRAL)
    weight, hue, sat, val = max(buckets.values(), key=lambda b: b[0])
    if weight < 12:
        return QColor(NEUTRAL)
    return QColor.fromHsvF(hue/weight, max(0.35, min(0.72, sat/weight)), max(0.30, min(0.50, val/weight)))
