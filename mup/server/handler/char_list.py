from mup.packet.client import CCharList
from mup.packet.server import SCharList
from mup.server.protocol import BaseProtocol


def char_list_handler(msg: CCharList, proto: BaseProtocol):
    if proto.acc is None:
        return

    chars = proto.server.characters.by_account(proto.acc.id)
    proto.write(SCharList.of(chars))
