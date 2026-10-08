from mup.model.player import Player
from mup.packet.base import Packet, C1, u8, u16, u32


class Respawn(Packet):
    """C1 F3 04: the player comes back to life at x, y of a map."""
    code = C1, 0xF3, 0x04
    size = 20
    fields = (
        (4, 'x', u8),
        (5, 'y', u8),
        (6, 'map', u8),
        (7, 'direction', u8),
        (8, 'life', u16),
        (10, 'mana', u16),
        (12, 'exp', u32),
        (16, 'money', u32),
    )

    @classmethod
    def of(cls, p: Player):
        return cls(x=p.x, y=p.y, map=p.map_id, direction=p.direction, life=p.life, mana=p.mana, exp=p.exp,
                   money=p.zen)
