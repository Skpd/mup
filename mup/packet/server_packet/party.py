from mup.packet.base import Packet, Entry, C1, cid, str10, u8, u32


class PartyRequest(Packet):
    """C1 40: the player [3..4] asks to party, the client answers 41 with the cid."""
    code = C1, 0x40
    size = 5
    fields = (
        (3, 'cid', cid),
    )


class PartyResult(Packet):
    """C1 41: [3] the message shown, closes the question."""
    code = C1, 0x41
    size = 4
    fields = (
        (3, 'result', u8),
    )

    FAILED, REFUSED, FULL, GONE, IN_PARTY, LEVEL_GAP = range(6)


class PartyList(Packet):
    """C1 42: the members, the leader first. 24 bytes each: name, index, map, x, y, life and max life (4 bytes)."""
    code = C1, 0x42
    fields = (
        (3, 'result', u8, 1),  # not read by the client
    )
    entry = Entry(count=(4, u8), size=24, fields=(
        (0, 'name', str10),
        (10, 'index', u8),
        (11, 'map', u8),
        (12, 'x', u8),
        (13, 'y', u8),
        (16, 'life', u32),
        (20, 'max_life', u32),
    ))

    @classmethod
    def of(cls, players):
        return cls(entries=[{'name': p.name, 'index': i, 'map': p.map_id, 'x': p.x, 'y': p.y, 'life': max(0, p.life),
                             'max_life': p.max_life} for i, p in enumerate(players)])


class PartyLeft(Packet):
    """C1 43: "You have just left the party.", the client's list is empty."""
    code = C1, 0x43
    size = 3


class PartyLife(Packet):
    """C1 44: one byte per member: index << 4 | life in tenths, the bars over their heads."""
    code = C1, 0x44
    entry = Entry(count=(3, u8), size=1, fields=(
        (0, 'value', u8),
    ))

    @classmethod
    def of(cls, players):
        return cls(entries=[{'value': i << 4 | tenths(p)} for i, p in enumerate(players)])


def tenths(p):
    """Life in tenths of the maximum, 0..10."""
    return max(0, p.life) * 10 // p.max_life if p.max_life > 0 else 0
