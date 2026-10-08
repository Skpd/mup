from mup.packet.base import Packet, Entry, C2, cid, str10, u8, u16


class MeetMonster(Packet):
    """C2 13: monsters in view."""
    code = C2, 0x13
    entry = Entry(count=(4, u8), size=12, fields=(
        (0, 'cid', cid),
        (2, 'type', u8),
        (4, 'effects', u16),  # bits 0..3 like players in view, bit 8 another effect
        (6, 'x', u8),
        (7, 'y', u8),
        (8, 'target_x', u8),  # the client walks the monster there
        (9, 'target_y', u8),
        (10, 'direction', u8, 0),  # direction << 4
    ))

    @classmethod
    def of(cls, monsters):
        return cls(entries=[{
            'cid': m.cid, 'type': m.type_id, 'effects': m.state, 'x': m.x, 'y': m.y,
            'target_x': m.walk_target[0], 'target_y': m.walk_target[1], 'direction': m.direction << 4,
        } for m in monsters])


class MeetSummon(Packet):
    """C2 1F: summoned monsters in view, 13's entry with the owner's name, the client names it after the owner."""
    code = C2, 0x1F
    entry = Entry(count=(4, u8), size=22, fields=(
        (0, 'cid', cid),
        (2, 'type', u8),
        (4, 'effects', u16),
        (6, 'x', u8),
        (7, 'y', u8),
        (8, 'target_x', u8),
        (9, 'target_y', u8),
        (10, 'direction', u8, 0),  # direction << 4, the low nibble goes where players keep the pk level
        (11, 'owner', str10),
    ))

    @classmethod
    def of(cls, monsters):
        return cls(entries=[{
            'cid': m.cid, 'type': m.type_id, 'effects': m.state, 'x': m.x, 'y': m.y,
            'target_x': m.walk_target[0], 'target_y': m.walk_target[1], 'direction': m.direction << 4,
            'owner': m.owner.player.name if m.owner.player is not None else '',
        } for m in monsters])
