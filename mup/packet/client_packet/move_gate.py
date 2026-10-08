from mup.packet.base import Packet, C3, u8


class MoveGate(Packet):
    """C3 1C: the player stepped on a gate entrance."""
    code = C3, 0x1C
    size = 6
    fields = (
        (3, 'gate', u8),
        (4, 'x', u8),  # 0 from gates
        (5, 'y', u8),
    )
