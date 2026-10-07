import logging
from mup.error import NotFoundError
from mup.packet.client_packet.char_delete import CharDelete
from mup.packet.server import SCharDeleted
from mup.server.protocol import BaseProtocol

logger = logging.getLogger(__name__)


def delete_character_handler(msg: CharDelete, proto: BaseProtocol):
    # todo verify personal code (msg.personal_code)

    if proto.acc is None:
        return

    players = proto.server.player_mapper
    try:
        p = players.load(msg.name)
    except NotFoundError:
        p = None

    ok = p is not None and p.account.id == proto.acc.id
    if ok:
        players.delete(p)
    logger.info('%s deletes %s: %s', proto.acc.name, msg.name, 'ok' if ok else 'refused')

    proto.write(SCharDeleted(result=1 if ok else 0))
