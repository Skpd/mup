from mup.common.helpers import str2b
from mup.model.player import Player
from mup.packet.base import Base
from mup.packet.server_packet.appearance import appearance


class MeetPlayer(Base):
    def __init__(self, cid, p: Player):
        data = bytearray([0xC2, 0, 0, 0x12])

        data += bytearray([1])  # number of players in packet
        data += bytearray([
            cid >> 8, cid & 0xFF,
            p.x, p.y,
            *appearance(p), 0, 0,
            0,  # effects: poisoned, iced, damage buff, defense buff
            *str2b(p.name),
            p.x, p.y,  # tx ty
            p.direction << 4 | p.pk  # direction << 4 | pk status
        ])

        super().__init__(data)
        self.length = len(self)
