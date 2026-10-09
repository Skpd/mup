from mup.packet.base import Packet, C1, Raw, Str, str10, u8, u16be


class GuildRequest(Packet):
    """C1 50: /guild at the guild master [3..4] (the player under the cursor or the one next to the hero)."""
    code = C1, 0x50
    size = 5
    fields = (
        (3, 'cid', u16be),
    )


class GuildAnswer(Packet):
    """C1 51: the master's answer [3] 1 yes, 0 no to the join request of [4..5]."""
    code = C1, 0x51
    size = 6
    fields = (
        (3, 'answer', u8),
        (4, 'cid', u16be),
    )


class GuildListRequest(Packet):
    """C1 52: the guild window opened (G): the members."""
    code = C1, 0x52
    size = 3


class GuildLeave(Packet):
    """C1 53: the member [3..12] leaves (its own name) or is put out by the master, [13..22] the personal code."""
    code = C1, 0x53
    size = 23
    fields = (
        (3, 'name', str10),
        (13, 'personal_code', str10),
    )


class GuildMasterAnswer(Packet):
    """C1 54: [3] 1 yes, 0 no in the guild master's window."""
    code = C1, 0x54
    size = 4
    fields = (
        (3, 'answer', u8),
    )


class GuildCreate(Packet):
    """C1 55: create the guild [3..10] with the mark [11..42], 64 colours of 4 bits, high nibble first."""
    code = C1, 0x55
    size = 43
    fields = (
        (3, 'name', Str(8)),
        (11, 'mark', Raw(32)),
    )


class GuildCancel(Packet):
    """C1 57: the guild master's window was closed at the mark."""
    code = C1, 0x57
    size = 3
