from mup.packet.base import Packet, Entry, C1, cid, u8


class Clear(Packet):
    """C1 14: objects out of view."""
    code = C1, 0x14
    entry = Entry(count=(3, u8), size=2, fields=(
        (0, 'cid', cid),
    ))

    @classmethod
    def of(cls, cids):
        return cls(entries=[{'cid': c} for c in cids])
