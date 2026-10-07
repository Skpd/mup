from mup.packet.base import Packet, C3, u8


class MagicAOE(Packet):
    """C3 1E: area skill."""
    code = C3, 0x1E
    size = 7
    fields = (
        (3, 'skill_index', u8),  # position in the skill list sent on join, not the skill number
        (4, 'x', u8),
        (5, 'y', u8),
        (6, 'direction', u8),
    )
