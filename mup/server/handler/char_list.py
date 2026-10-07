from mup.packet.client import CCharList
from mup.packet.server import SCharList
from mup.server.protocol import BaseProtocol


def char_list_handler(msg: CCharList, proto: BaseProtocol):
    print('got char list request, gotta send list of characters')

    if proto.acc is None:
        return

    chars = proto.server.player_mapper.get_by_account(proto.acc)
    proto.write(SCharList(chars))
