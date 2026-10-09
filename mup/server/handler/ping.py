import logging
from time import time

from mup.packet.client import CPing
from mup.server.session import Session

logger = logging.getLogger(__name__)


def ping_handler(msg: CPing, proto: Session):
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

    # the client's speeds come from its own values (Character values in docs/protocol-097.md), a difference means
    # a formula or an effect the server doesn't know, or a modified client
    p = proto.player
    if p is not None:
        speeds = msg.attack_speed, msg.magic_speed
        if speeds != (p.values.attack_speed, p.values.magic_speed) and speeds != proto.reported_speeds:
            logger.info('%s reports attack / magic speed %s / %s, the server has %s / %s', p.name, *speeds,
                        p.values.attack_speed, p.values.magic_speed)
        proto.reported_speeds = speeds
