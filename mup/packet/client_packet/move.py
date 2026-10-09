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

    MAX_STEPS = 15  # the count's nibble

    @classmethod
    def of(cls, x, y, steps, direction=None):
        """A walk from x, y, steps: directions (indexes into STEPS). direction: where the walker faces at the end, the
        last step's when not given."""
        if len(steps) > cls.MAX_STEPS:
            raise ValueError('{} steps, a walk has at most {}'.format(len(steps), cls.MAX_STEPS))
        if direction is None:
            direction = steps[-1] if steps else 0
        nibbles = list(steps) + [0] * (len(steps) % 2)
        path = bytes([direction << 4 | len(steps)]) + bytes(
            nibbles[i] << 4 | nibbles[i + 1] for i in range(0, len(nibbles), 2))
        return cls(x=x, y=y, path=path)

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
