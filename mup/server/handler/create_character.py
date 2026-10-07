from mup.error import NotFoundError
from mup.model.player import Player, CharacterClass, DEFAULT_SKILLS
from mup.packet.client_packet.char_create import CharCreate
from mup.packet.server import SCharCreated
from mup.server.protocol import BaseProtocol

MAX_CHARACTERS = 5


def create_character_handler(msg: CharCreate, proto: BaseProtocol):
    print('char create request {} class {}'.format(msg.name, msg.class_type))

    if proto.acc is None:
        return

    players = proto.server.player_mapper
    taken = {p.index for p in players.get_by_account(proto.acc)}
    free = [i for i in range(MAX_CHARACTERS) if i not in taken]

    try:
        class_type = CharacterClass(msg.class_type)
        players.load(msg.name)
        name_taken = True
    except ValueError:
        class_type = None
        name_taken = False
    except NotFoundError:
        name_taken = False

    if not msg.name or class_type is None or name_taken or not free:
        proto.write(SCharCreated())
        return

    p = Player(
        name=msg.name,
        index=free[0],
        class_type=class_type,
        skills=list(DEFAULT_SKILLS.get(class_type, [])),
        account=proto.acc,
    )
    players.store(p)
    proto.write(SCharCreated(p))
