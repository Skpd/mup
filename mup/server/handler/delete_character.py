import hmac
import logging
from mup.error import NotFoundError
from mup.packet.client_packet.char_delete import CharDelete
from mup.packet.server import SCharDeleted
from mup.server.protocol import BaseProtocol

logger = logging.getLogger(__name__)


def delete_character_handler(msg: CharDelete, proto: BaseProtocol):
    if proto.acc is None or proto.playing:
        return

    characters = proto.server.characters
    try:
        p = characters.load(msg.name)
    except NotFoundError:
        p = None

    if p is None or p.account_id != proto.acc.id:
        result = SCharDeleted.NOT_FOUND
    elif not hmac.compare_digest(msg.personal_code.encode('latin-1'), proto.acc.personal_code.encode('latin-1')):
        result = SCharDeleted.WRONG_CODE
    else:
        characters.delete(p)
        result = SCharDeleted.OK
    logger.info('%s deletes %s: result %s', proto.acc.name, msg.name, result)

    proto.write(SCharDeleted(result=result))
