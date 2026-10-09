import logging
from mup.packet.client import CPickUp, CDropItem, CMoveItem, CUseItem
from mup.packet.server import SDropResult, SMoveItemResult, SPickUpResult
from mup.server import ground, inventory, jewel, trade
from mup.server.session import Session

logger = logging.getLogger(__name__)


def pick_up_handler(msg: CPickUp, proto: Session):
    if proto.player is None:
        return
    if trade.is_open(proto):
        proto.write(SPickUpResult.failed())  # the money the client shows leaves out the trade's zen
        return
    ground.pick_up(proto.server, proto, msg.id & 0x7FFF)


def drop_item_handler(msg: CDropItem, proto: Session):
    if proto.player is None:
        return
    if ground.drop(proto.server, proto, msg.slot, msg.x, msg.y):
        proto.write(SDropResult(result=1, slot=msg.slot))
    else:
        proto.write(SDropResult(result=0, slot=msg.slot))


def move_item_handler(msg: CMoveItem, proto: Session):
    p = proto.player
    if p is None:
        return
    source = inventory.windows(proto).get(msg.source_window)
    item = source[0].get(msg.source) if source is not None else None
    ok = (item is not None and item.encode()[0] == msg.item[0] and item.encode()[3] >> 7 == msg.item[3] >> 7
          and inventory.move(proto.server, proto, msg.source, msg.target, msg.source_window, msg.target_window))
    if ok:
        proto.write(SMoveItemResult(window=msg.target_window, slot=msg.target, item=item.encode()))
        if trade.TRADE in (msg.source_window, msg.target_window):
            trade.moved(proto.server, proto, msg.source_window, msg.source, msg.target_window, msg.target, item)
    else:
        logger.debug('%s: move from %s %s to %s %s refused', p.name, msg.source_window, msg.source,
                     msg.target_window, msg.target)
        proto.write(SMoveItemResult.failed())


def use_item_handler(msg: CUseItem, proto: Session):
    if proto.player is None:
        return
    if jewel.is_jewel(proto.player.inventory.get(msg.slot)):
        jewel.apply(proto.server, proto, msg.slot, msg.target)
    else:
        inventory.use(proto.server, proto, msg.slot)
