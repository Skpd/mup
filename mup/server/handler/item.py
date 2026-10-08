import logging
from mup.packet.client import CPickUp, CDropItem, CMoveItem, CUseItem
from mup.packet.server import SDropResult, SMoveItemResult
from mup.server import ground, inventory
from mup.server.protocol import BaseProtocol

logger = logging.getLogger(__name__)


def pick_up_handler(msg: CPickUp, proto: BaseProtocol):
    if proto.player is None:
        return
    ground.pick_up(proto.server, proto, msg.id & 0x7FFF)


def drop_item_handler(msg: CDropItem, proto: BaseProtocol):
    if proto.player is None:
        return
    if ground.drop(proto.server, proto, msg.slot, msg.x, msg.y):
        proto.write(SDropResult(result=1, slot=msg.slot))
    else:
        proto.write(SDropResult(result=0, slot=msg.slot))


def move_item_handler(msg: CMoveItem, proto: BaseProtocol):
    p = proto.player
    if p is None:
        return
    item = p.inventory.get(msg.source)
    # todo trade, warehouse, chaos machine windows (roadmap M5, M6)
    ok = (msg.source_window == msg.target_window == SMoveItemResult.INVENTORY and item is not None
          and item.encode()[0] == msg.item[0] and item.encode()[3] >> 7 == msg.item[3] >> 7
          and inventory.move(proto.server, proto, msg.source, msg.target))
    if ok:
        proto.write(SMoveItemResult(window=SMoveItemResult.INVENTORY, slot=msg.target, item=item.encode()))
    else:
        logger.debug('%s: move from %s %s to %s %s refused', p.name, msg.source_window, msg.source,
                     msg.target_window, msg.target)
        proto.write(SMoveItemResult.failed())


def use_item_handler(msg: CUseItem, proto: BaseProtocol):
    if proto.player is None:
        return
    inventory.use(proto.server, proto, msg.slot)
