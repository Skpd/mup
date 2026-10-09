from mup.packet.base import Packet, C1, cid, u8


class PkLevel(Packet):
    """C1 F3 08: the pk level [6] of the player [4..5]: its name colour, the chat log names levels 2..6 (hero,
    commoner, the three murderers)."""
    code = C1, 0xF3, 0x08
    size = 7
    fields = (
        (4, 'cid', cid),
        (6, 'level', u8),
    )
