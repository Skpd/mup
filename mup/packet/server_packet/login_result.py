from mup.packet.base import Base


class LoginResult(Base):
    BAD_PASSWORD = 0x00
    SUCCESS = 0x01
    IN_USE = 0x03
    SERVER_IS_FULL = 0x04
    ACCOUNT_BANNED = 0x05
    NEW_VERSION_REQUIRED = 0x06
    CONNECTION_ERROR = 0x07
    CLOSED_BY_ATTEMPTS = 0x08
    BO_CHARGE_INFO = 0x09
    SUBSCRIPTION_IS_OVER = 0x0A
    SUBSCRIPTION_IS_OVER2 = 0x0B
    SUBSCRIPTION_IS_OVER_IP = 0x0C
    INVALID_ACCOUNT = 0x0D
    CONNECTION_ERROR2 = 0x0E

    def __init__(self, result):
        data = [0xC1, 0, 0xF1, 0x01, result]

        super().__init__(data)
        self.length = len(self)
