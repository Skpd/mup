from mup.packet.base import Packet, C1


class ServerList(Packet):
    """C1 F4 02: server list request, not xored."""
    code = C1, 0xF4, 0x02
    size = 4
