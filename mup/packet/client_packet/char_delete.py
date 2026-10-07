from mup.packet.base import Packet, C1, str10


class CharDelete(Packet):
    """C1 F3 02"""
    code = C1, 0xF3, 0x02
    size = 24
    fields = (
        (4, 'name', str10),
        (14, 'personal_code', str10),
    )
