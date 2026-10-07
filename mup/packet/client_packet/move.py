from mup.packet.base import Base

# x, y offset of a single step for each of the 8 path directions
STEPS = [(-1, -1), (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0)]


class Move(Base):
    x = None
    y = None
    path = None
    direction = None
    target_x = None
    target_y = None

    @property
    def key(self):
        return self[2], None

    def __init__(self, src):
        super().__init__(src)

        # x, y is where the walk starts, the target is x, y with all path steps applied
        self.x = self[3]
        self.y = self[4]
        self.path = self[5:]

        # path[0] is direction << 4 | step count, then one step per nibble, high nibble first
        self.direction = self.path[0] >> 4 if self.path else 0
        steps = self.path[0] & 0x0F if self.path else 0
        steps = min(steps, (len(self.path) - 1) * 2)

        x, y = self.x, self.y
        for n in range(steps):
            b = self.path[1 + n // 2]
            dx, dy = STEPS[(b >> 4 if n % 2 == 0 else b) & 0x07]
            x += dx
            y += dy

        self.target_x = max(0, min(x, 255))
        self.target_y = max(0, min(y, 255))
