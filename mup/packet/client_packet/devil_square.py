from mup.packet.base import Packet, C1, u8


class DevilSquareEnter(Packet):
    """C1 90: enter square [3] (0..3) of Charon's window with the invitation in grid tile [4] - 24."""
    code = C1, 0x90
    size = 5
    fields = (
        (3, 'square', u8),
        (4, 'slot', u8),
    )
