from mup.packet.base import Packet, C1, u16


class ServerInfo(Packet):
    """C1 F4 03: game server address request, not xored."""
    code = C1, 0xF4, 0x03
    size = 6
    fields = (
        (4, 'server_code', u16),  # group * 20 + index
    )
