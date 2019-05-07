from mup.model.player import Player
from mup.packet.client_packet.char_create import CharCreate
from mup.packet.server import SCharCreated
from mup.server.protocol import BaseProtocol


def create_character_handler(msg: CharCreate, proto: BaseProtocol):
    print('char create request')

    p = Player()
    p.name = msg.name
    p.index
    proto.write(SCharCreated(success=True, char=None, name=msg.name))
