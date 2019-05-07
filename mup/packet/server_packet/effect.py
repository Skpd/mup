from mup.common.helpers import short2b
from mup.packet.base import Base


class Effect(Base):
    def __init__(self, cid, effect_type):
        super().__init__([0xC1, 0x06, 0x48, *short2b(cid), effect_type])
