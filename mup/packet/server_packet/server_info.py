from mup.packet.base import Packet, C1, Str, u16


class ServerInfo(Packet):
    """C1 F4 03: game server address."""
    code = C1, 0xF4, 0x03
    size = 22
    fields = (
        (4, 'ip', Str(16)),  # 15 characters and a 0
        (20, 'port', u16),
    )
