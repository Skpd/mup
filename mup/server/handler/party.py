import logging
from mup.packet.client import CPartyRequest, CPartyAnswer, CPartyLeave
from mup.server import party
from mup.server.session import Session

logger = logging.getLogger(__name__)


def party_request_handler(msg: CPartyRequest, proto: Session):
    if proto.player is None:
        return
    party.request(proto.server, proto, msg.cid)


def party_answer_handler(msg: CPartyAnswer, proto: Session):
    if proto.player is None:
        return
    party.answer(proto.server, proto, msg.answer == 1, msg.cid)


def party_leave_handler(msg: CPartyLeave, proto: Session):
    if proto.player is None:
        return
    party.remove(proto.server, proto, msg.member)
