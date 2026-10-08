"""Paths over tiles in the 8 directions of the walk packet."""
import heapq
from mup.packet.client_packet.move import STEPS


def direction(dx, dy):
    """Walk direction (index into STEPS) for a step towards dx, dy, None for no step."""
    step = (dx > 0) - (dx < 0), (dy > 0) - (dy < 0)
    return STEPS.index(step) if step != (0, 0) else None


def find_path(can_step, start, goal, reach=0, max_steps=16, budget=800):
    """
    Tiles from start (not included) to the first tile at most reach tiles from goal, [] if start already is, None if
    no such path of at most max_steps steps is found within budget tiles looked at. can_step(x, y) tells whether a
    tile can be entered.
    """
    gx, gy = goal

    def left(x, y):
        return max(0, max(abs(x - gx), abs(y - gy)) - reach)

    if left(*start) == 0:
        return []
    came = {start: None}
    cost = {start: 0}
    heap = [(left(*start), 0, start)]
    while heap and budget > 0:
        budget -= 1
        _, steps, tile = heapq.heappop(heap)
        if steps > cost[tile]:
            continue
        if left(*tile) == 0:
            path = []
            while tile != start:
                path.append(tile)
                tile = came[tile]
            return path[::-1]
        if steps >= max_steps:
            continue
        x, y = tile
        for dx, dy in STEPS:
            n = x + dx, y + dy
            if cost.get(n, max_steps + 1) <= steps + 1 or not can_step(*n):
                continue
            cost[n] = steps + 1
            came[n] = tile
            heapq.heappush(heap, (steps + 1 + left(*n), steps + 1, n))
    return None
