from mup.packet.base import Packet, C3, cid, u8


class MagicAOE(Packet):
    """C3 1E: area skill animation, must be encrypted."""
    code = C3, 0x1E
    size = 8
    fields = (
        (3, 'skill', u8),  # skill number, not the list index
        (4, 'caster', cid),
        (6, 'x', u8),
        (7, 'y', u8),
    )
