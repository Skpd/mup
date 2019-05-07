from mup.common.helpers import short2b
from mup.packet.base import Base


class Exp(Base):
    def __init__(self, exp, target_cid=0, dmg=0):
        data = [0xC3, 0x09, 0x16, *short2b(target_cid), *short2b(exp), *short2b(dmg)]
        super().__init__(data)
