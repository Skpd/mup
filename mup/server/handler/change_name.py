from mup.mapper.player import NotFoundError
from mup.packet.client import CChangeName
from mup.packet.server import SAccountID, SCharList, SLoginResult
from mup.server.protocol import BaseProtocol

class_min = 0


def change_name_handler(msg: CChangeName, proto: BaseProtocol):
    proto.write(bytearray([
        0xC1, 15, 0xF3, 0x15,
        *bytearray('qwe'.encode('ascii')).ljust(10, b'\0'),
        0x00
    ]))
