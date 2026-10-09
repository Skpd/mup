import logging
from mup.error import NotFoundError
from mup.packet.client import CJoinGame
from mup.server.session import Session

logger = logging.getLogger(__name__)


def game_start_handler(msg: CJoinGame, proto: Session):
    if proto.acc is None or proto.playing:
        return

    try:
        player = proto.server.characters.load(msg.name)
    except NotFoundError:
        player = None

    if player is None or player.account_id != proto.acc.id:
        logger.warning('%s is not a character of this account', msg.name)
        return

    logger.info('%s enters the game as %s', proto.acc.name, player.name)
    proto.server.enter_world(proto, player)
