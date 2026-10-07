from mup.packet.base import Packet, C1, u8


class LoginResult(Packet):
    """C1 F1 01"""
    code = C1, 0xF1, 0x01
    size = 5
    fields = (
        (4, 'result', u8),
    )

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
