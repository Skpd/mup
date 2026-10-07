import logging
from time import time

from mup.packet.client import CPing
from mup.server.protocol import BaseProtocol

logger = logging.getLogger(__name__)


def ping_handler(msg: CPing, proto: BaseProtocol):
    next_server_tick = time() * 1000
    next_client_tick = msg.tick

    ping = None
    if proto.server_tick is not None and proto.client_tick is not None:
        server_diff = next_server_tick - proto.server_tick
        client_diff = next_client_tick - proto.client_tick
        ping = client_diff - server_diff

    logger.debug('Ping from %s: tick %s, attack speed %s, magic speed %s, tick drift %s',
                 proto.cid, msg.tick, msg.attack_speed, msg.magic_speed, ping)

    proto.server_tick = next_server_tick
    proto.client_tick = next_client_tick
