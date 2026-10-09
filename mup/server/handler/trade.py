import logging
from mup.packet.client import CTradeRequest, CTradeAnswer, CTradeZen, CTradeOk, CTradeCancel
from mup.server import trade
from mup.server.session import Session

logger = logging.getLogger(__name__)


def trade_request_handler(msg: CTradeRequest, proto: Session):
    if proto.player is None:
        return
    trade.request(proto.server, proto, msg.cid)


def trade_answer_handler(msg: CTradeAnswer, proto: Session):
    if proto.player is None:
        return
    trade.answer(proto.server, proto, msg.answer == 1)


def trade_zen_handler(msg: CTradeZen, proto: Session):
    if proto.player is None:
        return
    trade.zen(proto.server, proto, msg.amount)


def trade_ok_handler(msg: CTradeOk, proto: Session):
    if proto.player is None:
        return
    trade.ok(proto.server, proto, msg.ok)


def trade_cancel_handler(msg: CTradeCancel, proto: Session):
    if proto.player is None:
        return
    trade.cancel(proto.server, proto)
