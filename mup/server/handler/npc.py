import logging
from mup.packet.client import (CTalk, CCloseWindow, CBuy, CSell, CRepair, CWarehouseMoney, CWarehouseClose, CMix,
                               CChaosClose)
from mup.server import chaos, npc, shop, warehouse
from mup.server.session import Session

logger = logging.getLogger(__name__)


def talk_handler(msg: CTalk, proto: Session):
    if proto.player is None:
        return
    npc.talk(proto.server, proto, msg.cid)


def close_window_handler(msg: CCloseWindow, proto: Session):
    if proto.player is None:
        return
    npc.close(proto.server, proto)


def buy_handler(msg: CBuy, proto: Session):
    if proto.player is None:
        return
    shop.buy(proto.server, proto, msg.slot)


def sell_handler(msg: CSell, proto: Session):
    if proto.player is None:
        return
    shop.sell(proto.server, proto, msg.slot)


def repair_handler(msg: CRepair, proto: Session):
    if proto.player is None:
        return
    shop.repair(proto.server, proto, msg.slot, msg.own)


def warehouse_money_handler(msg: CWarehouseMoney, proto: Session):
    if proto.player is None:
        return
    warehouse.money(proto.server, proto, msg.type, msg.amount)


def warehouse_close_handler(msg: CWarehouseClose, proto: Session):
    if proto.player is None or not warehouse.is_open(proto):
        return
    npc.close(proto.server, proto)


def mix_handler(msg: CMix, proto: Session):
    if proto.player is None:
        return
    chaos.mix(proto.server, proto)


def chaos_close_handler(msg: CChaosClose, proto: Session):
    if proto.player is None:
        return
    npc.close_chaos(proto.server, proto)
