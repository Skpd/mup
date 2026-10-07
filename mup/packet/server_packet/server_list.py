from mup.packet.base import Packet, Entry, C2, u8, u16


class ServerList(Packet):
    """C2 F4 02: 4 bytes per server, the code is group * 20 + index (group 12 has a special name)."""
    code = C2, 0xF4, 0x02
    entry = Entry(count=(5, u8), size=4, fields=(
        (0, 'code', u16),
        (2, 'load', u8),  # percent
    ))

    @classmethod
    def of(cls, servers):
        return cls(entries=[{'code': s['group'] * 20 + s['code'], 'load': s['load']} for s in servers])
