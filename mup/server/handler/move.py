import logging
from mup.packet.client import CMove
from mup.server.protocol import BaseProtocol
from mup.server.world import distance

logger = logging.getLogger(__name__)

# a walk starts where the client is, somewhere on its last walk of at most 15 steps
MAX_START_DISTANCE = 15


def move_handler(msg: CMove, proto: BaseProtocol):
    p = proto.player
    if p is None or p.dead:
        return

    logger.debug('%s walks from %s,%s, %s steps to %s,%s', p.name, msg.x, msg.y, len(msg.steps), msg.target_x, msg.target_y)
    terrain = proto.server.maps[p.map_id].terrain
    if distance(msg.x, msg.y, p.x, p.y) > MAX_START_DISTANCE or not terrain.walkable(msg.x, msg.y):
        logger.warning('%s at %s,%s can\'t walk from %s,%s', p.name, p.x, p.y, msg.x, msg.y)
        return

    x, y = msg.x, msg.y
    path = [(x, y)]
    for dx, dy in msg.steps:
        if not terrain.walkable(x + dx, y + dy):
            logger.warning('%s walks into %s,%s (attribute %s), stopped at %s,%s', p.name, x + dx, y + dy,
                           terrain.attribute(x + dx, y + dy) if 0 <= x + dx < 256 and 0 <= y + dy < 256 else None, x, y)
            break
        x, y = x + dx, y + dy
        path.append((x, y))

    p.walk_path = path
    proto.server.walk(proto, x, y, msg.direction)
