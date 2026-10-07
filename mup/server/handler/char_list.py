from mup.mapper.player import NotFoundError
from mup.packet.client import CCharList
from mup.packet.server import SAccountID, SCharList, SLoginResult
from mup.server.protocol import BaseProtocol


class_min = 0

def char_list_handler(msg: CCharList, proto: BaseProtocol):
    global class_min
    print('got char list request, gotta send account id and list of characters')

    # todo remove hardcode
    from mup.model.player import Player
    # chars = [
    #     Player(level=32150, class_type=0b00000001),
    #     Player(level=32150, class_type=0b00000011),
    #     Player(level=32150, class_type=0b00000111),
    #     Player(level=32150, class_type=0b00000110),
    #     Player(level=32150, class_type=0b00000100),
    # ]
    from mup.model.player import CharacterClass
    chars = [
        Player(level=32150, class_type=CharacterClass.MAGIC_GLADIATOR, map_id=2),
    ]
    # chars = proto.server.player_mapper.get_by_account(proto.acc)
    proto.write(SCharList(chars))

    # from time import sleep
    # sleep(10)
    # proto.write(bytearray([0xC3, 5, 0xF1, 0x02, 0x01]))
    # sleep(1)
    # player1.name = 'test2'
    # proto.write(SCharList(chars))

# normal
# hero
