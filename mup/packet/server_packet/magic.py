from mup.packet.base import Base


class Magic(Base):
    def __init__(self, magic_id, success, target_cid, owner_cid=0):
        target_cid &= 0x7FFF

        if success:
            target_cid |= 0x8000

        data = [0xC3, 8, 0x19, magic_id, owner_cid >> 8, owner_cid & 0xFF, target_cid >> 8, target_cid & 0xFF]
        super().__init__(data)
