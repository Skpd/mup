from struct import pack
from mup.model.player import Player
from mup.packet.base import Base


class Stats(Base):
    def __init__(self, p: Player):
        data = bytearray([0xC3, 0, 0xF3, 0x04])

        data += bytearray(pack('4BQQ5H4H4HI2B2HH2H', *[
            p.x, p.y, p.map_id, 0,  # direction
            p.exp, p.next_exp,
            p.free_points, p.strength, p.agility, p.vitality, p.energy,
            p.life, p.max_life, p.mana, p.max_mana,
            0, 0, 0, 0,  # shield, max shield, ag, max ag
            p.zen,
            p.pk, p.role_code,
            0, 0,  # add point, max add point
            0,  # command
            0, 0,  # minus point, max minus point
        ]))

        data += bytearray([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
        data += bytearray([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
        data += bytearray([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
        data += bytearray([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])

        super().__init__(data)
        self.length = len(self)
