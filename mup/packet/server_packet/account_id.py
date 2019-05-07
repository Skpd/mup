from mup.packet.base import Base


class AccountID(Base):
    def __init__(self, account_id, connection_id: int):
        assert len(str(account_id)) <= 10, 'invalid account id, must be < 10 chars'

        data = [0xC1, 0, 0x01, *bytearray(bytes(str(account_id), 'ascii')).ljust(10, b'\0'), connection_id >> 8, connection_id & 0xFF]
        # data = [0xC1, 0, 0x01]

        super().__init__(data)
        self.length = len(self)
