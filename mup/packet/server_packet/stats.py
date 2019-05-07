from struct import pack
from mup.model.player import Player
from mup.packet.base import Base


class Stats(Base):
    def __init__(self, p: Player):
        data = bytearray([0xC3, 0, 0xF3, 0x03])

        data += bytearray(pack('4B2I9HI2B', *[
            p.x, p.y, p.map_id, 0,  # direction
            p.exp, p.next_exp,
            p.free_points, p.strength, p.agility, p.vitality, p.energy,
            p.life, p.max_life, p.mana, p.max_mana,
            p.zen,
            p.pk, p.role_code,
        ]))

        super().__init__(data)
        self.length = len(self)
