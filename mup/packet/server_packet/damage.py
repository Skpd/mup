from mup.packet.base import Base


class Damage(Base):
    def __init__(self, cid, dmg, dmg_type=0):
        if dmg > 0x3fff or dmg < 0:
            print('   - WARN dmg {} > 16383, lowered to 16383'.format(dmg))
            dmg &= 0x3fff

        super().__init__([
            0xC1, 0, 0x15,
            cid >> 8, cid & 0xFF,

            # next two lines is one byte
            ((dmg_type & 3) << 6)   # dmg type. two left bytes. 01/11 - exc, 10 - blue
            | (dmg >> 8),   # dmg high byte

            dmg & 0xFF,  # dmg low byte

        ])

        self.length = len(self)
