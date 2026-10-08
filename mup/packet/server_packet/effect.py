from mup.packet.base import Packet, C1, cid, u8


class EffectEnded(Packet):
    """C1 1B: the effect of a skill on an object ended, its bit in the object is cleared."""
    code = C1, 0x1B
    size = 6
    fields = (
        (3, 'skill', u8),
        (4, 'cid', cid),
    )
