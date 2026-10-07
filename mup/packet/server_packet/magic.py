from mup.packet.base import Packet, C3, cid, u8, u16be


class Magic(Packet):
    """C3 19: skill animation on a target, must be encrypted."""
    code = C3, 0x19
    size = 8
    fields = (
        (3, 'skill', u8),  # skill number, not the list index
        (4, 'caster', cid),
        (6, 'target', u16be),  # cid, bit 15: the effect applied
    )

    @classmethod
    def of(cls, skill, caster, target, hit):
        return cls(skill=skill, caster=caster, target=target & 0x7FFF | (0x8000 if hit else 0))
