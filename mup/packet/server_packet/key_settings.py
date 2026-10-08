from mup.packet.base import Packet, C1, Raw

HOTKEYS = 10


class KeySettings(Packet):
    """C1 F3 30: the hotkeys back on join, the client's layout. The client looks each skill number up in its skill
    list, FF: none."""
    code = C1, 0xF3, 0x30
    size = 18
    fields = (
        (4, 'data', Raw(14)),
    )

    @classmethod
    def of(cls, data):
        """data: [4..17] as the client sent it, its 0 hotkeys (none) become FF."""
        return cls(data=bytes(b or 0xFF for b in data[:HOTKEYS]) + bytes(data[HOTKEYS:]))
