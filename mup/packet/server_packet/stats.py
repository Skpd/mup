from struct import pack
from mup.model.player import Player
from mup.packet.base import Base


class Stats(Base):
    def __init__(self, p: Player):
        data = bytearray([0xC3, 0, 0xF3, 0x03])

        # layout from OpenMU CharacterInformation097
        data += bytearray(pack('<4B2I11H2xI2B3H', *[
            p.x, p.y, p.map_id, p.direction,
            p.exp, p.next_exp,
            p.free_points, p.strength, p.agility, p.vitality, p.energy,
            p.life, p.max_life, p.mana, p.max_mana,
            0, 0,  # ag, max ag
            p.zen,
            p.pk, p.role_code,
            0, 0,  # fruit points, max fruit points
            0,  # leadership
        ]))

        super().__init__(data)
        self.length = len(self)
