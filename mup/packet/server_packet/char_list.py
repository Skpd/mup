from mup.packet.base import Packet, Entry, C1, Raw, str10, u8, u16
from mup.packet.server_packet.appearance import equipment


class CharList(Packet):
    """C1 F3 00: characters of the account."""
    code = C1, 0xF3, 0x00
    entry = Entry(count=(4, u8), size=26, fields=(
        (0, 'slot', u8),
        (1, 'name', str10),
        (12, 'level', u16),
        (14, 'ctl', u8),  # & 0x10 marks the character
        (15, 'class_type', u8),
        (16, 'equipment', Raw(10)),
    ))

    @classmethod
    def of(cls, players):
        return cls(entries=[{
            'slot': p.index, 'name': p.name, 'level': p.level, 'ctl': p.role_code,
            'class_type': p.class_type.value, 'equipment': equipment(p),
        } for p in players])
