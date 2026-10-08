from mup.packet.base import Packet, C1, u8, u16be


class Life(Packet):
    """C1 26: the player's life, or its maximum, or unlocks item use."""
    code = C1, 0x26
    size = 6
    fields = (
        (3, 'type', u8, 0xFF),
        (4, 'value', u16be),
    )

    CURRENT = 0xFF
    MAX = 0xFE
    UNLOCK = 0xFD  # unlocks item use after a 26 request, value not read


class Mana(Packet):
    """C1 27: the player's mana, or its maximum."""
    code = C1, 0x27
    size = 6
    fields = (
        (3, 'type', u8, 0xFF),
        (4, 'value', u16be),
    )

    CURRENT = 0xFF
    MAX = 0xFE
