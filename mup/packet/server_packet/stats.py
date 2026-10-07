from mup.model.player import Player
from mup.packet.base import Packet, C3, u8, u16, u32


class Stats(Packet):
    """C3 F3 03: character info on entering the game, must be encrypted."""
    code = C3, 0xF3, 0x03
    size = 42
    fields = (
        (4, 'x', u8),
        (5, 'y', u8),
        (6, 'map', u8),
        (7, 'direction', u8),
        (8, 'exp', u32),
        (12, 'next_exp', u32),
        (16, 'points', u16),
        (18, 'strength', u16),
        (20, 'agility', u16),
        (22, 'vitality', u16),
        (24, 'energy', u16),
        (26, 'life', u16),
        (28, 'max_life', u16),
        (30, 'mana', u16),
        (32, 'max_mana', u16),
        (36, 'money', u32),
        (40, 'pk_level', u8),
        (41, 'ctl', u8),
    )

    @classmethod
    def of(cls, p: Player):
        return cls(
            x=p.x, y=p.y, map=p.map_id, direction=p.direction,
            exp=p.exp, next_exp=p.next_exp,
            points=p.free_points, strength=p.strength, agility=p.agility, vitality=p.vitality, energy=p.energy,
            life=p.life, max_life=p.max_life, mana=p.mana, max_mana=p.max_mana,
            money=p.zen, pk_level=p.pk, ctl=p.role_code,
        )
