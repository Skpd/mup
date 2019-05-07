from mup.mapper.player import NotFoundError
from mup.packet.client import CCharList
from mup.packet.server import SAccountID, SCharList
from mup.server.protocol import BaseProtocol


def char_list_handler(msg: CCharList, proto: BaseProtocol):
    print('got char list request, gotta send account id and list of characters')

    chars = proto.server.player_mapper.get_by_account(proto.acc)
    proto.write(SCharList(chars))
