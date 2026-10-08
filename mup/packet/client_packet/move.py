from mup.packet.base import Packet, C1, Tail, u8

# x, y offset of a single step for each of the 8 path directions
STEPS = [(-1, -1), (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0)]


class Move(Packet):
    """C1 10: walk. Sent with 0 steps to only turn."""
    code = C1, 0x10
    fields = (
        (3, 'x', u8),  # x, y is where the walk starts, the target is x, y with all path steps applied
        (4, 'y', u8),
        (5, 'path', Tail()),  # direction << 4 | step count, then one step per nibble, high nibble first
    )

    def __init__(self, data=None, /, **values):
        super().__init__(data, **values)

        self.direction = self.path[0] >> 4 if self.path else 0
        steps = self.path[0] & 0x0F if self.path else 0
        steps = min(steps, (len(self.path) - 1) * 2)

        self.steps = []  # x, y offsets, one per step
        x, y = self.x, self.y
        for n in range(steps):
            b = self.path[1 + n // 2]
            dx, dy = STEPS[(b >> 4 if n % 2 == 0 else b) & 0x07]
            self.steps.append((dx, dy))
            x += dx
            y += dy

        self.target_x = max(0, min(x, 255))
        self.target_y = max(0, min(y, 255))
