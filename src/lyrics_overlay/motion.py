"""The physics of dragging the card and letting it go."""
import math


def rubber(distance, room):
    """How far the card gives when pulled: about half at first, then less and less."""
    return math.copysign((1 - 1/(abs(distance)*0.55/room + 1))*room, distance)


def pick_corner(right, bottom, pull, velocity, width, height):
    """The corner a release lands in: where the pull and its momentum were heading."""
    reach_x = min(width*0.12, 320)
    reach_y = min(height*0.14, 200)
    aim_x = pull[0] + velocity[0]*0.18
    aim_y = pull[1] + velocity[1]*0.18
    if abs(aim_x) >= reach_x:
        right = aim_x > 0
    if abs(aim_y) >= reach_y:
        bottom = aim_y > 0
    return right, bottom


def approach(value, target, dt, rate):
    """Ease value toward target, covering the same share of the gap per unit of time."""
    return target + (value-target)*math.exp(-dt*rate)


def spring(position, velocity, target, dt, held):
    """Advance a damped spring one frame and return (position, velocity, settled)."""
    stiffness, damping = (520.0, 40.0) if held else (190.0, 21.0)
    steps = max(1, int(dt/0.004))
    step = dt/steps
    position, velocity = list(position), list(velocity)
    for _ in range(steps):
        for axis in (0, 1):
            force = -stiffness*(position[axis]-target[axis]) - damping*velocity[axis]
            velocity[axis] += force*step
            position[axis] += velocity[axis]*step
    settled = not held and all(abs(position[a]-target[a]) < 0.4 and abs(velocity[a]) < 6 for a in (0, 1))
    return position, velocity, settled
