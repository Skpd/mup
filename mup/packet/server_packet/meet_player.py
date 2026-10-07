from mup.packet.base import Packet, Entry, C2, Raw, cid, str10, u8
from mup.packet.server_packet.appearance import equipment


class MeetPlayer(Packet):
    """C2 12: players in view. Names containing "webzen" are skipped by the client."""
    code = C2, 0x12
    entry = Entry(count=(4, u8), size=32, fields=(
        (0, 'cid', cid),
        (2, 'x', u8),
        (3, 'y', u8),
        (4, 'class_pose', u8),  # class << 5 | 2nd class << 4 | pose, pose 2..4 sit or lean
        (5, 'equipment', Raw(10)),
        (16, 'effects', u8, 0),  # bits 0..3: poison, ice, damage buff, defense buff
        (17, 'effects2', u8, 0),  # bit 0: another effect
        (18, 'name', str10),
        (28, 'target_x', u8),
        (29, 'target_y', u8),
        (30, 'direction_pk', u8),  # direction << 4 | pk level
    ))

    @classmethod
    def of(cls, players):
        """players: (cid, Player) pairs"""
        return cls(entries=[{
            'cid': c, 'x': p.x, 'y': p.y, 'class_pose': p.class_type.value, 'equipment': equipment(p),
            'name': p.name, 'target_x': p.x, 'target_y': p.y, 'direction_pk': p.direction << 4 | p.pk,
        } for c, p in players])
