from mup.packet.base import Packet, C3, cid, u16be


class Exp(Packet):
    """C3 16: exp for a kill, must be encrypted. The damage of the last hit is shown like a damage number."""
    code = C3, 0x16
    size = 9
    fields = (
        (3, 'cid', cid),  # killed object
        (5, 'exp', u16be),
        (7, 'damage', u16be),
    )

    @classmethod
    def of(cls, target, exp, damage):
        return cls(cid=target, exp=min(exp, 0xFFFF), damage=max(0, min(damage, 0xFFFF)))
