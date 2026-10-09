import logging
from mup.packet.client_packet.char_create import CharCreate
from mup.packet.server import SCharCreated
from mup.server.character import MAX_CHARACTERS, valid_name, creatable_class, new_character, start_gate
from mup.server.session import Session

logger = logging.getLogger(__name__)


def create_character_handler(msg: CharCreate, proto: Session):
    if proto.acc is None or proto.playing:
        return

    characters = proto.server.characters
    taken = {p.index for p in characters.by_account(proto.acc.id)}
    free = [i for i in range(MAX_CHARACTERS) if i not in taken]
    class_type = creatable_class(msg.class_type)

    if not valid_name(msg.name) or characters.exists(msg.name):
        result = SCharCreated.BAD_NAME
    elif not free or class_type is None:
        result = SCharCreated.NO_SLOT
    else:
        result = SCharCreated.OK

    if result != SCharCreated.OK:
        logger.info('%s can\'t create %s, class %s: result %s', proto.acc.name, msg.name, msg.class_type, result)
        proto.write(SCharCreated(result=result))
        return

    map_id, x, y = proto.server.gate_spot(start_gate(class_type))
    p = new_character(proto.acc.id, free[0], msg.name, class_type, map_id, x, y)
    characters.create(p)
    logger.info('%s created %s, class %s in slot %s', proto.acc.name, p.name, class_type.name, p.index)
    proto.write(SCharCreated(result=result, name=p.name, slot=p.index))
